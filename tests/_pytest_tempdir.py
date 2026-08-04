"""Keep pytest's temporary repositories out of the project workspace."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

import pytest

_MANAGED_BASETEMP_ENV = "AUTOGIT_PYTEST_MANAGED_BASETEMP"


def pytest_load_initial_conftests(early_config: pytest.Config, parser: pytest.Parser, args: list[str]) -> None:
    """Set an external base before pytest initializes ``tmp_path``."""
    if any(argument == "--basetemp" or argument.startswith("--basetemp=") for argument in args):
        return
    workspace = Path.cwd().resolve()
    digest = hashlib.sha256(str(workspace).encode("utf-8")).hexdigest()[:12]
    configured_root = os.environ.get("AUTOGIT_TEST_TEMP_ROOT")
    if configured_root:
        root = Path(configured_root)
    elif os.name == "nt" and Path("C:/tmp").is_dir():
        root = Path("C:/tmp")
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Temp"
    else:
        root = Path(os.environ.get("TMPDIR", "/tmp"))
    base = root / f"autogit-pytest-{digest}-{os.getpid()}"
    args.append(f"--basetemp={base}")
    os.environ[_MANAGED_BASETEMP_ENV] = str(base)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Remove only the external base created by this plugin; never hide cleanup errors."""
    value = os.environ.pop(_MANAGED_BASETEMP_ENV, None)
    if value is not None:
        _remove_with_windows_retry(Path(value))


def _remove_with_windows_retry(path: Path) -> None:
    """Wait briefly for Windows to release handles, then surface the real error."""
    deadline = time.monotonic() + 60
    while True:
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
