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
    def __init__(self, root: Path, git: GitService, config: AutoGitConfig, runner: CommandRunner) -> None:
        self.root = root
        self.git = git
        self.config = config
        self.runner = runner

    def run(self) -> DoctorReport:
        checks: list[DoctorCheck] = []
        git_version = self.runner.run(["git", "--version"], self.root)
        checks.append(self._check("Git", git_version.exit_code == 0, git_version.output))
        version_ok = sys.version_info >= (3, 12)
        checks.append(self._check("Python 3.12+", version_ok, sys.version.split()[0]))
        is_repo = self.git.is_repository()
        checks.append(self._check("Git repository", is_repo, "Repository bulundu." if is_repo else "Repository bulunamadı."))
        if not is_repo:
            return DoctorReport(checks)
        checks.extend(
            [
                self._check("Aktif branch", self.git.get_current_branch() is not None, self.git.get_current_branch() or "Yok"),
                self._warning("Remote", self.git.get_remote_url() or "Remote tanımlı değil."),
                self._warning("Upstream", self.git.get_upstream_branch() or "Upstream tanımlı değil."),
                self._warning("Git kullanıcı adı", self.git.get_git_user_name() or "Tanımlı değil."),
                self._warning("Git email", self.git.get_git_user_email() or "Tanımlı değil."),
                self._warning(".gitignore", ".gitignore mevcut." if (self.root / ".gitignore").exists() else ".gitignore yok."),
                self._check("Tracked .env", not self.git.is_file_tracked(Path(".env")), ".env takip edilmiyor."),
                self._check("Tracked .venv", not self.git.is_file_tracked(Path(".venv")), ".venv takip edilmiyor."),
                self._warning("AutoGit config", "Geçerli." if config_path(self.root).exists() else "Varsayılanlar kullanılıyor."),
            ]
        )
        tracked = [item.path for item in self.git.get_changed_files()]
        findings = SecretScanner().scan_files(self.root, tracked, self.config.security.max_file_size_kb)
        checks.append(self._check("Secret taraması", not findings, "Şüpheli secret yok." if not findings else "Şüpheli secret bulundu."))
        if self.config.auto_push and not self.git.get_remote_url():
            checks.append(DoctorCheck("Auto push", CheckState.ERROR, "Auto push açık ancak remote yok."))
        return DoctorReport(checks)

    @staticmethod
    def _check(name: str, ok: bool, detail: str) -> DoctorCheck:
        return DoctorCheck(name, CheckState.PASS if ok else CheckState.ERROR, detail)

    @staticmethod
    def _warning(name: str, detail: str) -> DoctorCheck:
        return DoctorCheck(name, CheckState.PASS if "değil" not in detail.lower() and "yok" not in detail.lower() else CheckState.WARNING, detail)

