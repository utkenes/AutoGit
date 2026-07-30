"""Command line interface for the controlled AutoGit workflow."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from autogit.application.setup_service import SetupService
from autogit.config import update_config, write_default_config
from autogit.container import build_container
from autogit.domain.exceptions import AutoGitError, NothingToCommitError, PreStagedChangesError
from autogit.domain.models import CheckState, CommitGroup
from autogit.infrastructure.command_runner import CommandRunner
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.operation_lock import AutoGitOperationLock

app = typer.Typer(help="Güvenli ve onaylı Git commit asistanı.", no_args_is_help=True)
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
    console.print("[red]HATA[/] AutoGit dışında stage edilmiş dosyalar bulundu:")
    for path in error.files:
        console.print(f"  {path}")
    console.print("AutoGit mevcut staging area'yı değiştirmedi.")


def _ensure_repository(path: Path) -> Path:
    git = GitService(path, CommandRunner())
    if git.is_repository():
        return git.get_repository_root()
    console.print("Bu klasör bir Git repository değil.")
    choice = typer.prompt("1: Local oluştur, 2: Remote bağla, 3: İptal", default="3")
    if choice not in {"1", "2"}:
        raise typer.Exit()
    remote = typer.prompt("Repository URL'si") if choice == "2" else None
    try:
        return SetupService(path, git).create_repository(remote)
    except AutoGitError as error:
        console.print(f"[red]Kurulum başarısız:[/] {error}")
        raise typer.Exit(1) from error


def _configure_first_run(root: Path, git: GitService) -> None:
    setup = SetupService(root, git)
    if not setup.ensure_config():
        return
    console.print("[green]İlk kurulum:[/] .autogit.toml oluşturuldu.")
    for suggestion in setup.detect_quality_suggestions():
        if typer.confirm(f"{suggestion.message} {suggestion.command} aktif edilsin mi?", default=True):
            setup.enable(suggestion.setting, suggestion.command)


def _show_plan(groups: list[CommitGroup]) -> None:
    table = Table(title=f"{sum(len(group.files) for group in groups)} değişiklik için commit planı")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Önerilen mesaj", style="green")
    table.add_column("Dosyalar")
    for index, group in enumerate(groups, start=1):
        table.add_row(str(index), group.suggested_message, "\n".join(str(file.path) for file in group.files))
    console.print(table)


def _edit_messages(groups: list[CommitGroup]) -> list[CommitGroup]:
    edited: list[CommitGroup] = []
    for group in groups:
        message = typer.prompt("Commit mesajı", default=group.suggested_message).strip()
        edited.append(replace(group, suggested_message=message or group.suggested_message))
    return edited


@app.command()
def start(
    path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd(),
) -> None:
    """Analyze changes, show a plan, and commit only after confirmation."""
    root = _ensure_repository(path)
    git = GitService(root, CommandRunner())
    try:
        with AutoGitOperationLock(root):
            if git.has_index_lock():
                console.print("[red]Hata:[/] Git index.lock bulundu; başka bir Git işlemi tamamlanmadan devam edilemez.")
                raise typer.Exit(1)
            _configure_first_run(root, git)
            if not git.get_remote_url() and typer.confirm("Remote repository bulunamadı. URL eklemek ister misiniz?", default=False):
                SetupService(root, git).add_remote(typer.prompt("Repository URL'si"))

            container = _container(root)
            state = container.git.get_repository_state()  # type: ignore[attr-defined]
            allow_initial = not state.has_head
            if allow_initial and not typer.confirm("İlk commit oluşturmak için planı devam ettirmek ister misiniz?", default=False):
                raise typer.Exit()
            try:
                plan = container.commit.prepare(allow_initial_commit=allow_initial)  # type: ignore[attr-defined]
            except NothingToCommitError:
                console.print("Commit oluşturulacak değişiklik bulunamadı.")
                return
            groups = container.planner.plan(plan.candidates)  # type: ignore[attr-defined]
            _show_plan(groups)
            choice = typer.prompt("[A] Onayla  [E] Mesajları düzenle  [C] İptal", default="C").upper()
            if choice == "C":
                console.print("İşlem iptal edildi.")
                return
            if choice == "E":
                groups = _edit_messages(groups)
                _show_plan(groups)
                if not typer.confirm("Düzenlenen plan onaylansın mı?", default=False):
                    console.print("İşlem iptal edildi.")
                    return
            elif choice != "A":
                console.print("Geçersiz seçim; işlem iptal edildi.")
                return
            results = container.commit.execute_groups(  # type: ignore[attr-defined]
                groups, allow_initial_commit=allow_initial, lock_held=True
            )
            console.print(f"[green]{len(results)} local commit oluşturuldu.[/]")
            if container.git.get_remote_url() and typer.confirm("Remote'a push edilsin mi?", default=False):  # type: ignore[attr-defined]
                container.git.push()  # type: ignore[attr-defined]
                console.print("[green]Push tamamlandı.[/]")
            else:
                console.print("Commitler localde bırakıldı.")
    except PreStagedChangesError as error:
        _print_pre_staged_error(error)
        raise typer.Exit(1) from error
    except AutoGitError as error:
        console.print(f"[red]Hata:[/] {error}")
        raise typer.Exit(1) from error


@app.command()
def init(path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Create the default AutoGit configuration for an existing repository."""
    container = _container(path)
    target = write_default_config(container.root)  # type: ignore[attr-defined]
    console.print(f"[green]Başarılı:[/] {target}")


@app.command()
def commit(
    path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd(),
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Run the legacy single-commit workflow."""
    container = _container(path)
    try:
        if dry_run:
            plan = container.commit.preview()  # type: ignore[attr-defined]
            for file in plan.candidates:
                console.print(f"{file.status.value}: {file.path}")
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
    """Run the legacy watcher command."""
    container = _container(path)
    container.watch.run()  # type: ignore[attr-defined]


@app.command()
def status(path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Show repository and AutoGit status."""
    container = _container(path)
    table = Table(title="AutoGit Durumu")
    table.add_column("Alan", style="cyan")
    table.add_column("Değer")
    for key, value in container.status.get().items():  # type: ignore[attr-defined]
        table.add_row(key, "\n".join(value) if isinstance(value, list) else str(value))
    console.print(table)


@config_app.callback(invoke_without_command=True)
def config(ctx: typer.Context, path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Show current configuration."""
    if ctx.invoked_subcommand is None:
        container = _container(path)
        console.print_json(data=container.config.model_dump_json(indent=2))  # type: ignore[attr-defined]


@config_app.command("set")
def config_set(key: str, value: str, path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Update a supported setting."""
    container = _container(path)
    try:
        update_config(container.root, key, value)  # type: ignore[attr-defined]
    except AutoGitError as error:
        console.print(f"[red]Hata:[/] {error}")
        raise typer.Exit(1) from error
    console.print(f"[green]Güncellendi:[/] {key} = {value}")


@app.command()
def doctor(path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Check installation and repository health."""
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
