from pathlib import Path

from autogit.domain.models import ChangedFile, CommitContext, FileStatus
from autogit.providers.local_commit_provider import LocalCommitMessageProvider


def test_message_uses_conventional_commit_format() -> None:
    context = CommitContext([ChangedFile(Path("autogit/watcher.py"), FileStatus.ADDED)], "", "")
    message = LocalCommitMessageProvider().generate(context)
    assert message.startswith("feat: ")
    assert LocalCommitMessageProvider.is_valid(message)


def test_validator_rejects_unknown_type_control_characters_and_long_subject() -> None:
    provider = LocalCommitMessageProvider()

    assert provider.validation_error("unknown(cli): update output") is not None
    assert provider.validation_error("feat: update\nother") is not None
    assert provider.validation_error("feat: " + "x" * 80) is not None
    assert provider.validation_error("fix(cli): preserve UTF-8 output") is None
