"""Integration tests for FastAPI endpoints in main.py.

Uses the ``api_client`` fixture (from conftest.py) which replaces the real
ChunkStore with an in-memory FakeChunkStore and patches out Ollama via
``unittest.mock``.

Endpoints tested:
  GET  /health
  POST /complete
  POST /index
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
        with patch("main.complete", new_callable=AsyncMock, side_effect=Exception("connection refused")):
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
