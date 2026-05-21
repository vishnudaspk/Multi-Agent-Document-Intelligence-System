# setup_ollama.ps1
# Run in PowerShell as Administrator if Ollama is not yet installed.
# Usage: .\scripts\ollama_windows.ps1

$MODEL      = "qwen2:7b-instruct-q4_K_M"   # INT4 — fits 8GB VRAM
$OLLAMA_PORT = 11434                          # [CONFIGURE THIS]

# ── 1. Check / install Ollama ─────────────────────────────────────────────────
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host ">>> Downloading Ollama installer..."
    $installer = "$env:TEMP\OllamaSetup.exe"
    Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $installer
    Write-Host ">>> Running installer (follow the GUI)..."
    Start-Process -FilePath $installer -Wait
} else {
    Write-Host ">>> Ollama already installed: $(ollama --version)"
}

# ── 2. Set host env var and start server ──────────────────────────────────────
$env:OLLAMA_HOST = "0.0.0.0:$OLLAMA_PORT"
Write-Host ">>> Starting Ollama server on port $OLLAMA_PORT..."
Start-Process -FilePath "ollama" -ArgumentList "serve" -NoNewWindow

Start-Sleep -Seconds 4

# ── 3. Health check ───────────────────────────────────────────────────────────
try {
    $resp = Invoke-RestMethod "http://localhost:$OLLAMA_PORT/api/tags" -ErrorAction Stop
    Write-Host ">>> Ollama server is up."
} catch {
    Write-Host "ERROR: Ollama server did not respond. Is it installed?"
    exit 1
}

# ── 4. Pull model ─────────────────────────────────────────────────────────────
Write-Host ">>> Pulling $MODEL  (~4.5 GB, first run only)..."
ollama pull $MODEL

# ── 5. Smoke test ─────────────────────────────────────────────────────────────
Write-Host ">>> Smoke test..."
$out = ollama run $MODEL "Reply with exactly: OK"
Write-Host "    Response: $out"

Write-Host ""
Write-Host "Ollama ready at http://localhost:$OLLAMA_PORT"
Write-Host "Model: $MODEL"
