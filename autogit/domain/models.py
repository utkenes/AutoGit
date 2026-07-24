"""Katmanlar arasında taşınan yalın, tip güvenli veri modelleri."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class FileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    UNTRACKED = "untracked"
    STAGED = "staged"


class CheckState(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ChangedFile:
    path: Path
    status: FileStatus
    staged: bool = False


@dataclass(frozen=True)
class GitStatus:
    changed_files: list[ChangedFile] = field(default_factory=list)


@dataclass(frozen=True)
class CommitContext:
    files: list[ChangedFile]
    diff_stat: str
    diff_preview: str


@dataclass(frozen=True)
class CommitResult:
    message: str
    commit_hash: str
    staged_files: list[Path]


@dataclass(frozen=True)
class PushResult:
    pushed: bool
    detail: str


@dataclass(frozen=True)
class QualityCheck:
    name: str
    command: str
    enabled: bool


@dataclass(frozen=True)
class QualityCheckResult:
    check: QualityCheck
    exit_code: int
    duration_seconds: float
    output: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class SecretFinding:
    path: Path
    line_number: int
    secret_type: str
    masked_value: str


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    state: CheckState
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    checks: list[DoctorCheck]


@dataclass(frozen=True)
class WatchEvent:
    path: Path
    event_type: str

