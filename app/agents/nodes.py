"""
app/agents/nodes.py

The four specialized agent node functions for the MADIS LangGraph graph.

Node call order:
  /query mode:   retrieve → summarize → action → END
  /compare mode: retrieve → compare  → action → END

8GB VRAM notes (RTX 4060):
  - Qwen-7B-Q4_K_M consumes ~4.5 GB; leave KV-cache budget at max_tokens ≤ 1024
    for grading/flagging nodes, ≤ 2048 for the summarizer/generator only.
  - All sentence-transformer calls run on CPU (model is only 90 MB).
  - LLM calls are strictly sequential; never fan-out in parallel.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import logger
from app.db.models.alert import Alert, AlertSeverity
from app.services.llm.embedding_service import embed_query
from app.services.llm.llm_client import get_llm_client
from app.services.vector_store.qdrant_service import similarity_search


# ── Sync DB engine for agent nodes (same pattern as Celery tasks) ─────────────
_SYNC_DB_URL = settings.database_url.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
).replace("postgresql://", "postgresql+psycopg2://")
_sync_engine  = create_engine(_SYNC_DB_URL, pool_pre_ping=True, pool_size=5)
SyncSession   = sessionmaker(bind=_sync_engine, expire_on_commit=False)


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def _llm_json(prompt: str, system: str, max_tokens: int = 512, temperature: float = 0.1) -> dict:
    """Call LLM, expect JSON back. Gracefully falls back to {} on parse error."""
    llm = get_llm_client()
    try:
        raw = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error("agent.llm_json.error", error=str(e))
        if "Connection" in type(e).__name__ or "Connection" in str(e):
            logger.error("agent.llm_json.connection_error: LLM backend not reachable — is Ollama running?")
        return {}
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("agent.json_parse_failed", raw=raw[:200])
        return {}


def _format_chunks(chunks: list[dict], max_chars: int = 3000) -> str:
    """Format retrieved chunks into a context string, capped to avoid VRAM pressure."""
    parts = []
    total = 0
    for i, c in enumerate(chunks, 1):
        page = f" [Page {c['page_number']}]" if c.get("page_number") else ""
        doc  = f" [Doc {c.get('document_id', '')[:8]}]" if c.get("document_id") else ""
        entry = f"[{i}]{page}{doc}\n{c['text']}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n---\n\n".join(parts)


def _save_alerts(alerts: list[dict], session_id: str, document_ids: list[str]) -> None:
    """Persist Action Agent alerts to PostgreSQL."""
    if not alerts:
        return
    doc_id_str = "|".join(document_ids) if document_ids else None
    db = SyncSession()
    try:
        for a in alerts:
            severity_str = a.get("severity", "medium").lower()
            try:
                sev = AlertSeverity(severity_str)
            except ValueError:
                sev = AlertSeverity.MEDIUM

            db.add(Alert(
                session_id  = session_id,
                document_id = doc_id_str,
                alert_type  = a.get("type", "anomaly"),
                message     = a.get("message", ""),
                severity    = sev,
                context     = a.get("context", ""),
            ))
        db.commit()
        logger.info("agent.action.alerts_saved", count=len(alerts))
    except Exception as exc:
        db.rollback()
        logger.error("agent.action.alerts_save_failed", error=str(exc))
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Node 1 — Retriever Agent
# ─────────────────────────────────────────────────────────────────────────────

def node_retrieve(state: dict, config: dict = None) -> dict:
    """
    Embed the query and fetch top-K chunks from Qdrant.
    In compare mode, fetches chunks for EACH document_id separately
    and merges them (up to top_k per doc).
    """
    if config and "configurable" in config:
        cb = config["configurable"].get("stream_callback")
        if cb:
            cb("__PHASE__:Retrieving relevant chunks...")

    query       = state["query"]
    doc_ids     = state.get("document_ids") or []
    top_k       = state.get("top_k", 5)
    mode        = state.get("mode", "query")

    logger.info("agent.retrieve.start", query=query[:80], mode=mode, doc_ids=doc_ids)
    vec = embed_query(query)

    if mode == "compare" and len(doc_ids) >= 2:
        # Retrieve separately per document so both are represented
        chunks = []
        for doc_id in doc_ids[:2]:          # cap at 2 for compare mode
            hits = similarity_search(
                query_embedding=vec,
                top_k=min(top_k, 4),        # 4 chunks × 2 docs = 8 total, safe for VRAM
                document_id=doc_id,
            )
            # Tag each chunk with which document it belongs to
            for h in hits:
                h["_source_doc"] = doc_id
            chunks.extend(hits)
    else:
        doc_id = doc_ids[0] if doc_ids else None
        chunks = similarity_search(
            query_embedding=vec,
            top_k=top_k,
            document_id=doc_id,
        )

    logger.info("agent.retrieve.done", chunks=len(chunks))
    return {"retrieved_chunks": chunks}


# ─────────────────────────────────────────────────────────────────────────────
# Node 2 — Summarizer Agent
# ─────────────────────────────────────────────────────────────────────────────

def node_summarize(state: dict, config: dict = None) -> dict:
    """
    Condenses retrieved chunks into a structured, grounded summary.
    Also produces a direct answer to the user's query.

    8GB VRAM: max_tokens=2048, context capped at 3000 chars.
    """
    query   = state["query"]
    chunks  = state["retrieved_chunks"]
    context = _format_chunks(chunks, max_chars=3000)

    SYSTEM = """You are an expert document analyst and strategic advisor.
