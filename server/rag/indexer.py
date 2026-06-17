"""Workspace-level file discovery with .gitignore awareness.

Used by the /index-dir endpoint so local deployments (where the server has
filesystem access via a volume mount) can index an entire workspace in one
request instead of sending files one-by-one from the extension.

Architecture note: this module only *discovers* files and returns their paths.
It does not read content or interact with the store — callers own that step
so the dependency graph stays clean (indexer → chunker only).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from rag.chunker import detect_language

# Directories that are never worth indexing regardless of .gitignore.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        "target",   # Rust / Maven / Gradle output
        ".next",
        ".nuxt",
        "out",
        "vendor",   # Go vendor directory
        ".cache",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


def iter_source_files(
    root: str,
    *,
    respect_gitignore: bool = True,
) -> Iterator[str]:
    """Yield absolute paths of all indexable source files under *root*.

    Skips:
    - Hidden directories (starting with '.')
    - Common build / dependency / cache directories (see _SKIP_DIRS)
    - Files matching root/.gitignore (when pathspec is installed)
    - Files whose extension is not supported by the chunker
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"directory not found: {root}")
    spec = _load_gitignore(root_path) if respect_gitignore else None

    for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
        # Prune dirnames in-place — controls os.walk's recursion.
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            abs_path = Path(dirpath) / filename

            if spec is not None:
                rel = abs_path.relative_to(root_path)
                if spec.match_file(str(rel)):
                    continue

            if detect_language(str(abs_path)) is not None:
                yield str(abs_path)


def count_source_files(root: str, *, respect_gitignore: bool = True) -> int:
    """Return the number of indexable files under *root* without reading them."""
    return sum(1 for _ in iter_source_files(root, respect_gitignore=respect_gitignore))


# ── .gitignore loader ─────────────────────────────────────────────────────────


def _load_gitignore(root: Path) -> object | None:
    """Return a pathspec matcher for root/.gitignore, or None.

    Returns None when pathspec is not installed (optional dependency) or when
    no .gitignore file exists at root.
    """
    gi_file = root / ".gitignore"
    if not gi_file.is_file():
        return None
    try:
        import pathspec  # type: ignore[import-not-found]

        with gi_file.open() as fh:
            return pathspec.PathSpec.from_lines("gitwildmatch", fh)
    except ImportError:
        return None
