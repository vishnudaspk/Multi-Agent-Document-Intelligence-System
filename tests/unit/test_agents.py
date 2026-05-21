"""
tests/unit/test_agents.py — unit tests for the agent graph (mocked LLM/Qdrant).
"""
from unittest.mock import patch, MagicMock

import pytest


# ── Test graph structure ──────────────────────────────────────────────────────

def test_graph_builds_and_has_expected_nodes():
    """Graph should compile and contain all 8 agent/self-RAG nodes."""
    from app.agents.graph import build_graph

    with patch("app.agents.nodes.create_engine"):
        graph = build_graph()

    expected = {
        "__start__",
        "retrieve", "summarize", "compare", "action",
        "grade_docs", "generate", "hallucination_check", "grade_answer",
    }
    assert expected.issubset(set(graph.nodes)), (
        f"Missing nodes: {expected - set(graph.nodes)}"
    )


# ── Test node_retrieve ────────────────────────────────────────────────────────

@patch("app.agents.nodes.similarity_search")
@patch("app.agents.nodes.embed_query")
def test_node_retrieve_query_mode(mock_embed, mock_search):
    """In query mode, retrieve calls similarity_search once."""
    from app.agents.nodes import node_retrieve

    mock_embed.return_value = [0.1] * 384
    mock_search.return_value = [
        {"text": "chunk1", "score": 0.9, "document_id": "abc", "page_number": 1, "chunk_index": 0},
    ]

    state = {
        "query": "What is this about?",
        "document_ids": [],
        "top_k": 5,
        "mode": "query",
    }

    result = node_retrieve(state)
    assert "retrieved_chunks" in result
    assert len(result["retrieved_chunks"]) == 1
    mock_search.assert_called_once()


@patch("app.agents.nodes.similarity_search")
@patch("app.agents.nodes.embed_query")
def test_node_retrieve_compare_mode(mock_embed, mock_search):
    """In compare mode, retrieve calls similarity_search once per document."""
    from app.agents.nodes import node_retrieve

    mock_embed.return_value = [0.1] * 384
    mock_search.return_value = [
        {"text": "chunk1", "score": 0.9, "document_id": "a", "page_number": 1, "chunk_index": 0},
    ]

    state = {
        "query": "Compare these.",
        "document_ids": ["doc-a-id", "doc-b-id"],
        "top_k": 4,
        "mode": "compare",
    }

    result = node_retrieve(state)
    assert len(result["retrieved_chunks"]) == 2  # 1 per doc
    assert mock_search.call_count == 2


# ── Test node_summarize ───────────────────────────────────────────────────────

@patch("app.agents.nodes.get_llm_client")
def test_node_summarize_returns_answer(mock_llm_factory):
    """Summarize should return an answer and summary from the LLM."""
    from app.agents.nodes import node_summarize

    mock_llm = MagicMock()
    mock_llm.chat.return_value = '{"answer": "Paris, France.", "summary": "About the Eiffel Tower.", "confidence": "high"}'
    mock_llm_factory.return_value = mock_llm

    state = {
        "query": "Where is the Eiffel Tower?",
        "retrieved_chunks": [
            {"text": "The Eiffel Tower is in Paris.", "page_number": 1, "document_id": "abc"},
        ],
        "metadata": {},
    }

    result = node_summarize(state)
    assert result["answer"] == "Paris, France."
    assert result["summary"] == "About the Eiffel Tower."
    assert result["metadata"]["confidence"] == "high"


# ── Test node_compare ─────────────────────────────────────────────────────────

@patch("app.agents.nodes.get_llm_client")
def test_node_compare_returns_structured_diff(mock_llm_factory):
    """Compare should return similarities, differences, summary."""
    from app.agents.nodes import node_compare

    mock_llm = MagicMock()
    mock_llm.chat.return_value = '''{
        "similarities": ["Both mention Paris"],
        "differences": [{"aspect": "Year", "doc_a": "1889", "doc_b": "1890"}],
        "summary": "Documents mostly agree.",
        "recommendation": "Doc A is more accurate."
    }'''
    mock_llm_factory.return_value = mock_llm

    state = {
        "query": "Compare dates.",
        "retrieved_chunks": [
            {"text": "Built in 1889.", "_source_doc": "doc-a", "page_number": 1, "document_id": "doc-a"},
            {"text": "Built in 1890.", "_source_doc": "doc-b", "page_number": 1, "document_id": "doc-b"},
        ],
        "document_ids": ["doc-a", "doc-b"],
    }

    result = node_compare(state)
    assert "comparison" in result
    assert len(result["comparison"]["differences"]) == 1
    assert result["comparison"]["similarities"][0] == "Both mention Paris"


# ── Test node_action ──────────────────────────────────────────────────────────

@patch("app.agents.nodes._save_alerts")
@patch("app.agents.nodes.get_llm_client")
def test_node_action_flags_anomalies(mock_llm_factory, mock_save):
    """Action agent should parse alerts from LLM output and call _save_alerts."""
    from app.agents.nodes import node_action

    mock_llm = MagicMock()
    mock_llm.chat.return_value = '''{
        "alerts": [
            {
                "type": "anomaly",
                "severity": "high",
                "message": "Date mismatch between docs.",
                "context": "1889 vs 1890"
            }
        ]
    }'''
    mock_llm_factory.return_value = mock_llm

    state = {
        "mode": "compare",
        "session_id": "test-session",
        "document_ids": ["doc-a", "doc-b"],
        "comparison": {
            "summary": "Documents disagree on the date.",
            "differences": [{"aspect": "Year", "doc_a": "1889", "doc_b": "1890"}],
            "similarities": [],
        },
    }

    result = node_action(state)
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["type"] == "anomaly"
    assert result["alerts"][0]["severity"] == "high"
    mock_save.assert_called_once()


@patch("app.agents.nodes._save_alerts")
@patch("app.agents.nodes.get_llm_client")
def test_node_action_no_issues_returns_empty(mock_llm_factory, mock_save):
    """Action agent should return empty alerts when nothing is flagged."""
    from app.agents.nodes import node_action

    mock_llm = MagicMock()
    mock_llm.chat.return_value = '{"alerts": []}'
    mock_llm_factory.return_value = mock_llm

    state = {
        "mode": "query",
        "session_id": "test-session",
        "document_ids": [],
        "summary": "The Eiffel Tower is in Paris.",
    }

    result = node_action(state)
    assert result["alerts"] == []


# ── Test _format_chunks helper ────────────────────────────────────────────────

def test_format_chunks_caps_length():
    """Context should be capped at max_chars."""
    from app.agents.nodes import _format_chunks

    chunks = [
        {"text": "A" * 2000, "page_number": 1, "document_id": "abc"},
        {"text": "B" * 2000, "page_number": 2, "document_id": "abc"},
    ]

    result = _format_chunks(chunks, max_chars=2500)
    assert len(result) <= 2600   # first chunk + separator overhead
    assert "B" * 100 not in result  # second chunk should be excluded


def test_format_chunks_empty():
    """Empty chunk list should return empty string."""
    from app.agents.nodes import _format_chunks
    assert _format_chunks([]) == ""
