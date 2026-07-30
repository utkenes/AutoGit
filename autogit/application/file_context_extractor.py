"""Extract non-sensitive file metadata for local feature grouping."""

from __future__ import annotations

import re
from pathlib import Path

from autogit.domain.feature_grouping import ChangedFileContext, SymbolInfo
from autogit.domain.models import ChangedFile


class FileContextExtractor:
    _stop = frozenset(
        {
            "autogit",
            "test",
            "tests",
            "spec",
            "service",
            "controller",
            "handler",
            "model",
            "models",
            "repository",
            "application",
            "domain",
            "infrastructure",
            "src",
            "lib",
            "app",
            "implementation",
            "changes",
            "module",
            "index",
            "main",
            "unit",
            "integration",
        }
    )
    _wiring = frozenset(
        {
            "cli.py",
            "container.py",
            "config.py",
            "main.py",
            "__init__.py",
            "routes.py",
            "router.py",
            "registry.py",
            "bootstrap.py",
            "dependencies.py",
        }
    )

    def __init__(self, root: Path) -> None:
        self.root = root

    def extract(self, file: ChangedFile) -> ChangedFileContext:
        path = file.path.as_posix()
        tokens = self._tokens(path)
        content = self._content(file.path)
        name = file.path.name.lower()
        is_doc = name.startswith(("readme", "changelog")) or path.startswith("docs/")
        is_config = file.path.suffix in {".toml", ".json", ".yml", ".yaml"}
        imports, symbols, identifiers, symbol_info = self._code_metadata(
            content,
            file.path.suffix,
            is_doc,
            is_config,
        )
        keys = frozenset(re.findall(r"(?m)^\s*([A-Za-z_][\w-]*)\s*=", content))
        config_symbols = tuple(SymbolInfo(key, "config key") for key in sorted(keys))
        return ChangedFileContext(
            path=path,
            change_type=file.status.value,
            filename_tokens=tokens,
            imported_modules=imports,
            changed_symbols=symbols,
            changed_identifiers=identifiers,
            config_keys=keys,
            is_test=self._is_test(path, name),
            is_doc=is_doc,
            is_config=is_config,
            is_wiring=name in self._wiring,
            symbols=symbol_info or config_symbols,
            feature_tokens=self._feature_tokens(path, content, keys, is_doc),
        )

    @staticmethod
    def _code_metadata(
        content: str,
        suffix: str,
        is_doc: bool,
        is_config: bool,
    ) -> tuple[frozenset[str], frozenset[str], frozenset[str], tuple[SymbolInfo, ...]]:
        if is_doc or is_config:
            return frozenset(), frozenset(), frozenset(), ()
        identifiers = frozenset(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", content))
        if suffix == ".py":
            imports = frozenset(
                re.findall(r"(?m)^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", content)
            )
            symbol_info = tuple(
                SymbolInfo(name, "class")
                for name in re.findall(r"(?m)^class\s+([A-Za-z_][\w]*)", content)
            ) + tuple(
                SymbolInfo(name, "method")
                for name in re.findall(r"(?m)^[ \t]+(?:async\s+)?def\s+([A-Za-z_][\w]*)", content)
            ) + tuple(
                SymbolInfo(name, "function")
                for name in re.findall(r"(?m)^(?:async\s+)?def\s+([A-Za-z_][\w]*)", content)
            )
            symbols = frozenset(symbol.name for symbol in symbol_info)
            return imports, symbols, identifiers, symbol_info
        if suffix in {".js", ".jsx", ".ts", ".tsx"}:
            imports = frozenset(
                re.findall(r"(?:from|require\()\s*['\"]([^'\"]+)", content)
            )
            class_names = re.findall(r"(?m)^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", content)
            function_names = re.findall(
                r"(?m)^\s*(?:export\s+)?function\s+([A-Za-z_$][\w$]*)",
                content,
            )
            symbol_info = tuple(SymbolInfo(name, "class") for name in class_names) + tuple(
                SymbolInfo(name, "function") for name in function_names
            )
            return imports, frozenset(symbol.name for symbol in symbol_info), identifiers, symbol_info
        return frozenset(), frozenset(), frozenset(), ()

    @staticmethod
    def _feature_tokens(
        path: str,
        content: str,
        config_keys: frozenset[str],
        is_doc: bool,
    ) -> frozenset[str]:
        lowered = content.lower()
        name = Path(path).name.lower()
        grouping_modules = {
            "feature_clusterer.py",
            "file_context_extractor.py",
            "file_relation_scorer.py",
            "feature_grouping.py",
            "test_feature_grouping.py",
        }
        if name in grouping_modules or "feature-aware grouping" in lowered:
            return frozenset({"grouping"})
        planner_keys = {"group_tests_with_feature", "grouping_relation_threshold", "max_group_files"}
        if (
            name == "commit_planner.py"
            or name == "test_commit_planner.py"
            or "commitplanner" in lowered
            or ".planner" in lowered
            or planner_keys & config_keys
            or ("tests/integration/" in path and '["plan"' in content)
        ) and not is_doc:
            return frozenset({"planner"})
        if name == "models.py" and "confidence" in lowered:
            return frozenset({"grouping"})
        return frozenset()

    def _content(self, path: Path) -> str:
        try:
            return (self.root / path).read_text(encoding="utf-8", errors="replace")[:32_000]
        except OSError:
            return ""

    def _tokens(self, path: str) -> frozenset[str]:
        words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", str(Path(path).with_suffix("")).replace("-", "_").replace("/", "_"))
        cleaned = frozenset(word.lower() for word in words if word.lower() not in self._stop)
        return cleaned or frozenset(word.lower() for word in words)

    @staticmethod
    def _is_test(path: str, name: str) -> bool:
        return path.startswith(("tests/", "test/")) or name.startswith("test_") or ".test." in name or ".spec." in name
