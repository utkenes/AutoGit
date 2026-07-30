import json
from pathlib import Path

import pytest

from autogit.application.setup_service import SetupService
from autogit.domain.exceptions import ConfigurationError, GitOperationLockedError
from autogit.infrastructure.command_runner import CommandRunner
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.operation_lock import AutoGitOperationLock


def test_setup_detects_python_tools_and_writes_default_config(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    setup = SetupService(tmp_path, GitService(tmp_path, CommandRunner()))
    assert setup.ensure_config()
    assert {item.setting for item in setup.detect_quality_suggestions()} == {"run_tests", "run_lint"}


def test_setup_rejects_invalid_remote_url(tmp_path: Path) -> None:
    setup = SetupService(tmp_path, GitService(tmp_path, CommandRunner()))
    with pytest.raises(ConfigurationError):
        setup.add_remote("not-a-url")


def test_setup_persists_approved_detected_command(tmp_path: Path) -> None:
    setup = SetupService(tmp_path, GitService(tmp_path, CommandRunner()))
    setup.ensure_config()
    setup.enable("run_tests", "npm test")
    assert 'command = "npm test"' in (tmp_path / ".autogit.toml").read_text(encoding="utf-8")


def test_second_operation_lock_is_rejected(tmp_path: Path) -> None:
    with AutoGitOperationLock(tmp_path), pytest.raises(GitOperationLockedError), AutoGitOperationLock(tmp_path):
        pass


def test_stale_operation_lock_is_removed(tmp_path: Path) -> None:
    path = tmp_path / ".autogit" / "autogit.lock"
    path.parent.mkdir()
    path.write_text(json.dumps({"pid": 99999999}), encoding="utf-8")
    with AutoGitOperationLock(tmp_path):
        assert path.exists()
    assert not path.exists()
