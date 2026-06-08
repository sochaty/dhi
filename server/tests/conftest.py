"""Shared fixtures for the Dhi server test suite.

Design rule (see ARCHITECTURE.md):
  - Unit tests mock at layer boundaries — never start Docker/Ollama/Chroma.
  - Integration tests live in tests/integration/ and are marked with
    @pytest.mark.integration so they are excluded from CI by default.
"""

import textwrap
from typing import Any

import pytest
from fastapi.testclient import TestClient

# ── Fake ChunkStore ────────────────────────────────────────────────────────────


class FakeChunkStore:
    """In-memory replacement for ChunkStore.

    Satisfies the same interface (upsert / query / count / delete_file)
    without touching Chroma or making HTTP calls.
    """

    def __init__(self, query_results: list[str] | None = None) -> None:
        self._docs: list[dict[str, Any]] = []
        self._query_results = query_results or []

    def upsert(self, chunks) -> None:
        for c in chunks:
            self._docs.append(
                {
                    "id": f"{c.file_path}:{c.start_line}:{c.end_line}",
                    "text": c.text,
                    "file_path": c.file_path,
                }
            )

    def query(self, text: str, n_results: int = 3) -> list[str]:
        return self._query_results[:n_results]

    def count(self) -> int:
        return len(self._docs)

    def delete_file(self, file_path: str) -> None:
        self._docs = [d for d in self._docs if d["file_path"] != file_path]


# ── Sample source fixtures ─────────────────────────────────────────────────────

PYTHON_SOURCE = textwrap.dedent("""\
    import os
    from pathlib import Path

    def greet(name: str) -> str:
        return f"Hello, {name}"

    class Greeter:
        def __init__(self, prefix: str) -> None:
            self.prefix = prefix

        def greet(self, name: str) -> str:
            return f"{self.prefix}, {name}"
""")

TYPESCRIPT_SOURCE = textwrap.dedent("""\
    import { readFileSync } from 'fs';

    interface Config {
        host: string;
        port: number;
    }

    function loadConfig(path: string): Config {
        const raw = readFileSync(path, 'utf-8');
        return JSON.parse(raw) as Config;
    }

    class ConfigLoader {
        constructor(private path: string) {}
        load(): Config {
            return loadConfig(this.path);
        }
    }
""")


@pytest.fixture()
def python_source() -> str:
    return PYTHON_SOURCE


@pytest.fixture()
def typescript_source() -> str:
    return TYPESCRIPT_SOURCE


@pytest.fixture()
def fake_store() -> FakeChunkStore:
    return FakeChunkStore()


@pytest.fixture()
def fake_store_with_results() -> FakeChunkStore:
    return FakeChunkStore(
        query_results=[
            "def helper(x: int) -> int:\n    return x * 2",
            "CONSTANT = 42",
        ]
    )


# ── FastAPI test client ────────────────────────────────────────────────────────


@pytest.fixture()
def api_client(fake_store) -> TestClient:
    """TestClient where ChunkStore() is replaced by FakeChunkStore.

    We patch rag.store.ChunkStore *before* importing main so that
    main.py's module-level ``store = ChunkStore()`` gets our fake
    without ever entering __init__ (which would import chromadb and
    attempt a network connection to the Chroma server).
    """
    import sys
    from unittest.mock import patch

    # Remove any cached import so the fresh import sees our patched class.
    sys.modules.pop("main", None)

    with patch("rag.store.ChunkStore", return_value=fake_store):
        from main import app

    return TestClient(app)
