"""Protocols for replaceable infrastructure dependencies."""

from pathlib import Path
from typing import Protocol

from autogit.domain.models import CommitContext, SecretFinding


class CommitMessageProvider(Protocol):
    """Produces a Conventional Commit-compatible message."""

    def generate(self, context: CommitContext) -> str:
        """Return a commit message for the staged context."""


class SecretScannerProtocol(Protocol):
    """Scans supplied content instead of reading arbitrary worktree paths."""

    def scan_content(self, *, path: Path, content: bytes) -> list[SecretFinding]:
        """Return masked findings for the supplied bytes."""

    def is_binary_content(self, content: bytes) -> bool:
        """Return whether content must be skipped as binary."""
