"""Tests for chat.py — context assembly and streaming."""

from unittest.mock import MagicMock

import httpx
import respx

from chat import (
    _MAX_CHUNK_CHARS,
    _MAX_CHUNKS,
    _MAX_FILE_CHARS,
    _MAX_HISTORY_TURNS,
    _SYSTEM_PROMPT,
    ChatMessage,
    ChatRequest,
    assemble_prompt,
    stream_chat,
)

# ── assemble_prompt ────────────────────────────────────────────────────────────


class TestAssemblePrompt:
    def test_always_includes_system_prompt(self) -> None:
        req = ChatRequest(message="hello")
        assert _SYSTEM_PROMPT in assemble_prompt(req, [])

    def test_always_includes_user_message(self) -> None:
        req = ChatRequest(message="How does foo work?")
        assert "How does foo work?" in assemble_prompt(req, [])

    def test_ends_with_assistant_label(self) -> None:
        req = ChatRequest(message="hello")
        assert assemble_prompt(req, []).endswith("Assistant:")

    def test_includes_file_content(self) -> None:
        req = ChatRequest(
            message="explain",
            file_path="foo.py",
            language="python",
            file_content="def foo(): pass",
        )
        prompt = assemble_prompt(req, [])
        assert "def foo(): pass" in prompt
        assert "```python" in prompt
        assert "foo.py" in prompt

    def test_trims_long_file_content(self) -> None:
        req = ChatRequest(message="x", file_content="a" * (_MAX_FILE_CHARS + 500))
        prompt = assemble_prompt(req, [])
        assert "a" * (_MAX_FILE_CHARS + 1) not in prompt
        assert "a" * _MAX_FILE_CHARS in prompt

    def test_omits_file_block_when_content_empty(self) -> None:
        req = ChatRequest(message="x", file_path="foo.py", file_content="")
        prompt = assemble_prompt(req, [])
        assert "Active file" not in prompt

    def test_includes_rag_chunks(self) -> None:
        req = ChatRequest(message="x")
        prompt = assemble_prompt(req, ["def helper(): pass"])
        assert "def helper(): pass" in prompt
        assert "Relevant code" in prompt

    def test_trims_long_rag_chunks(self) -> None:
        req = ChatRequest(message="x")
        long_chunk = "z" * (_MAX_CHUNK_CHARS + 200)
        prompt = assemble_prompt(req, [long_chunk])
        assert "z" * (_MAX_CHUNK_CHARS + 1) not in prompt
        assert "z" * _MAX_CHUNK_CHARS in prompt

    def test_caps_rag_chunk_count(self) -> None:
        req = ChatRequest(message="x")
        chunks = [f"chunk{i}" for i in range(_MAX_CHUNKS + 2)]
        prompt = assemble_prompt(req, chunks)
        for i in range(_MAX_CHUNKS):
            assert f"chunk{i}" in prompt
        assert f"chunk{_MAX_CHUNKS}" not in prompt

    def test_includes_conversation_history(self) -> None:
        req = ChatRequest(
            message="follow up",
            history=[
                ChatMessage(role="user", content="first question"),
                ChatMessage(role="assistant", content="first answer"),
            ],
        )
        prompt = assemble_prompt(req, [])
        assert "first question" in prompt
        assert "first answer" in prompt

    def test_trims_old_history_turns(self) -> None:
        history = []
        for i in range(_MAX_HISTORY_TURNS + 3):
            history.append(ChatMessage(role="user", content=f"msg{i}"))
            history.append(ChatMessage(role="assistant", content=f"ans{i}"))
        req = ChatRequest(message="now", history=history)
        prompt = assemble_prompt(req, [])
        assert "msg0" not in prompt
        assert f"msg{_MAX_HISTORY_TURNS + 2}" in prompt

    def test_no_rag_section_when_chunks_empty(self) -> None:
        req = ChatRequest(message="x")
        assert "Relevant code" not in assemble_prompt(req, [])


# ── stream_chat ────────────────────────────────────────────────────────────────


class TestStreamChat:
    @respx.mock
    async def test_yields_tokens(self) -> None:
        content = (
            b'{"response": "Hello", "done": false}\n' b'{"response": " world", "done": true}\n'
        )
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=httpx.Response(200, content=content)
        )
        store = MagicMock()
        store.hybrid_query.return_value = []

        tokens = [t async for t in stream_chat(ChatRequest(message="hi"), store)]
        assert tokens == ["Hello", " world"]

    @respx.mock
    async def test_queries_store_with_message(self) -> None:
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=httpx.Response(200, content=b'{"response":"x","done":true}\n')
        )
        store = MagicMock()
        store.hybrid_query.return_value = []

        req = ChatRequest(message="find the bug")
        [t async for t in stream_chat(req, store)]

        store.hybrid_query.assert_called_once_with("find the bug", n_results=_MAX_CHUNKS)

    @respx.mock
    async def test_skips_store_query_for_empty_message(self) -> None:
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=httpx.Response(200, content=b'{"response":"x","done":true}\n')
        )
        store = MagicMock()
        store.hybrid_query.return_value = []

        [t async for t in stream_chat(ChatRequest(message="   "), store)]
        store.hybrid_query.assert_not_called()

    @respx.mock
    async def test_stops_on_done_flag(self) -> None:
        content = (
            b'{"response": "tok1", "done": false}\n'
            b'{"response": "tok2", "done": true}\n'
            b'{"response": "tok3", "done": false}\n'
        )
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=httpx.Response(200, content=content)
        )
        store = MagicMock()
        store.hybrid_query.return_value = []

        tokens = [t async for t in stream_chat(ChatRequest(message="hi"), store)]
        assert tokens == ["tok1", "tok2"]
        assert "tok3" not in tokens

    @respx.mock
    async def test_skips_empty_token_lines(self) -> None:
        content = b'{"response": "", "done": false}\n' b'{"response": "real", "done": true}\n'
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=httpx.Response(200, content=content)
        )
        store = MagicMock()
        store.hybrid_query.return_value = []

        tokens = [t async for t in stream_chat(ChatRequest(message="hi"), store)]
        assert tokens == ["real"]
