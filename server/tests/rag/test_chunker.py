"""Unit tests for rag/chunker.py.

These tests are pure: no I/O, no mocks, no network.
chunk_text() is used so tests never touch the real filesystem.
"""

import textwrap

from rag.chunker import Chunk, chunk_text, detect_language


# ── detect_language ────────────────────────────────────────────────────────────

class TestDetectLanguage:
    def test_python_extension(self):
        assert detect_language("app.py") == "python"

    def test_typescript_extension(self):
        assert detect_language("index.ts") == "typescript"

    def test_tsx_extension(self):
        assert detect_language("App.tsx") == "typescript"

    def test_uppercase_extension(self):
        assert detect_language("Main.PY") == "python"

    def test_unsupported_returns_none(self):
        assert detect_language("styles.css") is None
        assert detect_language("README.md") is None
        assert detect_language("Makefile") is None

    def test_no_extension_returns_none(self):
        assert detect_language("Dockerfile") is None


# ── chunk_text — Python ────────────────────────────────────────────────────────

class TestChunkTextPython:
    def test_function_becomes_one_chunk(self):
        src = textwrap.dedent("""\
            def add(a: int, b: int) -> int:
                return a + b
        """)
        chunks = chunk_text(src, "python")
        assert len(chunks) == 1
        assert chunks[0].node_type == "function_definition"
        assert "def add" in chunks[0].text

    def test_async_function_becomes_one_chunk(self):
        src = textwrap.dedent("""\
            async def fetch(url: str) -> str:
                return url
        """)
        chunks = chunk_text(src, "python")
        assert len(chunks) == 1
        # tree-sitter 0.23+ represents async def as function_definition
        # (async is a child token, not a separate node type)
        assert chunks[0].node_type == "function_definition"

    def test_class_becomes_one_chunk(self):
        src = textwrap.dedent("""\
            class Greeter:
                def __init__(self) -> None:
                    pass

                def greet(self, name: str) -> str:
                    return f"Hello, {name}"
        """)
        chunks = chunk_text(src, "python")
        # The class is one chunk; its methods are NOT separate chunks
        assert len(chunks) == 1
        assert chunks[0].node_type == "class_definition"
        assert "def greet" in chunks[0].text

    def test_import_statement_becomes_one_chunk(self):
        src = "import os\n"
        chunks = chunk_text(src, "python")
        assert len(chunks) == 1
        assert chunks[0].node_type == "import_statement"

    def test_from_import_becomes_one_chunk(self):
        src = "from pathlib import Path\n"
        chunks = chunk_text(src, "python")
        assert len(chunks) == 1
        assert chunks[0].node_type == "import_from_statement"

    def test_multiple_top_level_nodes(self, python_source):
        chunks = chunk_text(python_source, "python")
        node_types = [c.node_type for c in chunks]
        # Should contain imports, function, and class
        assert "import_statement" in node_types or "import_from_statement" in node_types
        assert "function_definition" in node_types
        assert "class_definition" in node_types

    def test_empty_source_returns_no_chunks(self):
        assert chunk_text("", "python") == []
        assert chunk_text("   \n\n  ", "python") == []

    def test_chunk_line_numbers_are_correct(self):
        src = textwrap.dedent("""\
            import os

            def foo():
                pass
        """)
        chunks = chunk_text(src, "python")
        fn_chunk = next(c for c in chunks if c.node_type == "function_definition")
        assert fn_chunk.start_line == 3
        assert fn_chunk.end_line == 4

    def test_chunk_metadata(self):
        src = "def f(): pass\n"
        chunks = chunk_text(src, "python", file_path="/repo/foo.py")
        assert chunks[0].file_path == "/repo/foo.py"
        assert chunks[0].language == "python"

    def test_unsupported_language_returns_empty(self):
        assert chunk_text("body { color: red; }", "css") == []

    def test_bare_expressions_not_chunked(self):
        # Bare expressions (not inside a function/class) are not chunk targets
        src = textwrap.dedent("""\
            x = 1
            y = 2
            print(x + y)
        """)
        chunks = chunk_text(src, "python")
        assert chunks == []

    def test_nested_functions_not_double_chunked(self):
        src = textwrap.dedent("""\
            def outer():
                def inner():
                    pass
                return inner
        """)
        chunks = chunk_text(src, "python")
        # Only outer is a top-level chunk; inner is nested inside it
        assert len(chunks) == 1
        assert "def inner" in chunks[0].text


# ── chunk_text — TypeScript ────────────────────────────────────────────────────

class TestChunkTextTypeScript:
    def test_function_declaration(self):
        src = "function greet(name: string): string { return `Hello ${name}`; }\n"
        chunks = chunk_text(src, "typescript")
        assert len(chunks) == 1
        assert chunks[0].node_type == "function_declaration"

    def test_interface_declaration(self):
        src = textwrap.dedent("""\
            interface Config {
                host: string;
                port: number;
            }
        """)
        chunks = chunk_text(src, "typescript")
        assert any(c.node_type == "interface_declaration" for c in chunks)

    def test_type_alias(self):
        src = "type ID = string | number;\n"
        chunks = chunk_text(src, "typescript")
        assert any(c.node_type == "type_alias_declaration" for c in chunks)

    def test_class_declaration(self):
        src = textwrap.dedent("""\
            class Loader {
                constructor(private path: string) {}
                load(): string { return this.path; }
            }
        """)
        chunks = chunk_text(src, "typescript")
        assert any(c.node_type == "class_declaration" for c in chunks)

    def test_import_declaration(self):
        src = "import { readFileSync } from 'fs';\n"
        chunks = chunk_text(src, "typescript")
        assert len(chunks) == 1

    def test_full_typescript_source(self, typescript_source):
        chunks = chunk_text(typescript_source, "typescript")
        assert len(chunks) >= 3  # import + interface + function + class


# ── Chunk dataclass ────────────────────────────────────────────────────────────

class TestChunkDataclass:
    def test_chunk_fields(self):
        c = Chunk(
            text="def f(): pass",
            file_path="/a.py",
            start_line=1,
            end_line=1,
            language="python",
            node_type="function_definition",
        )
        assert c.text == "def f(): pass"
        assert c.start_line == 1
        assert c.language == "python"
