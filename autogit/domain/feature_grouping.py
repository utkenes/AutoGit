"""Immutable models for explainable feature-aware grouping."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SymbolInfo:
    """A changed declaration and its local, language-level classification."""

    name: str
    kind: str


@dataclass(frozen=True)
class ChangedFileContext:
    path: str
    change_type: str
    filename_tokens: frozenset[str] = field(default_factory=frozenset)
    imported_modules: frozenset[str] = field(default_factory=frozenset)
    changed_symbols: frozenset[str] = field(default_factory=frozenset)
    changed_identifiers: frozenset[str] = field(default_factory=frozenset)
    config_keys: frozenset[str] = field(default_factory=frozenset)
    is_test: bool = False
    is_doc: bool = False
    is_config: bool = False
    is_wiring: bool = False
    symbols: tuple[SymbolInfo, ...] = ()
    feature_tokens: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class FileRelation:
    left_path: str
    right_path: str
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class FeatureCluster:
    key: str
    files: tuple[ChangedFileContext, ...]
    confidence: float
    reasons: tuple[str, ...]
