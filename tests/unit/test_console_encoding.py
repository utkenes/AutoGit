from __future__ import annotations

from autogit.infrastructure.console_encoding import _configure


class ReconfigurableStream:
    encoding = "cp1254"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def reconfigure(self, *, encoding: str, errors: str) -> None:
        self.calls.append((encoding, errors))


def test_configure_changes_a_legacy_reconfigurable_stream_to_utf8() -> None:
    stream = ReconfigurableStream()

    _configure(stream)  # type: ignore[arg-type]

    assert stream.calls == [("utf-8", "replace")]
