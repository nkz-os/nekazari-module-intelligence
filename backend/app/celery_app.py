"""
Celery application for V2 inference (API/Worker split).

Broker and backend use Redis DB 0 and DB 1. Worker writes results to Redis DB 2 (fast cache).
API pod only imports this module to send tasks (send_task); it does not import app.tasks.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings


def _make_celery_app() -> Celery:
    s = get_settings()
    app = Celery(
        "intelligence_v2",
        broker=s.redis_broker_url,
        backend=s.redis_backend_url,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Europe/Madrid",
        enable_utc=True,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_concurrency=2,
        task_time_limit=300,
    )
    # Precomputation: master task every 15 min; task itself fans out with jitter
    app.conf.beat_schedule = {
        "precompute-every-15-minutes": {
            "task": "app.tasks.trigger_precomputation_batch",
            "schedule": crontab(minute="*/15"),
        },
    }
    return app


celery_app = _make_celery_app()
