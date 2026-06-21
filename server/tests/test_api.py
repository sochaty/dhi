"""Integration tests for FastAPI endpoints in main.py.

Uses the ``api_client`` fixture (from conftest.py) which replaces the real
ChunkStore with an in-memory FakeChunkStore and patches out Ollama via
``unittest.mock``.

Endpoints tested:
  GET  /health
  POST /complete
  POST /index
  POST /index-dir
  POST /search
  POST /chat
"""

from unittest.mock import AsyncMock, patch

# api_client, fake_store are injected by pytest from conftest.py


# ── GET /health ────────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    def test_returns_200(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200

    def test_returns_ok_status(self, api_client):
        resp = api_client.get("/health")
        assert resp.json() == {"status": "ok"}


# ── POST /complete ─────────────────────────────────────────────────────────────


_COMPLETE_PAYLOAD = {
    "file_path": "/repo/foo.py",
    "prefix": "def add(a, b):\n    ",
    "suffix": "\n    return result",
    "language": "python",
}


class TestCompleteEndpoint:
    def test_returns_200(self, api_client):
        with patch("main.complete", new_callable=AsyncMock, return_value="    result = 42"):
            resp = api_client.post("/complete", json=_COMPLETE_PAYLOAD)
        assert resp.status_code == 200

    def test_returns_completion_field(self, api_client):
        with patch("main.complete", new_callable=AsyncMock, return_value="    x = 1"):
            resp = api_client.post("/complete", json=_COMPLETE_PAYLOAD)
        assert resp.json() == {"completion": "    x = 1"}

    def test_missing_prefix_returns_422(self, api_client):
        bad = {k: v for k, v in _COMPLETE_PAYLOAD.items() if k != "prefix"}
        resp = api_client.post("/complete", json=bad)
        assert resp.status_code == 422

    def test_missing_suffix_returns_422(self, api_client):
        bad = {k: v for k, v in _COMPLETE_PAYLOAD.items() if k != "suffix"}
        resp = api_client.post("/complete", json=bad)
        assert resp.status_code == 422

    def test_missing_language_returns_422(self, api_client):
        bad = {k: v for k, v in _COMPLETE_PAYLOAD.items() if k != "language"}
        resp = api_client.post("/complete", json=bad)
        assert resp.status_code == 422

    def test_ollama_error_returns_500(self, api_client):
        with patch(
            "main.complete", new_callable=AsyncMock, side_effect=Exception("connection refused")
        ):
            resp = api_client.post("/complete", json=_COMPLETE_PAYLOAD)
        assert resp.status_code == 500

    def test_500_body_contains_error_detail(self, api_client):
        with patch("main.complete", new_callable=AsyncMock, side_effect=Exception("timeout")):
            resp = api_client.post("/complete", json=_COMPLETE_PAYLOAD)
        assert "timeout" in resp.json()["detail"]

    def test_empty_prefix_and_suffix_still_returns_200(self, api_client):
        payload = {**_COMPLETE_PAYLOAD, "prefix": "", "suffix": ""}
        with patch("main.complete", new_callable=AsyncMock, return_value=""):
            resp = api_client.post("/complete", json=payload)
        assert resp.status_code == 200


# ── POST /index ────────────────────────────────────────────────────────────────


_INDEX_PAYLOAD = {
    "file_path": "/repo/foo.py",
    "content": "def foo(): pass\ndef bar(): pass\n",
    "language": "python",
}


