"""Unit tests for rag/store.py.

Mocks: httpx.post (embed API) and chromadb.HttpClient (vector store).
No real Chroma or Ollama process is started.
"""

from unittest.mock import MagicMock, patch

from rag.chunker import Chunk
from rag.store import ChunkStore, chunk_id

# ── Helpers ────────────────────────────────────────────────────────────────────


def _fake_embed_response(texts: list[str]):
    """Return a mock httpx response whose .json() gives fake embeddings."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[float(i)] * 768 for i in range(len(texts))]}
    return mock_resp


def _make_chunk(
    text: str = "def foo(): pass",
    file_path: str = "/repo/foo.py",
    start_line: int = 1,
    end_line: int = 1,
    language: str = "python",
    node_type: str = "function_definition",
) -> Chunk:
    return Chunk(
        text=text,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        language=language,
        node_type=node_type,
    )


def _make_store(chroma_mock: MagicMock) -> ChunkStore:
    """Build a ChunkStore whose Chroma client is fully mocked."""
    # chromadb is imported lazily inside ChunkStore.__init__, so patch the
    # module that __init__ will import rather than rag.store.chromadb.
    collection_mock = MagicMock()
    chroma_mock.get_or_create_collection.return_value = collection_mock
    with patch("chromadb.HttpClient", return_value=chroma_mock):
        store = ChunkStore()
    store._col = collection_mock
    return store


def _new_store(col: MagicMock) -> ChunkStore:
    """Bypass __init__ and return a ChunkStore with all fields initialised."""
    store = ChunkStore.__new__(ChunkStore)
    store._col = col
    store._bm25_corpus = {}
    store._bm25 = None
    store._bm25_ids = []
    return store


# ── chunk_id ───────────────────────────────────────────────────────────────────


class TestChunkId:
    def test_deterministic(self):
        c = _make_chunk(file_path="/a.py", start_line=5, end_line=10)
        assert chunk_id(c) == chunk_id(c)

    def test_different_files_differ(self):
        a = _make_chunk(file_path="/a.py", start_line=1, end_line=5)
        b = _make_chunk(file_path="/b.py", start_line=1, end_line=5)
        assert chunk_id(a) != chunk_id(b)

    def test_different_lines_differ(self):
        a = _make_chunk(file_path="/a.py", start_line=1, end_line=5)
        b = _make_chunk(file_path="/a.py", start_line=6, end_line=10)
        assert chunk_id(a) != chunk_id(b)

    def test_returns_hex_string(self):
        c = _make_chunk()
        result = chunk_id(c)
        assert isinstance(result, str)
        assert len(result) == 32
        int(result, 16)  # raises ValueError if not hex


# ── ChunkStore.upsert ──────────────────────────────────────────────────────────


class TestChunkStoreUpsert:
    def test_upsert_calls_embed_then_chroma(self):
        col = MagicMock()
        store = _new_store(col)

        chunk = _make_chunk()
        with patch(
            "rag.store.httpx.post", return_value=_fake_embed_response([chunk.text])
        ) as mock_post:
            store.upsert([chunk])

        mock_post.assert_called_once()
        col.upsert.assert_called_once()

    def test_upsert_empty_list_is_noop(self):
        col = MagicMock()
        store = _new_store(col)

        with patch("rag.store.httpx.post") as mock_post:
            store.upsert([])

        mock_post.assert_not_called()
        col.upsert.assert_not_called()

    def test_upsert_passes_correct_ids(self):
        col = MagicMock()
        store = _new_store(col)

        chunks = [_make_chunk(start_line=i, end_line=i) for i in range(1, 4)]
        expected_ids = [chunk_id(c) for c in chunks]

        with patch(
            "rag.store.httpx.post", return_value=_fake_embed_response([c.text for c in chunks])
        ):
            store.upsert(chunks)

        _, kwargs = col.upsert.call_args
        assert kwargs["ids"] == expected_ids

    def test_upsert_passes_correct_metadata(self):
        col = MagicMock()
        store = _new_store(col)

        chunk = _make_chunk(file_path="/repo/x.py", start_line=3, end_line=7, language="python")
        with patch("rag.store.httpx.post", return_value=_fake_embed_response([chunk.text])):
            store.upsert([chunk])

        _, kwargs = col.upsert.call_args
        meta = kwargs["metadatas"][0]
        assert meta["file_path"] == "/repo/x.py"
        assert meta["start_line"] == 3
        assert meta["end_line"] == 7
        assert meta["language"] == "python"

    def test_upsert_idempotent_same_chunk_twice(self):
        """Upserting the same chunk twice should call Chroma upsert twice
        (Chroma deduplicates by ID internally), but the IDs must be identical."""
        col = MagicMock()
        store = _new_store(col)

        chunk = _make_chunk()
        with patch("rag.store.httpx.post", return_value=_fake_embed_response([chunk.text])):
            store.upsert([chunk])
            store.upsert([chunk])

        assert col.upsert.call_count == 2
        first_ids = col.upsert.call_args_list[0][1]["ids"]
        second_ids = col.upsert.call_args_list[1][1]["ids"]
        assert first_ids == second_ids


# ── ChunkStore.query ───────────────────────────────────────────────────────────


class TestChunkStoreQuery:
    def test_query_returns_documents(self):
        col = MagicMock()
        col.count.return_value = 5
        col.query.return_value = {"documents": [["chunk A", "chunk B"]]}
        store = _new_store(col)

        with patch("rag.store.httpx.post", return_value=_fake_embed_response(["query"])):
            results = store.query("some query", n_results=2)

        assert results == ["chunk A", "chunk B"]

    def test_query_empty_store_returns_empty_list(self):
        col = MagicMock()
        col.count.return_value = 0
        store = _new_store(col)

        with patch("rag.store.httpx.post") as mock_post:
            results = store.query("anything")

        mock_post.assert_not_called()
        assert results == []

    def test_query_n_results_capped_at_collection_size(self):
        col = MagicMock()
        col.count.return_value = 2
        col.query.return_value = {"documents": [["a", "b"]]}
        store = _new_store(col)

        with patch("rag.store.httpx.post", return_value=_fake_embed_response(["q"])):
            store.query("q", n_results=10)

        _, kwargs = col.query.call_args
        assert kwargs["n_results"] == 2  # capped to collection size


# ── _rrf_merge ────────────────────────────────────────────────────────────────


class TestRrfMerge:
    def test_top_doc_in_both_lists_wins(self):
        from rag.store import _rrf_merge

        vector = ["A", "B", "C"]
        bm25 = ["A", "D", "E"]
        result = _rrf_merge(vector, bm25, n=3)
        assert result[0] == "A"

    def test_returns_at_most_n(self):
        from rag.store import _rrf_merge

        vector = ["A", "B", "C", "D"]
        bm25 = ["D", "C", "B", "A"]
        result = _rrf_merge(vector, bm25, n=2)
        assert len(result) == 2

    def test_union_of_both_lists(self):
        from rag.store import _rrf_merge

        result = _rrf_merge(["A"], ["B"], n=5)
        assert set(result) == {"A", "B"}

    def test_empty_lists_return_empty(self):
        from rag.store import _rrf_merge

        assert _rrf_merge([], [], n=5) == []

    def test_one_empty_list_returns_other(self):
        from rag.store import _rrf_merge

        result = _rrf_merge(["A", "B"], [], n=5)
        assert result == ["A", "B"]


# ── ChunkStore.bm25_query ──────────────────────────────────────────────────────


class TestChunkStoreBm25Query:
    def _store_with_corpus(self, docs: dict[str, str]) -> "ChunkStore":
        """Build a ChunkStore bypassing __init__ with a seeded BM25 corpus."""
        store = ChunkStore.__new__(ChunkStore)
        store._col = MagicMock()
        store._bm25_corpus = dict(docs)
        store._bm25 = None
        store._bm25_ids = []
        store._rebuild_bm25()
        return store

    def test_returns_empty_when_no_corpus(self):
        col = MagicMock()
        store = _new_store(col)
        assert store.bm25_query("foo") == []

    def test_returns_matching_doc(self):
        # Need >=3 docs so IDF is non-zero for terms appearing in <50% of corpus.
        store = self._store_with_corpus(
            {
                "id1": "greet hello world function",
                "id2": "add subtract multiply divide",
                "id3": "loop iterate repeat cycle",
            }
        )
        results = store.bm25_query("greet hello", n_results=1)
        assert len(results) == 1
        assert "greet" in results[0]

    def test_zero_score_docs_excluded(self):
        store = self._store_with_corpus(
            {"id1": "import os path", "id2": "import sys argv", "id3": "import json loads"}
        )
        results = store.bm25_query("completely unrelated query xyz987")
        assert results == []

    def test_respects_n_results(self):
        corpus = {f"id{i}": f"unique_{i} def func return value {i}" for i in range(10)}
        store = self._store_with_corpus(corpus)
        results = store.bm25_query("unique_0", n_results=3)
        assert len(results) <= 3

    def test_upsert_syncs_bm25_corpus(self):
        col = MagicMock()
        store = _new_store(col)

        chunk = _make_chunk(text="def helper(): return 42")
        with patch("rag.store.httpx.post", return_value=_fake_embed_response([chunk.text])):
            store.upsert([chunk])

        assert len(store._bm25_corpus) == 1
        assert store._bm25 is not None

    def test_delete_file_removes_from_corpus(self):
        col = MagicMock()
        col.get.return_value = {"ids": ["id1"]}
        store = _new_store(col)
        store._bm25_corpus = {"id1": "def foo(): pass", "id2": "def bar(): pass"}
        store._rebuild_bm25()

        store.delete_file("/repo/foo.py")

        assert "id1" not in store._bm25_corpus
        assert "id2" in store._bm25_corpus


# ── ChunkStore.hybrid_query ────────────────────────────────────────────────────


class TestChunkStoreHybridQuery:
    def test_falls_back_to_vector_when_bm25_empty(self):
        col = MagicMock()
        col.count.return_value = 2
        col.query.return_value = {"documents": [["vec_chunk_1", "vec_chunk_2"]]}
        store = _new_store(col)

        with patch("rag.store.httpx.post", return_value=_fake_embed_response(["q"])):
            results = store.hybrid_query("q", n_results=2)

        assert results == ["vec_chunk_1", "vec_chunk_2"]

    def test_merges_vector_and_bm25(self):
        col = MagicMock()
        col.count.return_value = 1
        col.query.return_value = {"documents": [["def greet(): pass"]]}
        store = _new_store(col)
        store._bm25_corpus = {
            "id_a": "def greet(): pass",
            "id_b": "def add(a, b): return a + b",
        }
        store._rebuild_bm25()

        with patch("rag.store.httpx.post", return_value=_fake_embed_response(["q"])):
            results = store.hybrid_query("greet", n_results=5)

        assert isinstance(results, list)
        assert len(results) >= 1

    def test_respects_n_results(self):
        col = MagicMock()
        col.count.return_value = 3
        col.query.return_value = {"documents": [["a", "b", "c", "d", "e", "f"]]}
        store = _new_store(col)
        store._bm25_corpus = {f"id{i}": f"doc {i}" for i in range(6)}
        store._rebuild_bm25()

        with patch("rag.store.httpx.post", return_value=_fake_embed_response(["q"])):
            results = store.hybrid_query("doc", n_results=2)

        assert len(results) <= 2


# ── ChunkStore.delete_file ─────────────────────────────────────────────────────


class TestChunkStoreDeleteFile:
    def test_delete_file_removes_matching_docs(self):
        col = MagicMock()
        col.get.return_value = {"ids": ["id1", "id2"]}
        store = _new_store(col)

        store.delete_file("/repo/foo.py")

        col.get.assert_called_once_with(where={"file_path": "/repo/foo.py"}, include=["documents"])
        col.delete.assert_called_once_with(ids=["id1", "id2"])

    def test_delete_file_no_match_skips_delete(self):
        col = MagicMock()
        col.get.return_value = {"ids": []}
        store = _new_store(col)

        store.delete_file("/repo/not_there.py")

        col.delete.assert_not_called()
