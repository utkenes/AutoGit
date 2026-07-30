"""Command line interface for the controlled AutoGit workflow."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from autogit.application.last_run_service import LastRunService
from autogit.application.quality_recovery_service import QualityRecoveryService
from autogit.application.setup_service import SetupService
from autogit.config import update_config, write_default_config
from autogit.container import build_container
from autogit.domain.exceptions import (
    AutoGitError,
    NothingToCommitError,
    PreStagedChangesError,
    QualityCheckFailedError,
    RepositoryUnsafeError,
)
from autogit.domain.models import CheckState, CommitGroup, CommitResult
from autogit.infrastructure.command_runner import CommandRunner
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.operation_lock import AutoGitOperationLock

app = typer.Typer(help="Güvenli ve onaylı Git commit asistanı.", no_args_is_help=True)
config_app = typer.Typer(help="Yapılandırmayı gösterir veya değiştirir.", no_args_is_help=False)
app.add_typer(config_app, name="config")
console = Console()
VERSION = "0.1.0"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"AutoGit {VERSION}")
        raise typer.Exit()


@app.callback()
def main(version: Annotated[bool, typer.Option("--version", callback=_version_callback, is_eager=True)] = False) -> None:
    """Provide global CLI metadata."""


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


def _ensure_repository(path: Path, *, allow_setup: bool = True) -> Path:
    git = GitService(path, CommandRunner())
    if git.is_repository():
        return git.get_repository_root()
    if not allow_setup:
        raise RepositoryUnsafeError("Dry-run Git repository olmayan bir klasörde kurulum yapmaz.")
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


def _print_auto_mode() -> None:
    console.print("[cyan]Auto mode enabled.[/]")
    console.print("Allowed: plan approval, low-risk lint fixes, quality retry, safe commits.")
    console.print("User approval is still required for push, remote changes, dependencies, and destructive operations.")


def _quality_commands(container: object) -> list[str]:
    config = container.config  # type: ignore[attr-defined]
    commands: list[str] = []
    if config.run_tests:
        commands.append(config.test.command)
    if config.run_lint:
        commands.append(config.lint.command)
    if config.run_type_check:
        commands.append(config.type_check.command)
    return commands


def _run_groups_with_recovery(container: object, groups: list[CommitGroup], allow_initial: bool, auto: bool) -> list[CommitResult]:
    attempts = 0
    config = container.config  # type: ignore[attr-defined]
    recovery = QualityRecoveryService(container.root, CommandRunner())  # type: ignore[attr-defined]
    while True:
        try:
            return container.commit.execute_groups(  # type: ignore[no-any-return,attr-defined]
                groups, allow_initial_commit=allow_initial, lock_held=True
            )
        except QualityCheckFailedError as error:
            suggestions = recovery.suggestions(error)
            console.print("[red]Kalite kontrolü başarısız oldu.[/]")
            console.print("AutoGit hiçbir commit veya push oluşturmadı.")
            if not suggestions:
                console.print(str(error))
                raise
            suggestion = suggestions[0]
            console.print(f"Önerilen güvenli çözüm: {' '.join(suggestion.command or ())}")
            apply = auto or typer.confirm("Düzeltme uygulansın ve kontroller tekrar çalışsın mı?", default=False)
            if not apply:
                raise
            attempts = recovery.apply(suggestion, attempts, config.max_fix_attempts)


@app.command()
def start(
    path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd(),
    auto: Annotated[bool, typer.Option("--auto", help="Yalnızca güvenli onayları otomatikleştirir.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Git veya config durumunu değiştirmez.")] = False,
) -> None:
    """Analyze changes, show a plan, and commit only after confirmation."""
    root = _ensure_repository(path, allow_setup=not dry_run)
    git = GitService(root, CommandRunner())
    if dry_run:
        container = _container(root)
        try:
            plan = container.commit.prepare()  # type: ignore[attr-defined]
        except NothingToCommitError:
            console.print("Commit oluşturulacak değişiklik bulunamadı.")
            console.print("Dry run tamamlandı. Repository durumu değiştirilmedi.")
            return
        groups = container.planner.plan(plan.candidates)  # type: ignore[attr-defined]
        _show_plan(groups)
        console.print("Çalıştırılacak kalite komutları:")
        for command in _quality_commands(container):
            console.print(f"  {command}")
        console.print(f"Push hedefi: {container.git.get_remote_url() or 'tanımlı değil'}")  # type: ignore[attr-defined]
        console.print("Dry run tamamlandı. Repository durumu değiştirilmedi.")
        return
    try:
        with AutoGitOperationLock(root):
            if git.has_index_lock():
                console.print("[red]Hata:[/] Git index.lock bulundu; başka bir Git işlemi tamamlanmadan devam edilemez.")
                raise typer.Exit(1)
            _configure_first_run(root, git)
            if not auto and not git.get_remote_url() and typer.confirm("Remote repository bulunamadı. URL eklemek ister misiniz?", default=False):
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
            if auto:
                _print_auto_mode()
                choice = "A"
            else:
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
            base_commit = container.git.get_head()  # type: ignore[attr-defined]
            results = _run_groups_with_recovery(container, groups, allow_initial, auto)
            if base_commit is not None:
                LastRunService(root, container.git).record(base_commit, results)  # type: ignore[attr-defined]
            console.print(f"[green]{len(results)} local commit oluşturuldu.[/]")
            if container.git.get_remote_url():  # type: ignore[attr-defined]
                for result in results:
                    console.print(f"{result.commit_hash[:8]} {result.message}")
                console.print(f"Remote: origin | Branch: {container.git.get_current_branch() or 'yok'}")  # type: ignore[attr-defined]
                console.print(f"Upstream: {container.git.get_upstream_branch() or 'tanımlı değil'}")  # type: ignore[attr-defined]
            if container.git.get_remote_url() and typer.confirm("Push edilsin mi?", default=False):  # type: ignore[attr-defined]
                sync = container.git.get_ahead_behind()  # type: ignore[attr-defined]
                if sync and sync[0] > 0:
                    console.print("[red]Remote branch ileride veya diverged.[/] git fetch origin ve git rebase origin/main kullanın.")
                    console.print("Local commitleriniz korunuyor.")
                    return
                try:
                    container.git.push()  # type: ignore[attr-defined]
                except AutoGitError as error:
                    console.print(f"[red]Push başarısız:[/] {error}")
                    console.print("Local commitleriniz korunuyor.")
                    return
                LastRunService(root, container.git).mark_pushed()  # type: ignore[attr-defined]
                console.print(f"[green]{len(results)} commit push edildi.[/]")
            else:
                console.print("Commitler local repository'de bırakıldı. Push yapılmadı.")
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


@app.command("plan")
def plan_command(
    path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd(),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show the commit plan, optionally as machine-readable JSON."""
    container = _container(path)
    try:
        state = container.git.get_repository_state()  # type: ignore[attr-defined]
        prepared = container.commit.prepare(allow_initial_commit=not state.has_head)  # type: ignore[attr-defined]
    except NothingToCommitError:
        prepared = None
    if prepared is None:
        groups: list[CommitGroup] = []
    else:
        groups = container.planner.plan(prepared.candidates)  # type: ignore[attr-defined]
    if json_output:
        payload = {
            "repository": {
                "root": str(container.root),  # type: ignore[attr-defined]
                "branch": container.git.get_current_branch(),  # type: ignore[attr-defined]
                "remote": "origin" if container.git.get_remote_url() else None,  # type: ignore[attr-defined]
                "upstream": container.git.get_upstream_branch(),  # type: ignore[attr-defined]
            },
            "groups": [
                {
                    "type": group.commit_type,
                    "scope": group.scope,
                    "message": group.suggested_message,
                    "files": [str(file.path) for file in group.files],
                    "reason": group.reason,
                }
                for group in groups
            ],
            "quality": {
                "tests_enabled": container.config.run_tests,  # type: ignore[attr-defined]
                "lint_enabled": container.config.run_lint,  # type: ignore[attr-defined]
                "security_enabled": container.config.security.scan_secrets,  # type: ignore[attr-defined]
            },
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    _show_plan(groups)


@app.command()
def undo(path: Annotated[Path, typer.Option("--path", "-p", exists=True, file_okay=False)] = Path.cwd()) -> None:
    """Safely undo the last unpushed AutoGit workflow after confirmation."""
    container = _container(path)
    try:
        with AutoGitOperationLock(container.root):  # type: ignore[attr-defined]
            service = LastRunService(container.root, container.git)  # type: ignore[attr-defined]
            run = service.validate_undo()
            console.print(f"Son AutoGit işlemi {len(run.commit_hashes)} local commit oluşturdu.")
            for message in run.messages:
                console.print(f"- {message}")
            if not typer.confirm("Dosyalar çalışma alanına geri alınsın mı?", default=False):
                console.print("İşlem iptal edildi.")
                return
            service.undo(run)
            console.print("Son AutoGit işlemi güvenli biçimde geri alındı.")
    except AutoGitError as error:
        console.print(f"[red]Hata:[/] {error}")
        raise typer.Exit(1) from error


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
