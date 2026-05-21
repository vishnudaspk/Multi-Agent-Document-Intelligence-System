# Complete Setup Procedure for MADIS

This guide provides a detailed, step-by-step walkthrough to set up the Multi-Agent Document Intelligence System (MADIS) on your local **Windows 11** machine.

**Hardware Target:** RTX 4060 (8GB VRAM), i9 13th Gen, 32GB RAM.

> [!IMPORTANT]
> **Critical Windows Note:** Celery's default `prefork` process pool relies on `os.fork()`, which **does not exist on Windows**. Without the correct pool setting, the Celery worker will appear to accept tasks but will never actually execute them (tasks remain permanently "pending" or "reserved"). MADIS automatically detects Windows and uses the `solo` pool. **Always start the worker with `--pool=solo`** as shown in Step 7.

---

## 1. Prerequisites

Before you begin, ensure you have the following installed on your Windows machine:

1. **Python 3.11+** — installed natively on Windows.
2. **Docker Desktop** — installed and running with WSL2 integration enabled.
3. **Git** — installed natively on Windows.

> [!NOTE]
> All commands in this guide are run in **Windows PowerShell** unless explicitly marked `[WSL2]`.

---

## 2. Environment Variables Setup

Open a new **Windows PowerShell** terminal and navigate to the project root.

1. Copy the example environment file:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` in your editor and configure the credentials. Find and update:
   ```ini
   POSTGRES_USER=madis_user
   POSTGRES_PASSWORD=your_secure_password_here
   DATABASE_URL=postgresql+asyncpg://madis_user:your_secure_password_here@localhost:5432/madis_db
   ```
3. All fields marked `# [CONFIGURE THIS]` require your input.

---

## 3. Python Virtual Environment & Dependencies

1. Create the virtual environment:
   ```powershell
   python -m venv .venv
   ```
2. Activate it:
   ```powershell
   .\.venv\Scripts\activate
   ```
   *(You should see `(.venv)` at the start of your prompt.)*

3. Upgrade build tools:
   ```powershell
   pip install --upgrade pip setuptools wheel
   ```

4. Install project dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

5. **(RTX 4060 only)** Replace CPU PyTorch with the CUDA 12.1 build for GPU-accelerated embeddings:
   ```powershell
   pip install torch==2.3.1+cu121 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```

> [!NOTE]
> `docling` has been removed from dependencies. It caused an `ImportError` on `AutoModelForImageTextToText` from `transformers==4.43.4`. The document parser now uses a 3-tier fallback strategy: **unstructured (fast)** → **pypdf** → **plain text**, all of which are pure-Python with no C-library dependencies.

> [!NOTE]
> `unstructured` is installed with `strategy="fast"` (pdfminer, pure Python). Do **not** use `strategy="hi_res"` unless you have `poppler` and `tesseract` installed and on your system PATH. The `hi_res` strategy also triggers the broken docling import chain.

---

## 4. Database & Infrastructure Setup (Docker)

This step starts Qdrant (Vector DB), PostgreSQL (Relational DB), and Redis (Celery Broker).

1. Ensure Docker Desktop is running.
2. Start all services:
   ```powershell
   docker compose up -d
   ```
3. Verify all services are healthy:
   ```powershell
   docker compose ps
   ```
   You should see `madis_qdrant`, `madis_postgres`, and `madis_redis` all showing `Up (healthy)`.

---

## 5. Local LLM Setup

You have an RTX 4060 (8GB VRAM). Use **Qwen2-7B-Instruct (Q4_K_M)** which fits comfortably within your VRAM.

### Option A: Ollama Native Windows (Recommended)

Native Windows provides the simplest GPU acceleration without WSL2 passthrough complexity.

1. Open a PowerShell terminal (Run as Administrator).
2. Run the provided setup script:
   ```powershell
   .\scripts\ollama_windows.ps1
   ```
   *This downloads the installer, starts the server, pulls the model (~4.5 GB), and runs a smoke test.*

