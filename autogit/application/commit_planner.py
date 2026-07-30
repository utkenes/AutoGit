"""Deterministic grouping of changed files into reviewable commits."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from autogit.domain.models import ChangedFile, CommitGroup, FileStatus


class CommitPlanner:
    """Prefer a small number of clear groups over aggressive splitting."""

    def plan(self, files: list[ChangedFile]) -> list[CommitGroup]:
        buckets: dict[tuple[str, str | None, str], list[ChangedFile]] = defaultdict(list)
        for file in files:
            commit_type, scope, reason = self._classify(file)
            buckets[(commit_type, scope, reason)].append(file)
        groups: list[CommitGroup] = []
        for (commit_type, scope, reason), grouped_files in buckets.items():
            message = self._message(commit_type, scope, reason)
            groups.append(CommitGroup(tuple(grouped_files), message, commit_type, scope, reason))
        return groups

    def _classify(self, file: ChangedFile) -> tuple[str, str | None, str]:
        path = file.path
        normalized = path.as_posix().lower()
        name = path.name.lower()
        if self._is_test(normalized, name):
            return "test", self._test_scope(path), "cover changed behavior"
        if normalized.startswith("docs/") or name.startswith(("readme", "changelog")):
            return "docs", "readme" if name.startswith("readme") else None, "document changes"
        if self._is_configuration(normalized, name):
            return "chore", "packaging" if name in {"pyproject.toml", "package.json"} else "config", "update configuration"
        scope = self._source_scope(path)
        if any(word in normalized for word in ("fix", "bug", "error", "exception", "validation")):
            return "fix", scope, "fix changed behavior"
        if file.status in {FileStatus.ADDED, FileStatus.UNTRACKED}:
            return "feat", scope, "add new functionality"
        return "refactor", scope, "update implementation"

    @staticmethod
    def _is_test(normalized: str, name: str) -> bool:
        return normalized.startswith(("tests/", "test/")) or name.startswith("test_") or ".test." in name or ".spec." in name

    @staticmethod
    def _is_configuration(normalized: str, name: str) -> bool:
        return normalized.startswith(".github/") or name in {
            "pyproject.toml", "package.json", "package-lock.json", "poetry.lock", "uv.lock", "tox.ini", ".gitignore",
        }

    @staticmethod
    def _source_scope(path: Path) -> str | None:
        if path.suffix:
            return path.stem.replace("_service", "") or None
        return path.parts[0] if path.parts else None

    @staticmethod
    def _test_scope(path: Path) -> str | None:
        stem = path.stem.removeprefix("test_")
        return stem.replace("_service", "") or None

    @staticmethod
    def _message(commit_type: str, scope: str | None, reason: str) -> str:
        subject = reason[0].lower() + reason[1:]
        prefix = f"{commit_type}({scope})" if scope else commit_type
        return f"{prefix}: {subject}"
