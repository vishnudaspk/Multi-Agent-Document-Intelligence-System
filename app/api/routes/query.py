"""
app/api/routes/query.py

Query and comparison endpoints for the MADIS agent graph.

Endpoints:
  POST /query/          — natural language RAG query (retrieve→summarize→action)
  POST /query/agent     — legacy self-correcting LangGraph RAG (backward compat)
  POST /query/compare   — cross-document comparison (retrieve→compare→action)
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.llm.embedding_service import embed_query
from app.services.llm.llm_client import get_llm_client
from app.services.vector_store.qdrant_service import similarity_search

router = APIRouter()

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question:    str            = Field(..., min_length=3, max_length=2000)
    top_k:       int            = Field(default=5, ge=1, le=20)
    document_id: Optional[str] = Field(default=None, description="Scope to one document")
    document_ids: Optional[List[str]] = Field(default=None, description="Scope to multiple documents")
    session_id:  Optional[str] = Field(default=None, description="Conversation session ID")
    temperature: float          = Field(default=0.1, ge=0.0, le=1.0)
    stream:      bool           = Field(default=False, description="Stream tokens (simple mode only)")


class CompareRequest(BaseModel):
    document_id_a: str          = Field(..., description="First document UUID")
    document_id_b: str          = Field(..., description="Second document UUID")
    query:         str          = Field(default="Compare these two documents.")
    session_id:    Optional[str] = None


class SourceChunk(BaseModel):
    text:        str
    document_id: Optional[str]
    filename:    Optional[str] = None
    page_number: Optional[int]
    score:       float
    chunk_index: Optional[int]


class AlertOut(BaseModel):
    type:     str
    severity: str
    message:  str
    context:  Optional[str] = None


class QueryResponse(BaseModel):
    answer:    str
    summary:   Optional[str]     = None
    sources:   List[SourceChunk] = []
    alerts:    List[AlertOut]    = []
    model:     str
    mode:      str               = "query"
    session_id: Optional[str]   = None
    latency_ms: Optional[int]   = None
    grounded:  Optional[bool]   = None
    useful:    Optional[bool]   = None
    confidence: Optional[str]   = "medium"


class DifferenceItem(BaseModel):
    aspect: str
    doc_a:  str
    doc_b:  str


class CompareResponse(BaseModel):
    similarities:   List[str]           = []
    differences:    List[DifferenceItem] = []
    summary:        str                 = ""
    recommendation: str                 = ""
    alerts:         List[AlertOut]      = []
    sources:        List[SourceChunk]   = []
    session_id:     Optional[str]       = None
    latency_ms:     Optional[int]       = None


# ── Shared helpers ────────────────────────────────────────────────────────────

def _hits_to_sources(hits: list[dict]) -> List[SourceChunk]:
    return [
        SourceChunk(
            text        = h["text"],
            document_id = h.get("document_id"),
            filename    = h.get("filename"),
            page_number = h.get("page_number"),
            score       = round(h.get("score", 0.0), 4),
            chunk_index = h.get("chunk_index"),
        )
        for h in hits
    ]


def _alerts_to_out(alerts: list[dict]) -> List[AlertOut]:
    return [
        AlertOut(
            type     = a.get("type", "anomaly"),
            severity = a.get("severity", "medium"),
            message  = a.get("message", ""),
            context  = a.get("context"),
        )
        for a in alerts
    ]


def _log_to_mlflow(run_data: dict) -> None:
    """Log query metadata to MLflow if configured. Silent on failure."""
    try:
        import mlflow
        from app.core.config import settings
        tracking_uri = getattr(settings, "mlflow_tracking_uri", None)
        if not tracking_uri:
            return
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("madis_queries")
        with mlflow.start_run():
            mlflow.log_params({
                "mode":        run_data.get("mode", "query"),
                "question":    run_data.get("question", "")[:250],
                "top_k":       run_data.get("top_k", 5),
                "num_sources": run_data.get("num_sources", 0),
                "num_alerts":  run_data.get("num_alerts", 0),
            })
            mlflow.log_metrics({
                "latency_ms": run_data.get("latency_ms", 0),
            })
    except Exception as exc:
        logger.warning("mlflow.log_failed", error=str(exc))


# ── Routes ────────────────────────────────────────────────────────────────────

RAG_SYSTEM_PROMPT = """You are a precise document analysis assistant.
Answer the user's question using ONLY the context provided below.
If the answer is not in the context, say "I could not find that information in the provided documents."
Be concise. Cite page numbers when available (e.g. [Page 3]).

