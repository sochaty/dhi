"""Unit tests for inference/fim.py.

Mocks: store.query() and httpx.post (Ollama).
The focus is prompt shape, truncation behaviour, and response parsing.
No real Ollama process is started.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inference.fim import (
    FIM_MIDDLE_TOKEN,
    FIM_PREFIX_TOKEN,
    FIM_SUFFIX_TOKEN,
    MAX_PREFIX_CHARS,
    MAX_SUFFIX_CHARS,
    FIMRequest,
    build_fim_prompt,
    complete,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _request(
    prefix: str = "def foo():\n    ",
    suffix: str = "\n    return result",
    file_path: str = "/repo/foo.py",
    language: str = "python",
) -> FIMRequest:
    return FIMRequest(
        file_path=file_path,
        prefix=prefix,
        suffix=suffix,
        language=language,
    )


def _ollama_response(text: str = "    x = 1") -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"response": text}
    return mock


def _store(results: list[str] | None = None) -> MagicMock:
    m = MagicMock()
    m.query.return_value = results or []
    return m


# ── build_fim_prompt ───────────────────────────────────────────────────────────


class TestBuildFimPrompt:
    def test_prompt_contains_all_three_tokens(self):
        prompt = build_fim_prompt(_request(), context_chunks=[])
        assert FIM_PREFIX_TOKEN in prompt
        assert FIM_SUFFIX_TOKEN in prompt
        assert FIM_MIDDLE_TOKEN in prompt

    def test_token_order_is_prefix_suffix_middle(self):
        prompt = build_fim_prompt(_request(), context_chunks=[])
        pi = prompt.index(FIM_PREFIX_TOKEN)
        si = prompt.index(FIM_SUFFIX_TOKEN)
        mi = prompt.index(FIM_MIDDLE_TOKEN)
        assert pi < si < mi

    def test_prefix_appears_between_prefix_and_suffix_tokens(self):
        req = _request(prefix="my_prefix_text", suffix="my_suffix_text")
        prompt = build_fim_prompt(req, context_chunks=[])
        pi = prompt.index(FIM_PREFIX_TOKEN) + len(FIM_PREFIX_TOKEN)
        si = prompt.index(FIM_SUFFIX_TOKEN)
        between = prompt[pi:si]
        assert "my_prefix_text" in between

    def test_suffix_appears_between_suffix_and_middle_tokens(self):
        req = _request(prefix="p", suffix="my_suffix_text")
        prompt = build_fim_prompt(req, context_chunks=[])
        si = prompt.index(FIM_SUFFIX_TOKEN) + len(FIM_SUFFIX_TOKEN)
        mi = prompt.index(FIM_MIDDLE_TOKEN)
        between = prompt[si:mi]
        assert "my_suffix_text" in between

    def test_context_chunks_appear_in_prefix_block(self):
        chunks = ["def helper(): pass", "CONSTANT = 42"]
        prompt = build_fim_prompt(_request(), context_chunks=chunks)
        pi = prompt.index(FIM_PREFIX_TOKEN) + len(FIM_PREFIX_TOKEN)
        si = prompt.index(FIM_SUFFIX_TOKEN)
        prefix_block = prompt[pi:si]
        assert "def helper(): pass" in prefix_block
        assert "CONSTANT = 42" in prefix_block

    def test_no_context_chunks_omits_repo_context_header(self):
        prompt = build_fim_prompt(_request(), context_chunks=[])
        assert "# Repo context" not in prompt

    def test_with_context_chunks_includes_repo_context_header(self):
        prompt = build_fim_prompt(_request(), context_chunks=["some chunk"])
        assert "# Repo context" in prompt

    def test_prefix_truncated_to_max_chars(self):
        long_prefix = "x" * (MAX_PREFIX_CHARS + 500)
        req = _request(prefix=long_prefix)
        prompt = build_fim_prompt(req, context_chunks=[])
        # The truncated prefix (last MAX_PREFIX_CHARS chars) should be in prompt
        assert "x" * MAX_PREFIX_CHARS in prompt
        # But the full original length should not be present as-is
        pi = prompt.index(FIM_PREFIX_TOKEN) + len(FIM_PREFIX_TOKEN)
        si = prompt.index(FIM_SUFFIX_TOKEN)
        actual_prefix = prompt[pi:si]
        assert len(actual_prefix) <= MAX_PREFIX_CHARS + 100  # small overhead for header

    def test_suffix_truncated_to_max_chars(self):
        long_suffix = "y" * (MAX_SUFFIX_CHARS + 500)
        req = _request(suffix=long_suffix)
        prompt = build_fim_prompt(req, context_chunks=[])
        si = prompt.index(FIM_SUFFIX_TOKEN) + len(FIM_SUFFIX_TOKEN)
        mi = prompt.index(FIM_MIDDLE_TOKEN)
        actual_suffix = prompt[si:mi]
        assert len(actual_suffix) == MAX_SUFFIX_CHARS

    def test_empty_prefix_and_suffix(self):
        req = _request(prefix="", suffix="")
        prompt = build_fim_prompt(req, context_chunks=[])
        assert FIM_PREFIX_TOKEN in prompt
        assert FIM_SUFFIX_TOKEN in prompt
        assert FIM_MIDDLE_TOKEN in prompt

    def test_prompt_ends_with_middle_token(self):
        prompt = build_fim_prompt(_request(), context_chunks=[])
        assert prompt.endswith(FIM_MIDDLE_TOKEN)


# ── complete() ────────────────────────────────────────────────────────────────


def _mock_client(response: MagicMock) -> MagicMock:
    """Async context manager mock for httpx.AsyncClient."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    return client


