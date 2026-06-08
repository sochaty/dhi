"""Integration tests for FastAPI endpoints in main.py.

Uses the ``api_client`` fixture (from conftest.py) which replaces the real
ChunkStore with an in-memory FakeChunkStore and patches out Ollama via
``unittest.mock.patch``.

Endpoints tested:
  GET  /health
  POST /complete
  POST /index
"""

from unittest.mock import MagicMock, patch

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

def _ollama_ok(text: str = "    result = 42") -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"response": text}
    return m


_COMPLETE_PAYLOAD = {
    "file_path": "/repo/foo.py",
    "prefix": "def add(a, b):\n    ",
    "suffix": "\n    return result",
    "language": "python",
}


class TestCompleteEndpoint:
    def test_returns_200(self, api_client):
        with patch("inference.fim.httpx.post", return_value=_ollama_ok()):
            resp = api_client.post("/complete", json=_COMPLETE_PAYLOAD)
        assert resp.status_code == 200

    def test_returns_completion_field(self, api_client):
        with patch("inference.fim.httpx.post", return_value=_ollama_ok("    x = 1")):
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
        err_resp = MagicMock()
        err_resp.raise_for_status.side_effect = Exception("connection refused")
        with patch("inference.fim.httpx.post", return_value=err_resp):
            resp = api_client.post("/complete", json=_COMPLETE_PAYLOAD)
        assert resp.status_code == 500

    def test_500_body_contains_error_detail(self, api_client):
        err_resp = MagicMock()
        err_resp.raise_for_status.side_effect = Exception("timeout")
        with patch("inference.fim.httpx.post", return_value=err_resp):
            resp = api_client.post("/complete", json=_COMPLETE_PAYLOAD)
        assert "timeout" in resp.json()["detail"]

    def test_empty_prefix_and_suffix_still_returns_200(self, api_client):
        payload = {**_COMPLETE_PAYLOAD, "prefix": "", "suffix": ""}
        with patch("inference.fim.httpx.post", return_value=_ollama_ok()):
            resp = api_client.post("/complete", json=payload)
        assert resp.status_code == 200


# ── POST /index ────────────────────────────────────────────────────────────────

class TestIndexEndpoint:
    def test_returns_200_and_indexed_count(self, api_client, tmp_path):
        src_file = tmp_path / "sample.py"
        src_file.write_text("def foo(): pass\ndef bar(): pass\n", encoding="utf-8")

        resp = api_client.post("/index", json={"file_path": str(src_file)})
        assert resp.status_code == 200
        data = resp.json()
        assert "indexed" in data
        assert isinstance(data["indexed"], int)
        assert data["indexed"] >= 0

    def test_nonexistent_file_returns_500(self, api_client):
        resp = api_client.post("/index", json={"file_path": "/nonexistent/file.py"})
        assert resp.status_code == 500

    def test_missing_file_path_returns_422(self, api_client):
        resp = api_client.post("/index", json={})
        assert resp.status_code == 422

    def test_index_stores_chunks_in_fake_store(self, api_client, fake_store, tmp_path):
        src_file = tmp_path / "module.py"
        src_file.write_text(
            "def alpha(): pass\ndef beta(): pass\n", encoding="utf-8"
        )

        resp = api_client.post("/index", json={"file_path": str(src_file)})
        assert resp.status_code == 200

        count = fake_store.count()
        assert count == resp.json()["indexed"]

    def test_unsupported_extension_indexes_zero_chunks(self, api_client, tmp_path):
        css_file = tmp_path / "styles.css"
        css_file.write_text("body { color: red; }\n", encoding="utf-8")

        resp = api_client.post("/index", json={"file_path": str(css_file)})
        assert resp.status_code == 200
        assert resp.json()["indexed"] == 0
