#!/usr/bin/env bash
# download-models.sh — Pull Ollama models needed by Dhi.
#
# Usage:
#   ./scripts/download-models.sh              # pulls default tier (starcoder2:3b + nomic)
#   FIM_MODEL=starcoder2:1b ./scripts/download-models.sh

set -euo pipefail

FIM_MODEL="${FIM_MODEL:-starcoder2:3b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"

OLLAMA_HOST="${OLLAMA_HOST:-localhost}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_URL="http://${OLLAMA_HOST}:${OLLAMA_PORT}"

info() { echo "[dhi] $*"; }
error() { echo "[dhi] ERROR: $*" >&2; exit 1; }

# ── Wait for Ollama ───────────────────────────────────────────────────────────
info "Waiting for Ollama at $OLLAMA_URL…"
for i in $(seq 1 20); do
    if curl -sf "$OLLAMA_URL" >/dev/null 2>&1; then
        break
    fi
    if [[ "$i" == "20" ]]; then
        error "Ollama did not respond. Is it running? docker compose up ollama"
    fi
    sleep 3
done

# ── Pull models ───────────────────────────────────────────────────────────────
pull_model() {
    local model="$1"
    info "Pulling $model…"
    curl -sf "$OLLAMA_URL/api/pull" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"$model\", \"stream\": false}" \
        | python3 -c "import sys, json; d = json.load(sys.stdin); print(d.get('status', d))"
    info "$model ready."
}

pull_model "$FIM_MODEL"
pull_model "$EMBED_MODEL"

info "All models downloaded."
info "FIM model:   $FIM_MODEL"
info "Embed model: $EMBED_MODEL"
