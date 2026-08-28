# Dhi — Architecture Reference

> **Read this before writing any code.** Every PR should stay within the patterns described here. Deviations need an explicit decision record in `docs/decisions/`.

---

## Pattern: Layered + Repository + Protocol

The project uses three interlocking patterns applied consistently across the server and the extension. They exist to make the codebase testable without running real infrastructure (Ollama, Chroma, Redis) in CI.

---

## Backend (Python / FastAPI)

```
┌──────────────────────────────────────────────┐
│  API Layer  —  server/main.py                │
│  Owns: HTTP routing, Pydantic models,        │
│        error → HTTPException translation     │
│  Does NOT: contain business logic            │
├──────────────────────────────────────────────┤
│  Service Layer                               │
│   server/inference/fim.py   FIM completion  │
│   server/chat.py            Chat streaming  │
│   server/agents/graph.py    LangGraph loop  │
│  Owns: business logic, prompt assembly       │
│  Does NOT: know about HTTP or Chroma         │
├──────────────────────────────────────────────┤
│  Data Access Layer (Repository pattern)      │
│   server/rag/store.py   ChunkStore          │
│   server/rag/chunker.py  chunk_file()       │
│  Owns: Chroma client, embed HTTP call        │
│  Does NOT: contain business logic            │
├──────────────────────────────────────────────┤
│  Infrastructure  (Docker Compose)            │
│   Ollama · Chroma · Redis                    │
└──────────────────────────────────────────────┘
```

### Repository pattern — `ChunkStore`

`ChunkStore` is the **only** place in the codebase that knows Chroma exists. No other module may import `chromadb` directly. Tests replace `ChunkStore` with a fake that satisfies the same interface — no patching, no `unittest.mock.patch`.

### Protocol typing — `ChunkLike`

`ChunkLike` in `rag/store.py` is a structural interface (Python `typing.Protocol`). Any object with `text`, `file_path`, `start_line`, `end_line`, `language`, `node_type` attributes satisfies it. This means test fixtures, future indexers, and the chunker all interoperate without a shared base class.

### Dependency injection (manual, no framework)

Service-layer functions receive their dependencies as arguments:

```python
# CORRECT
def complete(request: FIMRequest, store: ChunkStore) -> str: ...

# WRONG — import at module level, untestable without patching
from rag.store import store as _global_store
def complete(request: FIMRequest) -> str: ...
```

The FastAPI app instantiates `ChunkStore()` once at startup and passes it through. Tests pass a `FakeChunkStore` instance directly — no `monkeypatch` needed.

### What does NOT cross layer boundaries

| Layer | May NOT import |
|---|---|
| `main.py` (API) | `chromadb`, `httpx` (inference), `tree_sitter` |
| `inference/` | `chromadb`, `fastapi`, `chat` |
| `chat.py` | `chromadb`, `fastapi`, `inference/` |
| `rag/` | `fastapi`, `agents/`, `sandbox/` |
| `platform/` | `rag/`, `inference/` |

Violations are caught by `ruff` import rules configured in `pyproject.toml`.

---

## VS Code Extension (TypeScript)

```
┌──────────────────────────────────────────────┐
│  VS Code API surface  —  src/extension.ts    │
│  Owns: activate(), registerCommand(),        │
│        subscriptions[]                       │
├──────────────────────────────────────────────┤
│  Feature modules  (one folder per feature)   │
│   src/completion/provider.ts  FIM provider  │
│   src/chat/panel.ts           Chat webview  │
│   src/agent/view.ts           Diff view     │
│  Owns: VS Code UI logic                      │
│  Does NOT: call fetch() directly             │
├──────────────────────────────────────────────┤
│  Client layer  —  src/client/index.ts        │
│  Owns: fetch(), server URL, auth header,     │
│        AbortSignal timeout                   │
│  Does NOT: know about VS Code APIs           │
└──────────────────────────────────────────────┘
```

### Why the client layer exists

The provider must not call `fetch` directly. All HTTP calls go through `DhiClient`. This means provider tests stub `DhiClient` with `sinon` — no real network calls in tests.

```typescript
// CORRECT — provider receives client, test passes a stub
class DhiCompletionProvider {
    constructor(private client: DhiClient) {}
}

// WRONG — untestable without intercepting global fetch
async function provideInlineCompletionItems(...) {
    const res = await fetch(`${SERVER_URL}/complete`, ...)
}
```

---

## Test Strategy

| Component | Type | Mocks | Never mocks |
|---|---|---|---|
| `chunker.py` | Pure unit | Nothing | — |
| `store.py` | Unit | `httpx.post` (embed), `chromadb.HttpClient` | Chunk shape |
| `fim.py` | Unit | `store.hybrid_query()`, `httpx.AsyncClient` (Ollama) | Prompt assembly logic |
| `chat.py` | Unit | `store.hybrid_query()`, `httpx.AsyncClient` (Ollama) | Context assembly logic |
| `main.py` | Integration | `ChunkStore`, `complete()`, `stream_chat()` | FastAPI routing |
| `platform/` | Unit | `redis.Redis`, `stripe` | Auth/queue/meter logic |
| Extension providers | Unit | `DhiClient` (sinon stub) | Provider logic |
| Extension client | Unit | `global.fetch` (sinon) | HTTP construction |

**Rule:** No test in `server/tests/` may start a Docker container, call a live Ollama instance, or connect to a real Chroma. Infrastructure tests live in `tests/integration/` and are excluded from the CI `pytest` run with `-m "not integration"`.

---

## Adding a New Feature — Checklist

1. Identify which layer owns it (API / Service / Data Access / Infrastructure).
2. Define the interface (Protocol or TypeScript interface) before writing the implementation.
3. Inject dependencies — no module-level singletons except in `main.py`.
4. Write unit tests first; mock at the layer boundary below yours.
5. Update this file if a new cross-layer rule applies.

---

## What is NOT used (and why)

| Skipped | Reason |
|---|---|
| ORM (SQLAlchemy etc.) | Chroma is the only persistent store; accessed only through `ChunkStore` |
| DI framework (injector, lagom) | Manual injection is sufficient and explicit at this scale |
| Microservices split | Single FastAPI process until `post-9`; `platform/` is a module, not a service |
| Abstract base classes | `Protocol` achieves the same contract without inheritance coupling |
