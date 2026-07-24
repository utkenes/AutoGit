"""Repository durumunu tek bir okunabilir veri sözlüğüne çevirir."""

from __future__ import annotations

from autogit.config import AutoGitConfig, config_path
from autogit.infrastructure.git_service import GitService


class StatusService:
    def __init__(self, git: GitService, config: AutoGitConfig) -> None:
        self.git = git
        self.config = config

    def get(self) -> dict[str, object]:
        root = self.git.get_repository_root()
        files = self.git.get_changed_files()
        return {
            "Repository root": str(root),
            "Aktif branch": self.git.get_current_branch() or "Yok",
            "Remote URL": self.git.get_remote_url() or "Yok",
            "Upstream": self.git.get_upstream_branch() or "Yok",
            "Değişiklikler": [f"{item.status.value}: {item.path}" for item in files] or ["Temiz"],
            "Staged": [str(item.path) for item in self.git.get_staged_files()] or ["Yok"],
            "Son commit": self.git.get_last_commit() or "Yok",
            "Auto push": "Açık" if self.config.auto_push else "Kapalı",
            "Test": "Açık" if self.config.run_tests else "Kapalı",
            "Lint": "Açık" if self.config.run_lint else "Kapalı",
            "Secret scanning": "Açık" if self.config.security.scan_secrets else "Kapalı",
            "Debounce": f"{self.config.debounce_seconds} saniye",
            "Yapılandırma": str(config_path(root)),
        }