3. Verify your `.env` has these lines active:
   ```ini
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2:7b-instruct-q4_K_M
   # LMSTUDIO_BASE_URL=   ← keep commented out
   ```

> [!TIP]
> For WSL2 Ollama, open a **WSL terminal** and run `bash scripts/setup_ollama.sh`. Note that NVIDIA Container Toolkit must be properly configured in WSL for GPU passthrough. Native Windows is significantly simpler.

### Option B: LM Studio (GUI-based)

1. Download and install LM Studio from [lmstudio.ai](https://lmstudio.ai/).
2. Search for and download `qwen2 7b instruct q4_k_m` (GGUF format).
3. Go to the **Local Server** tab (`<->` icon).
4. Select the Qwen2 model and set the server port to `1234`.
5. Click **Start Server**.
6. In your `.env`, activate LM Studio:
   ```ini
   # OLLAMA_BASE_URL=http://localhost:11434   ← comment out
   LMSTUDIO_BASE_URL=http://localhost:1234/v1
   LMSTUDIO_API_KEY=lm-studio
   ```

---

## 6. Pre-Flight Verification

With Docker services running and your LLM serving, verify all connectivity:

```powershell
python scripts\verify_services.py
```

**Expected output:**
```
  ✔  OK  Qdrant       version=1.9.x  url=http://localhost:6333
  ✔  OK  PostgreSQL   PostgreSQL 16.x on x86_64-pc-linux-musl
  ✔  OK  Redis        version=7.2.x  url=redis://localhost:6379/0
  ✔  OK  Ollama       models: ['qwen2:7b-instruct-q4_K_M']

  4/4 services healthy
```

If any service shows a red `✘`, resolve it before continuing.

---

## 7. Running the Application

You need **two separate terminals** running simultaneously.

### Terminal 1: Start the FastAPI Server

```powershell
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

On startup, the server automatically:
- Creates all PostgreSQL tables (idempotent)
- Creates the Qdrant vector collection and payload indices

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Terminal 2: Start the Celery Worker

> [!IMPORTANT]
> The `--pool=solo` flag is **mandatory on Windows**. Without it, the Celery worker will accept tasks but never execute them due to the missing `os.fork()` system call.

```powershell
.\.venv\Scripts\activate
.\.venv\Scripts\celery -A app.workers.celery_app.celery_app worker --pool=solo --loglevel=INFO --logfile=logs\celery.log
```

Confirm the worker started correctly — you should see:
```
concurrency: 1 (solo)
[tasks]
  . tasks.ingest_document
celery@HOSTNAME ready.
```

Worker logs are written to `logs\celery.log` for debugging.

> [!TIP]
> `--concurrency=1` and `solo` pool together ensure one task runs at a time, preventing GPU out-of-memory errors during the embedding step. This is the recommended setting for a single RTX 4060.

---

## 8. Testing the End-to-End Pipeline

With FastAPI and Celery both running, open a **third PowerShell terminal**:

```powershell
.\.venv\Scripts\activate
python scripts\test_ingestion.py
```

**What the test does:**
1. Generates a valid, uncompressed test PDF with real extractable text (pure Python — no poppler required).
2. Posts it to `POST /documents/ingest`.
3. The API commits the document to PostgreSQL **before** queuing the Celery task (fixes a race condition where the solo worker starts before the DB row exists).
4. Polls `GET /documents/status/{job_id}` until the status changes from `processing` → `completed`.
5. Queries Qdrant directly to verify the vector (384 dimensions) and payload metadata (`document_id`, `filename`, `timestamp`, `chunk_index`, `text`) are all present.

**Expected output:**
```
=== Testing Ingestion Pipeline ===
Created sample PDF: ...\test_sample.pdf

[1] Uploading document to /documents/ingest...
Upload successful! Document ID: <uuid>, Job ID: <uuid>

[2] Polling ingestion status for Job ID: <uuid>...
  Attempt 1/30 - Status: completed
  Ingestion finished successfully!

[3] Verifying Qdrant chunks for Document ID: <uuid>...
  Found 1 chunks in Qdrant.
  Vector dimensionality: 384
  Payload metadata:
  { 'chunk_index': 0, 'document_id': '...', 'filename': 'test_sample.pdf', ... }
  All metadata fields present and correct!

=== Test Passed Successfully! ===
```

---

## 9. Known Issues & Fixes Applied

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Tasks stuck at "pending" forever | Celery `prefork` pool uses `os.fork()` which is Unix-only | `celery_app.py` auto-detects `win32` and uses `solo` pool; use `--pool=solo` CLI flag |
| `Unable to get page count. Is poppler installed?` | `unstructured` `hi_res` strategy requires poppler binary | Parser now uses `strategy="fast"` (pure Python pdfminer) |
| `ImportError: AutoModelForImageTextToText` | `docling` imports from newer `transformers` API not in `4.43.4` | `docling` removed; replaced with `pypdf` as Tier 2 fallback |
| `Document not found in DB` (task fails immediately) | Celery `solo` pool starts the task before the API commits the transaction | API route now commits DB **before** calling `.delay()` |
| Test PDF parsed to 0 chunks | Original test PDF used FlateDecode-compressed empty stream | `test_ingestion.py` generates a proper uncompressed PDF with real text |
| `Xet Storage` warning in logs | `hf_xet` package optional for HuggingFace downloads | Cosmetic only; install `pip install hf_xet` to silence it |

---

## 10. Document Parser Architecture

The parser in `app/services/document_parser/parser.py` uses a 3-tier fallback strategy:

```
Tier 1: unstructured (strategy="fast")
  └─ Uses pdfminer.six internally — pure Python, no system dependencies
  └─ Applies semantic chunking via chunk_by_title (max 1000 chars, 100-char overlap)
  └─ If returns 0 chunks → fall through to Tier 2

Tier 2: pypdf (PDF files only)
  └─ Pure Python PDF text extractor — no C dependencies
  └─ Paragraph-aware chunking (~800 chars per chunk)
  └─ If returns 0 chunks → fall through to Tier 3

Tier 3: plain text reader (.txt / .md / .html only)
  └─ UTF-8 text reader with paragraph splitting
```

> [!TIP]
> For scanned PDFs (image-only, no embedded text), you need OCR. Install `poppler` (for PDF→image conversion) and `tesseract` (for OCR), add them to your system PATH, then switch `strategy="hi_res"` in `parser.py`. This is **not** required for normal text-based PDFs.

---

## 11. Ingestion Pipeline Flow

```
POST /documents/ingest (FastAPI, async)
  │
  ├── 1. Validate file type & size
  ├── 2. Save to data/uploads/<uuid>.ext
  ├── 3. INSERT Document + ProcessingJob → PostgreSQL
  ├── 4. COMMIT (must happen before queuing!)
  └── 5. ingest_document.delay() → Redis queue
                │
                ▼
         Celery Worker (solo pool)
           │
           ├── 1. Mark job → PROCESSING
           ├── 2. parse_document()  [3-tier parser]
           ├── 3. embed_texts()     [sentence-transformers, 384-dim]
           ├── 4. ensure_collection() + upsert_chunks() → Qdrant
           ├── 5. INSERT DocumentChunks → PostgreSQL
           └── 6. Mark job → COMPLETED (or FAILED + error_msg)
```

---

## 12. Makefile Quick Reference

```powershell
make up          # docker compose up -d
make down        # docker compose down
make api         # start FastAPI dev server
make worker      # start Celery worker (solo pool)
make test        # run pytest suite
make logs        # tail celery.log
make clean       # remove __pycache__ and .pyc files
```
