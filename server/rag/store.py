"""Chunk store: vector search (Chroma) + BM25, merged with RRF.

Architecture rule: this is the ONLY module that imports chromadb.

Hybrid search pipeline
──────────────────────
query ──► nomic-embed-text ──► Chroma cosine ANN ──► top-2N vector results ┐
      └──────────────────────── BM25 Okapi ──────────── top-2N BM25 results ─┴► RRF ──► top-N
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from typing import Any, Protocol

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


# ── Embedding ─────────────────────────────────────────────────────────────────


def _embed(texts: list[str]) -> list[list[float]]:
    resp = httpx.post(
        f"http://{OLLAMA_HOST}:11434/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


# ── Chunk identity ─────────────────────────────────────────────────────────────


def chunk_id(chunk: ChunkLike) -> str:
    """Deterministic ID so re-indexing a file replaces rather than duplicates."""
    key = f"{chunk.file_path}:{chunk.start_line}:{chunk.end_line}"
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()


# ── RRF merge ─────────────────────────────────────────────────────────────────


def _rrf_merge(
    vector_hits: list[str],
    bm25_hits: list[str],
    n: int,
    k: int = 60,
) -> list[str]:
    """Reciprocal Rank Fusion — combine two ranked lists into one.

    score(doc) = Σ  1 / (k + rank_i + 1)
    Higher score = more relevant.  k=60 is the standard default.
    """
    scores: dict[str, float] = {}
    for rank, doc in enumerate(vector_hits):
        scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank + 1)
    for rank, doc in enumerate(bm25_hits):
        scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda d: scores[d], reverse=True)[:n]


# ── BM25 helpers ──────────────────────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokeniser — fast, language-agnostic."""
    return text.lower().split()


# ── ChunkStore ────────────────────────────────────────────────────────────────


class ChunkStore:
    def __init__(self, *, host: str = CHROMA_HOST, port: int = CHROMA_PORT) -> None:
        import chromadb  # lazy — avoids import-time numpy crash in unit tests

        client = chromadb.HttpClient(host=host, port=port)
        self._col = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        # In-memory BM25 corpus: id → text.  Seeded from Chroma on startup so
        # restarts don't lose the lexical index.
        self._bm25_corpus: dict[str, str] = {}
        self._bm25: Any = None  # BM25Okapi | None
        self._init_bm25()

    # ── BM25 lifecycle ────────────────────────────────────────────────────────

    def _init_bm25(self) -> None:
        """Seed the in-memory BM25 corpus from Chroma on startup."""
        if self._col.count() == 0:
            return
        result = self._col.get(include=["documents", "metadatas"])
        for cid, doc in zip(result["ids"], result["documents"] or []):
            if doc:
                self._bm25_corpus[cid] = doc
        self._rebuild_bm25()

    def _rebuild_bm25(self) -> None:
        if not self._bm25_corpus:
            self._bm25 = None
            return
        try:
            from rank_bm25 import BM25Okapi  # optional dep
        except ImportError:
            self._bm25 = None
            return
        corpus = list(self._bm25_corpus.values())
        self._bm25 = BM25Okapi([_tokenize(t) for t in corpus])
        # Keep an ordered list of ids that matches the BM25 corpus array index.
        self._bm25_ids: list[str] = list(self._bm25_corpus.keys())

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert(self, chunks: Sequence[ChunkLike]) -> None:
        """Idempotent upsert — safe to call on every file save."""
        if not chunks:
            return
        ids = [chunk_id(c) for c in chunks]
        texts = [c.text for c in chunks]
        embeddings: list[Any] = _embed(texts)
        metadatas: list[Any] = [
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
        # Sync BM25 corpus — update entries in place so rebuilds are minimal.
        for cid, text in zip(ids, texts):
            self._bm25_corpus[cid] = text
        self._rebuild_bm25()

    def delete_file(self, file_path: str) -> None:
        """Remove all chunks belonging to a file."""
        results = self._col.get(where={"file_path": file_path}, include=["documents"])
        if not results["ids"]:
            return
        self._col.delete(ids=results["ids"])
        for cid in results["ids"]:
            self._bm25_corpus.pop(cid, None)
        self._rebuild_bm25()

    # ── Read ──────────────────────────────────────────────────────────────────

    def query(self, text: str, n_results: int = 3) -> list[str]:
        """Vector-only search (kept for backward compatibility)."""
        return self._vector_query(text, n_results)

    def bm25_query(self, text: str, n_results: int = 5) -> list[str]:
        """Lexical BM25 search — exact keyword matches."""
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(text))
        # Pair each corpus entry with its score, sort descending, take top-N.
        ranked = sorted(
            zip(self._bm25_ids, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        return [
            self._bm25_corpus[cid]
            for cid, score in ranked[:n_results]
            if score > 0 and cid in self._bm25_corpus
        ]

    def hybrid_query(self, text: str, n_results: int = 5) -> list[str]:
        """Hybrid search: vector + BM25 merged with Reciprocal Rank Fusion."""
        fetch = n_results * 2
        vector_hits = self._vector_query(text, fetch)
        bm25_hits = self.bm25_query(text, fetch)
        if not bm25_hits:
            return vector_hits[:n_results]
        return _rrf_merge(vector_hits, bm25_hits, n_results)

    def count(self) -> int:
        return self._col.count()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _vector_query(self, text: str, n_results: int) -> list[str]:
        count = self._col.count()
        if count == 0:
            return []
        embeddings: list[Any] = _embed([text])
        results = self._col.query(
            query_embeddings=embeddings,
            n_results=min(n_results, count),
            include=["documents"],
        )
        docs = results["documents"]
        return docs[0] if docs is not None else []
