"""Tree-sitter–based source-code chunker.

Splits source files into semantic chunks (function, class, import …) that are
small enough to fit in a retrieval context window yet semantically complete.

Supported languages (grammar packages must be installed):
  python       tree-sitter-python
  typescript   tree-sitter-typescript
  javascript   tree-sitter-javascript
  go           tree-sitter-go
  rust         tree-sitter-rust
  java         tree-sitter-java
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Parser

# ── File-extension → language name ────────────────────────────────────────────

LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}

# ── Node types that become independent top-level chunks ───────────────────────
# The walker yields a node and stops recursing into it, so each entry here
# produces exactly one chunk regardless of nesting depth.

CHUNK_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "import_statement",
        "import_from_statement",
        "function_definition",
        "class_definition",
    },
    "typescript": {
        "import_declaration",
        "import_statement",
        "function_declaration",
        "arrow_function",
        "class_declaration",
        "method_definition",
        "interface_declaration",
        "type_alias_declaration",
        "export_statement",
    },
    "javascript": {
        "import_declaration",
        "import_statement",
        "function_declaration",
        "arrow_function",
        "class_declaration",
        "method_definition",
        "export_statement",
    },
    "go": {
        "function_declaration",
        "method_declaration",
        "type_declaration",
        "import_declaration",
        "const_declaration",
    },
    "rust": {
        "function_item",
        "impl_item",
        "struct_item",
        "enum_item",
        "use_declaration",
        "trait_item",
        "mod_item",
    },
    "java": {
        "class_declaration",
        "interface_declaration",
        "method_declaration",
        "import_declaration",
        "enum_declaration",
    },
}


# ── Lazy grammar loader ────────────────────────────────────────────────────────

_LANGUAGE_CACHE: dict[str, Language | None] = {}


def _load_grammar(name: str) -> Language | None:
    """Import the grammar package for *name* and return a Language object.

    Returns None when the optional grammar package is not installed so that
    callers can degrade gracefully instead of crashing at import time.
    """
    try:
        if name == "python":
            import tree_sitter_python as m  # type: ignore[import-not-found]

            return Language(m.language())
        if name == "typescript":
            import tree_sitter_typescript as m  # type: ignore[import-not-found]

            return Language(m.language_typescript())
        if name == "javascript":
            import tree_sitter_javascript as m  # type: ignore[import-not-found]

            return Language(m.language())
        if name == "go":
            import tree_sitter_go as m  # type: ignore[import-not-found]

            return Language(m.language())
        if name == "rust":
            import tree_sitter_rust as m  # type: ignore[import-not-found]

            return Language(m.language())
        if name == "java":
            import tree_sitter_java as m  # type: ignore[import-not-found]

            return Language(m.language())
    except (ImportError, AttributeError):
        return None
    return None


def _get_language(name: str) -> Language | None:
    if name not in _LANGUAGE_CACHE:
        _LANGUAGE_CACHE[name] = _load_grammar(name)
    return _LANGUAGE_CACHE[name]


# ── Public API ─────────────────────────────────────────────────────────────────


@dataclass
class Chunk:
    text: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    node_type: str


def detect_language(path: str) -> str | None:
    """Return the canonical language name for *path*, or None if unsupported."""
    return LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower())


def chunk_file(file_path: str) -> Generator[Chunk, None, None]:
    """Yield semantic chunks from a source file on disk.

    Unsupported file types or missing grammar packages yield nothing.
    """
    language = detect_language(file_path)
    if language is None:
        return

    grammar = _get_language(language)
    if grammar is None:
        return

    source = Path(file_path).read_bytes()
    if not source.strip():
        return

    yield from _parse_and_walk(source, language, grammar, file_path)


def chunk_text(source: str, language: str, file_path: str = "<string>") -> list[Chunk]:
    """Chunk an in-memory string — used by the /index endpoint and tests."""
    if language not in CHUNK_NODE_TYPES:
        return []
    grammar = _get_language(language)
    if grammar is None:
        return []
    return list(_parse_and_walk(source.encode("utf-8"), language, grammar, file_path))


# ── Internal helpers ───────────────────────────────────────────────────────────


def _parse_and_walk(
    source_bytes: bytes,
    language: str,
    grammar: Language,
    file_path: str,
) -> Generator[Chunk, None, None]:
    parser = Parser(grammar)
    tree = parser.parse(source_bytes)
    target_types = CHUNK_NODE_TYPES[language]

    def walk(node) -> Generator[Chunk, None, None]:
        if node.type in target_types:
            text = source_bytes[node.start_byte : node.end_byte].decode(
                "utf-8", errors="replace"
            )
            yield Chunk(
                text=text,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                language=language,
                node_type=node.type,
            )
            # Stop recursing — the whole node is one chunk.
        else:
            for child in node.children:
                yield from walk(child)

    yield from walk(tree.root_node)
