from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())

# Node types that become independent top-level chunks.
# The walker yields a node and stops recursing into it, so each entry
# here produces exactly one chunk regardless of nesting depth.
CHUNK_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "import_statement",
        "import_from_statement",
        "function_definition",   # covers both def and async def in tree-sitter 0.23+
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
}

LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
}


@dataclass
class Chunk:
    text: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    node_type: str


def _get_parser(language: str) -> Parser:
    # tree-sitter 0.23+ requires the Language passed to the constructor;
    # the set_language() API was removed in that release.
    if language == "python":
        return Parser(PY_LANGUAGE)
    return Parser(TS_LANGUAGE)


def detect_language(path: str) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower())


def chunk_file(file_path: str) -> Generator[Chunk, None, None]:
    """Yield semantic chunks from a Python or TypeScript source file.

    Each chunk maps to a single top-level syntactic node (function, class,
    import block, etc.) so that retrieval units are self-contained.
    Unsupported file types yield nothing.
    """
    language = detect_language(file_path)
    if language is None:
        return

    source = Path(file_path).read_bytes()
    if not source.strip():
        return

    parser = _get_parser(language)
    tree = parser.parse(source)
    target_types = CHUNK_NODE_TYPES[language]

    def walk(node) -> Generator[Chunk, None, None]:
        if node.type in target_types:
            text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
            yield Chunk(
                text=text,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                language=language,
                node_type=node.type,
            )
            # Stop recursing: the whole node is one chunk
        else:
            for child in node.children:
                yield from walk(child)

    yield from walk(tree.root_node)


def chunk_text(source: str, language: str, file_path: str = "<string>") -> list[Chunk]:
    """Chunk an in-memory string — useful for tests and streaming indexing."""
    if language not in CHUNK_NODE_TYPES:
        return []
    parser = _get_parser(language)
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    target_types = CHUNK_NODE_TYPES[language]

    results: list[Chunk] = []

    def walk(node) -> None:
        if node.type in target_types:
            text = source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
            results.append(
                Chunk(
                    text=text,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    language=language,
                    node_type=node.type,
                )
            )
        else:
            for child in node.children:
                walk(child)

    walk(tree.root_node)
    return results
