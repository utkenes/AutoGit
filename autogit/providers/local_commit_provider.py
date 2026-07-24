"""Harici servis gerektirmeyen yerel commit mesajı sağlayıcısı."""

from __future__ import annotations

import re
from collections.abc import Sequence

from autogit.domain.exceptions import CommitMessageError
from autogit.domain.models import ChangedFile, CommitContext, FileStatus

VALID_PREFIXES = {
    "feat", "fix", "docs", "style", "refactor", "test", "build", "ci", "chore", "perf", "revert"
}


class LocalCommitMessageProvider:
    """Dosya yollarına göre kısa ve deterministik Conventional Commit üretir."""

    def generate(self, context: CommitContext) -> str:
        if not context.files:
            raise CommitMessageError("Commit mesajı için değişiklik bilgisi bulunamadı.")
        prefix = self._prefix(context)
        subject = self._subject(context.files)
        message = f"{prefix}: {subject}"
        if not self.is_valid(message):
            raise CommitMessageError("Üretilen commit mesajı Conventional Commits biçiminde değil.")
        return message

    @staticmethod
    def is_valid(message: str) -> bool:
        return bool(re.fullmatch(r"(?:" + "|".join(VALID_PREFIXES) + r")(?:\([^)]+\))?: .+", message))

    def _prefix(self, context: CommitContext) -> str:
        paths = [file.path for file in context.files]
        names = [path.name.lower() for path in paths]
        suffixes = {path.suffix.lower() for path in paths}
        if all(name.startswith("test_") or "test" in path.parts for name, path in zip(names, paths, strict=True)):
            return "test"
        if any(path.suffix.lower() in {".md", ".rst"} for path in paths):
            return "docs"
        if any(".github" in path.parts for path in paths):
            return "ci"
        if any(name in {"pyproject.toml", ".autogit.toml"} for name in names):
            return "chore"
        if any(status.status is FileStatus.ADDED for status in context.files) and suffixes:
            return "feat"
        if any("fix" in name or "bug" in name for name in names):
            return "fix"
        return "chore"

    @staticmethod
    def _subject(files: Sequence[ChangedFile]) -> str:
        paths = [file.path for file in files]
        if len(paths) == 1:
            return f"update {paths[0].name}"
        return f"update {len(paths)} files"
