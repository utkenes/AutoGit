from pathlib import Path

from autogit.domain.models import ChangedFile, CommitContext, FileStatus
from autogit.providers.local_commit_provider import LocalCommitMessageProvider


def test_message_uses_conventional_commit_format() -> None:
    context = CommitContext([ChangedFile(Path("autogit/watcher.py"), FileStatus.ADDED)], "", "")
    message = LocalCommitMessageProvider().generate(context)
    assert message.startswith("feat: ")
    assert LocalCommitMessageProvider.is_valid(message)

