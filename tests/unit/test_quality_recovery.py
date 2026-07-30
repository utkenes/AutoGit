from pathlib import Path

import pytest

from autogit.application.quality_recovery_service import (
    QualityFailureAnalyzer,
    QualityRecoveryService,
)
from autogit.domain.exceptions import QualityCheckFailedError
from autogit.infrastructure.command_runner import CommandResult


class SuccessfulRunner:
    def run(self, command: list[str], cwd: Path) -> CommandResult:
        return CommandResult(command, 0, "fixed", "", 0.1)


def test_ruff_failure_has_low_risk_fix() -> None:
    suggestions = QualityFailureAnalyzer().analyze(QualityCheckFailedError("Lint failed: ruff I001"))
    assert suggestions[0].command == ("python", "-m", "ruff", "check", ".", "--fix")
    assert suggestions[0].auto_fixable


def test_test_failure_has_no_automatic_fix() -> None:
    assert QualityFailureAnalyzer().analyze(QualityCheckFailedError("Test failed: assertion")) == []


def test_recovery_applies_only_once(tmp_path: Path) -> None:
    service = QualityRecoveryService(tmp_path, SuccessfulRunner())  # type: ignore[arg-type]
    suggestion = service.suggestions(QualityCheckFailedError("Lint failed: ruff F401"))[0]
    assert service.apply(suggestion, 0, 1) == 1
    with pytest.raises(QualityCheckFailedError):
        service.apply(suggestion, 1, 1)
