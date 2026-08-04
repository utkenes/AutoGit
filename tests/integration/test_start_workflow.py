from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autogit.cli import app
from autogit.config import write_default_config

runner = CliRunner()


@pytest.fixture()
def repository(tmp_path: Path) -> Path:
    for command in (
        ["git", "init"],
        ["git", "config", "user.name", "Test User"],
        ["git", "config", "user.email", "test@example.com"],
    ):
        subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "README.md").write_text("# initial\n", encoding="utf-8")
    write_default_config(tmp_path)
    subprocess.run(["git", "add", "README.md", ".autogit.toml"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


@pytest.fixture()
def empty_repository(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "feature.py").write_text("value = 1\n", encoding="utf-8")
    return tmp_path


def test_start_cancellation_does_not_commit(repository: Path) -> None:
    (repository / "feature.py").write_text("value = 1\n", encoding="utf-8")
    result = runner.invoke(app, ["start", "--path", str(repository)], input="n\nC\n")
    assert result.exit_code == 0
    assert "İşlem iptal edildi" in result.output
    assert _commit_count(repository) == 1


def test_start_approved_plan_commits_without_push(repository: Path) -> None:
    (repository / "feature.py").write_text("value = 1\n", encoding="utf-8")
    result = runner.invoke(app, ["start", "--path", str(repository)], input="n\nA\n")
    assert result.exit_code == 0
    assert "local commit oluşturuldu" in result.output
    assert _commit_count(repository) == 2


def test_start_releases_log_file_handlers(repository: Path) -> None:
    (repository / "feature.py").write_text("value = 1\n", encoding="utf-8")

    result = runner.invoke(app, ["start", "--path", str(repository)], input="n\nA\n")

    assert result.exit_code == 0
    logger = logging.getLogger(f"autogit.{repository.resolve()}")
    assert not logger.handlers


def test_start_writes_missing_config_before_showing_plan(repository: Path) -> None:
    (repository / ".autogit.toml").unlink()
    result = runner.invoke(app, ["start", "--path", str(repository)], input="n\nC\n")
    assert result.exit_code == 0
    assert (repository / ".autogit.toml").exists()


def test_start_blocks_detached_head(repository: Path) -> None:
    subprocess.run(["git", "checkout", "--detach"], cwd=repository, check=True, capture_output=True)
    (repository / "feature.py").write_text("value = 1\n", encoding="utf-8")
    result = runner.invoke(app, ["start", "--path", str(repository)], input="n\n")
    assert result.exit_code == 1
    assert "detached HEAD" in result.output


def test_start_edits_message(repository: Path) -> None:
    (repository / "feature.py").write_text("value = 1\n", encoding="utf-8")
    result = runner.invoke(app, ["start", "--path", str(repository)], input="n\nE\nfeat: custom message\ny\n")
    assert result.exit_code == 0
    subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert subject == "feat: custom message"


def test_start_dry_run_keeps_head_and_index(repository: Path) -> None:
    (repository / "feature.py").write_text("value = 1\n", encoding="utf-8")
    before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout
    result = runner.invoke(app, ["start", "--path", str(repository), "--dry-run"])
    after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=repository, check=True, capture_output=True, text=True).stdout
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert before == after
    assert staged == ""


def test_dry_run_is_side_effect_free_for_initial_repository(empty_repository: Path) -> None:
    result = runner.invoke(app, ["start", "--path", str(empty_repository), "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert not (empty_repository / ".autogit").exists()
    assert not (empty_repository / ".autogit.toml").exists()
    assert not (empty_repository / ".git" / "index.lock").exists()
    assert not (empty_repository / ".git" / "config.lock").exists()


def test_plan_is_side_effect_free_for_initial_repository(empty_repository: Path) -> None:
    result = runner.invoke(app, ["plan", "--path", str(empty_repository), "--json"])

    assert result.exit_code == 0
    assert '"groups"' in result.output
    assert not (empty_repository / ".autogit").exists()
    assert not (empty_repository / ".autogit.toml").exists()


@pytest.mark.parametrize("lock_name", ["index.lock", "config.lock"])
def test_start_reports_git_locks_without_removing_them(repository: Path, lock_name: str) -> None:
    lock = repository / ".git" / lock_name
    lock.write_text("held", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))

    result = runner.invoke(app, ["start", "--path", str(repository)])
    output = result.output.replace("\n", "")

    assert result.exit_code == 1
    assert lock_name in output
    assert "2 dakika" in output
    assert "otomatik silmez" in output
    assert lock.exists()


def test_plan_json_is_machine_readable(repository: Path) -> None:
    (repository / "feature.py").write_text("value = 1\n", encoding="utf-8")
    result = runner.invoke(app, ["plan", "--path", str(repository), "--json"])
    import json

    payload = json.loads(result.output)
    assert payload["repository"]["root"] == str(repository)
    assert payload["groups"][0]["type"] == "feat"
    assert payload["groups"][0]["confidence"] > 0


def test_undo_restores_last_unpushed_start_workflow(repository: Path) -> None:
    (repository / "feature.py").write_text("value = 1\n", encoding="utf-8")
    created = runner.invoke(app, ["start", "--path", str(repository)], input="n\nA\n")
    assert created.exit_code == 0
    undone = runner.invoke(app, ["undo", "--path", str(repository)], input="y\n")
    assert undone.exit_code == 0
    assert _commit_count(repository) == 1
    assert (repository / "feature.py").exists()


def _commit_count(root: Path) -> int:
    return int(
        subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout
    )
