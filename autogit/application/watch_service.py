"""Debounce kurallarıyla dosya olaylarını tek commit akışında birleştirir."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from autogit.application.commit_service import CommitService
from autogit.config import AutoGitConfig
from autogit.domain.exceptions import AutoGitError
from autogit.domain.models import WatchEvent
from autogit.infrastructure.file_watcher import FileWatcher


class WatchService:
    def __init__(
        self, root: Path, config: AutoGitConfig, commit_service: CommitService, logger: logging.Logger
    ) -> None:
        self.root = root
        self.config = config
        self.commit_service = commit_service
        self.logger = logger
        self._last_event: float | None = None
        self._pending = False
        self._committing = False
        self._lock = threading.Lock()

    def run(self) -> None:
        watcher = FileWatcher(self.root, self.config.watch.ignored_paths, self._record_event)
        watcher.start()
        try:
            while True:
                time.sleep(self.config.check_interval_seconds)
                self._process_if_ready()
        except KeyboardInterrupt:
            self.logger.info("Watcher Ctrl+C ile güvenle kapatıldı.")
        finally:
            watcher.stop()

    def _record_event(self, event: WatchEvent) -> None:
        with self._lock:
            self._last_event = time.monotonic()
            self._pending = True
        self.logger.info("Dosya olayı: %s %s", event.event_type, event.path)

    def _process_if_ready(self) -> None:
        with self._lock:
            ready = (
                self._pending
                and not self._committing
                and self._last_event is not None
                and time.monotonic() - self._last_event >= self.config.debounce_seconds
            )
            if not ready:
                return
            self._pending = False
            self._committing = True
        try:
            self.commit_service.execute()
        except AutoGitError as error:
            self.logger.error("Otomatik commit başarısız: %s", error)
        finally:
            with self._lock:
                self._committing = False

