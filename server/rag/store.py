import hashlib
import os
from collections.abc import Sequence
from typing import Protocol

import httpx

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
COLLECTION_NAME = "dhi_chunks"


class ChunkLike(Protocol):
    text: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    node_type: str


def _embed(texts: list[str]) -> list[list[float]]:
    resp = httpx.post(
        f"http://{OLLAMA_HOST}:11434/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def chunk_id(chunk: ChunkLike) -> str:
    """Deterministic ID so re-indexing a file replaces rather than duplicates chunks."""
    key = f"{chunk.file_path}:{chunk.start_line}:{chunk.end_line}"
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()


class ChunkStore:
    def __init__(self, *, host: str = CHROMA_HOST, port: int = CHROMA_PORT) -> None:
        import chromadb  # lazy — avoids import-time numpy crash in unit tests
        client = chromadb.HttpClient(host=host, port=port)
        self._col = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Write ──────────────────────────────────────────────────────────────────

    def upsert(self, chunks: Sequence[ChunkLike]) -> None:
        """Idempotent upsert — safe to call on every file save."""
        if not chunks:
            return
        ids = [chunk_id(c) for c in chunks]
        texts = [c.text for c in chunks]
        embeddings = _embed(texts)
        metadatas = [
            {
                "file_path": c.file_path,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "language": c.language,
                "node_type": c.node_type,
            }
            for c in chunks
        ]
        self._col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def delete_file(self, file_path: str) -> None:
        """Remove all chunks belonging to a file (e.g. on file deletion)."""
        results = self._col.get(where={"file_path": file_path}, include=["documents"])
        if results["ids"]:
            self._col.delete(ids=results["ids"])

    # ── Read ───────────────────────────────────────────────────────────────────

    def query(self, text: str, n_results: int = 3) -> list[str]:
        """Return the top-N most relevant chunk texts for a query string."""
        count = self._col.count()
        if count == 0:
            return []
        embeddings = _embed([text])
        results = self._col.query(
            query_embeddings=embeddings,
            n_results=min(n_results, count),
            include=["documents"],
        )
        return results["documents"][0]

    def count(self) -> int:
        return self._col.count()
