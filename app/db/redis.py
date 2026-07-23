"""
Redis client — caching, rate limiting, FL round state, task queues.

Architecture: arch_backend.md §3.3
"""
import json
from typing import Any, Optional

import redis.asyncio as redis
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

_redis: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Get the shared Redis connection pool."""
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
        await _redis.ping()
        logger.info("redis_connected")
    return _redis


async def close_redis():
    """Close Redis on shutdown."""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
        logger.info("redis_closed")


class RedisCache:
    """Simple Redis cache wrapper with JSON serialization."""

    def __init__(self, r: redis.Redis, prefix: str = "cache", ttl: int = 3600):
        self.redis = r
        self.prefix = prefix
        self.default_ttl = ttl

    async def get(self, key: str) -> Optional[Any]:
        raw = await self.redis.get(f"{self.prefix}:{key}")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        data = json.dumps(value, default=str)
        await self.redis.set(
            f"{self.prefix}:{key}", data, ex=ttl or self.default_ttl
        )

    async def delete(self, key: str):
        await self.redis.delete(f"{self.prefix}:{key}")

    async def incr(self, key: str) -> int:
        return await self.redis.incr(f"{self.prefix}:{key}")

    async def exists(self, key: str) -> bool:
        return bool(await self.redis.exists(f"{self.prefix}:{key}"))
