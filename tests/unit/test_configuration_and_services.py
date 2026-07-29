from __future__ import annotations

from pathlib import Path

import pytest

from autogit.application.quality_service import QualityService
from autogit.application.watch_service import WatchService
from autogit.config import AutoGitConfig, load_config, update_config, write_default_config
from autogit.domain.exceptions import (
    ConfigurationError,
    QualityCheckFailedError,
    RepositoryNotFoundError,
)
from autogit.domain.models import WatchEvent
from autogit.infrastructure.command_runner import CommandResult
from autogit.infrastructure.git_service import GitService
from autogit.utils.masking import mask_secret, redact_text
from autogit.utils.paths import is_ignored, is_within_root


class FailingRunner:
    def run(self, command: list[str], cwd: Path, timeout: float | None = None) -> CommandResult:
        return CommandResult(command, 1, "", "kontrol hatası", 0.1)


class DummyCommitService:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self) -> None:
        self.calls += 1


def test_default_config_can_be_written_and_loaded(tmp_path: Path) -> None:
    write_default_config(tmp_path)
    assert load_config(tmp_path).debounce_seconds == 60


def test_config_update_is_type_safe(tmp_path: Path) -> None:
    write_default_config(tmp_path)
    assert update_config(tmp_path, "auto_push", "true").auto_push
    with pytest.raises(ConfigurationError):
        update_config(tmp_path, "auto_push", "yes")


def test_invalid_toml_is_reported(tmp_path: Path) -> None:
    (tmp_path / ".autogit.toml").write_text("debounce_seconds = [", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(tmp_path)


def test_quality_failure_blocks_pipeline(tmp_path: Path) -> None:
    config = AutoGitConfig(run_tests=True, run_lint=False)
    with pytest.raises(QualityCheckFailedError):
        QualityService(tmp_path, config, FailingRunner()).run()  # type: ignore[arg-type]


def test_non_repository_is_detected(tmp_path: Path) -> None:
    from autogit.infrastructure.command_runner import CommandRunner

    with pytest.raises(RepositoryNotFoundError):
        GitService(tmp_path, CommandRunner()).get_repository_root()


def test_paths_do_not_escape_repository(tmp_path: Path) -> None:
    assert is_within_root(tmp_path / "inside.txt", tmp_path)
    assert not is_within_root(tmp_path.parent / "outside.txt", tmp_path)
    assert is_ignored(tmp_path / ".git" / "config", tmp_path, [".git"])


def test_masking_does_not_expose_key() -> None:
    secret = "sk-proj-abcdefghijklmnop12345678"
    assert "abcdefgh" not in mask_secret(secret)
    assert "abcdefgh" not in redact_text(secret)


def test_debounce_creates_one_commit_after_wait(tmp_path: Path) -> None:
    import logging
    import time

    dummy = DummyCommitService()
    config = AutoGitConfig(debounce_seconds=1, check_interval_seconds=1)
    watcher = WatchService(tmp_path, config, dummy, logging.getLogger("watch-test"))  # type: ignore[arg-type]
    watcher._record_event(WatchEvent(tmp_path / "file.txt", "modified"))
    watcher._process_if_ready()
    assert dummy.calls == 0
    watcher._last_event = time.monotonic() - 2
    watcher._process_if_ready()
    watcher._process_if_ready()
    assert dummy.calls == 1

