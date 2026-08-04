from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from autogit.application.commit_service import CommitService
from autogit.application.quality_service import QualityService
from autogit.config import AutoGitConfig
from autogit.domain.exceptions import (
    NothingToCommitError,
    PreStagedChangesError,
    RepositoryUnsafeError,
    SecurityViolationError,
)
from autogit.domain.models import CommitGroup
from autogit.infrastructure.command_runner import CommandRunner
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.secret_scanner import SecretScanner
from autogit.providers.local_commit_provider import LocalCommitMessageProvider


@pytest.fixture()
def repository(tmp_path: Path) -> Path:
    for command in (["git", "init"], ["git", "config", "user.name", "Test User"], ["git", "config", "user.email", "test@example.com"]):
        subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def service(root: Path) -> CommitService:
    runner = CommandRunner()
    git = GitService(root, runner)
    config = AutoGitConfig(run_tests=False, run_lint=False)
    import logging
    return CommitService(root, config, git, SecretScanner(), QualityService(root, config, runner), LocalCommitMessageProvider(), logging.getLogger("test"))


def test_no_change_does_not_commit(repository: Path) -> None:
    with pytest.raises(NothingToCommitError):
        service(repository).execute()


def test_normal_file_creates_commit(repository: Path) -> None:
    (repository / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    result, _ = service(repository).execute()
    assert result.message.startswith("feat: ")
    assert GitService(repository, CommandRunner()).get_last_commit() is not None


def test_env_file_is_never_staged(repository: Path) -> None:
    (repository / ".env").write_text("VALUE=safe\n", encoding="utf-8")
    with pytest.raises(SecurityViolationError):
        service(repository).execute()


def test_env_example_with_secret_blocks_commit(repository: Path) -> None:
    (repository / ".env.example").write_text("OPENAI_API_KEY=sk-proj-abcdefghijklmnop12345678\n", encoding="utf-8")
    with pytest.raises(SecurityViolationError):
        service(repository).execute()


def test_deleted_file_is_staged(repository: Path) -> None:
    file = repository / "old.txt"
    file.write_text("old\n", encoding="utf-8")
    git = GitService(repository, CommandRunner())
    git.stage_files([Path("old.txt")])
    git.commit("feat: add old file")
    file.unlink()
    service(repository).execute()
    assert GitService(repository, CommandRunner()).get_last_commit() is not None


def test_path_with_spaces_is_supported(repository: Path) -> None:
    folder = repository / "space folder"
    folder.mkdir()
    (folder / "note.txt").write_text("safe\n", encoding="utf-8")
    result, _ = service(repository).execute()
    assert result.staged_files == [Path("space folder/note.txt")]


def test_path_with_turkish_characters_is_supported(repository: Path) -> None:
    path = repository / "Türkçe Dosya.py"
    path.write_text("print('safe')\n", encoding="utf-8")
    result, _ = service(repository).execute()
    assert result.staged_files == [Path("Türkçe Dosya.py")]


def test_auto_push_without_remote_is_skipped(repository: Path) -> None:
    (repository / "safe.txt").write_text("safe\n", encoding="utf-8")
    commit_service = service(repository)
    commit_service.config = commit_service.config.model_copy(update={"auto_push": True})
    _, push = commit_service.execute()
    assert not push.pushed
    assert "Remote" in push.detail


def test_pre_staged_files_are_left_untouched(repository: Path) -> None:
    (repository / ".env").write_text("VALUE=safe\n", encoding="utf-8")
    git = GitService(repository, CommandRunner())
    git.stage_files([Path(".env")])
    with pytest.raises(PreStagedChangesError) as raised:
        service(repository).execute()
    assert raised.value.files == [".env"]
    assert [file.path for file in git.get_staged_files()] == [Path(".env")]


def test_secret_rolls_back_only_autogit_staging(repository: Path) -> None:
    (repository / ".env.example").write_text(
        "OPENAI_API_KEY=sk-proj-abcdefghijklmnop12345678\n", encoding="utf-8"
    )
    with pytest.raises(SecurityViolationError):
        service(repository).execute()
    assert not GitService(repository, CommandRunner()).has_staged_changes()


def test_preview_does_not_stage_files(repository: Path) -> None:
    (repository / "preview.txt").write_text("safe\n", encoding="utf-8")
    plan = service(repository).preview()
    assert [file.path for file in plan.candidates] == [Path("preview.txt")]
    assert not GitService(repository, CommandRunner()).has_staged_changes()


def test_group_execution_rejects_duplicate_or_partial_plans(repository: Path) -> None:
    (repository / "first.py").write_text("first = 1\n", encoding="utf-8")
    (repository / "second.py").write_text("second = 2\n", encoding="utf-8")
    commit_service = service(repository)
    plan = commit_service.prepare()
    duplicate = CommitGroup(
        files=(plan.candidates[0], plan.candidates[0]),
        suggested_message="feat: add first file",
        commit_type="feat",
        scope=None,
        reason="test",
    )

    with pytest.raises(SecurityViolationError):
        commit_service.execute_groups([duplicate])

    assert not GitService(repository, CommandRunner()).has_staged_changes()


def test_detached_head_is_blocked_before_staging(repository: Path) -> None:
    subprocess.run(["git", "checkout", "--detach"], cwd=repository, check=True, capture_output=True)
    (repository / "safe.txt").write_text("safe\n", encoding="utf-8")
    with pytest.raises(RepositoryUnsafeError, match="detached HEAD"):
        service(repository).execute()
    assert not GitService(repository, CommandRunner()).has_staged_changes()
