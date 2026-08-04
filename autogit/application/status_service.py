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
        state = self.git.get_repository_state()
        locks = self.git.get_operation_locks()
        sync = self.git.get_ahead_behind()
        return {
            "Repository root": str(root),
            "Aktif branch": self.git.get_current_branch() or "Yok",
            "HEAD": "Mevcut" if state.has_head else "Initial commit bekliyor",
            "Remote URL": self.git.get_remote_url() or "Yok",
            "Upstream": self.git.get_upstream_branch() or "Yok",
            "Değişiklikler": [f"{item.status.value}: {item.path}" for item in files] or ["Temiz"],
            "Staged": [str(item.path) for item in self.git.get_staged_files()] or ["Yok"],
            "Untracked": [str(item.path) for item in self.git.get_untracked_files()] or ["Yok"],
            "Ahead/behind": f"{sync[1]}/{sync[0]}" if sync else "Yok",
            "Git operation": ", ".join(
                name
                for name, active in (
                    ("merge", state.merge_in_progress),
                    ("rebase", state.rebase_in_progress),
                    ("cherry-pick", state.cherry_pick_in_progress),
                    ("revert", state.revert_in_progress),
                )
                if active
            ) or "Yok",
            "Git locks": [f"{lock.path.name} ({lock.age_description})" for lock in locks] or ["Yok"],
            "Son commit": self.git.get_last_commit() or "Yok",
            "Auto push": "Açık" if self.config.auto_push else "Kapalı",
            "Test": "Açık" if self.config.run_tests else "Kapalı",
            "Lint": "Açık" if self.config.run_lint else "Kapalı",
            "Secret scanning": "Açık" if self.config.security.scan_secrets else "Kapalı",
            "Debounce": f"{self.config.debounce_seconds} saniye",
            "Yapılandırma": str(config_path(root)),
            "Son AutoGit run": "Var" if (root / ".autogit" / "last-run.json").exists() else "Yok",
        }
