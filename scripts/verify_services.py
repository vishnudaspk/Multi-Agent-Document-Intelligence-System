"""
verify_services.py
Run BEFORE starting the app.
Usage: python scripts/verify_services.py

Checks:
  - Qdrant   REST API
  - PostgreSQL connection
  - Redis    PING
  - Ollama   /api/tags endpoint  (or LMStudio /v1/models)
"""

import sys
import os
import asyncio
import time
from pathlib import Path

# ── allow running from repo root ──────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # dotenv optional at this stage

import httpx
import redis as redis_sync
import asyncpg

# ─────────────────────────────────────────────────────────────────────────────
# Config — reads from env, falls back to defaults matching docker-compose.yml
# ─────────────────────────────────────────────────────────────────────────────
QDRANT_URL   = os.getenv("QDRANT_URL",     "http://localhost:6333")
POSTGRES_DSN = os.getenv("DATABASE_URL",   "postgresql://madis_user:madis_pass@localhost:5432/madis_db")
REDIS_URL    = os.getenv("REDIS_URL",      "redis://localhost:6379/0")
OLLAMA_URL   = os.getenv("OLLAMA_BASE_URL","http://localhost:11434")
LMSTUDIO_URL = os.getenv("LMSTUDIO_BASE_URL", "")   # set in .env to skip Ollama check

TIMEOUT = 5  # seconds per check

# ─────────────────────────────────────────────────────────────────────────────
# ANSI colours
# ─────────────────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(service: str, detail: str = ""):
    tag = f"{GREEN}✔  OK{RESET}"
    print(f"  {tag}  {BOLD}{service}{RESET}  {detail}")

def fail(service: str, error: str):
    tag = f"{RED}✘  FAIL{RESET}"
    print(f"  {tag}  {BOLD}{service}{RESET}  → {error}")

def warn(msg: str):
    print(f"  {YELLOW}⚠  {msg}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────

def check_qdrant() -> bool:
    try:
        r = httpx.get(f"{QDRANT_URL}/healthz", timeout=TIMEOUT)
        if r.status_code == 200:
            info = httpx.get(f"{QDRANT_URL}/", timeout=TIMEOUT).json()
            version = info.get("version", "?")
            ok("Qdrant", f"version={version}  url={QDRANT_URL}")
            return True
        fail("Qdrant", f"HTTP {r.status_code}")
        return False
    except Exception as e:
        fail("Qdrant", str(e))
        return False


async def check_postgres() -> bool:
    # asyncpg uses postgres:// scheme
    dsn = POSTGRES_DSN.replace("postgresql+asyncpg://", "postgresql://") \
                      .replace("postgresql+psycopg2://", "postgresql://")
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=TIMEOUT)
        row = await conn.fetchrow("SELECT version()")
        await conn.close()
        version = row[0].split(",")[0] if row else "?"
        ok("PostgreSQL", version)
        return True
    except Exception as e:
        fail("PostgreSQL", str(e))
        return False


def check_redis() -> bool:
    try:
        client = redis_sync.from_url(REDIS_URL, socket_connect_timeout=TIMEOUT)
        resp = client.ping()
        if resp:
            info = client.info("server")
            version = info.get("redis_version", "?")
            ok("Redis", f"version={version}  url={REDIS_URL}")
            return True
        fail("Redis", "PING returned False")
        return False
    except Exception as e:
        fail("Redis", str(e))
        return False


def check_llm() -> bool:
    # Prefer LMStudio if configured, else check Ollama
    if LMSTUDIO_URL:
        try:
            r = httpx.get(f"{LMSTUDIO_URL}/v1/models", timeout=TIMEOUT,
                          headers={"Authorization": "Bearer lm-studio"})
            if r.status_code == 200:
                models = [m["id"] for m in r.json().get("data", [])]
                ok("LMStudio", f"loaded models: {models or ['(none loaded)']}")
                return True
            fail("LMStudio", f"HTTP {r.status_code}")
            return False
        except Exception as e:
            fail("LMStudio", str(e))
            return False
    else:
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=TIMEOUT)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                if not models:
                    warn("Ollama is running but NO models are loaded. Run: ollama pull qwen2:7b-instruct-q4_K_M")
                ok("Ollama", f"models: {models or []}")
                return True
            fail("Ollama", f"HTTP {r.status_code}")
            return False
        except Exception as e:
            fail("Ollama", str(e))
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print(f"\n{BOLD}{'─'*54}{RESET}")
    print(f"{BOLD}  MADIS — Service Pre-flight Check{RESET}")
    print(f"{BOLD}{'─'*54}{RESET}\n")

    start = time.monotonic()

    results = {}
    results["Qdrant"]     = check_qdrant()
    results["PostgreSQL"] = await check_postgres()
    results["Redis"]      = check_redis()
    results["LLM"]        = check_llm()

    elapsed = time.monotonic() - start

    print(f"\n{'─'*54}")
    passed = sum(results.values())
    total  = len(results)
    colour = GREEN if passed == total else RED
    print(f"  {colour}{BOLD}{passed}/{total} services healthy{RESET}  ({elapsed:.2f}s)\n")

    failed = [k for k, v in results.items() if not v]
    if failed:
        print(f"  {RED}Failed:{RESET} {', '.join(failed)}")
        print(f"  → Start Docker services:  docker compose up -d")
        print(f"  → Then re-run this script.\n")
        sys.exit(1)

    print(f"  {GREEN}All services reachable. You're good to go.{RESET}\n")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