class TestComplete:
    async def test_returns_response_text(self):
        store = _store()
        with patch("inference.fim.httpx.AsyncClient", return_value=_mock_client(_ollama_response("    result = 42"))):
            result = await complete(_request(), store)
        assert result == "    result = 42"

    async def test_queries_store_with_end_of_prefix(self):
        store = _store()
        prefix = "some code\n" + "x" * 300  # last 200 chars is what gets queried
        req = _request(prefix=prefix)
        with patch("inference.fim.FIM_USE_RAG", True), \
             patch("inference.fim.httpx.AsyncClient", return_value=_mock_client(_ollama_response())):
            await complete(req, store)
        store.query.assert_called_once()
        query_arg = store.query.call_args[0][0]
        assert query_arg == prefix[-200:].strip()

    async def test_uses_file_path_as_fallback_query_when_prefix_empty(self):
        store = _store()
        req = _request(prefix="   ", file_path="/repo/utils.py")
        with patch("inference.fim.FIM_USE_RAG", True), \
             patch("inference.fim.httpx.AsyncClient", return_value=_mock_client(_ollama_response())):
            await complete(req, store)
        query_arg = store.query.call_args[0][0]
        assert query_arg == "/repo/utils.py"

    async def test_context_from_store_injected_into_prompt(self):
        store = _store(results=["def helper(): return 1"])
        captured: dict = {}

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        async def fake_post(url, json=None, **kwargs):
            captured["prompt"] = json["prompt"]
            return _ollama_response()

        client.post = fake_post

        with patch("inference.fim.FIM_USE_RAG", True), \
             patch("inference.fim.httpx.AsyncClient", return_value=client):
            await complete(_request(), store)

        assert "def helper(): return 1" in captured["prompt"]

    async def test_empty_store_results_still_completes(self):
        store = _store(results=[])
        with patch("inference.fim.httpx.AsyncClient", return_value=_mock_client(_ollama_response("x = 1"))):
            result = await complete(_request(), store)
        assert result == "x = 1"

    async def test_ollama_called_with_low_temperature(self):
        store = _store()
        captured: dict = {}

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        async def fake_post(url, json=None, **kwargs):
            captured["options"] = json["options"]
            return _ollama_response()

        client.post = fake_post

        with patch("inference.fim.httpx.AsyncClient", return_value=client):
            await complete(_request(), store)

        assert captured["options"]["temperature"] == 0.1

    async def test_ollama_called_with_stop_tokens(self):
        store = _store()
        captured: dict = {}

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        async def fake_post(url, json=None, **kwargs):
            captured["options"] = json["options"]
            return _ollama_response()

        client.post = fake_post

        with patch("inference.fim.httpx.AsyncClient", return_value=client):
            await complete(_request(), store)

        stops = captured["options"]["stop"]
        assert FIM_PREFIX_TOKEN in stops
        assert FIM_SUFFIX_TOKEN in stops
        assert "\n" in stops

    async def test_http_error_propagates(self):
        store = _store()
        error_resp = MagicMock()
        error_resp.raise_for_status.side_effect = Exception("HTTP 500")
        error_resp.json.return_value = {"response": ""}

        with patch("inference.fim.httpx.AsyncClient", return_value=_mock_client(error_resp)):
            with pytest.raises(Exception, match="HTTP 500"):
                await complete(_request(), store)

    async def test_rag_disabled_by_default_skips_store_query(self):
        store = _store(results=["def helper(): return 1"])
        with patch("inference.fim.httpx.AsyncClient", return_value=_mock_client(_ollama_response("x = 1"))):
            result = await complete(_request(), store)
        store.query.assert_not_called()
        assert result == "x = 1"
