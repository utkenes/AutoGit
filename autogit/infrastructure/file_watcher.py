"""Watchdog olaylarını repository içindeki güvenli yollarla sınırlar."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from autogit.domain.models import WatchEvent
from autogit.utils.paths import is_ignored, is_within_root


class _Handler(FileSystemEventHandler):
    def __init__(self, root: Path, ignored: list[str], callback: Callable[[WatchEvent], None]) -> None:
        self.root = root
        self.ignored = ignored
        self.callback = callback

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if not isinstance(event.src_path, str):
            return
        path = Path(event.src_path)
        if is_within_root(path, self.root) and not is_ignored(path, self.root, self.ignored):
            self.callback(WatchEvent(path, event.event_type))


class FileWatcher:
    def __init__(self, root: Path, ignored: list[str], callback: Callable[[WatchEvent], None]) -> None:
        self.observer = Observer()
        self.observer.schedule(_Handler(root, ignored, callback), str(root), recursive=True)

    def start(self) -> None:
        self.observer.start()

    def stop(self) -> None:
        self.observer.stop()
        self.observer.join(timeout=5)
