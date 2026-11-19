from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "ai_document_research_agent",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.document_tasks.process_document_task": {
            "queue": "document_processing"
        }
    },
)

celery_app.autodiscover_tasks([
    "app.workers",
])