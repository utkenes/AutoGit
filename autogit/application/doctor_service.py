"""Ortam ve repository sağlığını PASS/WARNING/ERROR olarak raporlar."""

from __future__ import annotations

import sys
from pathlib import Path

from autogit.config import AutoGitConfig, config_path
from autogit.domain.models import CheckState, DoctorCheck, DoctorReport
from autogit.infrastructure.command_runner import CommandRunner
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.secret_scanner import SecretScanner


class DoctorService:
    def __init__(
        self,
        root: Path,
        git: GitService,
        config: AutoGitConfig,
        runner: CommandRunner,
    ) -> None:
        self.root = root
        self.git = git
        self.config = config
        self.runner = runner

    def run(self) -> DoctorReport:
        checks: list[DoctorCheck] = []

        git_version = self.runner.run(["git", "--version"], self.root)
        checks.append(
            self._check(
                "Git",
                git_version.exit_code == 0,
                git_version.output,
            )
        )

        version_ok = sys.version_info >= (3, 12)
        checks.append(
            self._check(
                "Python 3.12+",
                version_ok,
                sys.version.split()[0],
            )
        )

        is_repo = self.git.is_repository()
        checks.append(
            self._check(
                "Git repository",
                is_repo,
                "Repository bulundu."
                if is_repo
                else "Repository bulunamadı.",
            )
        )

        if not is_repo:
            return DoctorReport(checks)

        branch = self.git.get_current_branch()
        remote_url = self.git.get_remote_url()
        upstream = self.git.get_upstream_branch()
        git_user_name = self.git.get_git_user_name()
        git_user_email = self.git.get_git_user_email()

        gitignore_exists = (self.root / ".gitignore").exists()
        env_tracked = self.git.is_file_tracked(Path(".env"))
        venv_tracked = self.git.is_file_tracked(Path(".venv"))
        config_exists = config_path(self.root).exists()

        checks.extend(
            [
                self._check(
                    "Aktif branch",
                    branch is not None,
                    branch or "Yok",
                ),
                self._optional(
                    "Remote",
                    remote_url,
                    "Remote tanımlı değil.",
                ),
                self._optional(
                    "Upstream",
                    upstream,
                    "Upstream tanımlı değil.",
                ),
                self._optional(
                    "Git kullanıcı adı",
                    git_user_name,
                    "Tanımlı değil.",
                ),
                self._optional(
                    "Git email",
                    git_user_email,
                    "Tanımlı değil.",
                ),
                self._check(
                    ".gitignore",
                    gitignore_exists,
                    ".gitignore mevcut."
                    if gitignore_exists
                    else ".gitignore yok.",
                ),
                self._check(
                    "Tracked .env",
                    not env_tracked,
                    ".env takip edilmiyor."
                    if not env_tracked
                    else ".env Git tarafından takip ediliyor.",
                ),
                self._check(
                    "Tracked .venv",
                    not venv_tracked,
                    ".venv takip edilmiyor."
                    if not venv_tracked
                    else ".venv Git tarafından takip ediliyor.",
                ),
                self._optional(
                    "AutoGit config",
                    "Geçerli." if config_exists else None,
                    "Varsayılanlar kullanılıyor.",
                ),
            ]
        )

        changed_files = self.git.get_changed_files()
        tracked_paths = [item.path for item in changed_files]

        findings = SecretScanner().scan_files(
            self.root,
            tracked_paths,
            self.config.security.max_file_size_kb,
        )

        checks.append(
            self._check(
                "Secret taraması",
                not findings,
                "Şüpheli secret yok."
                if not findings
                else "Şüpheli secret bulundu.",
            )
        )

        if self.config.auto_push and remote_url is None:
            checks.append(
                DoctorCheck(
                    "Auto push",
                    CheckState.ERROR,
                    "Auto push açık ancak remote yok.",
                )
            )

        return DoctorReport(checks)

    @staticmethod
    def _check(
        name: str,
        ok: bool,
        detail: str,
    ) -> DoctorCheck:
        return DoctorCheck(
            name,
            CheckState.PASS if ok else CheckState.ERROR,
            detail,
        )

    @staticmethod
    def _optional(
        name: str,
        value: str | None,
        missing_detail: str,
    ) -> DoctorCheck:
        if value:
            return DoctorCheck(
                name,
                CheckState.PASS,
                value,
            )

        return DoctorCheck(
            name,
            CheckState.WARNING,
            missing_detail,
        )