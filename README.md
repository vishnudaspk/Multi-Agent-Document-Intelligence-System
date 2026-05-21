<div align="center">
  <h1>MADIS</h1>
  <p><strong>Multi-Agent Document Intelligence System</strong></p>
  
  <p>
    A production-grade, locally-hosted, multi-agent AI system designed to intelligently ingest, query, and audit complex documents with uncompromising privacy.
  </p>
</div>

<hr />

## Overview

MADIS represents a paradigm shift in how organizations interact with unstructured data. Engineered to operate entirely on consumer-grade hardware without sacrificing analytical rigor, MADIS acts as a private, high-performance team of AI agents living within your local infrastructure.

Whether dealing with dense legal contracts, intricate financial statements, or vast medical records, MADIS utilizes an advanced Retrieval-Augmented Generation (RAG) pipeline and multi-agent workflows to synthesize, compare, and audit information securely.

## Key Differentiators

*   **Absolute Privacy (100% Local):** Unlike cloud-based LLMs, MADIS processes everything locally. Your sensitive documents never leave your secure environment.
*   **Multi-Agent Orchestration:** MADIS leverages a LangGraph-powered network of specialized AI agents -- including Retrievers, Summarizers, Comparators, and Auditors -- to fact-check and validate outputs.
*   **Consumer Hardware Optimized:** Specifically tuned to run advanced reasoning on local hardware (e.g., Nvidia RTX 4060 8GB VRAM) using precise memory management, model quantization (Q4_K_M), and sequential processing workflows.
*   **Production-Grade User Interface:** Built on Streamlit but heavily customized with a premium, responsive frontend featuring hardware telemetry, dynamic auto-scrolling, and inline metadata analysis.

## System Architecture

MADIS is constructed as a distributed, microservice-based application, ensuring scalability and fault tolerance.

### 1. Data Ingestion and Semantic Parsing
*   **FastAPI** handles secure, asynchronous file uploads.
*   **Celery and Redis** manage background task queues to process massive PDFs without blocking the API.
*   The **Document Parser** intelligently chunks text and preserves semantic boundaries.

### 2. High-Performance Vector Storage
*   Text chunks are mapped into high-dimensional semantic spaces using `sentence-transformers/all-MiniLM-L6-v2` (offloaded to the CPU to preserve VRAM).
*   Vectors are stored in **Qdrant**, an ultra-fast Rust-based vector database, enabling sub-millisecond semantic similarity searches.

### 3. The Multi-Agent Cognitive Engine
User queries are routed through an intricate cyclic workflow managed by **LangGraph**:
*   **Retriever Agent:** Identifies and extracts the most relevant document chunks from the vector space.
*   **Summarizer Agent:** Synthesizes the extracted chunks into a concise, strictly formatted response.
*   **Comparator Agent:** Conducts side-by-side analyses of different documents, highlighting similarities and discrepancies.
*   **Auditor Agent:** Acts as a compliance guardrail, rigorously checking the generated responses against the source text to flag anomalies, contradictions, or hallucinations, which are then logged to a PostgreSQL database.

## Technology Stack

| Component | Technology | Description |
|-----------|------------|-------------|
| **Frontend** | Streamlit | Responsive, custom UI with advanced telemetry and user experience enhancements. |
| **Backend** | FastAPI, Uvicorn, Pydantic | High-performance, strictly-typed ASGI API. |
| **Task Queue** | Celery, Redis | Robust asynchronous background processing. |
| **AI / ML** | LangGraph, Ollama, Qwen2 7B | Multi-agent orchestration and quantized local LLM inference. |
| **Database** | PostgreSQL, Qdrant | Relational metadata storage and semantic vector indexing. |
| **Observability** | MLflow | Comprehensive query tracking, latency monitoring, and telemetry. |
| **Infrastructure**| Docker | Containerized, easily deployable microservices. |

## Quick Start

### Prerequisites
*   Docker and Docker Compose
*   Nvidia GPU with CUDA toolkit (Minimum 8GB VRAM recommended)
*   Python 3.10+

### Installation
1.  Clone the repository.
2.  Follow the official [Installation Guide](INSTALLATION.md) for detailed, step-by-step instructions on environment setup, Docker orchestration, and LLM configuration.
3.  Launch the orchestration via Docker Compose.
4.  Access the UI at `http://localhost:8501`.

## Documentation

*   [Installation Guide](INSTALLATION.md): Detailed deployment instructions.
*   [Architecture and Roadmap](ROADMAP.md): Future vision towards multi-modal intelligence and distributed GPU clusters.

## Known Constraints

*   **Clipboard API**: The copy functionality in the chat interface relies on `navigator.clipboard.writeText()`. This browser API enforces a secure context. It will work locally on `localhost:8501`, but if deployed on a remote server without HTTPS, the copy buttons will silently fail. Ensure you deploy behind a reverse proxy with TLS/HTTPS enabled for full functionality.

## License

This project is proprietary and confidential. Unauthorized copying of this file, via any medium, is strictly prohibited.
