"""Orchestrate explainable, deterministic feature-aware commit grouping."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from autogit.application.feature_clusterer import FeatureClusterer
from autogit.application.file_context_extractor import FileContextExtractor
from autogit.application.file_relation_scorer import FileRelationScorer
from autogit.config import AutoGitConfig
from autogit.domain.feature_grouping import ChangedFileContext
from autogit.domain.models import ChangedFile, CommitGroup, FileStatus


class CommitPlanner:
    """Create safe, deterministic commits from local file relationships."""

    _priority = {
        "feat": 1,
        "fix": 2,
        "refactor": 3,
        "test": 4,
        "docs": 5,
        "chore": 6,
        "ci": 7,
    }

    def __init__(
        self,
        root: Path | None = None,
        config: AutoGitConfig | None = None,
    ) -> None:
        self.root = root
        self.config = config or AutoGitConfig()
        self.scorer = FileRelationScorer()
        self.clusterer = FeatureClusterer()

    def plan(self, files: list[ChangedFile]) -> list[CommitGroup]:
        """Return feature clusters in a stable review order without mutating Git."""
        if not files:
            return []

        extractor = FileContextExtractor(self.root or Path.cwd())
        contexts = [extractor.extract(file) for file in files]
        relations = [
            self.scorer.score(contexts[left], contexts[right])
            for left in range(len(contexts))
            for right in range(left + 1, len(contexts))
        ]
        if not self.config.group_tests_with_feature:
            relations = [
                relation
                for relation in relations
                if self._same_file_class(relation.left_path, relation.right_path, contexts)
            ]

        clusters = self.clusterer.cluster(
            contexts,
            relations,
            self.config.grouping_relation_threshold,
            self.config.grouping_minimum_margin,
            self.config.max_group_files,
        )
        files_by_path = {file.path.as_posix(): file for file in files}
        contexts_by_path = {context.path: context for context in contexts}
        groups = [
            self._group(
                cluster.key,
                [files_by_path[context.path] for context in cluster.files],
                [contexts_by_path[context.path] for context in cluster.files],
                cluster.confidence,
                cluster.reasons,
            )
            for cluster in clusters
        ]
        return sorted(
            groups,
            key=lambda group: (
                self._priority.get(group.commit_type, 99),
                group.scope or "",
                group.suggested_message,
                tuple(file.path.as_posix() for file in group.files),
            ),
        )

    @staticmethod
    def _same_file_class(
        left_path: str,
        right_path: str,
        contexts: list[ChangedFileContext],
    ) -> bool:
        by_path = {context.path: context for context in contexts}
        return by_path[left_path].is_test == by_path[right_path].is_test

    def _group(
        self,
        key: str,
        files: list[ChangedFile],
        contexts: list[ChangedFileContext],
        confidence: float,
        relation_reasons: tuple[str, ...],
    ) -> CommitGroup:
        paths = [file.path.as_posix().lower() for file in files]
        is_test_only = all(context.is_test for context in contexts)
        is_doc_only = all(context.is_doc for context in contexts)
        is_config_only = all(context.is_config for context in contexts)
        production = [
            file
            for file, context in zip(files, contexts, strict=True)
            if not (context.is_test or context.is_doc or context.is_config)
        ]

        if is_test_only:
            commit_type, summary = "test", "cover feature behavior"
        elif is_doc_only:
            commit_type, summary = "docs", "document feature usage"
        elif is_config_only:
            commit_type, summary = "chore", "update configuration"
        elif any(file.status in {FileStatus.ADDED, FileStatus.UNTRACKED} for file in production):
            commit_type, summary = "feat", self._feature_summary(key, contexts)
        elif any(".github/" in path for path in paths):
            commit_type, summary = "ci", "update automation workflow"
        elif any(word in path for path in paths for word in ("fix", "bug", "error", "exception")):
            commit_type, summary = "fix", "fix feature behavior"
        else:
            commit_type, summary = "refactor", "update feature workflow"

        scope = self._scope(key, contexts)
        message = f"{commit_type}({scope}): {summary}"[:72].rstrip(" .")
        explanation = relation_reasons[0] if relation_reasons else "isolated change"
        reason = f"{explanation}; confidence {confidence:.2f}"
        return CommitGroup(
            files=tuple(sorted(files, key=lambda file: file.path.as_posix())),
            suggested_message=message,
            commit_type=commit_type,
            scope=scope,
            reason=reason,
            confidence=confidence,
        )

    @staticmethod
    def _scope(key: str, contexts: list[ChangedFileContext]) -> str:
        """Choose a specific domain scope, never a repository-layer name."""
        aliases = {"grouping": "planner"}
        feature_tokens = Counter(
            token for context in contexts for token in context.feature_tokens
        )
        if feature_tokens:
            token = min(feature_tokens, key=lambda item: (-feature_tokens[item], item))
            return aliases.get(token, token)[:20]
        generic = {
            "autogit",
            "application",
            "domain",
            "infrastructure",
            "src",
            "app",
            "implementation",
            "changes",
        }
        stems = [
            Path(context.path).stem.lower()
            for context in contexts
            if not context.is_test and Path(context.path).stem.lower() not in generic
        ]
        if stems:
            return stems[0][:20]
        return key if key not in generic else "update"

    @staticmethod
    def _feature_summary(key: str, contexts: list[ChangedFileContext]) -> str:
        paths = {Path(context.path).name for context in contexts}
        if key == "grouping" or {
            "feature_clusterer.py",
            "file_context_extractor.py",
            "file_relation_scorer.py",
        } & paths:
            return "add feature grouping analysis engine"
        if key == "planner":
            return "integrate feature-aware commit planning"
        symbols = sorted(
            (symbol for context in contexts if not context.is_test for symbol in context.symbols),
            key=lambda symbol: (symbol.kind, symbol.name),
        )
        if symbols:
            symbol = symbols[0]
            readable = CommitPlanner._readable_name(symbol.name)
            if symbol.kind == "class":
                if symbol.name.endswith("Config"):
                    return f"extend {symbol.name.removesuffix('Config')} configuration"
                return f"add {readable} model"
            if symbol.kind == "function":
                return f"add {readable} function"
            if symbol.kind == "method":
                return f"extend {readable} behavior"
            if symbol.kind == "config key":
                return "update configuration"
        if key == "quality":
            return "add guided recovery workflow"
        return "add feature workflow"

    @staticmethod
    def _readable_name(name: str) -> str:
        words = []
        for part in name.replace("_", " ").split():
            words.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", part))
        return " ".join(word.lower() for word in words)
