#!/usr/bin/env bash
# bootstrap.sh — Auto-detect GPU, pick the right compose file, pull models.
#
# Usage:
#   ./scripts/bootstrap.sh           # interactive — prompts for model tier
#   FIM_TIER=fast ./scripts/bootstrap.sh   # non-interactive

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[dhi]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[dhi]${RESET} $*"; }
error()   { echo -e "${RED}[dhi]${RESET} $*" >&2; exit 1; }

# ── Prerequisites ─────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || error "Docker is not installed. https://docs.docker.com/get-docker/"
command -v docker compose >/dev/null 2>&1 || error "Docker Compose V2 is required."

# ── GPU detection ─────────────────────────────────────────────────────────────
HAS_NVIDIA=false
HAS_AMD=false
COMPOSE_FILE="docker-compose.yml"

if command -v nvidia-smi >/dev/null 2>&1; then
    VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
    if [[ -n "$VRAM_MB" && "$VRAM_MB" -gt 0 ]]; then
        HAS_NVIDIA=true
        VRAM_GB=$(( VRAM_MB / 1024 ))
        info "NVIDIA GPU detected — ${VRAM_GB} GB VRAM"
        COMPOSE_FILE="docker-compose.gpu.yml"
    fi
fi

if [[ "$HAS_NVIDIA" == "false" ]] && command -v rocm-smi >/dev/null 2>&1; then
    HAS_AMD=true
    info "AMD ROCm GPU detected"
    COMPOSE_FILE="docker-compose.gpu.yml"
fi

if [[ "$HAS_NVIDIA" == "false" && "$HAS_AMD" == "false" ]]; then
    warn "No GPU detected — running on CPU. Completions will be slower (~2–5s)."
fi

# ── Pick FIM model tier ───────────────────────────────────────────────────────
if [[ -z "${FIM_TIER:-}" ]]; then
    echo ""
    echo -e "${BOLD}Choose a FIM model tier:${RESET}"
    echo "  1) fast    — starcoder2:1b   (3+ GB VRAM / CPU-friendly)"
    echo "  2) default — starcoder2:3b   (6+ GB VRAM)  ← recommended"
    echo "  3) quality — deepseek-coder-v2:16b (12+ GB VRAM)"
    echo "  4) max     — qwen2.5-coder:32b     (24+ GB VRAM)"
    read -rp "Enter choice [1-4, default 2]: " CHOICE
    case "${CHOICE:-2}" in
        1) FIM_TIER=fast ;;
        3) FIM_TIER=quality ;;
        4) FIM_TIER=max ;;
        *) FIM_TIER=default ;;
    esac
fi

case "$FIM_TIER" in
    fast)    FIM_MODEL="starcoder2:1b"            EMBED_MODEL="nomic-embed-text" ;;
    default) FIM_MODEL="starcoder2:3b"            EMBED_MODEL="nomic-embed-text" ;;
    quality) FIM_MODEL="deepseek-coder-v2:16b"    EMBED_MODEL="nomic-embed-text" ;;
    max)     FIM_MODEL="qwen2.5-coder:32b"        EMBED_MODEL="nomic-embed-text" ;;
    *) error "Unknown FIM_TIER: $FIM_TIER" ;;
esac

info "Using compose file: $COMPOSE_FILE"
info "FIM model: $FIM_MODEL"
info "Embed model: $EMBED_MODEL"

# ── Write .env if missing ─────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    info "Creating .env from .env.example"
    cp .env.example .env
    # sed -i behaves differently on macOS (requires empty backup arg) vs Linux
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|FIM_MODEL=.*|FIM_MODEL=$FIM_MODEL|" .env
        sed -i '' "s|EMBED_MODEL=.*|EMBED_MODEL=$EMBED_MODEL|" .env
    else
        sed -i "s|FIM_MODEL=.*|FIM_MODEL=$FIM_MODEL|" .env
        sed -i "s|EMBED_MODEL=.*|EMBED_MODEL=$EMBED_MODEL|" .env
    fi
fi

# ── Start services ────────────────────────────────────────────────────────────
info "Starting services…"
info "Note: first run pulls model weights (~2–8 GB). This can take several minutes."
FIM_MODEL="$FIM_MODEL" EMBED_MODEL="$EMBED_MODEL" docker compose -f "$COMPOSE_FILE" up -d

# ── Wait for server health (server waits for ollama healthcheck, so this
#    also implicitly waits for models to finish downloading) ──────────────────
info "Waiting for Dhi server to be ready (includes model download)…"
for i in $(seq 1 90); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        info "Dhi server is ready!"
        break
    fi
    if [[ "$i" == "90" ]]; then
        error "Server did not become ready in 3 minutes. Run: docker compose logs"
    fi
    sleep 2
done

echo ""
echo -e "${BOLD}${GREEN}Dhi is running!${RESET}"
echo ""
echo "  Server:    http://localhost:8000"
echo "  Chroma UI: http://localhost:8001"
echo ""
echo "  Next steps:"
echo "    1. Install the VS Code extension: Extensions → search 'Dhi'"
echo "    2. Open a Python or TypeScript file and start typing"
echo "    3. Run Cmd+Shift+P → 'Dhi: Index Workspace' for better context"
echo ""
