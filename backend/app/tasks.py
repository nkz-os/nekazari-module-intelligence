"""
Celery tasks for V2 inference. Loaded only in the worker process (e.g. celery -A app.celery_app worker --include app.tasks).
"""

import json
import logging
from typing import Any

import redis

from app.celery_app import celery_app
from app.config import get_settings
from app.schemas.v2_predict import AVAILABLE_MODELS

logger = logging.getLogger(__name__)

# Sync Redis client for worker to write to fast cache (DB 2). Do not use in API.
def _get_fast_cache_sync():
    return redis.Redis.from_url(get_settings().redis_fast_cache_url, decode_responses=True)


FAST_CACHE_TTL_SECONDS = 1800  # 30 min


class ModelNotAvailableError(RuntimeError):
    """Raised when a registered model_id has no deployed implementation."""


def _run_model(model_id: str, features: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to the deployed model implementation.

    No V2 model is deployed yet. Never return placeholder values here: downstream
    consumers (e.g. tracker actuation rules) act on these scalars.
    """
    raise ModelNotAvailableError(f"No implementation deployed for model_id={model_id}")


@celery_app.task(name="app.tasks.run_lstm_inference", bind=True, max_retries=3)
def run_lstm_inference(
    self,
    model_id: str,
    features: dict[str, Any],
    target_key: str,
) -> dict[str, Any]:
    """
    Run inference and write scalar bundle to fast cache (Redis DB 2).
    Fails without caching when the model is not available.
    """
    if model_id not in AVAILABLE_MODELS:
        logger.warning("Inference refused: model not available model_id=%s key=%s", model_id, target_key)
        raise ModelNotAvailableError(f"Model not available: {model_id}")
    try:
        scalar_bundle = _run_model(model_id, features)
        cache = _get_fast_cache_sync()
        cache_key = f"intelligence:cache:{target_key}"
        cache.setex(cache_key, FAST_CACHE_TTL_SECONDS, json.dumps(scalar_bundle))
        logger.info("Cached inference result for key=%s model_id=%s", target_key, model_id)
        return scalar_bundle
    except ModelNotAvailableError:
        raise
    except Exception as exc:
        logger.exception("run_lstm_inference failed for key=%s", target_key)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
