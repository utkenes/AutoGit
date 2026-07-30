from pathlib import Path

from autogit.application.commit_planner import CommitPlanner
from autogit.domain.models import ChangedFile, FileStatus


def changed(path: str, status: FileStatus = FileStatus.MODIFIED) -> ChangedFile:
    return ChangedFile(Path(path), status)


def test_planner_splits_source_test_docs_and_config() -> None:
    groups = CommitPlanner().plan(
        [
            changed("autogit/cli.py", FileStatus.ADDED),
            changed("tests/unit/test_cli.py"),
            changed("README.md"),
            changed("pyproject.toml"),
        ]
    )
    assert [group.commit_type for group in groups] == ["feat", "test", "docs", "chore"]
    assert groups[0].scope == "cli"
    assert groups[1].scope == "cli"


def test_planner_keeps_related_source_files_together() -> None:
    groups = CommitPlanner().plan([changed("autogit/application/service.py"), changed("autogit/application/service.py")])
    assert len(groups) == 1
    assert len(groups[0].files) == 2


def test_planner_handles_empty_list() -> None:
    assert CommitPlanner().plan([]) == []
