"""Repository dışına taşmayı engelleyen yol araçları."""

from pathlib import Path


def is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def is_ignored(path: Path, root: Path, ignored_parts: list[str]) -> bool:
    try:
        relative_parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return True
    return any(part in ignored_parts for part in relative_parts)

