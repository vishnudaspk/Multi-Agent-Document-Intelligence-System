"""
app/main.py — FastAPI application entry point.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.db.session import engine, Base
from app.services.vector_store.qdrant_service import ensure_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("MADIS starting", llm_url=settings.llm_base_url, model=settings.llm_model)

    # Create all DB tables (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db.tables.ready")

    # Ensure Qdrant collection exists
    ensure_collection()
    logger.info("qdrant.collection.ready", name=settings.qdrant_collection_name)

    yield

    logger.info("MADIS shutting down")
    await engine.dispose()


app = FastAPI(
    title="Multi-Agent Document Intelligence System",
    version="0.2.0",
    description=(
        "LangGraph + Qwen-7B-Instruct powered document ingestion and RAG query API. "
        "Upload documents, queue ingestion, and query via vector similarity search."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # [CONFIGURE THIS] restrict to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.routes import alerts as alerts_router
from app.api.routes import health, documents, query as query_router

# Import models so SQLAlchemy registers them for create_all
from app.db.models import document  # noqa: F401
from app.db.models import alert     # noqa: F401

from app.api.routes import system as system_router
app.include_router(health.router,        prefix="/health",    tags=["Health"])
app.include_router(system_router.router, prefix="/system",    tags=["System"])
app.include_router(documents.router,     prefix="/documents", tags=["Documents"])
app.include_router(query_router.router,  prefix="/query",     tags=["Query"])
app.include_router(alerts_router.router, prefix="/alerts",    tags=["Alerts"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "MADIS",
        "version": app.version,
        "docs":    "/docs",
        "health":  "/health",
        "upload":  "POST /documents/upload",
        "query":   "POST /query",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
