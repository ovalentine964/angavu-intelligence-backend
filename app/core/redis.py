"""Redis connection management."""
from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis

from app.core import settings


@lru_cache
def get_redis() -> redis.Redis:
    """Cached Redis client."""
    return redis.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )


async def get_redis_dependency() -> redis.Redis:
    """FastAPI dependency for Redis."""
    return get_redis()
