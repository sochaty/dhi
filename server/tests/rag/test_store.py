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
    mock_resp.json.return_value = {
        "embeddings": [[float(i)] * 768 for i in range(len(texts))]
    }
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
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

        chunk = _make_chunk()
        with patch("rag.store.httpx.post", return_value=_fake_embed_response([chunk.text])) as mock_post:
            store.upsert([chunk])

        mock_post.assert_called_once()
        col.upsert.assert_called_once()

    def test_upsert_empty_list_is_noop(self):
        col = MagicMock()
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

        with patch("rag.store.httpx.post") as mock_post:
            store.upsert([])

        mock_post.assert_not_called()
        col.upsert.assert_not_called()

    def test_upsert_passes_correct_ids(self):
        col = MagicMock()
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

        chunks = [_make_chunk(start_line=i, end_line=i) for i in range(1, 4)]
        expected_ids = [chunk_id(c) for c in chunks]

        with patch("rag.store.httpx.post", return_value=_fake_embed_response([c.text for c in chunks])):
            store.upsert(chunks)

        _, kwargs = col.upsert.call_args
        assert kwargs["ids"] == expected_ids

    def test_upsert_passes_correct_metadata(self):
        col = MagicMock()
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

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
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

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
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

        with patch("rag.store.httpx.post", return_value=_fake_embed_response(["query"])):
            results = store.query("some query", n_results=2)

        assert results == ["chunk A", "chunk B"]

    def test_query_empty_store_returns_empty_list(self):
        col = MagicMock()
        col.count.return_value = 0
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

        with patch("rag.store.httpx.post") as mock_post:
            results = store.query("anything")

        mock_post.assert_not_called()
        assert results == []

    def test_query_n_results_capped_at_collection_size(self):
        col = MagicMock()
        col.count.return_value = 2
        col.query.return_value = {"documents": [["a", "b"]]}
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

        with patch("rag.store.httpx.post", return_value=_fake_embed_response(["q"])):
            store.query("q", n_results=10)

        _, kwargs = col.query.call_args
        assert kwargs["n_results"] == 2  # capped to collection size


# ── ChunkStore.delete_file ─────────────────────────────────────────────────────

class TestChunkStoreDeleteFile:
    def test_delete_file_removes_matching_docs(self):
        col = MagicMock()
        col.get.return_value = {"ids": ["id1", "id2"]}
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

        store.delete_file("/repo/foo.py")

        col.get.assert_called_once_with(
            where={"file_path": "/repo/foo.py"}, include=["documents"]
        )
        col.delete.assert_called_once_with(ids=["id1", "id2"])

    def test_delete_file_no_match_skips_delete(self):
        col = MagicMock()
        col.get.return_value = {"ids": []}
        store = ChunkStore.__new__(ChunkStore)
        store._col = col

        store.delete_file("/repo/not_there.py")

        col.delete.assert_not_called()
