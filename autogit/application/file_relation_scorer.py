"""Deterministic explainable pair scoring for changed files."""

from __future__ import annotations

from autogit.domain.feature_grouping import ChangedFileContext, FileRelation


class FileRelationScorer:
    def score(self, left: ChangedFileContext, right: ChangedFileContext) -> FileRelation:
        score = 0
        reasons: list[str] = []
        shared_features = left.feature_tokens & right.feature_tokens
        incompatible_features = bool(
            left.feature_tokens
            and right.feature_tokens
            and not shared_features
        )
        if shared_features and not (left.is_doc or right.is_doc):
            score += 20
            reasons.append(f"shared feature: {sorted(shared_features)[0]}")
        shared = left.filename_tokens & right.filename_tokens
        if left.is_test != right.is_test and shared and not incompatible_features:
            score += 10
            reasons.append("test-source filename match")
        if (
            left.is_test != right.is_test
            and not incompatible_features
            and self._references_other_module(left, right)
        ):
            score += 12
            reasons.append("direct test import")
        shared_imports = left.imported_modules & right.imported_modules
        if shared_imports and not incompatible_features:
            score += 8
            reasons.append("shared import")
        if len(shared) >= 2 and not incompatible_features:
            score += 6
            reasons.append(f"shared tokens: {', '.join(sorted(shared))}")
        elif shared and not incompatible_features:
            score += 4
            reasons.append(f"shared token: {next(iter(shared))}")
        identifiers = left.changed_identifiers & right.changed_identifiers
        if identifiers and not incompatible_features:
            score += 6
            reasons.append(f"shared identifier: {sorted(identifiers)[0]}")
        symbols = left.changed_symbols & right.changed_symbols
        if symbols and not incompatible_features:
            score += 8
            reasons.append(f"shared symbol: {sorted(symbols)[0]}")
        if left.config_keys & right.config_keys and not incompatible_features:
            score += 5
            reasons.append("shared config key")
        return FileRelation(left.path, right.path, score, tuple(reasons))

    @staticmethod
    def _references_other_module(
        left: ChangedFileContext,
        right: ChangedFileContext,
    ) -> bool:
        left_tokens = {
            part
            for module in left.imported_modules
            for part in module.replace("-", "_").split("_")
            for part in part.split(".")
        }
        right_tokens = {
            part
            for module in right.imported_modules
            for part in module.replace("-", "_").split("_")
            for part in part.split(".")
        }
        return bool(
            left_tokens & right.filename_tokens or right_tokens & left.filename_tokens
        )
