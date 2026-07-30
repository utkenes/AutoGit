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
    assert [group.commit_type for group in groups] == ["feat", "docs", "chore"]
    assert groups[0].scope == "planner"
    assert {file.path.as_posix() for file in groups[0].files} == {
        "autogit/cli.py",
        "tests/unit/test_cli.py",
    }


def test_planner_keeps_related_source_files_together() -> None:
    groups = CommitPlanner().plan([changed("autogit/application/service.py"), changed("autogit/application/service.py")])
    assert len(groups) == 1
    assert len(groups[0].files) == 2


def test_planner_handles_empty_list() -> None:
    assert CommitPlanner().plan([]) == []


def test_planner_orders_source_test_docs_and_config() -> None:
    groups = CommitPlanner().plan(
        [
            changed("README.md"),
            changed("tests/test_app.py"),
            changed("pyproject.toml"),
            changed("app.py", FileStatus.ADDED),
        ]
    )
    assert [group.commit_type for group in groups] == ["feat", "docs", "chore"]


def test_planner_uses_safe_function_name_for_new_source(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def greet(name: str) -> str:\n    return name\n", encoding="utf-8")
    groups = CommitPlanner(tmp_path).plan([changed("app.py", FileStatus.ADDED)])
    assert groups[0].suggested_message == "feat(update): add greet function"
    assert len(groups[0].suggested_message) <= 72
