# Makefile for MADIS — Multi-Agent Document Intelligence System
# Usage: make <target>
# Requires: Docker, Python 3.11, make (install via 'winget install GnuWin32.Make' on Windows)

PYTHON   := python
VENV     := .venv
PIP      := $(VENV)/Scripts/pip
PYTEST   := $(VENV)/Scripts/pytest

.PHONY: help setup venv install docker-up docker-down verify server worker test clean

help:
	@echo.
	@echo  MADIS — Available targets:
	@echo  ─────────────────────────────────────────────────
	@echo  setup        Full first-time setup (venv + install + docker)
	@echo  venv         Create Python virtual environment
	@echo  install      Install Python dependencies
	@echo  docker-up    Start Qdrant + PostgreSQL + Redis
	@echo  docker-down  Stop all containers
	@echo  verify       Run service pre-flight check
	@echo  server       Start FastAPI dev server
	@echo  worker       Start Celery worker
	@echo  test         Run pytest
	@echo  clean        Remove venv + __pycache__
	@echo.

# ── First-time setup ─────────────────────────────────────────────────────────
setup: venv install docker-up verify
	@echo Setup complete.

# ── Virtual environment ──────────────────────────────────────────────────────
venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

# ── Install dependencies ─────────────────────────────────────────────────────
install:
	$(PIP) install -r requirements.txt

# ── Docker services ──────────────────────────────────────────────────────────
docker-up:
	docker compose up -d
	@echo Waiting for services to be healthy...
	@timeout /t 8 /nobreak >nul
	docker compose ps

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Pre-flight check ─────────────────────────────────────────────────────────
verify:
	$(VENV)/Scripts/python scripts/verify_services.py

# ── Application ──────────────────────────────────────────────────────────────
server:
	$(VENV)/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker:
	$(VENV)/Scripts/celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=1

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	$(PYTEST) tests/ -v

# ── Cleanup ──────────────────────────────────────────────────────────────────
clean:
	if exist $(VENV) rmdir /s /q $(VENV)
	for /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	@echo Cleaned.