Given retrieved document chunks, your goal is to provide a comprehensive, deeply reasoned, and highly detailed response to the user's query.
You must:
1. Synthesize the provided context to form a complete and thoughtful answer. Do NOT just copy and paste sentences; explain the concepts, implications, and context.
2. If the context contains complex ideas, break them down clearly.
3. If the answer is completely absent from the context, state "NOT_IN_CONTEXT".

Structure your response using the following Markdown headers:
**Reasoning:**
(explain your thought process and synthesis)

**Summary:**
(3-5 detailed bullet points summarising key information)

**Answer:**
(detailed comprehensive answer)

Always cite page numbers like [Page N] when available, but weave them naturally into your comprehensive explanation."""

    prompt = f"User question: {query}\n\nRetrieved context:\n{context}"

    logger.info("agent.summarize.start")
    
    stream_cb = None
    if config and "configurable" in config:
        stream_cb = config.get("configurable", {}).get("stream_callback")
        if stream_cb:
            stream_cb("__PHASE__:Reasoning over context...")
        
    llm = get_llm_client()
    final_response = ""
    
    if stream_cb:
        try:
            for token in llm.stream([{"role": "user", "content": prompt}], system_prompt=SYSTEM, temperature=0.3, max_tokens=2048):
                final_response += token
                stream_cb(token)
        except Exception as e:
            logger.error(f"agent.summarize.error: {e}")
            if "Connection" in type(e).__name__ or "Connection" in str(e):
                final_response = "⚠️ LLM backend is not reachable. Please ensure Ollama is running (`ollama serve`) and the model is available."
                stream_cb(final_response)
            else:
                final_response = f"An error occurred during summarization: {e}"
    else:
        try:
            final_response = llm.chat([{"role": "user", "content": prompt}], system_prompt=SYSTEM, temperature=0.3, max_tokens=2048)
        except Exception as e:
            logger.error(f"agent.summarize.error: {e}")
            if "Connection" in type(e).__name__ or "Connection" in str(e):
                final_response = "⚠️ LLM backend is not reachable. Please ensure Ollama is running (`ollama serve`) and the model is available."
            else:
                final_response = f"An error occurred during summarization: {e}"

    logger.info("agent.summarize.done")
    
    confidence = "high"
    retrieved_chunks = state.get("retrieved_chunks", [])
    if "NOT_IN_CONTEXT" in final_response:
        confidence = "low"
        retrieved_chunks = []  # Clear sources if the answer is not in context

    return {
        "summary":        final_response,
        "answer":         final_response,
        "final_response": final_response,
        "retrieved_chunks": retrieved_chunks,
        "metadata":       {**state.get("metadata", {}), "confidence": confidence},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — Comparator Agent
# ─────────────────────────────────────────────────────────────────────────────

def node_compare(state: dict, config: dict = None) -> dict:
    """
    Reasons across chunks from two documents.
    Produces a structured diff: similarities, differences, and key distinctions.

    8GB VRAM: two-doc context is capped at 3000 chars total (1500 per doc).
    """
    chunks  = state["retrieved_chunks"]
    doc_ids = state.get("document_ids", [])
    query   = state.get("query", "Compare these documents.")

    # Split chunks by document
    doc_a_id = doc_ids[0] if len(doc_ids) > 0 else None
    doc_b_id = doc_ids[1] if len(doc_ids) > 1 else None

    chunks_a = [c for c in chunks if c.get("_source_doc") == doc_a_id or
                (not c.get("_source_doc") and chunks.index(c) % 2 == 0)]
    chunks_b = [c for c in chunks if c.get("_source_doc") == doc_b_id or
                (not c.get("_source_doc") and chunks.index(c) % 2 == 1)]

    ctx_a = _format_chunks(chunks_a, max_chars=1500)
    ctx_b = _format_chunks(chunks_b, max_chars=1500)

    SYSTEM = """You are an expert document comparison specialist and analytical thinker.
You will receive content from two documents and must produce a deeply reasoned, structured, and factual comparison.
Focus on factual differences, subtle nuances, and strategic implications rather than just listing facts. Provide meaningful insights.

Structure your response using the following Markdown headers:
**Reasoning:**
(analyze the nuances between the documents)

