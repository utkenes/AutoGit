"""Small, Windows-only UTF-8 console setup for the CLI entrypoint."""

from __future__ import annotations

import os
import sys
from typing import TextIO


def configure_windows_utf8() -> None:
    """Prefer UTF-8 where Python exposes a reconfigurable Windows text stream.

    This is deliberately limited to the CLI process on Windows.  It does not
    replace global codecs, alter filesystem encoding, or touch streams that do
    not expose ``reconfigure`` (for example test doubles and some IDE hosts).
    """
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        _configure(stream)


def _configure(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    encoding = getattr(stream, "encoding", "") or ""
    if not callable(reconfigure) or encoding.lower().replace("-", "") == "utf8":
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        # A redirected or host-owned stream can reject reconfiguration.  The
        # CLI must remain usable in that environment.
        return
