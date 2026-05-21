"""
tests/integration/test_api.py

Integration tests against the running stack.
Requires: docker compose up -d + Ollama running + FastAPI + Celery worker.

Run: pytest tests/integration/ -v
"""
import time

import pytest
import httpx

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=60)


# ── Health ────────────────────────────────────────────────────────────────────

def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "MADIS" in r.json()["service"]


def test_health_liveness(client):
    r = client.get("/health/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_readiness(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["backends"]["qdrant"] == "ok"
    assert data["backends"]["redis"]  == "ok"


# ── Documents ─────────────────────────────────────────────────────────────────

def test_list_documents(client):
    r = client.get("/documents/?limit=10&offset=0")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_upload_and_query(client, tmp_path):
    """Full end-to-end: upload → poll → query → delete."""

    # 1. Upload a text file via /documents/ingest
    test_doc = tmp_path / "test.txt"
    test_doc.write_text(
        "The Eiffel Tower is located in Paris, France. "
        "It was built by Gustave Eiffel and completed in 1889. "
        "It stands 330 meters tall and is the most-visited paid monument in the world."
    )

    with open(test_doc, "rb") as f:
        r = client.post(
            "/documents/ingest",
            files={"file": ("test.txt", f, "text/plain")},
        )
    assert r.status_code == 202, r.text
    data = r.json()
    document_id = data["document_id"]
    job_id      = data["job_id"]
    assert document_id
    assert job_id

    # 2. Poll job status until completed (max 90s)
    for attempt in range(30):
        time.sleep(3)
        r = client.get(f"/documents/status/{job_id}")
        assert r.status_code == 200
        status = r.json()["status"]
        if status == "completed":
            break
        assert status != "failed", f"Ingestion failed: {r.json()}"
    else:
        pytest.fail("Ingestion did not complete in 90s")

    # 3. Get document detail
    r = client.get(f"/documents/{document_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"

    # 4. RAG query via /query/
    r = client.post(
        "/query/",
        json={"question": "Where is the Eiffel Tower?", "top_k": 3},
        timeout=120,
    )
    assert r.status_code == 200, r.text
    ans = r.json()
    assert ans.get("answer"), "Answer should not be empty"
    assert len(ans.get("sources", [])) > 0

    # 5. Delete
    r = client.delete(f"/documents/{document_id}")
    assert r.status_code == 204


# ── Alerts ────────────────────────────────────────────────────────────────────

def test_alerts_endpoint(client):
    """GET /alerts/ should return a list (possibly empty)."""
    r = client.get("/alerts/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_alerts_with_filters(client):
    """GET /alerts/ with query params should not error."""
    r = client.get("/alerts/?severity=high&limit=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Query edge cases ─────────────────────────────────────────────────────────

def test_query_no_documents_returns_404_or_answer(client):
    r = client.post("/query/", json={"question": "What is the meaning of life?"})
    assert r.status_code in (200, 404)


def test_query_validation_rejects_short_question(client):
    r = client.post("/query/", json={"question": "ab"})
    assert r.status_code == 422  # Pydantic validation: min_length=3
