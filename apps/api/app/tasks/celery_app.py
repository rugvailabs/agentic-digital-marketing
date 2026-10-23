"""Celery app + beat schedule.

Runs in the `worker` and `beat` containers (never on Windows — Celery has no
supported Windows worker pool). Entrypoint is
`celery -A app.tasks.celery_app:celery_app`.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery_app = Celery(
    "trendforge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.ingest", "app.tasks.curate"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.tz,
    enable_utc=True,
    task_track_started=True,
    # Tasks are idempotent (unique per region+source+run_id), so a redelivery
    # after a worker dies is safe and preferable to losing the cycle.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=600,
    task_time_limit=900,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)

_minutes = max(1, min(59, settings.ingest_interval_minutes))

celery_app.conf.beat_schedule = {
    "ingest-all-regions": {
        "task": "app.tasks.ingest.ingest_all_regions",
        # Every N minutes on the clock rather than N minutes after the last
        # run, so snapshot timestamps stay comparable across restarts.
        "schedule": crontab(minute=f"*/{_minutes}"),
    }
}