Context:
{context}
"""


@router.post(
    "/",
    response_model=QueryResponse,
    summary="Natural language RAG query with multi-agent pipeline",
)
async def query(req: QueryRequest):
    """
    Runs the full agent pipeline:
      retrieve → summarize → action (flag anomalies)
    Returns structured answer, sources, and any flagged alerts.
    Supports streaming for simple mode fallback.
    """
    t0 = time.monotonic()
    logger.info("query.start", question=req.question[:80], session=req.session_id)

    # Resolve document IDs (support both single and multi-doc filter)
    doc_ids: List[str] = []
    if req.document_ids:
        doc_ids = req.document_ids
    elif req.document_id:
        doc_ids = [req.document_id]

    if req.stream:
        import queue
        import json
        
        q = queue.Queue()
        
        def _stream_callback(token: str):
            q.put({"type": "token", "content": token})
            
        async def _streamer():
            loop = asyncio.get_running_loop()
            
            def _run_and_notify():
                try:
                    from app.agents.graph import run_query
                    res = run_query(
                        query=req.question,
                        session_id=req.session_id,
                        document_ids=doc_ids,
                        top_k=req.top_k,
                        stream_callback=_stream_callback
                    )
                    
                    llm = get_llm_client()
                    latency = int((time.monotonic() - t0) * 1000)
                    
                    final_res = {
                        "answer": res.get("answer", ""),
                        "summary": res.get("summary", ""),
                        "sources": [s.model_dump() for s in _hits_to_sources(res.get("sources", []))],
                        "alerts": [a.model_dump() for a in _alerts_to_out(res.get("alerts", []))],
                        "model": llm.model,
                        "mode": "query",
                        "session_id": req.session_id,
                        "latency_ms": latency,
                        "confidence": res.get("metadata", {}).get("confidence", "medium")
                    }
                    
                    q.put({"type": "done", "result": final_res})
                except Exception as e:
                    logger.error("stream.error", exc_info=True)
                    q.put({"type": "error", "error": str(e)})

            task = loop.run_in_executor(None, _run_and_notify)
            
            while True:
                try:
                    # Non-blocking get with timeout to allow checking if task died
                    item = await asyncio.to_thread(q.get, timeout=0.1)
                    if item["type"] == "token":
                        yield f"data: {json.dumps(item)}\n\n"
                    elif item["type"] == "done":
                        yield f"data: {json.dumps(item)}\n\n"
                        break
                    elif item["type"] == "error":
                        yield f"data: {json.dumps(item)}\n\n"
                        break
                except queue.Empty:
                    if task.done():
                        break

        return StreamingResponse(_streamer(), media_type="text/event-stream")

    # Full agent graph
    from app.agents.graph import run_query
    result = await asyncio.to_thread(
        run_query,
        query       = req.question,
        session_id  = req.session_id,
        document_ids= doc_ids,
        top_k       = req.top_k,
    )

    latency = int((time.monotonic() - t0) * 1000)
    llm = get_llm_client()

    _log_to_mlflow({
        "mode":        "query",
        "question":    req.question,
        "top_k":       req.top_k,
        "num_sources": len(result.get("sources", [])),
        "num_alerts":  len(result.get("alerts", [])),
        "latency_ms":  latency,
    })

    ans = result["answer"]
    if isinstance(ans, list):
        ans = "\n".join(str(s) for s in ans)

    summ = result.get("summary")
    if isinstance(summ, list):
        summ = "\n".join(str(s) for s in summ)

    logger.info("query.done", latency_ms=latency, alerts=len(result.get("alerts", [])))
    return QueryResponse(
        answer     = ans,
        summary    = summ,
        sources    = _hits_to_sources(result.get("sources", [])),
        alerts     = _alerts_to_out(result.get("alerts", [])),
        model      = llm.model,
        mode       = "query",
        session_id = req.session_id,
        latency_ms = latency,
        confidence = result.get("metadata", {}).get("confidence", "medium"),
    )


@router.post(
    "/compare",
    response_model=CompareResponse,
    summary="Compare two documents using the Comparator + Action agents",
)
async def compare(req: CompareRequest):
    """
    Runs: retrieve (both docs) → compare → action
    Returns a structured diff with similarities, differences, and alerts.
    """
    t0 = time.monotonic()
    logger.info("compare.start", doc_a=req.document_id_a, doc_b=req.document_id_b)

    from app.agents.graph import run_compare
    result = await asyncio.to_thread(
        run_compare,
        document_ids = [req.document_id_a, req.document_id_b],
        query        = req.query,
        session_id   = req.session_id,
    )

    latency = int((time.monotonic() - t0) * 1000)
    comp    = result.get("comparison", {})

    _log_to_mlflow({
        "mode":        "compare",
        "question":    req.query,
        "top_k":       4,
        "num_sources": len(result.get("sources", [])),
        "num_alerts":  len(result.get("alerts", [])),
        "latency_ms":  latency,
    })

    differences = [
        DifferenceItem(
            aspect=d.get("aspect", ""),
            doc_a =d.get("doc_a", ""),
            doc_b =d.get("doc_b", ""),
        )
        for d in comp.get("differences", [])
    ]

    logger.info("compare.done", latency_ms=latency)
    return CompareResponse(
        similarities   = comp.get("similarities", []),
        differences    = differences,
        summary        = comp.get("summary", result.get("answer", "")),
        recommendation = comp.get("recommendation", ""),
        alerts         = _alerts_to_out(result.get("alerts", [])),
        sources        = _hits_to_sources(result.get("sources", [])),
        session_id     = req.session_id,
        latency_ms     = latency,
    )


@router.post(
    "/agent",
    response_model=QueryResponse,
    summary="Legacy self-correcting LangGraph RAG (backward compat)",
)
async def query_agent(req: QueryRequest):
    """Backward-compatible self-RAG endpoint (grade_docs → generate → hallucination_check)."""
    logger.info("query.agent.start", question=req.question[:80])
    t0 = time.monotonic()

    from app.agents.graph import run_rag_query
    result = await asyncio.to_thread(
        run_rag_query,
        question    = req.question,
        top_k       = req.top_k,
        document_id = req.document_id,
    )

    if not result["answer"]:
        raise HTTPException(500, "Agent returned an empty answer.")

    latency = int((time.monotonic() - t0) * 1000)
    llm = get_llm_client()
    logger.info("query.agent.done", latency_ms=latency)

    return QueryResponse(
        answer     = result["answer"],
        sources    = _hits_to_sources(result.get("sources", [])),
        model      = llm.model,
        grounded   = result.get("grounded"),
        useful     = result.get("useful"),
        mode       = "agent",
        latency_ms = latency,
    )
