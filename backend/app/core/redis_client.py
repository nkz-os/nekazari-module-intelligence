"""
Redis clients with strict DB segmentation (ARCHITECTURE_V2_PLAN.md §4.1).

- JobQueue uses DB 3 only (legacy queue).
- Fast cache (V2 scalar bundles) uses DB 2 only; API reads here.
"""

import logging
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client; connect via URL (with DB index) for strict segmentation."""

    def __init__(self, role: str = "jobqueue"):
        """
        Args:
            role: 'jobqueue' -> DB 3 (legacy JobQueue); 'fast_cache' -> DB 2 (V2 scalar cache).
        """
        self.role = role
        self.client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        from app.config import get_settings
        s = get_settings()
        url = s.redis_jobqueue_url if self.role == "jobqueue" else s.redis_fast_cache_url
        logger.info("Connecting to Redis role=%s", self.role)
        try:
            self.client = redis.Redis.from_url(url, decode_responses=True)
            await self.client.ping()
            logger.info("Connected to Redis (role=%s) successfully.", self.role)
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise

    async def close(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None


# JobQueue MUST use DB 3 only (legacy queue).
redis_client_jobqueue = RedisClient(role="jobqueue")

# Fast-result cache (DB 2); API reads precomputed scalar bundles here.
redis_client_fast_cache = RedisClient(role="fast_cache")


def get_jobqueue_client() -> RedisClient:
    """Return the JobQueue Redis client (DB 3). Used by JobQueue and lifespan."""
    return redis_client_jobqueue


def get_fast_cache_client() -> RedisClient:
    """Return the fast-cache Redis client (DB 2). Used by V2 /predict and evaluate_status."""
    return redis_client_fast_cache


# Backward compatibility: alias for code that still expects "redis_client"
redis_client = redis_client_jobqueue
