"""Graph clustering that prevents wiring files from merging features."""

from __future__ import annotations

from collections import defaultdict

from autogit.domain.feature_grouping import ChangedFileContext, FeatureCluster, FileRelation


class FeatureClusterer:
    def cluster(self, contexts: list[ChangedFileContext], relations: list[FileRelation], threshold: int, margin: int, maximum: int) -> list[FeatureCluster]:
        parent = {item.path: item.path for item in contexts}
        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value
        def join(left: str, right: str) -> None:
            left, right = find(left), find(right)
            if left != right:
                parent[right] = left
        by_path = {item.path: item for item in contexts}
        for relation in relations:
            if relation.score >= threshold and not (by_path[relation.left_path].is_wiring or by_path[relation.right_path].is_wiring):
                join(relation.left_path, relation.right_path)
        groups: dict[str, list[ChangedFileContext]] = defaultdict(list)
        for item in contexts:
            if not item.is_wiring:
                groups[find(item.path)].append(item)
        for item in (item for item in contexts if item.is_wiring):
            scores: dict[str, int] = defaultdict(int)
            for relation in relations:
                other = relation.right_path if relation.left_path == item.path else relation.left_path if relation.right_path == item.path else None
                if other and not by_path[other].is_wiring:
                    scores[find(other)] += relation.score
            ranked = sorted(scores.items(), key=lambda value: (-value[1], value[0]))
            if ranked and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= margin):
                groups[ranked[0][0]].append(item)
            else:
                groups[item.path].append(item)
        clusters = [
            self._to_cluster(chunk, relations)
            for files in groups.values()
            for chunk in self._split(files, maximum)
        ]
        return sorted(clusters, key=lambda cluster: tuple(file.path for file in cluster.files))

    def _to_cluster(
        self,
        files: list[ChangedFileContext],
        relations: list[FileRelation],
    ) -> FeatureCluster:
        paths = {file.path for file in files}
        reasons = tuple(
            sorted(
                {
                    reason
                    for relation in relations
                    if {relation.left_path, relation.right_path} <= paths
                    for reason in relation.reasons
                }
            )
        )
        confidence = min(1.0, 0.5 + len(files) * 0.1 + len(reasons) * 0.03)
        return FeatureCluster(
            key=self._key(files),
            files=tuple(sorted(files, key=lambda item: item.path)),
            confidence=confidence,
            reasons=reasons,
        )
    @staticmethod
    def _split(files: list[ChangedFileContext], maximum: int) -> list[list[ChangedFileContext]]:
        return [files[index:index + maximum] for index in range(0, len(files), maximum)]
    @staticmethod
    def _key(files: list[ChangedFileContext]) -> str:
        feature_tokens: dict[str, int] = defaultdict(int)
        for file in files:
            for token in file.feature_tokens:
                feature_tokens[token] += 1
        if feature_tokens:
            return sorted(feature_tokens, key=lambda token: (-feature_tokens[token], token))[0]
        tokens: dict[str, int] = defaultdict(int)
        for file in files:
            for token in file.filename_tokens:
                tokens[token] += 1
        return sorted(tokens, key=lambda token: (-tokens[token], token))[0] if tokens else "changes"
