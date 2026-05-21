#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_ollama.sh
# Run this INSIDE WSL2:  bash scripts/setup_ollama.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODEL="qwen2:7b-instruct-q4_K_M"    # INT4 quantised — fits in 8GB VRAM
OLLAMA_PORT=11434                    # [CONFIGURE THIS] if you need a different port

# ── 1. Install Ollama (skip if already installed) ─────────────────────────────
if ! command -v ollama &>/dev/null; then
  echo ">>> Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo ">>> Ollama already installed: $(ollama --version)"
fi

# ── 2. Start Ollama server in background ──────────────────────────────────────
echo ">>> Starting Ollama server on port ${OLLAMA_PORT}..."
OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT}" nohup ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!
echo "    PID: ${OLLAMA_PID}  |  Log: /tmp/ollama.log"

# Give it a moment to bind
sleep 3

# ── 3. Verify server is up ────────────────────────────────────────────────────
if ! curl -sf "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null; then
  echo "ERROR: Ollama server did not start. Check /tmp/ollama.log"
  exit 1
fi
echo ">>> Ollama server is up."

# ── 4. Pull the model ─────────────────────────────────────────────────────────
echo ">>> Pulling model: ${MODEL}  (~4.5 GB, first run only)"
ollama pull "${MODEL}"

# ── 5. Smoke test ─────────────────────────────────────────────────────────────
echo ">>> Running smoke test..."
RESPONSE=$(ollama run "${MODEL}" "Reply with exactly: OK" 2>&1 | head -1)
echo "    Model response: ${RESPONSE}"

echo ""
echo "═══════════════════════════════════════════"
echo "  Ollama is ready."
echo "  Model : ${MODEL}"
echo "  URL   : http://localhost:${OLLAMA_PORT}"
echo "  Verify: curl http://localhost:${OLLAMA_PORT}/api/tags"
echo "═══════════════════════════════════════════"