class TestIndexEndpoint:
    def test_returns_200_and_indexed_count(self, api_client):
        resp = api_client.post("/index", json=_INDEX_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert "indexed" in data
        assert isinstance(data["indexed"], int)
        assert data["indexed"] >= 0

    def test_missing_file_path_returns_422(self, api_client):
        resp = api_client.post("/index", json={})
        assert resp.status_code == 422

    def test_missing_content_returns_422(self, api_client):
        bad = {k: v for k, v in _INDEX_PAYLOAD.items() if k != "content"}
        resp = api_client.post("/index", json=bad)
        assert resp.status_code == 422

    def test_missing_language_returns_422(self, api_client):
        bad = {k: v for k, v in _INDEX_PAYLOAD.items() if k != "language"}
        resp = api_client.post("/index", json=bad)
        assert resp.status_code == 422

    def test_index_stores_chunks_in_fake_store(self, api_client, fake_store):
        resp = api_client.post("/index", json=_INDEX_PAYLOAD)
        assert resp.status_code == 200
        assert fake_store.count() == resp.json()["indexed"]

    def test_unsupported_language_indexes_zero_chunks(self, api_client):
        payload = {
            "file_path": "/repo/styles.css",
            "content": "body { color: red; }\n",
            "language": "css",
        }
        resp = api_client.post("/index", json=payload)
        assert resp.status_code == 200
        assert resp.json()["indexed"] == 0

    def test_store_error_returns_500(self, api_client, fake_store):
        with patch.object(fake_store, "upsert", side_effect=Exception("db error")):
            resp = api_client.post("/index", json=_INDEX_PAYLOAD)
        assert resp.status_code == 500


# ── POST /index-dir ────────────────────────────────────────────────────────────


class TestIndexDirEndpoint:
    def test_returns_200_with_counts(self, api_client, tmp_path):
        (tmp_path / "main.py").write_text("def hello(): pass\n")
        resp = api_client.post(
            "/index-dir",
            json={"dir_path": str(tmp_path), "respect_gitignore": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "indexed_files" in data
        assert "indexed_chunks" in data
        assert data["indexed_files"] >= 1

    def test_missing_dir_path_returns_422(self, api_client):
        resp = api_client.post("/index-dir", json={})
        assert resp.status_code == 422

    def test_empty_dir_returns_zero_counts(self, api_client, tmp_path):
        resp = api_client.post(
            "/index-dir",
            json={"dir_path": str(tmp_path), "respect_gitignore": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["indexed_files"] == 0
        assert data["indexed_chunks"] == 0

    def test_nonexistent_dir_returns_500(self, api_client):
        resp = api_client.post(
            "/index-dir",
            json={"dir_path": "/does/not/exist/xyzzy", "respect_gitignore": False},
        )
        assert resp.status_code == 500

    def test_indexes_multiple_files(self, api_client, tmp_path):
        (tmp_path / "a.py").write_text("def foo(): pass\n")
        (tmp_path / "b.py").write_text("def bar(): pass\n")
        resp = api_client.post(
            "/index-dir",
            json={"dir_path": str(tmp_path), "respect_gitignore": False},
        )
        assert resp.status_code == 200
        assert resp.json()["indexed_files"] == 2

    def test_respect_gitignore_default_is_true(self, api_client, tmp_path):
        (tmp_path / ".gitignore").write_text("*.py\n")
        (tmp_path / "app.py").write_text("def foo(): pass\n")
        resp = api_client.post("/index-dir", json={"dir_path": str(tmp_path)})
        assert resp.status_code == 200
        assert resp.json()["indexed_files"] == 0


# ── POST /search ───────────────────────────────────────────────────────────────


class TestSearchEndpoint:
    def test_returns_200_with_results_field(self, api_client):
        resp = api_client.post("/search", json={"query": "def greet"})
        assert resp.status_code == 200
        assert "results" in resp.json()

    def test_results_is_a_list(self, api_client):
        resp = api_client.post("/search", json={"query": "anything"})
        assert isinstance(resp.json()["results"], list)

    def test_missing_query_returns_422(self, api_client):
        resp = api_client.post("/search", json={})
        assert resp.status_code == 422

    def test_mode_hybrid_is_default(self, api_client, fake_store):
        with patch.object(fake_store, "hybrid_query", return_value=["chunk1"]) as mock_hq:
            resp = api_client.post("/search", json={"query": "greet"})
        assert resp.status_code == 200
        mock_hq.assert_called_once()

    def test_mode_bm25_calls_bm25_query(self, api_client, fake_store):
        with patch.object(fake_store, "bm25_query", return_value=["lex_chunk"]) as mock_bm:
            resp = api_client.post("/search", json={"query": "greet", "mode": "bm25"})
        assert resp.status_code == 200
        mock_bm.assert_called_once()

    def test_mode_vector_calls_query(self, api_client, fake_store):
        with patch.object(fake_store, "query", return_value=["vec_chunk"]) as mock_q:
            resp = api_client.post("/search", json={"query": "greet", "mode": "vector"})
        assert resp.status_code == 200
        mock_q.assert_called_once()

    def test_n_results_capped_at_20(self, api_client, fake_store):
        with patch.object(fake_store, "hybrid_query", return_value=[]) as mock_hq:
            api_client.post("/search", json={"query": "x", "n_results": 9999})
        args, _ = mock_hq.call_args
        assert args[1] <= 20  # second positional arg is n

    def test_n_results_minimum_is_1(self, api_client, fake_store):
        with patch.object(fake_store, "hybrid_query", return_value=[]) as mock_hq:
            api_client.post("/search", json={"query": "x", "n_results": 0})
        args, _ = mock_hq.call_args
        assert args[1] >= 1  # second positional arg is n

    def test_store_error_returns_500(self, api_client, fake_store):
        with patch.object(fake_store, "hybrid_query", side_effect=Exception("index error")):
            resp = api_client.post("/search", json={"query": "greet"})
        assert resp.status_code == 500


# ── POST /chat ─────────────────────────────────────────────────────────────────


async def _fake_stream_tokens(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    yield "Hello"
    yield " world"


async def _fake_stream_empty(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    return
    yield  # make it an async generator


async def _fake_stream_error(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    raise RuntimeError("ollama down")
    yield  # make it an async generator


class TestChatEndpoint:
    def test_returns_200(self, api_client):
        with patch("main.stream_chat", new=_fake_stream_tokens):
            resp = api_client.post("/chat", json={"message": "hello"})
        assert resp.status_code == 200

    def test_response_is_event_stream(self, api_client):
        with patch("main.stream_chat", new=_fake_stream_tokens):
            resp = api_client.post("/chat", json={"message": "hello"})
        assert "text/event-stream" in resp.headers["content-type"]

    def test_tokens_emitted_as_sse_data(self, api_client):
        with patch("main.stream_chat", new=_fake_stream_tokens):
            resp = api_client.post("/chat", json={"message": "hello"})
        assert 'data: {"token": "Hello"}' in resp.text
        assert 'data: {"token": " world"}' in resp.text

    def test_done_sentinel_is_last_event(self, api_client):
        with patch("main.stream_chat", new=_fake_stream_tokens):
            resp = api_client.post("/chat", json={"message": "hello"})
        assert resp.text.endswith("data: [DONE]\n\n")

    def test_empty_stream_sends_only_done(self, api_client):
        with patch("main.stream_chat", new=_fake_stream_empty):
            resp = api_client.post("/chat", json={"message": "hi"})
        assert resp.text == "data: [DONE]\n\n"

    def test_missing_message_returns_422(self, api_client):
        resp = api_client.post("/chat", json={})
        assert resp.status_code == 422

    def test_stream_error_emits_error_event_then_done(self, api_client):
        with patch("main.stream_chat", new=_fake_stream_error):
            resp = api_client.post("/chat", json={"message": "hello"})
        assert '"error"' in resp.text
        assert resp.text.endswith("data: [DONE]\n\n")

    def test_accepts_optional_fields(self, api_client):
        payload = {
            "message": "what does this do?",
            "file_path": "/repo/app.py",
            "language": "python",
            "file_content": "def main(): pass",
            "history": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        }
        with patch("main.stream_chat", new=_fake_stream_tokens):
            resp = api_client.post("/chat", json=payload)
        assert resp.status_code == 200
