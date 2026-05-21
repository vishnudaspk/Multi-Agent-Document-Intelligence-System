"""
app/agents/graph.py

Multi-agent LangGraph graph for MADIS.

Two execution modes (selected by state["mode"]):

  "query" mode:
    retrieve → grade_docs → generate → hallucination_check → grade_answer
              ↘ summarize → action → END   (after grade_docs)

  "compare" mode:
    retrieve → compare → action → END

The original self-RAG loop (grade_docs → generate → hallucination_check →
grade_answer) is preserved for backward compatibility via /query/agent.
The new specialized nodes (summarize, compare, action) are added for the
new /query and /compare endpoints.

Session memory: MemorySaver checkpointer keyed by session_id (thread_id).
"""
from __future__ import annotations

import json
import uuid
from typing import Annotated, List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.agents.nodes import node_action, node_compare, node_retrieve, node_summarize
from app.core.logging import logger
from app.services.llm.embedding_service import embed_query
from app.services.llm.llm_client import get_llm_client
from app.services.vector_store.qdrant_service import similarity_search


# ─────────────────────────────────────────────────────────────────────────────
# Unified graph state
# ─────────────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    session_id:        str
    query:             str
    document_ids:      List[str]        # empty = search all; 2 items = compare mode
    top_k:             int
    mode:              str              # "query" | "compare" | "agent"

    # Pipeline data
    retrieved_chunks:  List[dict]
    filtered_chunks:   List[dict]
    summary:           str
    answer:            str
    comparison:        dict
    alerts:            List[dict]
    final_response:    str

    # Self-RAG state (backward-compat with /query/agent)
    generation_count:  int
    re_query_count:    int
    grounded:          bool
    useful:            bool
    sources:           List[dict]

    # Metadata
    metadata:          dict
    messages:          Annotated[List, add_messages]


# ─────────────────────────────────────────────────────────────────────────────
# Self-RAG nodes (preserved from original graph for /query/agent endpoint)
# ─────────────────────────────────────────────────────────────────────────────

def _llm_json(prompt: str, system: str) -> dict:
    llm = get_llm_client()
    raw = llm.chat(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=system,
        temperature=0.0,
        max_tokens=512,
    )
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("llm.json_parse_failed", raw=raw[:200])
        return {}


def node_grade_docs(state: AgentState) -> dict:
    question = state["query"]
    chunks   = state["retrieved_chunks"]
    SYSTEM = (
        "You are a relevance grader. "
        "Given a user question and a document chunk, decide if the chunk is relevant. "
        'Respond with JSON only: {"relevant": "yes" or "no"}'
    )
    filtered = []
    for chunk in chunks:
        result = _llm_json(
            prompt=f"Question: {question}\n\nChunk:\n{chunk['text'][:500]}",
            system=SYSTEM,
        )
        if result.get("relevant", "no").lower() == "yes":
            filtered.append(chunk)
    logger.info("agent.grade_docs", total=len(chunks), relevant=len(filtered))
    return {"filtered_chunks": filtered or chunks}


def node_generate(state: AgentState) -> dict:
    question = state["query"]
    chunks   = state.get("filtered_chunks") or state.get("retrieved_chunks", [])
    parts = []
    for i, c in enumerate(chunks, 1):
        page = f" [Page {c['page_number']}]" if c.get("page_number") else ""
        parts.append(f"[{i}]{page}\n{c['text']}")
    context = "\n\n---\n\n".join(parts)
    SYSTEM = (
        "You are a precise document analysis assistant. "
        "Answer ONLY using the context below. "
        "If the context does not contain the answer, say exactly: 'NOT_IN_CONTEXT'. "
        f"Cite page numbers when available.\n\nContext:\n{context}"
    )
    llm    = get_llm_client()
    answer = llm.chat(
        messages=[{"role": "user", "content": question}],
        system_prompt=SYSTEM,
        temperature=0.1,
        max_tokens=2048,
    )
    count = state.get("generation_count", 0) + 1
    logger.info("agent.generate", attempt=count)
    return {"answer": answer, "generation_count": count, "sources": chunks, "final_response": answer}


def node_hallucination_check(state: AgentState) -> dict:
    SYSTEM = (
        "You are a hallucination detector. "
        "Given a context and an answer, decide if every factual claim in the answer "
        "is explicitly supported by the context. "
        'Respond with JSON only: {"grounded": "yes" or "no"}'
    )
    chunks  = state.get("filtered_chunks") or state.get("retrieved_chunks", [])
    context = "\n".join(c["text"][:300] for c in chunks)
    result  = _llm_json(
        prompt=f"Context:\n{context}\n\nAnswer:\n{state.get('answer', '')}",
        system=SYSTEM,
    )
    grounded = result.get("grounded", "yes").lower() == "yes"
    logger.info("agent.hallucination_check", grounded=grounded)
    return {"grounded": grounded}


def node_grade_answer(state: AgentState) -> dict:
    SYSTEM = (
        "You are an answer quality grader. "
        "Given a question and an answer, decide if the answer usefully resolves the question. "
        'Respond with JSON only: {"useful": "yes" or "no"}'
    )
    result = _llm_json(
        prompt=f"Question: {state['query']}\n\nAnswer:\n{state.get('answer', '')}",
        system=SYSTEM,
    )
    useful = result.get("useful", "yes").lower() == "yes"
    logger.info("agent.grade_answer", useful=useful)
    return {"useful": useful}


# ─────────────────────────────────────────────────────────────────────────────
# Routing functions
# ─────────────────────────────────────────────────────────────────────────────

