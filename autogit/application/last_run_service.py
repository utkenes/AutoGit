"""Persist and safely undo the last unpushed AutoGit workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from autogit.domain.exceptions import RepositoryUnsafeError
from autogit.domain.models import CommitResult
from autogit.infrastructure.git_service import GitService


@dataclass(frozen=True)
class LastRun:
    base_commit: str
    commit_hashes: tuple[str, ...]
    messages: tuple[str, ...]
    pushed: bool


class LastRunService:
    """Stores only local workflow metadata; it never records file contents."""

    def __init__(self, root: Path, git: GitService) -> None:
        self.root = root
        self.git = git
        self.path = root / ".autogit" / "last-run.json"

    def record(self, base_commit: str, results: list[CommitResult]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write(LastRun(base_commit, tuple(item.commit_hash for item in results), tuple(item.message for item in results), False))

    def mark_pushed(self) -> None:
        run = self.load()
        self._write(LastRun(run.base_commit, run.commit_hashes, run.messages, True))

    def load(self) -> LastRun:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return LastRun(str(data["base_commit"]), tuple(data["commit_hashes"]), tuple(data["messages"]), bool(data["pushed"]))
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise RepositoryUnsafeError("Geri alınabilecek bir AutoGit işlemi bulunamadı.") from error

    def validate_undo(self) -> LastRun:
        run = self.load()
        if run.pushed:
            raise RepositoryUnsafeError("Push edilmiş AutoGit commitleri güvenli olarak geri alınamaz.")
        if not run.commit_hashes or self.git.get_head() != run.commit_hashes[-1]:
            raise RepositoryUnsafeError("Son AutoGit işleminden sonra yeni commit oluştu; undo durduruldu.")
        changed = [file for file in self.git.get_changed_files() if not file.path.parts or file.path.parts[0] != ".autogit"]
        if changed:
            raise RepositoryUnsafeError("Working tree temiz değil; undo öncesinde değişiklikleri saklayın.")
        return run

    def undo(self, run: LastRun) -> None:
        self.git.reset_mixed(run.base_commit)
        self.path.unlink(missing_ok=True)

    def _write(self, run: LastRun) -> None:
        self.path.write_text(
            json.dumps({"base_commit": run.base_commit, "commit_hashes": run.commit_hashes, "messages": run.messages, "pushed": run.pushed}, indent=2),
            encoding="utf-8",
        )
