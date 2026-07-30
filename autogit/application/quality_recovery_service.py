"""Analyze failed quality checks and run only approved low-risk fixes."""

from __future__ import annotations

from pathlib import Path

from autogit.domain.exceptions import QualityCheckFailedError
from autogit.domain.models import FixSuggestion
from autogit.infrastructure.command_runner import CommandRunner


class QualityFailureAnalyzer:
    """Maps known tool failures to conservative remediation suggestions."""

    def analyze(self, error: QualityCheckFailedError) -> list[FixSuggestion]:
        output = str(error)
        if "Lint" in output and ("ruff" in output.lower() or any(code in output for code in ("I001", "F401", "UP", "SIM"))):
            return [
                FixSuggestion(
                    "Ruff lint düzeltmesi",
                    "Ruff import ve düşük riskli lint sorunlarını düzeltebilir.",
                    ("python", "-m", "ruff", "check", ".", "--fix"),
                    "low",
                    True,
                    ("lint", "tests"),
                )
            ]
        if "Lint" in output and "eslint" in output.lower():
            return [
                FixSuggestion(
                    "ESLint düzeltmesi",
                    "ESLint'in önerdiği güvenli düzeltmeleri uygulayabilir.",
                    ("npm", "run", "lint", "--", "--fix"),
                    "low",
                    True,
                    ("lint", "tests"),
                )
            ]
        if "Lint" in output and "biome" in output.lower():
            return [
                FixSuggestion(
                    "Biome düzeltmesi",
                    "Biome biçimlendirme ve lint düzeltmelerini uygulayabilir.",
                    ("npx", "biome", "check", "--write", "."),
                    "low",
                    True,
                    ("lint", "tests"),
                )
            ]
        return []


class SafeFixExecutor:
    """Executes an explicit allow-list of non-destructive quality commands."""

    def __init__(self, root: Path, runner: CommandRunner) -> None:
        self.root = root
        self.runner = runner

    def apply(self, suggestion: FixSuggestion) -> None:
        if not suggestion.auto_fixable or suggestion.risk_level != "low" or not suggestion.command:
            raise QualityCheckFailedError("Bu kalite hatası için otomatik düzeltme güvenli değil.")
        result = self.runner.run(list(suggestion.command), self.root)
        if result.exit_code != 0:
            raise QualityCheckFailedError(f"Otomatik düzeltme başarısız: {result.output}")


class QualityRecoveryService:
    """Coordinates one approved fix attempt per workflow."""

    def __init__(self, root: Path, runner: CommandRunner) -> None:
        self.analyzer = QualityFailureAnalyzer()
        self.executor = SafeFixExecutor(root, runner)

    def suggestions(self, error: QualityCheckFailedError) -> list[FixSuggestion]:
        return self.analyzer.analyze(error)

    def apply(self, suggestion: FixSuggestion, attempts: int, max_attempts: int) -> int:
        if attempts >= max_attempts:
            raise QualityCheckFailedError("Otomatik düzeltme deneme sınırına ulaştı.")
        self.executor.apply(suggestion)
        return attempts + 1
