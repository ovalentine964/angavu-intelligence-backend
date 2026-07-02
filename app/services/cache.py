"""
Redis caching layer for Biashara Intelligence.

Provides a unified CacheService that wraps Redis with JSON serialization,
key prefixing, TTL management, and pattern-based invalidation.

Caching Strategy (Tier 2 — Growth):
    - Intelligence products  → TTL: 1 hour
    - Worker profiles        → TTL: 24 hours
    - Market prices          → TTL: 15 minutes
    - Report data            → TTL: 1 hour

Falls back to an in-memory dict when Redis is unavailable (dev mode).
"""

import asyncio
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Default TTLs per data category (seconds)
DEFAULT_TTL = 3600          # 1 hour
TTL_INTELLIGENCE = 3600     # 1 hour
TTL_PROFILES = 86400        # 24 hours
TTL_MARKET_PRICES = 900     # 15 minutes
TTL_REPORTS = 3600          # 1 hour

KEY_PREFIX = "biashara:"


class InMemoryFallback:
    """Simple in-memory cache used when Redis is unavailable."""

    def __init__(self):
        self._store: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and asyncio.get_event_loop().time() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        async with self._lock:
            expires_at = asyncio.get_event_loop().time() + ex if ex else None
            self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def keys(self, pattern: str) -> list[str]:
        import fnmatch
        async with self._lock:
            return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._store.clear()


class CacheService:
    """
    Redis-backed caching service for Biashara Intelligence.

    Usage:
        cache = CacheService()
        await cache.connect()

        # Store with default TTL (1 hour)
        await cache.set("user:123", {"name": "Wanjiku"})

        # Store with custom TTL
        await cache.set("prices:nairobi", prices, ttl=900)

        # Retrieve
        user = await cache.get("user:123")

        # Invalidate all keys matching a pattern
        await cache.invalidate_pattern("prices:*")
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._fallback: Optional[InMemoryFallback] = None
        self._connected = False

    async def connect(self) -> None:
        """Initialize the Redis connection (or in-memory fallback)."""
        if not settings.REDIS_URL:
            logger.warning("REDIS_URL not set — using in-memory cache fallback")
            self._fallback = InMemoryFallback()
            self._connected = True
            return

        try:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True,
            )
            await self._redis.ping()
            self._connected = True
            logger.info("redis_connected", url=settings.REDIS_URL.split("@")[-1])
        except Exception as exc:
            logger.warning("redis_connection_failed", error=str(exc))
            logger.warning("falling_back_to_in_memory_cache")
            self._fallback = InMemoryFallback()
            self._connected = True

    async def close(self) -> None:
        """Shut down the cache connection."""
        if self._redis:
            await self._redis.close()
        if self._fallback:
            await self._fallback.close()
        self._connected = False

    @property
    def is_available(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Core Operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value by key.

        Returns deserialized JSON object, or None on cache miss.
        """
        full_key = f"{KEY_PREFIX}{key}"
        try:
            if self._fallback:
                raw = await self._fallback.get(full_key)
            else:
                raw = await self._redis.get(full_key)

            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("cache_get_error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
        """
        Store a value in the cache with a TTL.

        Args:
            key: Cache key (prefix is added automatically)
            value: JSON-serializable object
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            True if stored successfully, False otherwise.
        """
        full_key = f"{KEY_PREFIX}{key}"
        try:
            serialized = json.dumps(value, default=str)
            if self._fallback:
                await self._fallback.set(full_key, serialized, ex=ttl)
            else:
                await self._redis.set(full_key, serialized, ex=ttl)
            return True
        except Exception as exc:
            logger.warning("cache_set_error", key=key, error=str(exc))
            return False

    async def delete(self, key: str) -> bool:
        """Remove a specific key from the cache."""
        full_key = f"{KEY_PREFIX}{key}"
        try:
            if self._fallback:
                await self._fallback.delete(full_key)
            else:
                await self._redis.delete(full_key)
            return True
        except Exception as exc:
            logger.warning("cache_delete_error", key=key, error=str(exc))
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "prices:*", "user:123:*")

        Returns:
            Number of keys deleted.
        """
        full_pattern = f"{KEY_PREFIX}{pattern}"
        count = 0
        try:
            if self._fallback:
                keys = await self._fallback.keys(full_pattern)
                for k in keys:
                    await self._fallback.delete(k)
                    count += 1
            else:
                # Use SCAN to avoid blocking Redis on large key sets
                async for key in self._redis.scan_iter(match=full_pattern, count=100):
                    await self._redis.delete(key)
                    count += 1
            if count:
                logger.info("cache_invalidate_pattern", pattern=pattern, keys_deleted=count)
            return count
        except Exception as exc:
            logger.warning("cache_invalidate_pattern_error", pattern=pattern, error=str(exc))
            return count

    # ------------------------------------------------------------------
    # Convenience Methods (domain-specific helpers)
    # ------------------------------------------------------------------

    async def cache_intelligence_product(self, product_id: str, data: dict) -> bool:
        """Cache an intelligence product (TTL: 1 hour)."""
        return await self.set(f"intelligence:{product_id}", data, ttl=TTL_INTELLIGENCE)

    async def get_intelligence_product(self, product_id: str) -> Optional[dict]:
        """Retrieve a cached intelligence product."""
        return await self.get(f"intelligence:{product_id}")

    async def cache_worker_profile(self, worker_id: str, data: dict) -> bool:
        """Cache a worker profile (TTL: 24 hours)."""
        return await self.set(f"profile:{worker_id}", data, ttl=TTL_PROFILES)

    async def get_worker_profile(self, worker_id: str) -> Optional[dict]:
        """Retrieve a cached worker profile."""
        return await self.get(f"profile:{worker_id}")

    async def cache_market_prices(self, market_id: str, data: dict) -> bool:
        """Cache market prices (TTL: 15 minutes — prices change frequently)."""
        return await self.set(f"prices:{market_id}", data, ttl=TTL_MARKET_PRICES)

    async def get_market_prices(self, market_id: str) -> Optional[dict]:
        """Retrieve cached market prices."""
        return await self.get(f"prices:{market_id}")

    async def cache_report(self, report_id: str, data: dict) -> bool:
        """Cache a generated report (TTL: 1 hour)."""
        return await self.set(f"report:{report_id}", data, ttl=TTL_REPORTS)

    async def get_report(self, report_id: str) -> Optional[dict]:
        """Retrieve a cached report."""
        return await self.get(f"report:{report_id}")

    async def invalidate_user_cache(self, user_id: str) -> int:
        """Invalidate all cached data for a specific user."""
        return await self.invalidate_pattern(f"*:{user_id}:*")

    async def invalidate_market_cache(self, market_id: str | None = None) -> int:
        """Invalidate market price caches. If market_id is None, invalidate all."""
        pattern = f"prices:{market_id}" if market_id else "prices:*"
        return await self.invalidate_pattern(pattern)


# Singleton instance
_cache_service: Optional[CacheService] = None


def get_cache() -> CacheService:
    """Get the singleton CacheService instance."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
