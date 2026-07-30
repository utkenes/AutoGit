"""A conservative, process-aware lock for one AutoGit workflow per repository."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from autogit.domain.exceptions import GitOperationLockedError


class AutoGitOperationLock:
    """Create an exclusive lock without touching Git's own lock files."""

    def __init__(self, root: Path) -> None:
        self.path = root / ".autogit" / "autogit.lock"
        self._held = False

    def __enter__(self) -> AutoGitOperationLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._remove_stale_lock()
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise GitOperationLockedError("Bu repository için başka bir AutoGit işlemi çalışıyor.") from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump({"pid": os.getpid(), "started_at": datetime.now(UTC).isoformat()}, file)
        self._held = True
        return self

    def __exit__(self, *_: object) -> None:
        if self._held:
            with suppress(FileNotFoundError):
                self.path.unlink()
            self._held = False

    def _remove_stale_lock(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(data["pid"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise GitOperationLockedError("AutoGit lock dosyası okunamadı; güvenlik için işlem durduruldu.") from error
        if self._is_process_running(pid):
            return
        try:
            self.path.unlink()
        except OSError as error:
            raise GitOperationLockedError("Eski AutoGit lock dosyası temizlenemedi.") from error

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        if pid <= 0:
            return False

    # Nested lock attempts happen inside the same AutoGit/Python process.
    # Avoid calling os.kill(current_pid, 0) on Windows.
        if pid == os.getpid():
            return True

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False

        return True