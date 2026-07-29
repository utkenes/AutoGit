"""AutoGit's Typer command line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from autogit.config import config_path, update_config, write_default_config
from autogit.container import build_container
from autogit.domain.exceptions import AutoGitError, PreStagedChangesError
from autogit.domain.models import CheckState

app = typer.Typer(help="Güvenli, debounce tabanlı otomatik Git commit aracı.", no_args_is_help=True)
config_app = typer.Typer(help="Yapılandırmayı gösterir veya değiştirir.", no_args_is_help=False)
app.add_typer(config_app, name="config")
console = Console()


def _container(path: Path) -> object:
    try:
        return build_container(path)
    except AutoGitError as error:
        console.print(f"[red]Hata:[/] {error}")
        raise typer.Exit(1) from error


def _print_pre_staged_error(error: PreStagedChangesError) -> None:
    console.print("[red]HATA[/] AutoGit dışında stage edilmiş dosyalar bulundu:\n")
    for path in error.files:
        console.print(f"  {path}")
    console.print("\nAutoGit mevcut staging area'yı değiştirmedi.")
    console.print("Çözüm: git restore --staged .\nArdından `autogit commit` komutunu tekrar çalıştırın.")


@app.command()
def init(path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Repository için varsayılan .autogit.toml ve çalışma alanı oluşturur."""
    container = _container(path)
    root = container.root  # type: ignore[attr-defined]
    existed = config_path(root).exists()
    target = write_default_config(root)
    (root / ".autogit" / "logs").mkdir(parents=True, exist_ok=True)
    ignore_path = root / ".gitignore"
    existing = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
    required = [".autogit/", ".env", ".env.*", "!.env.example"]
    missing = [line for line in required if line not in existing]
    if missing:
        with ignore_path.open("a", encoding="utf-8") as file:
            if existing and not existing.endswith("\n"):
                file.write("\n")
            file.write("\n# AutoGit güvenlik girdileri\n" + "\n".join(missing) + "\n")
    message = "zaten vardı" if existed else "oluşturuldu"
    console.print(f"[green]Başarılı:[/] {target} {message}.")


@app.command()
def commit(
    path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd(),
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Git durumunu değiştirmeden commit planını göster.")] = False,
) -> None:
    """Güvenli tek seferlik commit akışını çalıştırır veya --dry-run ile önizler."""
    container = _container(path)
    try:
        if dry_run:
            plan = container.commit.preview()  # type: ignore[attr-defined]
            console.print("[cyan]DRY RUN[/] Git durumu değiştirilmedi.")
            console.print("Stage edilecek dosyalar:")
            for file in plan.candidates:
                console.print(f"  {file.status.value}: {file.path}")
            if plan.excluded_files:
                console.print("Hariç tutulan dosyalar:")
                for file in plan.excluded_files:
                    console.print(f"  {file.status.value}: {file.path}")
            return
        result, push = container.commit.execute()  # type: ignore[attr-defined]
    except PreStagedChangesError as error:
        _print_pre_staged_error(error)
        raise typer.Exit(1) from error
    except AutoGitError as error:
        console.print(f"[yellow]{error}[/]")
        raise typer.Exit(1) from error
    console.print(f"[green]Commit oluşturuldu:[/] {result.commit_hash[:12]} {result.message}")
    console.print(push.detail)


@app.command()
def watch(path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Dosya değişikliklerini izler; debounce sonunda güvenli commit dener."""
    container = _container(path)
    console.print(f"[cyan]İzleniyor:[/] {container.root}")  # type: ignore[attr-defined]
    console.print("Durdurmak için Ctrl+C kullanın.")
    container.watch.run()  # type: ignore[attr-defined]


@app.command()
def status(path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Repository ve AutoGit durumunu gösterir."""
    container = _container(path)
    table = Table(title="AutoGit Durumu")
    table.add_column("Alan", style="cyan")
    table.add_column("Değer")
    for key, value in container.status.get().items():  # type: ignore[attr-defined]
        table.add_row(key, "\n".join(value) if isinstance(value, list) else str(value))
    console.print(table)


@config_app.callback(invoke_without_command=True)
def config(
    ctx: typer.Context,
    path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd(),
) -> None:
    """Mevcut yapılandırmayı gösterir."""
    if ctx.invoked_subcommand is None:
        container = _container(path)
        console.print_json(data=container.config.model_dump_json(indent=2))  # type: ignore[attr-defined]


@config_app.command("set")
def config_set(
    key: str,
    value: str,
    path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd(),
) -> None:
    """Desteklenen bir yapılandırma değerini tip güvenli biçimde değiştirir."""
    container = _container(path)
    try:
        update_config(container.root, key, value)  # type: ignore[attr-defined]
    except AutoGitError as error:
        console.print(f"[red]Hata:[/] {error}")
        raise typer.Exit(1) from error
    console.print(f"[green]Güncellendi:[/] {key} = {value}")


@app.command()
def doctor(path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Kurulum ve repository sağlığını kontrol eder."""
    container = _container(path)
    table = Table(title="AutoGit Doctor")
    table.add_column("Durum")
    table.add_column("Kontrol")
    table.add_column("Açıklama")
    for check in container.doctor.run().checks:  # type: ignore[attr-defined]
        color = {CheckState.PASS: "green", CheckState.WARNING: "yellow", CheckState.ERROR: "red"}[check.state]
        table.add_row(f"[{color}]{check.state.value}[/]", check.name, check.detail)
    console.print(table)


if __name__ == "__main__":
    app()
