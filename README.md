# MADIS: Multi-Agent Document Intelligence System 🧠

Welcome to **MADIS**—a production-grade, fully local, multi-agent AI system designed to intelligently read, summarize, compare, and audit your documents. 

Whether you are completely new to Artificial Intelligence or an experienced engineer, this guide will walk you through exactly what MADIS is, how it works, and how every piece of its complex pipeline fits together. 

---

## 📖 Table of Contents

1. [What is MADIS? (For Beginners)](#what-is-madis-for-beginners)
2. [How is MADIS different from ChatGPT or Gemini?](#how-is-madis-different-from-chatgpt-or-gemini)
3. [The Core Philosophy](#the-core-philosophy)
4. [System Architecture & The Pipeline](#system-architecture--the-pipeline)
   - [1. Data Ingestion & Parsing](#1-data-ingestion--parsing)
   - [2. The Vector Database (Memory)](#2-the-vector-database-memory)
   - [3. The Multi-Agent Brain (LangGraph)](#3-the-multi-agent-brain-langgraph)
5. [The Agents Explained](#the-agents-explained)
6. [Tools, Libraries & Technologies Used](#tools-libraries--technologies-used)
7. [Hardware Limitations & 8GB VRAM Tuning](#hardware-limitations--8gb-vram-tuning)
8. [How to Host & Run MADIS](#how-to-host--run-madis)
9. [Project Directory Structure](#project-directory-structure)

---

## 1. What is MADIS? (For Beginners)

Imagine you have hundreds of legal contracts, research papers, or financial reports. Reading them, finding specific clauses, comparing two different versions of a contract, and spotting anomalies (like a missing signature or a contradictory date) would take a human days or weeks.

**MADIS** acts as a team of hyper-fast, highly-focused AI assistants living entirely on your computer. 

You hand MADIS your documents, and it carefully reads and memorizes them. Then, through a beautiful web interface, you can ask questions like:
- *"What are the key liability clauses in this contract?"*
- *"What is the difference between Document A and Document B?"*

Behind the scenes, MADIS doesn't just use one AI. It uses a **Multi-Agent System**—a workflow where different AI "personas" pass information to one another. One agent finds the document, another summarizes it, and a third audits the summary to raise red flags if it finds contradictions.

## 2. How is MADIS different from ChatGPT or Gemini?

While ChatGPT and Gemini are massive, generalized cloud AI systems, MADIS is a **Specialized, Local RAG System**.

- **100% Private (Local):** When you use ChatGPT, you send your documents to a remote server. MADIS runs **entirely on your own hardware**. Your sensitive documents never leave your computer. 
- **Retrieval-Augmented Generation (RAG):** Standard LLMs (Large Language Models) hallucinate (make things up) because they rely on their pre-trained memory. MADIS uses RAG. It actively searches your specific documents and *forces* the AI to only answer based on the exact paragraphs it retrieved.
- **Team of Agents:** ChatGPT is a single chatbot. MADIS uses a graph of AI agents. Before you even see an answer, MADIS has already had its "Auditor Agent" double-check the work of its "Summarizer Agent".

## 3. The Core Philosophy

MADIS was built with strict hardware constraints in mind. Large language models require massive amounts of VRAM (Video RAM on a Graphics Card). MADIS is specifically engineered to run advanced AI reasoning on consumer-grade hardware—specifically, an **Nvidia RTX 4060 with 8GB of VRAM**.

To achieve this, MADIS relies on **Sequential Processing** (doing one thing at a time) and **Model Quantization** (compressing the AI model) to ensure it never exceeds the GPU's memory limits.

---

## 4. System Architecture & The Pipeline

MADIS is not a single script; it is a distributed, microservice-based application. Here is the step-by-step pipeline of how a document flows through the system.

### 1. Data Ingestion & Parsing
When you upload a file (PDF, DOCX, TXT, Markdown, HTML, or an Image):
1. **FastAPI (The Web Server)** receives the file and saves it securely to the disk.
2. It assigns the job a unique ID and hands it to **Celery** (a background task queue worker).
3. Celery uses the **Document Parser** (powered by `unstructured.io` and `pypdf`) to extract raw text.
4. The text is split into small "chunks" (usually a few paragraphs each) so the AI can digest them easily.

### 2. The Vector Database (Memory)
Computers don't understand words; they understand numbers.
1. Each chunk of text is passed to an **Embedding Model** (`sentence-transformers/all-MiniLM-L6-v2`).
2. This model converts the text into a dense array of numbers (a vector) that captures the *semantic meaning* of the text.
3. These vectors are stored in **Qdrant**, an advanced Vector Database. 
4. Later, when you ask a question, your question is also turned into a vector. Qdrant instantly mathematically calculates which document chunks have a similar meaning to your question.

### 3. The Multi-Agent Brain (LangGraph)
When you ask a question, the request enters **LangGraph**, a framework for creating cyclic AI agent workflows. The workflow passes a shared "State" (a dictionary of data) from one agent node to the next.

---

## 5. The Agents Explained

MADIS utilizes four distinct "Agents" to process queries:

### 🕵️‍♂️ 1. The Retriever Agent
- **Goal:** Find the needle in the haystack.
- **How it works:** It takes your question, embeds it, and queries Qdrant. It pulls the top 5 to 15 most relevant chunks of text from your documents. If you are doing a comparison, it smartly retrieves chunks from both documents equally.

### 📝 2. The Summarizer Agent
- **Goal:** Read the retrieved chunks and formulate a direct answer.
- **How it works:** It reads only the chunks provided by the Retriever. It generates a concise, 3-5 bullet point summary formatted as strict JSON. It is strictly instructed: *"If the answer is not in the context, state exactly: NOT_IN_CONTEXT."*

### ⚖️ 3. The Comparator Agent (Only used in Compare Mode)
- **Goal:** Analyze two different documents side-by-side.
- **How it works:** It receives context from Document A and Document B. It then outputs a highly structured JSON dictionary mapping out exact similarities, precise differences, and a final recommendation.

### 🚨 4. The Action (Auditor) Agent
- **Goal:** Risk and Compliance Analysis.
- **How it works:** It takes the output from the Summarizer or Comparator and audits it. It looks for:
  - **Anomalies:** Outlier data or suspicious claims.
  - **Contradictions:** Two statements in the text that oppose each other.
  - **Missing Clauses:** Important legal/financial elements that should be there but aren't.
- It then saves these flags into a **PostgreSQL Database** so they can be reviewed in the "Alerts" dashboard.

---

## 6. Tools, Libraries & Technologies Used

MADIS is built on a modern Python web stack. Here is the full breakdown:

### Frontend (UI)
- **Streamlit:** Used to build the beautiful, reactive web application in pure Python.
- **Custom CSS:** Injected into Streamlit to create a modern, dark "glassmorphism" aesthetic with gradient backgrounds, soft shadows, and dynamic chat bubbles.

### Backend API
- **FastAPI:** A lightning-fast ASGI Python web framework used to expose endpoints (`/documents/ingest`, `/query`, etc.).
- **Uvicorn:** The ASGI server that runs the FastAPI application.
- **Pydantic:** Used for strict data validation and typing for API requests and responses.

### Background Processing
- **Celery:** Asynchronous task queue used so the web API doesn't freeze while parsing massive PDFs.
- **Redis:** Acts as the message broker for Celery. When FastAPI creates a task, it puts it in Redis. Celery pulls it from Redis.

### AI & Agents
- **LangChain / LangGraph:** Frameworks used to orchestrate the multi-agent state machines and memory check-pointing.
- **Ollama:** A local runtime that allows us to run Large Language Models (like Qwen) natively on Windows/Linux without writing complex PyTorch inference code.
- **Qwen2 (7B-Instruct):** The chosen Local LLM. A 7-billion parameter model by Alibaba, heavily quantized (compressed) to `Q4_K_M` to fit in 4.5GB of VRAM while maintaining excellent reasoning capabilities.
- **Sentence-Transformers:** A highly efficient HuggingFace library used to run the embedding model (`all-MiniLM-L6-v2`) strictly on the CPU.

### Databases & Storage
- **Qdrant:** A high-performance, Rust-based Vector Database used for semantic search.
- **PostgreSQL (via SQLAlchemy & Psycopg2/Asyncpg):** A relational database used to store persistent metadata, file upload statuses, and Action Agent Alerts.

### Observability & Infrastructure
- **MLflow:** Used for experiment tracking. Every query is logged to MLflow with its total latency, number of retrieved sources, and alert counts to monitor system health over time.
- **Docker & Docker Compose:** Used to containerize the infrastructure (Postgres, Redis, Qdrant, MLflow) so the system can be spun up reliably on any machine with a single command.
- **Pytest:** Used for comprehensive Unit and Integration testing.

---

## 7. Hardware Limitations & 8GB VRAM Tuning

Running AI locally is extremely challenging due to memory (VRAM) constraints. An Nvidia RTX 4060 has 8GB of VRAM. A raw 7-billion parameter model requires ~14GB of VRAM. 

Here is exactly how MADIS circumvents these limitations:

1. **Quantization (`Q4_K_M`):** The weights of the LLM are mathematically compressed from 16-bit floating point down to 4-bit integers. This shrinks the model footprint from 14GB down to ~4.5GB, leaving 3.5GB of VRAM for the "Context Window" (KV-Cache).
2. **Strict Context Capping:** The more text you feed the AI, the more VRAM it consumes. The pipeline enforces a hard limit of `3000 characters` of context per query. It will intelligently truncate less relevant chunks rather than crashing the GPU.
3. **CPU Offloading:** The embedding model (`MiniLM`) is explicitly forced to run on the CPU. It is tiny (~90MB) and fast enough on a CPU that it isn't worth taking up precious GPU memory.
4. **Sequential Processing:** The LangGraph nodes are completely synchronous. If the Retriever, Summarizer, and Action agents tried to run at the same time, the GPU would immediately run out of memory (OOM error). `Celery` is explicitly run with `--pool=solo` (concurrency of 1) to guarantee that only one heavy task runs at any given millisecond.

---

## 8. How to Host & Run MADIS

### Prerequisites
- Python 3.11+
- Docker Desktop
- Nvidia GPU (8GB+ VRAM)
- Ollama installed locally.

### Step 1: Install Dependencies
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Download the LLM
Open your terminal and pull the Qwen model via Ollama:
```bash
ollama run qwen2:7b-instruct-q4_K_M
```

### Step 3: Start the Infrastructure
Use Docker to spin up the required databases and MLflow:
```bash
docker compose up -d
```

### Step 4: Start the Backend (FastAPI)
In a new terminal window:
```bash
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 5: Start the Background Worker (Celery)
In a new terminal window:
```bash
.\.venv\Scripts\activate
.\.venv\Scripts\celery -A app.workers.celery_app.celery_app worker --pool=solo --loglevel=INFO
```

### Step 6: Start the Frontend (Streamlit)
In a new terminal window:
```bash
.\.venv\Scripts\activate
streamlit run ui/streamlit_app.py
```
*MADIS will automatically open in your default web browser.*

---

## 9. Project Directory Structure

```text
MADIS/
├── app/                      # Core Backend Code
│   ├── agents/               # LangGraph state machine, nodes, and LLM logic
│   ├── api/                  # FastAPI routers (/documents, /query, /alerts)
│   ├── core/                 # Config, Database setup, Logging
│   ├── models/               # SQLAlchemy ORM Models (Document, Alert)
│   ├── services/             # Abstractions for Qdrant, Parsing, Embeddings
│   └── workers/              # Celery task definitions
├── ui/                       # Frontend Code
│   └── streamlit_app.py      # Streamlit GUI
├── tests/                    # Unit and Integration Tests
├── data/                     # Local storage for uploaded files
├── .github/workflows/        # CI/CD pipelines
├── docker-compose.yml        # Infrastructure setup (Postgres, Qdrant, Redis, MLflow)
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

---

*MADIS represents the bleeding edge of entirely localized, secure, and intelligent document processing. By combining strict engineering constraints with multi-agent orchestration, it achieves enterprise-grade semantic intelligence on consumer-grade hardware.*
