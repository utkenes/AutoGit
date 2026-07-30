from pathlib import Path

from autogit.application.commit_planner import CommitPlanner
from autogit.application.feature_clusterer import FeatureClusterer
from autogit.application.file_context_extractor import FileContextExtractor
from autogit.application.file_relation_scorer import FileRelationScorer
from autogit.config import AutoGitConfig
from autogit.domain.feature_grouping import ChangedFileContext, FileRelation
from autogit.domain.models import ChangedFile, FileStatus


def changed(path: str, status: FileStatus = FileStatus.MODIFIED) -> ChangedFile:
    return ChangedFile(Path(path), status)


def test_context_extractor_classifies_and_extracts_non_sensitive_metadata(tmp_path: Path) -> None:
    source = tmp_path / "autogit" / "application"
    source.mkdir(parents=True)
    (source / "quality_recovery.py").write_text(
        "from autogit.domain.models import QualityCheck\n\n"
        "def recover_quality(check_name: str) -> None:\n"
        "    retry_count = 1\n",
        encoding="utf-8",
    )

    context = FileContextExtractor(tmp_path).extract(
        changed("autogit/application/quality_recovery.py", FileStatus.ADDED)
    )

    assert {"quality", "recovery"} <= context.filename_tokens
    assert "recover_quality" in context.changed_symbols
    assert "retry_count" in context.changed_identifiers
    assert [(symbol.name, symbol.kind) for symbol in context.symbols] == [
        ("recover_quality", "function")
    ]
    assert not context.is_test
    assert not context.is_wiring


def test_relation_scorer_strongly_relates_test_and_source() -> None:
    source = ChangedFileContext(
        path="autogit/application/quality_recovery.py",
        change_type="added",
        filename_tokens=frozenset({"quality", "recovery"}),
        changed_identifiers=frozenset({"retry_count"}),
    )
    test = ChangedFileContext(
        path="tests/unit/test_quality_recovery.py",
        change_type="added",
        filename_tokens=frozenset({"quality", "recovery"}),
        changed_identifiers=frozenset({"retry_count"}),
        is_test=True,
    )

    relation = FileRelationScorer().score(source, test)

    assert relation.score >= 16
    assert "test-source filename match" in relation.reasons


def test_clusterer_keeps_wiring_from_bridging_two_features() -> None:
    first = ChangedFileContext("autogit/application/quality.py", "modified", frozenset({"quality"}))
    second = ChangedFileContext("autogit/application/undo.py", "modified", frozenset({"undo"}))
    wiring = ChangedFileContext(
        "autogit/container.py",
        "modified",
        frozenset({"container"}),
        is_wiring=True,
    )
    relations = [
        FileRelation(first.path, wiring.path, 10, ("wiring reference",)),
        FileRelation(second.path, wiring.path, 9, ("wiring reference",)),
    ]

    clusters = FeatureClusterer().cluster([first, second, wiring], relations, 8, 3, 8)

    assert [tuple(file.path for file in cluster.files) for cluster in clusters] == [
        ("autogit/application/quality.py",),
        ("autogit/application/undo.py",),
        ("autogit/container.py",),
    ]


def test_planner_separates_tests_when_configured(tmp_path: Path) -> None:
    (tmp_path / "quality_recovery.py").write_text(
        "def recover_quality() -> None:\n    pass\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_quality_recovery.py").write_text(
        "def test_recover_quality() -> None:\n    pass\n",
        encoding="utf-8",
    )
    config = AutoGitConfig(group_tests_with_feature=False)

    groups = CommitPlanner(tmp_path, config).plan(
        [
            changed("quality_recovery.py", FileStatus.ADDED),
            changed("tests/test_quality_recovery.py", FileStatus.ADDED),
        ]
    )

    assert [group.commit_type for group in groups] == ["feat", "test"]
    assert all(len(group.files) == 1 for group in groups)


