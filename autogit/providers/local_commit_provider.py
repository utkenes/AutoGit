"""Harici servis gerektirmeyen yerel commit mesajı sağlayıcısı."""

from __future__ import annotations

import re
from collections.abc import Sequence

from autogit.domain.exceptions import CommitMessageError
from autogit.domain.models import ChangedFile, CommitContext, FileStatus

VALID_PREFIXES = {
    "feat", "fix", "docs", "style", "refactor", "test", "build", "ci", "chore", "perf", "revert"
}
MAX_MESSAGE_LENGTH = 72
_MESSAGE_PATTERN = re.compile(
    r"(?P<type>" + "|".join(sorted(VALID_PREFIXES)) + r")(?:\((?P<scope>[^()\s\x00-\x1f]+)\))?: (?P<subject>[^\r\n\x00-\x1f].*)"
)


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

    @classmethod
    def validation_error(cls, message: str) -> str | None:
        """Return a safe, user-facing reason when a message is invalid."""
        if not message:
            return "Commit mesajı boş olamaz."
        if len(message) > MAX_MESSAGE_LENGTH:
            return f"Commit mesajı en fazla {MAX_MESSAGE_LENGTH} karakter olabilir."
        if any(ord(character) < 32 or ord(character) == 127 for character in message):
            return "Commit mesajı satır sonu veya kontrol karakteri içeremez."
        match = _MESSAGE_PATTERN.fullmatch(message)
        if match is None:
            allowed = ", ".join(sorted(VALID_PREFIXES))
            return f"Biçim type: subject veya type(scope): subject olmalı. Türler: {allowed}."
        subject = match.group("subject").strip()
        if not subject:
            return "Commit mesajı konusu boş olamaz."
        if subject.endswith("."):
            return "Commit mesajı konusu nokta ile bitmemeli."
        return None

    @classmethod
    def is_valid(cls, message: str) -> bool:
        return cls.validation_error(message) is None

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
