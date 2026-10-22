"""
Celery tasks for V2 inference. Loaded only in the worker process (e.g. celery -A app.celery_app worker --include app.tasks).
"""

import json
import logging
import random
from typing import Any

import redis

from app.celery_app import celery_app
from app.config import get_settings

logger = logging.getLogger(__name__)

# Sync Redis client for worker to write to fast cache (DB 2). Do not use in API.
def _get_fast_cache_sync():
    return redis.Redis.from_url(get_settings().redis_fast_cache_url, decode_responses=True)


FAST_CACHE_TTL_SECONDS = 1800  # 30 min
MAX_JITTER_SECONDS = 300  # 5 min spread for precomputation


@celery_app.task(name="app.tasks.run_lstm_inference", bind=True, max_retries=3)
def run_lstm_inference(
    self,
    model_id: str,
    features: dict[str, Any],
    target_key: str,
) -> dict[str, Any]:
    """
    Run inference and write scalar bundle to fast cache (Redis DB 2).
    Called by API (on_demand_sync wait) or by precomputation batch (with jitter).
    """
    try:
        # Stub: replace with real model load and inference (e.g. model_registry.predict)
        scalar_bundle: dict[str, Any] = {
            "stress_index": 0.82,
            "fruit_count_pred": 1345,
            "oil_concentration_pred": 16.4,
        }
        cache = _get_fast_cache_sync()
        cache_key = f"intelligence:cache:{target_key}"
        cache.setex(cache_key, FAST_CACHE_TTL_SECONDS, json.dumps(scalar_bundle))
        logger.info("Cached inference result for key=%s model_id=%s", target_key, model_id)
        return scalar_bundle
    except Exception as exc:
        logger.exception("run_lstm_inference failed for key=%s", target_key)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(name="app.tasks.trigger_precomputation_batch")
def trigger_precomputation_batch() -> None:
    """
    Master task run by Celery Beat every 15 min. Fans out inference tasks with jitter
    to avoid thundering herd (ARCHITECTURE_V2_PLAN.md §4.3).
    """
    # Placeholder: replace with real entity discovery (Orion, config, or registration).
    entities = ["parcel_001", "parcel_002", "parcel_003"]
    model_id = "olive_lstm_yield_v1"
    for entity_id in entities:
        features = {
            "temp_max": 30.0,
            "soil_moisture": 0.15,
            "shade_percentage": 65.0,
        }
        jitter = random.randint(0, MAX_JITTER_SECONDS)
        run_lstm_inference.apply_async(
            kwargs={"model_id": model_id, "features": features, "target_key": entity_id},
            countdown=jitter,
        )
    logger.info("Precomputation batch enqueued %d entities with jitter", len(entities))
