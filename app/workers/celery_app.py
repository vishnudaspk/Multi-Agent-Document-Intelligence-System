"""
app/workers/celery_app.py
Celery application instance — import this everywhere you need @app.task
"""
import sys
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "madis",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks.document_tasks"],
)

# prefork pool uses os.fork() which is Unix-only.
# On Windows, use 'threads' pool to allow multi-core concurrency.
_pool = "threads" if sys.platform == "win32" else "prefork"

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_pool=_pool,
    worker_prefetch_multiplier=4,   # Allow prefetching more tasks
    worker_concurrency=4,           # Allow multiple tasks concurrently on threads
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)