def route_after_retrieve(state: AgentState) -> str:
    """Route based on execution mode."""
    mode = state.get("mode", "query")
    if mode == "compare":
        return "compare"
    if mode == "agent":
        return "grade_docs"
    return "summarize"     # default: new query mode


def route_after_hallucination(state: AgentState) -> str:
    if state.get("grounded", True):
        return "grade_answer"
    if state.get("generation_count", 0) >= 2:
        return "grade_answer"
    return "generate"


def route_after_grade_answer(state: AgentState) -> str:
    if state.get("useful", True):
        return END
    if state.get("re_query_count", 0) >= 1:
        return END
    return "retrieve"


# ─────────────────────────────────────────────────────────────────────────────
# Build and compile the unified graph
# ─────────────────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # ── All nodes ──────────────────────────────────────────────
    g.add_node("retrieve",            node_retrieve)
    g.add_node("summarize",           node_summarize)
    g.add_node("compare",             node_compare)
    g.add_node("action",              node_action)

    # Self-RAG nodes (legacy /query/agent endpoint)
    g.add_node("grade_docs",          node_grade_docs)
    g.add_node("generate",            node_generate)
    g.add_node("hallucination_check", node_hallucination_check)
    g.add_node("grade_answer",        node_grade_answer)

    # ── Entry point ────────────────────────────────────────────
    g.set_entry_point("retrieve")

    # After retrieve, branch by mode
    g.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {
            "summarize": "summarize",
            "compare":   "compare",
            "grade_docs": "grade_docs",
        },
    )

    # ── New query pipeline ─────────────────────────────────────
    g.add_edge("summarize", "action")
    g.add_edge("action",    END)

    # ── Compare pipeline ───────────────────────────────────────
    g.add_edge("compare", "action")

    # ── Legacy self-RAG pipeline ───────────────────────────────
    g.add_edge("grade_docs", "generate")
    g.add_edge("generate",   "hallucination_check")

    g.add_conditional_edges(
        "hallucination_check",
        route_after_hallucination,
        {"grade_answer": "grade_answer", "generate": "generate"},
    )
    g.add_conditional_edges(
        "grade_answer",
        route_after_grade_answer,
        {END: END, "retrieve": "retrieve"},
    )

    # Compile with in-memory session checkpointer
    checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)


# ── Module-level singleton ────────────────────────────────────────────────────
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────

def run_query(
    query: str,
    session_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    top_k: int = 5,
) -> dict:
    """Execute the query pipeline (retrieve → summarize → action)."""
    session_id = session_id or str(uuid.uuid4())
    initial: AgentState = {
        "session_id":       session_id,
        "query":            query,
        "document_ids":     document_ids or [],
        "top_k":            top_k,
        "mode":             "query",
        "retrieved_chunks": [],
        "filtered_chunks":  [],
        "summary":          "",
        "answer":           "",
        "comparison":       {},
        "alerts":           [],
        "final_response":   "",
        "generation_count": 0,
        "re_query_count":   0,
        "grounded":         False,
        "useful":           False,
        "sources":          [],
        "metadata":         {},
        "messages":         [],
    }
    config = {"configurable": {"thread_id": session_id}}
    result = get_graph().invoke(initial, config=config)
    return {
        "answer":   result.get("final_response") or result.get("answer", ""),
        "summary":  result.get("summary", ""),
        "sources":  result.get("retrieved_chunks", []),
        "alerts":   result.get("alerts", []),
        "metadata": result.get("metadata", {}),
    }


def run_compare(
    document_ids: List[str],
    query: str = "Compare these two documents.",
    session_id: Optional[str] = None,
) -> dict:
    """Execute the compare pipeline (retrieve → compare → action)."""
    session_id = session_id or str(uuid.uuid4())
    initial: AgentState = {
        "session_id":       session_id,
        "query":            query,
        "document_ids":     document_ids,
        "top_k":            4,
        "mode":             "compare",
        "retrieved_chunks": [],
        "filtered_chunks":  [],
        "summary":          "",
        "answer":           "",
        "comparison":       {},
        "alerts":           [],
        "final_response":   "",
        "generation_count": 0,
        "re_query_count":   0,
        "grounded":         False,
        "useful":           False,
        "sources":          [],
        "metadata":         {},
        "messages":         [],
    }
    config = {"configurable": {"thread_id": session_id}}
    result = get_graph().invoke(initial, config=config)
    return {
        "comparison": result.get("comparison", {}),
        "answer":     result.get("final_response") or result.get("answer", ""),
        "sources":    result.get("retrieved_chunks", []),
        "alerts":     result.get("alerts", []),
    }


def run_rag_query(
    question: str,
    top_k: int = 5,
    document_id: Optional[str] = None,
) -> dict:
    """Legacy self-RAG entry point — backward compat with /query/agent."""
    session_id = str(uuid.uuid4())
    initial: AgentState = {
        "session_id":       session_id,
        "query":            question,
        "document_ids":     [document_id] if document_id else [],
        "top_k":            top_k,
        "mode":             "agent",
        "retrieved_chunks": [],
        "filtered_chunks":  [],
        "summary":          "",
        "answer":           "",
        "comparison":       {},
        "alerts":           [],
        "final_response":   "",
        "generation_count": 0,
        "re_query_count":   0,
        "grounded":         False,
        "useful":           False,
        "sources":          [],
        "metadata":         {},
        "messages":         [],
    }
    config = {"configurable": {"thread_id": session_id}}
    result = get_graph().invoke(initial, config=config)
    return {
        "answer":   result.get("answer", ""),
        "sources":  result.get("sources", []),
        "grounded": result.get("grounded", True),
        "useful":   result.get("useful", True),
    }
