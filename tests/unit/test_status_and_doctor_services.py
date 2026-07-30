"""Doctor ve status servislerinin davranış testleri."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from autogit.application.doctor_service import DoctorService
from autogit.application.status_service import StatusService
from autogit.config import AutoGitConfig
from autogit.domain.models import CheckState


def test_doctor_returns_early_outside_git_repository(tmp_path: Path) -> None:
    git = MagicMock()
    git.is_repository.return_value = False

    runner = MagicMock()
    runner.run.return_value = SimpleNamespace(
        exit_code=0,
        output="git version 2.51.0",
    )

    service = DoctorService(
        root=tmp_path,
        git=git,
        config=AutoGitConfig(),
        runner=runner,
    )

    report = service.run()

    assert len(report.checks) == 3
    assert report.checks[0].name == "Git"
    assert report.checks[0].state is CheckState.PASS
    assert report.checks[2].name == "Git repository"
    assert report.checks[2].state is CheckState.ERROR

    git.get_current_branch.assert_not_called()
    git.get_changed_files.assert_not_called()


def test_doctor_reports_missing_optional_repository_settings(
    tmp_path: Path,
) -> None:
    git = MagicMock()
    git.is_repository.return_value = True
    git.get_current_branch.return_value = "main"
    git.get_remote_url.return_value = None
    git.get_upstream_branch.return_value = None
    git.get_git_user_name.return_value = None
    git.get_git_user_email.return_value = None
    git.is_file_tracked.return_value = False
    git.get_changed_files.return_value = []

    runner = MagicMock()
    runner.run.return_value = SimpleNamespace(
        exit_code=0,
        output="git version 2.51.0",
    )

    service = DoctorService(
        root=tmp_path,
        git=git,
        config=AutoGitConfig(),
        runner=runner,
    )

    report = service.run()
    checks = {check.name: check for check in report.checks}

    assert checks["Aktif branch"].state is CheckState.PASS
    assert checks["Remote"].state is CheckState.WARNING
    assert checks["Upstream"].state is CheckState.WARNING
    assert checks["Git kullanıcı adı"].state is CheckState.WARNING
    assert checks["Git email"].state is CheckState.WARNING
    assert checks[".gitignore"].state is CheckState.ERROR
    assert checks["AutoGit config"].state is CheckState.WARNING
    assert checks["Secret taraması"].state is CheckState.PASS

    git.get_current_branch.assert_called_once_with()
    git.get_remote_url.assert_called_once_with()
    git.get_upstream_branch.assert_called_once_with()


def test_doctor_reports_healthy_repository(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".env\n.venv\n", encoding="utf-8")

    git = MagicMock()
    git.is_repository.return_value = True
    git.get_current_branch.return_value = "main"
    git.get_remote_url.return_value = "https://github.com/example/repo.git"
    git.get_upstream_branch.return_value = "origin/main"
    git.get_git_user_name.return_value = "developer"
    git.get_git_user_email.return_value = "developer@example.com"
    git.is_file_tracked.return_value = False
    git.get_changed_files.return_value = []

    runner = MagicMock()
    runner.run.return_value = SimpleNamespace(
        exit_code=0,
        output="git version 2.51.0",
    )

    service = DoctorService(
        root=tmp_path,
        git=git,
        config=AutoGitConfig(),
        runner=runner,
    )

    report = service.run()
    checks = {check.name: check for check in report.checks}

    assert checks["Git"].state is CheckState.PASS
    assert checks["Git repository"].state is CheckState.PASS
    assert checks["Aktif branch"].detail == "main"
    assert checks["Remote"].state is CheckState.PASS
    assert checks[".gitignore"].state is CheckState.PASS
    assert checks["Tracked .env"].state is CheckState.PASS
    assert checks["Tracked .venv"].state is CheckState.PASS
    assert checks["Secret taraması"].state is CheckState.PASS


def test_status_returns_readable_repository_summary(tmp_path: Path) -> None:
    git = MagicMock()
    git.get_repository_root.return_value = tmp_path
    git.get_changed_files.return_value = []
    git.get_current_branch.return_value = "main"
    git.get_remote_url.return_value = "https://github.com/example/repo.git"
    git.get_upstream_branch.return_value = "origin/main"
    git.get_staged_files.return_value = []
    git.get_last_commit.return_value = "feat: initial commit"

    config = AutoGitConfig()
    service = StatusService(git=git, config=config)

    status = service.get()

    assert status["Repository root"] == str(tmp_path)
    assert status["Aktif branch"] == "main"
    assert status["Remote URL"] == "https://github.com/example/repo.git"
    assert status["Upstream"] == "origin/main"
    assert status["Değişiklikler"] == ["Temiz"]
    assert status["Staged"] == ["Yok"]
    assert status["Son commit"] == "feat: initial commit"
    assert status["Yapılandırma"] == str(tmp_path / ".autogit.toml")