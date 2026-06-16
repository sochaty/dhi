# Dhi (धी) — Open-Source AI Coding IDE

> *"Pure intelligence for your code. Open source."*

[![CI](https://github.com/sochaty/dhi/actions/workflows/ci.yml/badge.svg)](https://github.com/sochaty/dhi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sochaty.dhi?label=VS%20Code)](https://marketplace.visualstudio.com/items?itemName=sochaty.dhi)

**Tired of $20/month AI IDEs and per-token pricing?**

Dhi gives you FIM autocomplete, in-editor chat, and multi-file agent editing — powered entirely by open-source models. Run locally on your laptop or use our shared GPU pool for ~$3/month. No API keys. No rate limits. No surprises.

---

## What works today

| Feature | Status |
|---|---|
| FIM ghost-text autocomplete (Python, TS, JS, Go, Rust, Java) | ✅ Post 1 |
| RAG-based context retrieval (Chroma + nomic-embed-text) | ✅ Post 1 |
| Workspace indexing via `Dhi: Index Workspace` command | ✅ Post 1 |
| In-editor chat panel | 🚧 Post 3 |
| Multi-file agent editing | 🚧 Post 4 |
| Shared GPU inference pool | 🚧 Post 11 |

---

## Why Dhi?

| Feature | Cursor | Copilot | Continue.dev | **Dhi** |
|---|---|---|---|---|
| Open source | ✗ | ✗ | ✓ | **✓** |
| Managed inference | ✓ (closed) | ✓ (closed) | ✗ (BYOK) | **✓ (open)** |
| Self-hostable | ✗ | ✗ | ✓ | **✓** |
| Price | $20/mo | $10–19/mo | Free + API costs | **Free + ~$3/mo** |
| FIM autocomplete | ✓ | ✓ | ✓ | **✓** |
| Multi-file agent | ✓ | ✗ | ✗ | **✓ (Post 4)** |
| Local model | ✗ | ✗ | ✓ | **✓** |

---

## Quickstart

**Prerequisites**
- [Docker Desktop 4.x](https://www.docker.com/products/docker-desktop/) with at least **6 GB RAM** allocated to Docker
- VS Code 1.90+
- 8 GB free disk space (model weights)

### Step 1 — Start the server stack

**Linux / macOS**
```bash
git clone https://github.com/sochaty/dhi
cd dhi
./scripts/bootstrap.sh      # detects GPU, picks model, pulls weights, starts containers
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/sochaty/dhi
cd dhi
docker compose up -d
```

On first run Ollama downloads `starcoder2:3b` (~1.7 GB). Track progress:
```bash
docker compose logs -f ollama
# wait for: "Models ready."
```

Verify the server is up:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### Step 2 — Install the VS Code extension

Download `dhi-0.1.0.vsix` from the [latest GitHub release](https://github.com/sochaty/dhi/releases/latest), then:

```
Extensions panel (Ctrl+Shift+X) → ⋯ menu → Install from VSIX…
```

Or build from source:
```bash
cd extension
npm install
npx vsce package --out dhi.vsix
# install dhi.vsix via the Extensions panel
```

### Step 3 — Index your workspace (optional but recommended)

```
Ctrl+Shift+P → Dhi: Index Workspace
```

This reads your source files, chunks them with Tree-sitter, embeds them with `nomic-embed-text`, and stores them in Chroma. Completions work without indexing, but indexed workspaces get relevant context from across the repo.

### Step 4 — Start coding

Open any `.py`, `.ts`, `.tsx`, `.js`, `.go`, `.rs`, or `.java` file.  
Type a function body, pause for 2–8 seconds, and ghost text appears.

```python
def add(a, b):
    return              # ← cursor here, pause → ghost: a + b
```

Accept with `Tab`. Dismiss with `Escape`.

> **Completion latency** depends on your hardware and model tier — see the [Models](#models) section below.  
> On CPU with `starcoder2:1b`, expect **2–5 seconds**. With a GPU and `starcoder2:3b`, expect **< 1 second**.

---

## Models

Choose the model that fits your hardware by setting `FIM_MODEL` in a `.env` file at the repo root before running `docker compose up`.

| Tier | Model | VRAM | Latency (CPU) | Latency (GPU) | HumanEval |
|---|---|---|---|---|---|
| **CPU (recommended start)** | `starcoder2:1b` | 0 GB | 2–5 s | — | 27% |
| Default | `starcoder2:3b` | 6 GB | 8–15 s | < 1 s | 46% |
| Quality | `deepseek-coder-v2:16b` | 12 GB | — | 1–2 s | 73% |
| Max | `qwen2.5-coder:32b` | 24 GB | — | 2–4 s | 90% |

**Example `.env` for CPU users:**
```env
FIM_MODEL=starcoder2:1b
EMBED_MODEL=nomic-embed-text
FIM_MODEL_MAX_TOKENS=10
```

Full model registry: [models/registry.yaml](models/registry.yaml)

---

## Configuration

All extension settings live under the `dhi.*` namespace in VS Code settings.

| Setting | Default | Description |
|---|---|---|
| `dhi.serverUrl` | `http://localhost:8000` | FastAPI server URL |
| `dhi.completionEnabled` | `true` | Toggle ghost-text completions on/off |
| `dhi.completionDebounceMs` | `150` | Milliseconds to wait after last keystroke before fetching |

All server tunables are set via environment variables (`.env` file or `docker compose` override):

| Variable | Default | Description |
|---|---|---|
| `FIM_MODEL` | `starcoder2:3b` | Ollama model tag for FIM completions |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama model tag for embeddings |
| `FIM_MODEL_MAX_TOKENS` | `10` | Max new tokens per completion (higher = longer suggestions) |
| `OLLAMA_TIMEOUT` | `120` | Seconds before Ollama request times out |
| `MAX_PREFIX_CHARS` | `256` | Characters of file above cursor to include in prompt |
| `MAX_SUFFIX_CHARS` | `128` | Characters of file below cursor to include in prompt |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  VS Code Extension (TypeScript)                      │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ FIM Provider │  │ Chat     │  │ Agent View   │  │
│  │ async/await  │  │ (Post 3) │  │ (Post 4)     │  │
│  └──────┬───────┘  └────┬─────┘  └──────┬───────┘  │
│         └───────────────┼───────────────┘           │
│                    DhiClient (all HTTP here)         │
└─────────────────────────┼───────────────────────────┘
                          │ HTTP
┌─────────────────────────▼───────────────────────────┐
│  FastAPI Server (Python)                             │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │ POST /complete│  │ POST /index  │                 │
│  └──────┬───────┘  └──────┬───────┘                 │
│  Service│                 │ Service                  │
│  ┌──────▼───────┐  ┌──────▼───────┐                 │
│  │ inference/   │  │ rag/         │                 │
│  │ fim.py       │  │ chunker.py   │                 │
│  └──────┬───────┘  │ store.py     │                 │
│         │          └──────┬───────┘                 │
└─────────┼─────────────────┼──────────────────────── ┘
          │                 │
    ┌─────▼────┐      ┌─────▼────┐
    │  Ollama  │      │  Chroma  │
    │  (FIM +  │      │  (vector │
    │  embed)  │      │   store) │
    └──────────┘      └──────────┘
```

**Layer rules (enforced by `ruff`):**
- `ChunkStore` is the only module that imports `chromadb`
- Service functions receive all dependencies as arguments — no module-level singletons except in `main.py`
- The extension calls the server exclusively through `DhiClient` — providers never call `fetch()` directly

Full reference: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Troubleshooting

**Ghost text never appears**

1. Check the Dhi output channel in VS Code (`View → Output → Dhi`) for error messages.
2. Check the server is running: `curl http://localhost:8000/health`
3. Check Ollama finished pulling the model: `docker compose logs ollama | tail -20`
4. Make sure the file language is supported: Python, TypeScript, JS, Go, Rust, Java.

**Completions are very slow (> 15 seconds)**

You are likely running `starcoder2:3b` on CPU. Switch to `starcoder2:1b`:
```env
# .env
FIM_MODEL=starcoder2:1b
```
Then `docker compose up -d` (Ollama pulls the new model automatically).

**Server returns 500 or times out**

Ollama may have a backlog from a previous in-flight request. Restart it:
```bash
docker compose restart ollama
```

**`422 Unprocessable Entity` from `/complete`**

The extension sent a malformed request body. Check that `file_path`, `prefix`, `suffix`, and `language` are all present. Look at `docker compose logs server --tail 30`.

**Chroma errors on startup**

Delete the persisted volume and let it rebuild:
```bash
docker compose down -v
docker compose up -d
```

**Extension not activating**

Make sure you installed the VSIX and reloaded VS Code. Check `Extensions panel → Dhi` to confirm version `0.1.0` is listed and enabled.

---

## Contributing

```bash
# Server
cd server
pip install -r requirements-dev.txt
pytest -m "not integration"        # unit tests only
pytest -m integration              # requires running Docker stack

# Extension
cd extension
npm install
npm test
npx tsc --noEmit                   # type-check
```

**Before opening a PR:**
- Run `ruff check server/` and `ruff format server/`
- Run `npx eslint extension/src/`
- Add a test for any new server endpoint or service function
- Keep the layer rules in [ARCHITECTURE.md](ARCHITECTURE.md) intact

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

---

## Blog Series: "Build Dhi From Scratch"

Each post ships a tagged commit — `git checkout post-N` to reproduce the codebase at that point.

| Post | Topic | Tag |
|---|---|---|
| 0 | [Architecture overview](https://sourishchakraborty.com/open-source-ai-coding-ide-architecture) | — |
| **1** | **[FIM autocomplete engine (Tree-sitter + StarCoder2)](https://sourishchakraborty.com/dhi-fim-autocomplete-engine)** | `post-1` |

Blog: [blogs.sourishchakraborty.com](https://blogs.sourishchakraborty.com)

---

## License

MIT — see [LICENSE](LICENSE).

---

⭐ **Star this repo if you're tired of $20/month AI IDEs.**
