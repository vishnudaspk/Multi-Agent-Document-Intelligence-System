# MADIS Installation & Setup Guide

This comprehensive guide provides the step-by-step procedure required to deploy the **Multi-Agent Document Intelligence System (MADIS)** on a local Windows 11 environment.

**Target Hardware Profile:** NVIDIA RTX 4060 (8GB VRAM), Intel Core i9 (13th Gen) or equivalent, 32GB RAM.

> [!IMPORTANT]
> **Windows Compatibility Notice:** Celery's default `prefork` process pool relies on the `os.fork()` system call, which is not supported natively on Windows. You **must** start the Celery worker using the `--pool=solo` flag. Failure to do so will result in tasks hanging in a "pending" state indefinitely.

---

## 1. Prerequisites

Ensure the following dependencies are installed and configured on your host machine:

- **Python 3.11+** (Native Windows installation)
- **Docker Desktop** (With WSL2 backend integration enabled)
- **Git** (Native Windows installation)

---

## 2. Environment Configuration

1. Open **Windows PowerShell** and navigate to the MADIS project root directory.
2. Duplicate the environment template:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Open the `.env` file in your preferred text editor and configure your secure credentials:
   ```ini
   POSTGRES_USER=madis_user
   POSTGRES_PASSWORD=your_secure_password_here
   DATABASE_URL=postgresql+asyncpg://madis_user:your_secure_password_here@localhost:5432/madis_db
   ```
   *Note: Ensure all fields marked with `# [CONFIGURE THIS]` are properly updated.*

---

## 3. Python Virtual Environment

1. Initialize a new virtual environment:
   ```powershell
   python -m venv .venv
   ```
2. Activate the environment:
   ```powershell
   .\.venv\Scripts\activate
   ```
3. Upgrade core build tools:
   ```powershell
   pip install --upgrade pip setuptools wheel
   ```
4. Install the required project dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
5. **(For NVIDIA GPU Acceleration):** Install the CUDA 12.1 PyTorch build to enable GPU-accelerated embeddings:
   ```powershell
   pip install torch==2.3.1+cu121 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```

---

## 4. Infrastructure Deployment

MADIS relies on Docker to orchestrate its core infrastructure: Qdrant (Vector DB), PostgreSQL (Relational DB), and Redis (Task Broker).

1. Ensure Docker Desktop is running.
2. Spin up the infrastructure in detached mode:
   ```powershell
   docker compose up -d
   ```
3. Verify the health of all containers:
   ```powershell
   docker compose ps
   ```
   *Expect to see `madis_qdrant`, `madis_postgres`, and `madis_redis` with a status of `Up (healthy)`.*

---

## 5. Local LLM Configuration (Ollama)

Given the 8GB VRAM constraint, MADIS utilizes **Qwen2-7B-Instruct (Q4_K_M)** for optimal performance-to-memory ratio.

1. Open a new PowerShell terminal (Run as Administrator).
2. Execute the automated Ollama setup script:
   ```powershell
   .\scripts\ollama_windows.ps1
   ```
   *This script downloads the Ollama runtime, starts the server, pulls the quantized Qwen2 model (~4.5 GB), and runs a validation test.*
3. Verify your `.env` configuration points to the local Ollama instance:
   ```ini
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2:7b-instruct-q4_K_M
   ```

---

## 6. Pre-Flight System Verification

Before launching the application stack, run the verification script to ensure all microservices are communicating correctly:

```powershell
python scripts\verify_services.py
```

**Expected Output:**
```text
  ✔  OK  Qdrant       version=1.9.x  url=http://localhost:6333
  ✔  OK  PostgreSQL   PostgreSQL 16.x on x86_64-pc-linux-musl
  ✔  OK  Redis        version=7.2.x  url=redis://localhost:6379/0
  ✔  OK  Ollama       models: ['qwen2:7b-instruct-q4_K_M']

  4/4 services healthy
```

---

## 7. Launching the MADIS Stack

The system requires two distinct processes running concurrently.

### Terminal 1: FastAPI Backend
Launch the core API server:
```powershell
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*The server will automatically perform idempotent database migrations and initialize Qdrant collections. API documentation is available at `http://localhost:8000/docs`.*

### Terminal 2: Celery Background Worker
Launch the task queue worker. **Do not omit the `--pool=solo` flag.**
```powershell
.\.venv\Scripts\activate
.\.venv\Scripts\celery -A app.workers.celery_app.celery_app worker --pool=solo --loglevel=INFO --logfile=logs\celery.log
```
*Using `--concurrency=1` via the solo pool guarantees sequential processing, preventing GPU Out-Of-Memory (OOM) faults during embedding generation.*

### Terminal 3: Streamlit Frontend (Optional)
Launch the user interface:
```powershell
.\.venv\Scripts\activate
streamlit run ui/streamlit_app.py
```

---

## 8. End-to-End Pipeline Validation

To ensure the entire ingestion and retrieval pipeline is fully operational, open a new terminal and run the test suite:

```powershell
.\.venv\Scripts\activate
python scripts\test_ingestion.py
```

This automated test will generate a sample PDF, submit it to the API, poll the Celery worker for completion, and verify the resulting semantic vectors in Qdrant. A successful test will conclude with `=== Test Passed Successfully! ===`.

---

## Quick Reference (Makefile)

For rapid orchestration, MADIS includes a `Makefile`:

```powershell
make up          # Start Docker infrastructure
make down        # Teardown Docker infrastructure
make api         # Start FastAPI server
make worker      # Start Celery worker (solo pool)
make test        # Execute Pytest suite
make logs        # Tail Celery worker logs
```