def test_planner_groups_source_and_test_with_reason_and_confidence(tmp_path: Path) -> None:
    (tmp_path / "quality_recovery.py").write_text(
        "def recover_quality() -> None:\n    pass\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_quality_recovery.py").write_text(
        "def test_recover_quality() -> None:\n    pass\n",
        encoding="utf-8",
    )

    groups = CommitPlanner(tmp_path).plan(
        [
            changed("quality_recovery.py", FileStatus.ADDED),
            changed("tests/test_quality_recovery.py", FileStatus.ADDED),
        ]
    )

    assert len(groups) == 1
    assert groups[0].commit_type == "feat"
    assert groups[0].confidence > 0
    assert "confidence" in groups[0].reason


def test_scope_rejects_generic_repository_tokens(tmp_path: Path) -> None:
    path = tmp_path / "autogit" / "application"
    path.mkdir(parents=True)
    (path / "implementation.py").write_text("value = 1\n", encoding="utf-8")

    group = CommitPlanner(tmp_path).plan(
        [changed("autogit/application/implementation.py", FileStatus.ADDED)]
    )[0]

    assert group.scope not in {
        "autogit",
        "application",
        "domain",
        "infrastructure",
        "src",
        "app",
        "implementation",
        "changes",
    }


def test_message_uses_class_and_function_kinds(tmp_path: Path) -> None:
    (tmp_path / "context.py").write_text(
        "class ChangedFileContext:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "parser.py").write_text(
        "def parse_plan() -> None:\n    pass\n",
        encoding="utf-8",
    )

    groups = CommitPlanner(tmp_path).plan(
        [
            changed("context.py", FileStatus.ADDED),
            changed("parser.py", FileStatus.ADDED),
        ]
    )
    messages = [group.suggested_message for group in groups]

    assert any("add changed file context model" in message for message in messages)
    assert any("add parse plan function" in message for message in messages)
    assert all("ChangedFileContext function" not in message for message in messages)


def test_dominant_grouping_feature_uses_planner_scope(tmp_path: Path) -> None:
    for path in (
        "autogit/application/feature_clusterer.py",
        "autogit/application/file_context_extractor.py",
        "autogit/domain/feature_grouping.py",
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("class FeatureGrouping:\n    pass\n", encoding="utf-8")

    groups = CommitPlanner(tmp_path).plan(
        [
            changed("autogit/application/feature_clusterer.py", FileStatus.ADDED),
            changed("autogit/application/file_context_extractor.py", FileStatus.ADDED),
            changed("autogit/domain/feature_grouping.py", FileStatus.ADDED),
        ]
    )

    assert len(groups) == 1
    assert groups[0].scope == "planner"


def test_current_feature_aware_dry_run_has_three_reviewable_groups() -> None:
    root = Path.cwd()
    paths = [
        "autogit/application/feature_clusterer.py",
        "autogit/application/file_context_extractor.py",
        "autogit/application/file_relation_scorer.py",
        "autogit/domain/feature_grouping.py",
        "autogit/domain/models.py",
        "tests/unit/test_feature_grouping.py",
        "autogit/application/commit_planner.py",
        "autogit/cli.py",
        "autogit/config.py",
        "autogit/container.py",
        ".autogit.example.toml",
        "tests/unit/test_commit_planner.py",
        "tests/integration/test_start_workflow.py",
        "README.md",
    ]

    groups = CommitPlanner(root).plan([changed(path, FileStatus.ADDED) for path in paths])

    assert [(group.commit_type, group.scope) for group in groups] == [
        ("feat", "planner"),
        ("feat", "planner"),
        ("docs", "planner"),
    ]
    assert [file.path.as_posix() for file in groups[0].files] == [
        "autogit/application/feature_clusterer.py",
        "autogit/application/file_context_extractor.py",
        "autogit/application/file_relation_scorer.py",
        "autogit/domain/feature_grouping.py",
        "autogit/domain/models.py",
        "tests/unit/test_feature_grouping.py",
    ]
    assert [file.path.as_posix() for file in groups[1].files] == [
        ".autogit.example.toml",
        "autogit/application/commit_planner.py",
        "autogit/cli.py",
        "autogit/config.py",
        "autogit/container.py",
        "tests/integration/test_start_workflow.py",
        "tests/unit/test_commit_planner.py",
    ]
    assert [file.path.as_posix() for file in groups[2].files] == ["README.md"]
