"""Guided repository and optional quality-check setup helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from autogit.config import config_path, configure_quality_command, write_default_config
from autogit.domain.exceptions import ConfigurationError
from autogit.infrastructure.git_service import GitService


@dataclass(frozen=True)
class QualitySuggestion:
    setting: str
    command: str
    message: str


class SetupService:
    """Performs explicit, user-approved setup actions only."""

    def __init__(self, root: Path, git: GitService) -> None:
        self.root = root
        self.git = git

    def create_repository(self, remote_url: str | None = None) -> Path:
        self.git.initialize_repository()
        self.git.set_main_branch()
        if remote_url:
            self.add_remote(remote_url)
        return self.git.get_repository_root()

    def add_remote(self, remote_url: str) -> None:
        if not self._is_remote_url(remote_url):
            raise ConfigurationError("Geçerli bir repository URL'si girin.")
        self.git.add_remote(remote_url)

    def ensure_config(self) -> bool:
        if config_path(self.root).exists():
            return False
        write_default_config(self.root)
        return True

    def enable(self, setting: str, command: str) -> None:
        configure_quality_command(self.root, setting, command)

    def detect_quality_suggestions(self) -> list[QualitySuggestion]:
        suggestions: list[QualitySuggestion] = []
        if self._has_python_tests():
            suggestions.append(QualitySuggestion("run_tests", "python -m pytest", "Python test yapısı bulundu."))
        package = self._package_json()
        scripts = package.get("scripts", {}) if package else {}
        if isinstance(scripts, dict) and scripts.get("test"):
            suggestions.append(QualitySuggestion("run_tests", "npm test", "JavaScript test komutu bulundu."))
        if self._has_python_lint():
            suggestions.append(QualitySuggestion("run_lint", "python -m ruff check .", "Ruff yapılandırması bulundu."))
        if isinstance(scripts, dict) and scripts.get("lint"):
            suggestions.append(QualitySuggestion("run_lint", "npm run lint", "JavaScript lint komutu bulundu."))
        return suggestions

    def _has_python_tests(self) -> bool:
        return any((self.root / path).exists() for path in ("tests", "test", "pytest.ini", "tox.ini")) or self._pyproject_contains("pytest")

    def _has_python_lint(self) -> bool:
        return self._pyproject_contains("ruff") or (self.root / ".flake8").exists()

    def _pyproject_contains(self, token: str) -> bool:
        path = self.root / "pyproject.toml"
        try:
            return token.lower() in path.read_text(encoding="utf-8").lower()
        except OSError:
            return False

    def _package_json(self) -> dict[str, object] | None:
        try:
            value = json.loads((self.root / "package.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _is_remote_url(url: str) -> bool:
        return url.startswith(("https://", "http://", "ssh://", "git@")) and len(url) > 10
