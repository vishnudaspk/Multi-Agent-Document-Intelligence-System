"""
scripts/test_ingestion.py

Uploads a sample PDF to POST /ingest, polls for completion, 
and queries Qdrant directly to verify chunks and metadata payload.

Run: python scripts/test_ingestion.py
"""
import sys
import time
import requests
from pathlib import Path
from pprint import pprint

# Ensure we can import from app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings

API_URL = f"http://localhost:{settings.app_port}"
QDRANT_URL = f"http://localhost:{settings.qdrant_port}"
COLLECTION_NAME = settings.qdrant_collection_name


def _create_test_pdf(path: Path) -> None:
    """
    Write a minimal but valid, uncompressed PDF with real extractable text.
    No FlateDecode — pdfminer, pypdf, and unstructured can all read it reliably.
    """
    lines = [
        "(Multi-Agent Document Intelligence System - Test Document) Tj",
        "0 -20 Td (This document tests the full ingestion pipeline.) Tj",
        "0 -20 Td (It includes multiple lines of text for semantic chunking.) Tj",
        "0 -20 Td (The ingestion pipeline parses, embeds, and stores this content.) Tj",
        "0 -20 Td (Vector storage is handled by Qdrant for similarity search.) Tj",
        "0 -20 Td (This verifies end-to-end document processing on Windows.) Tj",
        "0 -20 Td (Celery workers use the solo pool to avoid os.fork issues.) Tj",
    ]
    content_stream = (
        "BT\n/F1 12 Tf\n72 720 Td\n" +
        "\n".join(lines) +
        "\nET"
    ).encode()
    content_length = len(content_stream)

    # Build objects dict
    objs = {
        1: b"<</Type/Catalog/Pages 2 0 R>>",
        2: b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        3: b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
           b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
        4: b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        5: (
            f"<</Length {content_length}>>".encode() +
            b"\nstream\n" + content_stream + b"\nendstream"
        ),
    }

    # Assemble body and track byte offsets for xref
    body = b"%PDF-1.4\n"
    offsets: dict[int, int] = {}
    for n in sorted(objs):
        offsets[n] = len(body)
        body += f"{n} 0 obj\n".encode() + objs[n] + b"\nendobj\n\n"

    # xref table
    xref_pos = len(body)
    n_objs = len(objs) + 1          # +1 for the free entry (obj 0)
    xref = b"xref\n"
    xref += f"0 {n_objs}\n".encode()
    xref += b"0000000000 65535 f \n"
    for i in range(1, n_objs):
        xref += f"{offsets[i]:010d} 00000 n \n".encode()

    trailer = (
        b"trailer\n"
        + f"<</Size {n_objs}/Root 1 0 R>>\n".encode()
        + b"startxref\n"
        + f"{xref_pos}\n".encode()
        + b"%%EOF\n"
    )

    path.write_bytes(body + xref + trailer)

def main():
    print("=== Testing Ingestion Pipeline ===")
    
    # 1. Create a sample PDF file
    test_pdf_path = Path("test_sample.pdf")
    _create_test_pdf(test_pdf_path)
    
    print(f"Created sample PDF: {test_pdf_path.absolute()}")

    try:
        # 2. Upload the document via POST /ingest
        print("\n[1] Uploading document to /documents/ingest...")
        with open(test_pdf_path, "rb") as f:
            resp = requests.post(
                f"{API_URL}/documents/ingest",
                files={"file": ("test_sample.pdf", f, "application/pdf")}
            )
            
        if resp.status_code != 202:
            print(f"Upload failed: {resp.status_code} - {resp.text}")
            sys.exit(1)
            
        data = resp.json()
        doc_id = data["document_id"]
        job_id = data["job_id"]
        print(f"Upload successful! Document ID: {doc_id}, Job ID: {job_id}")

        # 3. Poll GET /status/{job_id} until completed
        print(f"\n[2] Polling ingestion status for Job ID: {job_id}...")
        max_attempts = 30
        for attempt in range(max_attempts):
            resp = requests.get(f"{API_URL}/documents/status/{job_id}")
            if resp.status_code != 200:
                print(f"Failed to fetch status: {resp.text}")
                sys.exit(1)
                
            job_info = resp.json()
            status = job_info["status"]
            
            print(f"  Attempt {attempt+1}/{max_attempts} - Status: {status}")
            
            if status == "completed":
                print("  Ingestion finished successfully!")
                break
            elif status == "failed":
                print(f"  Ingestion failed: {job_info.get('error_msg')}")
                sys.exit(1)
                
            time.sleep(2)
        else:
            print("  Timeout waiting for ingestion to complete.")
            sys.exit(1)

        # 4. Verify Qdrant vectors and metadata directly
        print(f"\n[3] Verifying Qdrant chunks for Document ID: {doc_id}...")
        qdrant_query = {
            "filter": {
                "must": [
                    {
                        "key": "document_id",
                        "match": {"value": doc_id}
                    }
                ]
            },
            "limit": 10,
            "with_payload": True,
            "with_vector": True
        }
        
        q_resp = requests.post(f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/scroll", json=qdrant_query)
        if q_resp.status_code != 200:
            print(f"Qdrant query failed: {q_resp.text}")
            sys.exit(1)
            
        points = q_resp.json().get("result", {}).get("points", [])
        
        if not points:
            print("No points found in Qdrant for this document!")
            sys.exit(1)
            
        print(f"  Found {len(points)} chunks in Qdrant.")
        
        # Verify metadata fields
        point = points[0]
        payload = point["payload"]
        vector = point["vector"]
        
        print(f"  Vector dimensionality: {len(vector)}")
        print("  Payload metadata:")
        pprint(payload, indent=4)
        
        expected_fields = ["document_id", "filename", "timestamp", "chunk_index", "text"]
        missing_fields = [f for f in expected_fields if f not in payload]
        if missing_fields:
            print(f"  ERROR: Missing expected metadata fields: {missing_fields}")
            sys.exit(1)
            
        print("  All metadata fields present and correct!")
        print("\n=== Test Passed Successfully! ===")
        
    finally:
        # Cleanup test file
        if test_pdf_path.exists():
            test_pdf_path.unlink()


if __name__ == "__main__":
    main()
