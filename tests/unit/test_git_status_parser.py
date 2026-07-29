from pathlib import Path

from autogit.domain.models import FileStatus
from autogit.infrastructure.git_status_parser import GitStatusParser


def test_parser_preserves_spaces_unicode_and_special_characters() -> None:
    raw = b" M dosya adi.py\0?? Turkce Dosya.py\0?? dosya[1].txt\0"
    files = GitStatusParser().parse(raw)
    assert [file.path for file in files] == [
        Path("dosya adi.py"),
        Path("Turkce Dosya.py"),
        Path("dosya[1].txt"),
    ]
    assert files[0].unstaged
    assert files[1].status is FileStatus.UNTRACKED


def test_parser_keeps_rename_source_and_destination_separate() -> None:
    files = GitStatusParser().parse(b"R  src/yeni ad.py\0src/eski ad.py\0")
    assert len(files) == 1
    assert files[0].status is FileStatus.RENAMED
    assert files[0].path == Path("src/yeni ad.py")
    assert files[0].old_path == Path("src/eski ad.py")
    assert files[0].staged


def test_parser_handles_deleted_entries() -> None:
    files = GitStatusParser().parse(b" D deleted.txt\0")
    assert files[0].status is FileStatus.DELETED
    assert files[0].unstaged