**Similarities:**
(bullet points of similarities)

**Differences:**
(bullet points of differences)

**Recommendation:**
(which document is more complete/accurate and why)"""

    prompt = f"Compare Document A and Document B based on this focus: {query}\n\n=== DOCUMENT A (ID: {doc_a_id or 'unknown'}) ===\n{ctx_a}\n\n=== DOCUMENT B (ID: {doc_b_id or 'unknown'}) ===\n{ctx_b}"

    logger.info("agent.compare.start", doc_a=doc_a_id, doc_b=doc_b_id)
    
    stream_cb = None
    if config and "configurable" in config:
        stream_cb = config.get("configurable", {}).get("stream_callback")
        
    llm = get_llm_client()
    final_response = ""
    
    if stream_cb:
        for token in llm.stream([{"role": "user", "content": prompt}], system_prompt=SYSTEM, temperature=0.3, max_tokens=1024):
            final_response += token
            stream_cb(token)
    else:
        final_response = llm.chat([{"role": "user", "content": prompt}], system_prompt=SYSTEM, temperature=0.3, max_tokens=1024)

    logger.info("agent.compare.done")
    
    return {
        "comparison":     {"summary": final_response},
        "answer":         final_response,
        "final_response": final_response,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 4 — Action Agent
# ─────────────────────────────────────────────────────────────────────────────

def node_action(state: dict, config: dict = None) -> dict:
    """
    Reviews the summary/comparison output and flags:
      - Anomalies (unusual or unexpected content)
      - Contradictions (statements that conflict with each other)
      - Missing clauses (expected sections not present)

    Persists alerts to PostgreSQL. Returns updated state with alerts list.

    8GB VRAM: receives condensed text (summary/comparison), not raw chunks.
    max_tokens=512 — this is a classification/flagging task, not generation.
    """
    if config and "configurable" in config:
        cb = config["configurable"].get("stream_callback")
        if cb:
            cb("__PHASE__:Running audit checks...")

    mode        = state.get("mode", "query")
    session_id  = state.get("session_id", str(uuid.uuid4()))
    doc_ids     = state.get("document_ids", [])

    # Build input text from prior agent output
    if mode == "compare":
        comp = state.get("comparison", {})
        input_text = (
            f"Comparison summary: {comp.get('summary', '')}\n\n"
            f"Differences: {json.dumps(comp.get('differences', []))}\n\n"
            f"Similarities: {json.dumps(comp.get('similarities', []))}"
        )
    else:
        input_text = state.get("summary", state.get("answer", ""))
        if isinstance(input_text, list):
            input_text = "\n".join(str(item) for item in input_text)
        elif not isinstance(input_text, str):
            input_text = str(input_text)

    if not input_text.strip():
        logger.info("agent.action.skip", reason="no input text")
        return {"alerts": []}

    SYSTEM = """You are a document risk and compliance analyst.
Review the provided document analysis output and identify ONLY genuine issues:
1. ANOMALIES: unusual claims, outlier data, or suspicious statements that deviate from expected norms
2. CONTRADICTIONS: statements within the same analysis that directly contradict each other
3. MISSING_CLAUSES: important expected elements (dates, signatures, liability terms, definitions) that are conspicuously absent

RULES:
- Only flag issues backed by specific evidence from the text
- Do NOT flag stylistic differences or formatting issues
- Do NOT flag items that are simply not discussed (absence ≠ missing clause)
- A missing clause must be something EXPECTED for the document type
- If nothing is genuinely concerning, return an EMPTY alerts array

FEW-SHOT EXAMPLES:

Example 1 (genuine issue found):
Input: "Document A states the contract expires on 2024-12-31. Document B states the same contract expires on 2025-06-30."
Output: {"alerts": [{"type": "contradiction", "severity": "high", "message": "Contract expiry dates conflict: Doc A says 2024-12-31, Doc B says 2025-06-30", "context": "expires on 2024-12-31 vs expires on 2025-06-30"}]}

Example 2 (no issues):
Input: "Both documents describe the same product specifications. Document A is more detailed on technical specs while Document B focuses on pricing."
Output: {"alerts": []}"""

    prompt = f"""Review this document analysis output for issues:

{input_text[:2000]}

Respond in this exact JSON format:
{{
  "alerts": [
    {{
      "type": "anomaly|contradiction|missing_clause",
      "severity": "low|medium|high|critical",
      "message": "<clear description backed by evidence>",
      "context": "<exact quote or reference from the text>"
    }}
  ]
}}

If no issues found, return: {{"alerts": []}}"""

    logger.info("agent.action.start")
    result = _llm_json(prompt, SYSTEM, max_tokens=512)
    alerts = result.get("alerts", [])

    # Persist to PostgreSQL
    _save_alerts(alerts, session_id, doc_ids)

    logger.info("agent.action.done", alert_count=len(alerts))
    return {"alerts": alerts}
