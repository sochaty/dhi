"""Streaming chat endpoint — context assembly + Ollama token stream.

Context slot order (highest → lowest trim priority):
  1. System prompt  (fixed, never trimmed)
  2. User message   (never trimmed)
  3. Active file    (trimmed to _MAX_FILE_CHARS)
  4. RAG chunks     (top _MAX_CHUNKS, each trimmed to _MAX_CHUNK_CHARS)
  5. History        (last _MAX_HISTORY_TURNS turns × 2 messages)
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import httpx

CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.2:3b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
_OLLAMA_CONNECT_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "30"))
# No read deadline for streaming — model generation can take arbitrarily long.
_STREAM_TIMEOUT = httpx.Timeout(connect=_OLLAMA_CONNECT_TIMEOUT, read=None, write=30.0, pool=10.0)

_SYSTEM_PROMPT = (
    "You are Dhi, a coding assistant embedded in VS Code. "
    "Answer concisely. Prefer working code examples over long explanations. "
    "If you are unsure, say so."
)
_MAX_FILE_CHARS = 2_000
_MAX_CHUNK_CHARS = 400
_MAX_CHUNKS = 3
_MAX_HISTORY_TURNS = 4  # turns = user+assistant pairs; stored as 2× messages


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ChatRequest:
    message: str
    file_path: str = ""
    language: str = ""
    file_content: str = ""
    history: list[ChatMessage] = field(default_factory=list)


def assemble_prompt(request: ChatRequest, rag_chunks: list[str]) -> str:
    """Build a flat-string prompt from prioritised context slots."""
    parts: list[str] = [_SYSTEM_PROMPT]

    if request.file_content:
        content = request.file_content[:_MAX_FILE_CHARS]
        lang = request.language or "text"
        parts.append(f"# Active file: {request.file_path}\n```{lang}\n{content}\n```")

    if rag_chunks:
        trimmed = [c[:_MAX_CHUNK_CHARS] for c in rag_chunks[:_MAX_CHUNKS]]
        parts.append("# Relevant code from this repo\n" + "\n---\n".join(trimmed))

    for msg in request.history[-(_MAX_HISTORY_TURNS * 2) :]:
        label = "User" if msg.role == "user" else "Assistant"
        parts.append(f"{label}: {msg.content}")

    parts.append(f"User: {request.message}\nAssistant:")
    return "\n\n".join(parts)


async def stream_chat(request: ChatRequest, store: Any) -> AsyncGenerator[str, None]:
    """Yield response tokens from Ollama, streaming one token at a time."""
    rag_chunks: list[str] = []
    if request.message.strip():
        rag_chunks = store.hybrid_query(request.message, n_results=_MAX_CHUNKS)

    prompt = assemble_prompt(request, rag_chunks)

    async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"http://{OLLAMA_HOST}:11434/api/generate",
            json={
                "model": CHAT_MODEL,
                "prompt": prompt,
                "stream": True,
                "options": {"temperature": 0.7},
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token: str = data.get("response", "")
                if token:
                    yield token
                if data.get("done"):
                    break
