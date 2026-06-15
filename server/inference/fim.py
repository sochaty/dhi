import logging
import os
import re
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
FIM_MODEL = os.getenv("FIM_MODEL", "starcoder2:3b")
FIM_MODEL_MAX_TOKENS = int(os.getenv("FIM_MODEL_MAX_TOKENS", "10"))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
# Small models (≤7B) hallucinate from RAG context — they copy retrieved chunks
# instead of using them as reference.  Enable only when using a larger model.
FIM_USE_RAG = os.getenv("FIM_USE_RAG", "false").lower() == "true"

# Supported by StarCoder2, DeepSeek-Coder, and Qwen2.5-Coder
FIM_PREFIX_TOKEN = "<fim_prefix>"
FIM_SUFFIX_TOKEN = "<fim_suffix>"
FIM_MIDDLE_TOKEN = "<fim_middle>"

# Keep context tiny — CPU prefill is ~10 tok/s; 3200 chars = ~900 tokens = 90 s timeout.
# 512 chars ≈ 130 tokens → ~13 s prefill; generation stops at first "\n" (1–5 tokens).
MAX_PREFIX_CHARS = 256
MAX_SUFFIX_CHARS = 128
# Search the last N chars of prefix for the context query
QUERY_WINDOW = 200


@dataclass
class FIMRequest:
    file_path: str
    prefix: str
    suffix: str
    language: str


_NEXT_SCOPE_RE = re.compile(r"\n(?:async )?def |\nclass ")
_DEF_RE = re.compile(r"^(?:async )?def |^class ", re.MULTILINE)


def _trim_prefix(prefix: str, max_chars: int) -> str:
    """Take the last max_chars of prefix, then advance to the most recent
    function/class definition so that section-header comments (# --- X ---)
    before it don't corrupt the FIM prompt.
    """
    raw = prefix[-max_chars:]
    # Find the last def/class inside the window
    last = None
    for m in _DEF_RE.finditer(raw):
        last = m
    if last and last.start() > 0:
        return raw[last.start() :]
    return raw


def _trim_suffix(suffix: str, max_chars: int) -> str:
    """Stop at the next top-level def/class boundary, or max_chars — whichever comes first.

    128 raw chars of suffix can slice into an adjacent function and confuse the
    model.  Stopping at the next function boundary gives a semantically clean
    suffix (just the remainder of the current scope).
    """
    match = _NEXT_SCOPE_RE.search(suffix)
    limit = match.start() if match else len(suffix)
    return suffix[: min(max_chars, limit)]


def build_fim_prompt(request: FIMRequest, context_chunks: list[str]) -> str:
    """Assemble the FIM prompt with an optional repo-context block.

    Layout
    ------
    <fim_prefix>
    # Repo context          ← omitted when context_chunks is empty
    {chunk_1}
    ...
    {chunk_N}

    # Current file
    {prefix_truncated}
    <fim_suffix>
    {suffix_truncated}
    <fim_middle>
    """

    # Normalize Windows CRLF → LF; bare \r (old Mac) → LF.
    # StarCoder2 was trained on Unix line endings — CRLF in the prompt causes
    # hallucinations because \r is not in the stop-token list.
    def _lf(s: str) -> str:
        return s.replace("\r\n", "\n").replace("\r", "\n")

    prefix = _lf(_trim_prefix(request.prefix, MAX_PREFIX_CHARS))
    suffix = _lf(_trim_suffix(request.suffix, MAX_SUFFIX_CHARS))

    if context_chunks:
        context_block = "\n\n".join(context_chunks)
        fim_prefix_content = f"# Repo context\n{context_block}\n\n# Current file\n{prefix}"
    else:
        fim_prefix_content = prefix

    return (
        f"{FIM_PREFIX_TOKEN}"
        f"{fim_prefix_content}"
        f"{FIM_SUFFIX_TOKEN}"
        f"{suffix}"
        f"{FIM_MIDDLE_TOKEN}"
    )


async def complete(request: FIMRequest, store) -> str:
    """Run a FIM completion via Ollama and return the generated text.

    ``store`` is typed as Any to avoid a circular import; it must expose a
    ``query(text: str, n_results: int) -> list[str]`` method.

    Using async httpx so that cancellation propagates: when the VS Code
    extension aborts its HTTP connection (user typed again), FastAPI cancels
    this coroutine, which closes the TCP connection to Ollama, which causes
    Ollama's Go request context to cancel mid-generation — releasing the GPU/CPU
    for the next request instead of holding it for 5–7 seconds.
    """
    query_text = request.prefix[-QUERY_WINDOW:].strip() or request.file_path
    context_chunks: list[str] = store.query(query_text, n_results=3) if FIM_USE_RAG else []

    prompt = build_fim_prompt(request, context_chunks)

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(
            f"http://{OLLAMA_HOST}:11434/api/generate",
            json={
                "model": FIM_MODEL,
                "prompt": prompt,
                "raw": True,
                "stream": False,
                "options": {
                    "num_predict": FIM_MODEL_MAX_TOKENS,
                    "temperature": 0.1,
                    "stop": [
                        "\n",
                        FIM_PREFIX_TOKEN,
                        FIM_SUFFIX_TOKEN,
                        FIM_MIDDLE_TOKEN,
                        "<|endoftext|>",
                    ],
                },
            },
        )
    resp.raise_for_status()
    data = resp.json()
    log.info(
        "FIM done_reason=%s response=%r prompt_tail=%r",
        data.get("done_reason"),
        data.get("response", ""),
        prompt[-120:],
    )
    return data["response"]
