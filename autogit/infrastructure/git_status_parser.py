"""Parses Git's NUL-delimited porcelain status output without path quoting."""

from __future__ import annotations

from pathlib import Path

from autogit.domain.models import ChangedFile, FileStatus


class GitStatusParser:
    """Convert ``git status --porcelain=v1 -z`` bytes into domain models."""

    def parse(self, raw_output: bytes) -> list[ChangedFile]:
        records = raw_output.split(b"\0")
        changed: list[ChangedFile] = []
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if len(record) < 4:
                continue

            index_status = chr(record[0])
            worktree_status = chr(record[1])
            path = self._path(record[3:])
            status = self._to_status(index_status, worktree_status)
            old_path: Path | None = None
            if status in {FileStatus.RENAMED, FileStatus.COPIED} and index < len(records):
                old_path = self._path(records[index])
                index += 1
            changed.append(
                ChangedFile(
                    path=path,
                    status=status,
                    old_path=old_path,
                    staged=index_status not in {" ", "?"},
                    unstaged=worktree_status != " ",
                )
            )
        return changed

    @staticmethod
    def _path(value: bytes) -> Path:
        return Path(value.decode("utf-8", errors="surrogateescape"))

    @staticmethod
    def _to_status(index_status: str, worktree_status: str) -> FileStatus:
        code = index_status if index_status not in {" ", "?"} else worktree_status
        mapping = {
            "A": FileStatus.ADDED,
            "M": FileStatus.MODIFIED,
            "D": FileStatus.DELETED,
            "R": FileStatus.RENAMED,
            "C": FileStatus.COPIED,
            "?": FileStatus.UNTRACKED,
        }
        return mapping.get(code, FileStatus.MODIFIED)
