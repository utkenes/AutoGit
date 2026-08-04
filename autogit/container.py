"""Uygulama bileşenlerini tek yerde bağımlılık enjeksiyonu ile kurar."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from autogit.application.commit_planner import CommitPlanner
from autogit.application.commit_service import CommitService
from autogit.application.doctor_service import DoctorService
from autogit.application.quality_service import QualityService
from autogit.application.status_service import StatusService
from autogit.application.watch_service import WatchService
from autogit.config import AutoGitConfig, load_config
from autogit.infrastructure.command_runner import CommandRunner
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.logging_setup import create_logger
from autogit.infrastructure.secret_scanner import SecretScanner
from autogit.providers.local_commit_provider import LocalCommitMessageProvider


@dataclass(frozen=True)
class Container:
    root: Path
    config: AutoGitConfig
    git: GitService
    commit: CommitService
    planner: CommitPlanner
    status: StatusService
    doctor: DoctorService
    watch: WatchService


def build_container(working_directory: Path, *, read_only: bool = False) -> Container:
    runner = CommandRunner()
    preliminary_git = GitService(working_directory, runner)
    root = preliminary_git.get_repository_root()
    config = load_config(root)
    git = GitService(root, runner)
    logger = _read_only_logger(root) if read_only else create_logger(root)
    quality = QualityService(root, config, runner)
    commit = CommitService(root, config, git, SecretScanner(), quality, LocalCommitMessageProvider(), logger)
    return Container(
        root=root,
        config=config,
        git=git,
        commit=commit,
        planner=CommitPlanner(root, config),
        status=StatusService(git, config),
        doctor=DoctorService(root, git, config, runner),
        watch=WatchService(root, config, commit, logger),
    )


def _read_only_logger(root: Path) -> logging.Logger:
    """Return an in-memory logger for preview commands."""
    logger = logging.getLogger(f"autogit.preview.{root}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger
