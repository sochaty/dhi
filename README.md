# Dhi (धी) — Open-Source AI Coding IDE

> *"Pure intelligence for your code. Open source."*

[![CI](https://github.com/sochaty/dhi/actions/workflows/ci.yml/badge.svg)](https://github.com/sochaty/dhi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sochaty.dhi?label=VS%20Code)](https://marketplace.visualstudio.com/items?itemName=sochaty.dhi)

**Tired of $20/month AI IDEs and per-token pricing?**

Dhi gives you FIM autocomplete, in-editor chat, and multi-file agent editing — powered entirely by open-source models. Run locally on your laptop or use our shared GPU pool for ~$3/month. No API keys. No rate limits. No surprises.

```
git clone https://github.com/sochaty/dhi
cd dhi
./scripts/bootstrap.sh
```

That's it. Open VS Code and start coding.

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

## Quickstart (60 seconds)

**Prerequisites:** [Docker Desktop 4.x](https://www.docker.com/products/docker-desktop/), VS Code 1.90+

### Linux / macOS

```bash
git clone https://github.com/sochaty/dhi
cd dhi
./scripts/bootstrap.sh   # auto-detects GPU, picks model tier, pulls weights
```

### Windows

```powershell
git clone https://github.com/sochaty/dhi
cd dhi
copy .env.example .env   # edit .env if you want a different model tier
docker compose up -d
```

### After startup

```bash
# 2. Install the VS Code extension
# Extensions panel → search "Dhi" → Install

# 3. Open any Python or TypeScript file and start typing
# 4. Optional: Cmd/Ctrl+Shift+P → "Dhi: Index Workspace" for better context
```

> **First run:** Ollama pulls model weights on startup (~2–8 GB depending on tier).
> The server won't accept requests until the download completes — this is normal.
> Track progress with `docker compose logs -f ollama`.

No GPU? It works on CPU using StarCoder2-1B (~2–5s per completion).
Set `FIM_MODEL=starcoder2:1b` in `.env` before starting.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  VS Code Extension (TypeScript)                      │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ FIM Provider │  │ Chat     │  │ Agent View   │  │
│  │ (Post 1)     │  │ (Post 3) │  │ (Post 4)     │  │
│  └──────┬───────┘  └────┬─────┘  └──────┬───────┘  │
│         └───────────────┼───────────────┘           │
│                    DhiClient (all HTTP here)         │
└─────────────────────────┼───────────────────────────┘
                          │ HTTP
┌─────────────────────────▼───────────────────────────┐
│  FastAPI Server (Python)                             │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │ /complete    │  │ /index       │                 │
│  └──────┬───────┘  └──────┬───────┘                 │
│  Service │                │ Service                  │
│  ┌───────▼──────┐  ┌──────▼───────┐                 │
│  │ inference/   │  │ rag/         │                 │
│  │ fim.py       │  │ chunker.py   │                 │
│  └───────┬──────┘  │ store.py     │                 │
│          │         └──────┬───────┘                 │
└──────────┼────────────────┼────────────────────────┘
           │                │
     ┌─────▼────┐     ┌─────▼────┐
     │  Ollama  │     │  Chroma  │
     │  (FIM +  │     │  (vector │
     │  embed)  │     │   store) │
     └──────────┘     └──────────┘
```

Full architecture reference: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Models

| Tier | FIM Model | VRAM | HumanEval pass@1 |
|---|---|---|---|
| CPU | starcoder2:1b | 0 GB | 27% |
| Default | starcoder2:3b | 6 GB | 46% |
| Quality | deepseek-coder-v2:16b | 12 GB | 73% |
| Max | qwen2.5-coder:32b | 24 GB | 90% |

Full model registry: [models/registry.yaml](models/registry.yaml)

---

## Blog Series: "Build Dhi From Scratch"

Each blog post ships a tagged commit you can `git checkout` to reproduce exactly.

| Post | Topic | Tag |
|---|---|---|
| 0 | Architecture overview | — |
| **1** | **FIM autocomplete engine (Tree-sitter + StarCoder2)** | `post-1` |
| 2 | Repository intelligence (hybrid search) | `post-2` |
| 3 | In-editor chat with streaming RAG | `post-3` |
| 4 | Multi-file agent with LangGraph | `post-4` |
| 5 | Sandboxed code execution | `post-5` |
| 6 | VS Code extension deep-dive | `post-6` |
| 7 | vLLM inference and model registry | `post-7` |
| 8 | 3× faster FIM with speculative decoding | `post-8` |
| 9 | Multi-user platform: auth, queue, metering | `post-9` |
| 10 | Docker Compose: zero to IDE in 60 seconds | `post-10` |
| 11 | Deploying the shared GPU pool on RunPod | `post-11` |
| 12 | Model benchmark: StarCoder vs DeepSeek vs Qwen | `post-12` |

Blog: [blogs.sourishchakraborty.com](https://blogs.sourishchakraborty.com)

---

## Contributing

```bash
# Server
cd server
pip install -r requirements-dev.txt
pytest

# Extension
cd extension
npm install
npm test
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for layer rules and contribution guidelines.

---

## License

MIT — see [LICENSE](LICENSE).

---

⭐ **Star this repo if you're tired of $20/month AI IDEs.**
