"""Conservative inspection of Git's own operation lock files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from autogit.domain.exceptions import RepositoryUnsafeError


@dataclass(frozen=True)
class GitLock:
    """A Git lock that AutoGit must report but never remove."""

    kind: str
    path: Path
    blocked_operation: str
    age_seconds: float

    @property
    def age_description(self) -> str:
        seconds = max(0, int(self.age_seconds))
        if seconds < 60:
            return "bir dakikadan kısa"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"yaklaşık {minutes} dakika"
        hours, minutes = divmod(minutes, 60)
        if hours < 48:
            return f"yaklaşık {hours} saat {minutes} dakika"
        days, hours = divmod(hours, 24)
        return f"yaklaşık {days} gün {hours} saat"


class GitLockInspector:
    """Classify Git locks without guessing whether they are stale."""

    _LOCKS = (
        ("index", "index.lock", "stage ve commit işlemlerini"),
        ("config", "config.lock", "repository yapılandırma işlemlerini"),
    )

    def find(self, git_directory: Path | None) -> list[GitLock]:
        if git_directory is None:
            return []
        locks: list[GitLock] = []
        for kind, name, blocked_operation in self._LOCKS:
            path = git_directory / name
            try:
                modified_at = path.stat().st_mtime
            except FileNotFoundError:
                continue
            except OSError:
                # A lock that cannot be inspected is still unsafe to ignore.
                modified_at = datetime.now(UTC).timestamp()
            locks.append(
                GitLock(
                    kind=kind,
                    path=path,
                    blocked_operation=blocked_operation,
                    age_seconds=datetime.now(UTC).timestamp() - modified_at,
                )
            )
        return locks

    def require_unlocked(self, git_directory: Path | None) -> None:
        locks = self.find(git_directory)
        if not locks:
            return
        details = "\n".join(self._message(lock) for lock in locks)
        raise RepositoryUnsafeError(details)

    @staticmethod
    def _message(lock: GitLock) -> str:
        return (
            f"Git {lock.kind} kilidi bulundu: {lock.path} (yaşı {lock.age_description}). "
            f"Bu kilit {lock.blocked_operation} engeller. Başka bir Git işlemi çalışıyor olabilir; "
            "çalışan Git süreçlerini kontrol edin. AutoGit lock dosyasını otomatik silmez. "
            f"Aktif bir işlem olmadığından eminseniz {lock.path} dosyasını manuel olarak kaldırabilirsiniz."
        )
