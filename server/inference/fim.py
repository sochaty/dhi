import os
from dataclasses import dataclass

import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
FIM_MODEL = os.getenv("FIM_MODEL", "starcoder2:3b")
FIM_MODEL_MAX_TOKENS = int(os.getenv("FIM_MODEL_MAX_TOKENS", "64"))

# Supported by StarCoder2, DeepSeek-Coder, and Qwen2.5-Coder
FIM_PREFIX_TOKEN = "<fim_prefix>"
FIM_SUFFIX_TOKEN = "<fim_suffix>"
FIM_MIDDLE_TOKEN = "<fim_middle>"

# Truncate to avoid quadratic prompt-processing cost on long files
MAX_PREFIX_CHARS = 3_200
MAX_SUFFIX_CHARS = 1_600
# Search the last N chars of prefix for the context query
QUERY_WINDOW = 200


@dataclass
class FIMRequest:
    file_path: str
    prefix: str
    suffix: str
    language: str


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
    prefix = request.prefix[-MAX_PREFIX_CHARS:]
    suffix = request.suffix[:MAX_SUFFIX_CHARS]

    if context_chunks:
        context_block = "\n\n".join(context_chunks)
        fim_prefix_content = (
            f"# Repo context\n{context_block}\n\n# Current file\n{prefix}"
        )
    else:
        fim_prefix_content = prefix

    return (
        f"{FIM_PREFIX_TOKEN}"
        f"{fim_prefix_content}"
        f"{FIM_SUFFIX_TOKEN}"
        f"{suffix}"
        f"{FIM_MIDDLE_TOKEN}"
    )


def complete(request: FIMRequest, store) -> str:
    """Run a FIM completion via Ollama and return the generated text.

    ``store`` is typed as Any to avoid a circular import; it must expose a
    ``query(text: str, n_results: int) -> list[str]`` method.
    """
    query_text = request.prefix[-QUERY_WINDOW:].strip() or request.file_path
    context_chunks: list[str] = store.query(query_text, n_results=3)

    prompt = build_fim_prompt(request, context_chunks)

    resp = httpx.post(
        f"http://{OLLAMA_HOST}:11434/api/generate",
        json={
            "model": FIM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": FIM_MODEL_MAX_TOKENS,
                "temperature": 0.1,
                "stop": ["\n\n", FIM_PREFIX_TOKEN, FIM_SUFFIX_TOKEN],
            },
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["response"]
