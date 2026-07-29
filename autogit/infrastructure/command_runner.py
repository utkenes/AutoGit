"""Kabuk kullanmadan dış komut çalıştırma altyapısı."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def output(self) -> str:
        return self.stdout.strip() or self.stderr.strip()


class CommandRunner:
    """Komutları platformdan bağımsız liste biçiminde çalıştırır."""

    def run_bytes(self, command: list[str], cwd: Path, timeout: float | None = None) -> CommandResult:
        """Run a command preserving byte output for Git's NUL-delimited modes."""
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command, cwd=cwd, capture_output=True, timeout=timeout, shell=False, check=False
            )
            return CommandResult(
                command=command,
                exit_code=completed.returncode,
                stdout=completed.stdout.decode("utf-8", errors="surrogateescape"),
                stderr=completed.stderr.decode("utf-8", errors="replace"),
                duration_seconds=time.monotonic() - started,
            )
        except FileNotFoundError as error:
            return CommandResult(command, 127, "", str(error), time.monotonic() - started)
        except subprocess.TimeoutExpired as error:
            output = error.stdout.decode("utf-8", errors="surrogateescape") if error.stdout else ""
            return CommandResult(command, 124, output, "Command timed out.", time.monotonic() - started)

    def run(self, command: list[str], cwd: Path, timeout: float | None = None) -> CommandResult:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
                check=False,
            )
            return CommandResult(
                command=command,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_seconds=time.monotonic() - started,
            )
        except FileNotFoundError as error:
            return CommandResult(command, 127, "", str(error), time.monotonic() - started)
        except subprocess.TimeoutExpired as error:
            output = (error.stdout or "") if isinstance(error.stdout, str) else ""
            return CommandResult(command, 124, output, "Komut zaman aşımına uğradı.", time.monotonic() - started)
