"""TOML dosyasından güvenli AutoGit yapılandırması yüklenir."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from autogit.domain.exceptions import ConfigurationError

DEFAULT_CONFIG = """debounce_seconds = 60
check_interval_seconds = 5
auto_push = false
run_tests = true
run_lint = true
run_type_check = false
commit_message_provider = "local"

[test]
command = "python -m pytest"

[lint]
command = "python -m ruff check ."

[type_check]
command = "python -m mypy ."

[security]
block_env_files = true
scan_secrets = true
max_file_size_kb = 512
scan_diff_only = false

[watch]
ignored_paths = [".git", ".autogit", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build", "node_modules"]
"""


class CommandConfig(BaseModel):
    command: str = Field(min_length=1)


class SecurityConfig(BaseModel):
    block_env_files: bool = True
    scan_secrets: bool = True
    max_file_size_kb: int = Field(default=512, ge=1, le=10_240)
    scan_diff_only: bool = False


class WatchConfig(BaseModel):
    ignored_paths: list[str] = Field(default_factory=list)


class AutoGitConfig(BaseModel):
    debounce_seconds: int = Field(default=60, ge=1, le=86_400)
    check_interval_seconds: int = Field(default=5, ge=1, le=3_600)
    auto_push: bool = False
    run_tests: bool = True
    run_lint: bool = True
    run_type_check: bool = False
    commit_message_provider: str = "local"
    test: CommandConfig = Field(default_factory=lambda: CommandConfig(command="python -m pytest"))
    lint: CommandConfig = Field(
        default_factory=lambda: CommandConfig(command="python -m ruff check .")
    )
    type_check: CommandConfig = Field(
        default_factory=lambda: CommandConfig(command="python -m mypy .")
    )
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    watch: WatchConfig = Field(default_factory=WatchConfig)

    @field_validator("commit_message_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value != "local":
            raise ValueError("Bu sürüm yalnızca 'local' commit mesajı sağlayıcısını destekler.")
        return value


def config_path(repository_root: Path) -> Path:
    return repository_root / ".autogit.toml"


def load_config(repository_root: Path) -> AutoGitConfig:
    path = config_path(repository_root)
    if not path.exists():
        return AutoGitConfig()
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
        return AutoGitConfig.model_validate(data)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
        raise ConfigurationError(f"Yapılandırma geçersiz: {path}. {error}") from error


def write_default_config(repository_root: Path) -> Path:
    path = config_path(repository_root)
    if not path.exists():
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return path


def update_config(repository_root: Path, key: str, raw_value: str) -> AutoGitConfig:
    """Desteklenen üst seviye bir değeri doğrulayıp dosyaya atomik biçimde yazar."""
    config = load_config(repository_root)
    supported = {
        "debounce_seconds": int,
        "check_interval_seconds": int,
        "auto_push": bool,
        "run_tests": bool,
        "run_lint": bool,
        "run_type_check": bool,
    }
    if key not in supported:
        choices = ", ".join(supported)
        raise ConfigurationError(f"Bilinmeyen ayar: {key}. Kullanılabilir ayarlar: {choices}")
    value: Any
    if supported[key] is bool:
        lowered = raw_value.lower()
        if lowered not in {"true", "false"}:
            raise ConfigurationError("Boolean değer yalnızca true veya false olabilir.")
        value = lowered == "true"
    else:
        try:
            value = int(raw_value)
        except ValueError as error:
            raise ConfigurationError(f"{key} için sayısal değer gerekli.") from error
    try:
        updated = config.model_copy(update={key: value})
        updated = AutoGitConfig.model_validate(updated.model_dump())
    except ValidationError as error:
        raise ConfigurationError(str(error)) from error
    lines = DEFAULT_CONFIG.splitlines()
    prefix = f"{key} = "
    replacement = f"{key} = {str(value).lower() if isinstance(value, bool) else value}"
    content = "\n".join(replacement if line.startswith(prefix) else line for line in lines) + "\n"
    config_path(repository_root).write_text(content, encoding="utf-8")
    return updated

