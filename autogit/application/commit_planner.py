"""Deterministic, context-aware grouping of changes into safe commits."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from autogit.domain.models import ChangedFile, CommitGroup, FileStatus


class CommitPlanner:
    """Prefer clear, dependency-ordered groups over aggressive splitting."""

    _priority = {"feat": 1, "fix": 2, "refactor": 3, "test": 4, "docs": 5, "chore": 6, "ci": 7}

    def __init__(self, root: Path | None = None) -> None:
        self.root = root

    def plan(self, files: list[ChangedFile]) -> list[CommitGroup]:
        buckets: dict[tuple[str, str | None, str], list[ChangedFile]] = defaultdict(list)
        for file in files:
            commit_type, scope, reason = self._classify(file)
            buckets[(commit_type, scope, reason)].append(file)
        groups = [
            CommitGroup(tuple(grouped), self._message(kind, scope, reason), kind, scope, reason)
            for (kind, scope, reason), grouped in buckets.items()
        ]
        return sorted(
            groups,
            key=lambda group: (
                self._priority.get(group.commit_type, 99),
                group.scope or "",
                min(file.path.as_posix() for file in group.files),
            ),
        )

    def _classify(self, file: ChangedFile) -> tuple[str, str | None, str]:
        path = file.path
        normalized = path.as_posix().lower()
        name = path.name.lower()
        context = self._safe_context(path)
        if self._is_test(normalized, name):
            action = f"cover {context} behavior" if context else "cover changed behavior"
            return "test", self._test_scope(path), action
        if normalized.startswith("docs/") or name.startswith(("readme", "changelog")):
            action = f"document {context} usage" if context else "document changes"
            return "docs", "readme" if name.startswith("readme") else None, action
        if normalized.startswith(".github/"):
            return "ci", "github", "update automation"
        if self._is_configuration(normalized, name):
            config_scope = "packaging" if name in {"pyproject.toml", "package.json"} else "config"
            return "chore", config_scope, "update configuration"
        scope: str | None = self._source_scope(path)
        if any(word in normalized for word in ("fix", "bug", "error", "exception", "validation")):
            return "fix", scope, "fix changed behavior"
        if file.status in {FileStatus.ADDED, FileStatus.UNTRACKED}:
            action = f"add {context} function" if context else "add new functionality"
            return "feat", scope, action
        return "refactor", scope, "update implementation"

    def _safe_context(self, path: Path) -> str | None:
        name = path.stem.removeprefix("test_")
        if name and path.name.lower().startswith("test_"):
            return self._identifier_words(name)
        if self.root is None or path.suffix.lower() not in {".py", ".js", ".ts", ".tsx"}:
            return "usage" if path.name.lower().startswith("readme") else None
        try:
            text = (self.root / path).read_text(encoding="utf-8", errors="replace")[:32_000]
        except OSError:
            return None
        match = re.search(r"^\s*(?:def|class|function|export\s+function)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.MULTILINE)
        return self._identifier_words(match.group(1)) if match else None

    @staticmethod
    def _identifier_words(value: str) -> str | None:
        words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").strip().lower()
        return words if words and all(part.isidentifier() or part.isdigit() for part in words.split()) else None

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
        return path.stem.replace("_service", "") if path.suffix else (path.parts[0] if path.parts else None)

    @staticmethod
    def _test_scope(path: Path) -> str | None:
        return path.stem.removeprefix("test_").replace("_service", "") or None

    @staticmethod
    def _message(commit_type: str, scope: str | None, reason: str) -> str:
        prefix = f"{commit_type}({scope})" if scope else commit_type
        subject = reason.lower().rstrip(".")
        message = f"{prefix}: {subject}"
        return message[:72].rstrip(" .")
