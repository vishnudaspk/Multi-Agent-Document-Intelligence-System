"""
app/api/routes/health.py — liveness + readiness probes.
"""
import httpx
import redis as redis_sync
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/", summary="Liveness probe")
async def liveness():
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe — checks all backends")
async def readiness():
    results: dict = {}

    # Qdrant
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"http://{settings.qdrant_host}:{settings.qdrant_port}/healthz")
        results["qdrant"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as e:
        results["qdrant"] = f"error: {e}"

    # Redis
    try:
        rc = redis_sync.from_url(settings.redis_url, socket_connect_timeout=3)
        rc.ping()
        results["redis"] = "ok"
    except Exception as e:
        results["redis"] = f"error: {e}"

    # Ollama / LMStudio
    try:
        probe_url = (
            f"{settings.lmstudio_base_url}/v1/models"
            if settings.lmstudio_base_url
            else f"{settings.ollama_base_url}/api/tags"
        )
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(probe_url)
        results["llm"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as e:
        results["llm"] = f"error: {e}"

    all_ok = all(v == "ok" for v in results.values())
    return {"status": "ready" if all_ok else "degraded", "backends": results}
