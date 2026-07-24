"""Yapılandırılmış kalite kontrollerini çalıştırır."""

from __future__ import annotations

import shlex
from pathlib import Path

from autogit.config import AutoGitConfig
from autogit.domain.exceptions import QualityCheckFailedError
from autogit.domain.models import QualityCheck, QualityCheckResult
from autogit.infrastructure.command_runner import CommandRunner


class QualityService:
    def __init__(self, root: Path, config: AutoGitConfig, runner: CommandRunner) -> None:
        self.root = root
        self.config = config
        self.runner = runner

    def run(self) -> list[QualityCheckResult]:
        checks = [
            QualityCheck("Test", self.config.test.command, self.config.run_tests),
            QualityCheck("Lint", self.config.lint.command, self.config.run_lint),
            QualityCheck("Type check", self.config.type_check.command, self.config.run_type_check),
        ]
        results: list[QualityCheckResult] = []
        for check in checks:
            if not check.enabled:
                continue
            result = self.runner.run(shlex.split(check.command, posix=False), self.root)
            item = QualityCheckResult(check, result.exit_code, result.duration_seconds, result.output)
            results.append(item)
            if not item.succeeded:
                summary = item.output[-500:] if item.output else "Çıktı alınamadı."
                raise QualityCheckFailedError(
                    f"{check.name} kontrolü başarısız (exit code {item.exit_code}): {summary}"
                )
        return results

