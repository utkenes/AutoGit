from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from autogit.application.commit_service import CommitService
from autogit.application.quality_service import QualityService
from autogit.config import AutoGitConfig
from autogit.domain.exceptions import NothingToCommitError, SecurityViolationError
from autogit.infrastructure.command_runner import CommandRunner
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.secret_scanner import SecretScanner
from autogit.providers.local_commit_provider import LocalCommitMessageProvider


@pytest.fixture()
def repository(tmp_path: Path) -> Path:
    for command in (["git", "init"], ["git", "config", "user.name", "Test User"], ["git", "config", "user.email", "test@example.com"]):
        subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
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

