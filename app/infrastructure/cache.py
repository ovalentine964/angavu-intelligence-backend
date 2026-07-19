"""
Advanced Caching Layer — Redis-based cache-aside pattern with metrics.

Extends the existing cache.py with:
- Cache-aside pattern for database queries
- Cache invalidation strategies (TTL, event-driven, versioned)
- Cache hit/miss metrics for observability
- Warm-up support for critical data
- Stampede prevention (single-flight)

Caching Strategy (Optimization — Applied Math):
    Cache hit ratio target: > 80%
    Memory efficiency: LRU eviction with per-category TTLs

    TTL tiers based on data volatility:
    - Market prices:     15 min  (high volatility)
    - Intelligence:       1 hour (medium volatility)
    - Worker profiles:   24 hours (low volatility)
    - Static config:     7 days  (very low volatility)

    Cache-aside pattern:
    1. Check cache → hit? return cached
    2. Cache miss → query database
    3. Store result in cache with TTL
    4. Return result

References:
- Optimization (Applied Math): Optimal TTL = f(write_frequency, read_frequency)
- Statistical Quality Control: Cache hit ratio as a quality metric
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

T = TypeVar("T")

# ── TTL Constants ──────────────────────────────────────────────────

TTL_MARKET_PRICES = 900       # 15 minutes
TTL_INTELLIGENCE = 3600       # 1 hour
TTL_PROFILES = 86400          # 24 hours
TTL_REPORTS = 3600            # 1 hour
TTL_STATIC_CONFIG = 604800    # 7 days
TTL_DEFAULT = 3600            # 1 hour

KEY_PREFIX = "biashara:cache:"
METRICS_KEY = "biashara:cache:metrics"


@dataclass
class CacheMetrics:
    """Cache performance metrics."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    invalidations: int = 0
    errors: int = 0
    total_get_time_ms: float = 0.0
    total_set_time_ms: float = 0.0
    get_count: int = 0
    set_count: int = 0

    @property
    def hit_ratio(self) -> float:
        """Cache hit ratio (0.0 - 1.0)."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    @property
    def avg_get_time_ms(self) -> float:
        """Average GET latency in milliseconds."""
        if self.get_count == 0:
            return 0.0
        return self.total_get_time_ms / self.get_count

    @property
    def avg_set_time_ms(self) -> float:
        """Average SET latency in milliseconds."""
        if self.set_count == 0:
            return 0.0
        return self.total_set_time_ms / self.set_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": round(self.hit_ratio, 4),
            "sets": self.sets,
            "deletes": self.deletes,
            "invalidations": self.invalidations,
            "errors": self.errors,
            "avg_get_time_ms": round(self.avg_get_time_ms, 3),
            "avg_set_time_ms": round(self.avg_set_time_ms, 3),
            "total_operations": self.hits + self.misses + self.sets + self.deletes,
        }


class CacheAside:
    """
    Cache-aside pattern implementation with metrics and stampede prevention.

    Usage:
        cache = CacheAside()
        await cache.connect()

        # Simple get/set
        data = await cache.get("user:123")
        if data is None:
            data = await db.fetch_user(123)
            await cache.set("user:123", data, ttl=TTL_PROFILES)

        # Cache-aside helper (auto-fetches on miss)
        user = await cache.get_or_set(
            "user:123",
            fetcher=lambda: db.fetch_user(123),
            ttl=TTL_PROFILES,
        )

        # Pattern-based invalidation
        await cache.invalidate_pattern("user:*")

        # Versioned cache (for write-heavy patterns)
        await cache.set_versioned("config:app", config_data, version=3)
    """

    def __init__(self):
        self._redis = None
        self._fallback = None
        self._connected = False
        self._metrics = CacheMetrics()

        # Stampede prevention: single-flight per key
        self._inflight: dict[str, asyncio.Future] = {}

        self._logger = logger.bind(component="cache_aside")

    async def connect(self) -> None:
        """Connect to Redis or fall back to in-memory."""
        if not settings.REDIS_URL:
            self._logger.warning("no_redis_url_cache_fallback_in_memory")
            from app.services.cache import InMemoryFallback
            self._fallback = InMemoryFallback()
            self._connected = True
            return

        try:
            import redis.asyncio as aioredis
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
            self._logger.info("cache_aside_connected")
        except (ImportError, ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("cache_aside_connect_failed", error=str(exc))
            from app.services.cache import InMemoryFallback
            self._fallback = InMemoryFallback()
            self._connected = True

    async def disconnect(self) -> None:
        """Close connections."""
        if self._redis:
            await self._redis.close()
            self._redis = None
        if self._fallback:
            await self._fallback.close()
            self._fallback = None
        self._connected = False

    @property
    def is_available(self) -> bool:
        return self._connected

    # ── Core Operations ─────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """Get a value from cache. Returns None on miss."""
        full_key = f"{KEY_PREFIX}{key}"
        start = time.monotonic()

        try:
            if self._fallback:
                raw = await self._fallback.get(full_key)
            else:
                raw = await self._redis.get(full_key)

            elapsed = (time.monotonic() - start) * 1000
            self._metrics.total_get_time_ms += elapsed
            self._metrics.get_count += 1

            if raw is None:
                self._metrics.misses += 1
                return None

            self._metrics.hits += 1
            return json.loads(raw)

        except Exception as exc:
            self._metrics.errors += 1
            self._logger.warning("cache_get_error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: Any, ttl: int = TTL_DEFAULT) -> bool:
        """Set a value in cache with TTL."""
        full_key = f"{KEY_PREFIX}{key}"
        start = time.monotonic()

        try:
            serialized = json.dumps(value, default=str)
            if self._fallback:
                await self._fallback.set(full_key, serialized, ex=ttl)
            else:
                await self._redis.set(full_key, serialized, ex=ttl)

            elapsed = (time.monotonic() - start) * 1000
            self._metrics.total_set_time_ms += elapsed
            self._metrics.set_count += 1
            self._metrics.sets += 1
            return True

        except Exception as exc:
            self._metrics.errors += 1
            self._logger.warning("cache_set_error", key=key, error=str(exc))
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        full_key = f"{KEY_PREFIX}{key}"
        try:
            if self._fallback:
                await self._fallback.delete(full_key)
            else:
                await self._redis.delete(full_key)
            self._metrics.deletes += 1
            return True
        except Exception:
            self._metrics.errors += 1
            return False

    # ── Cache-Aside Pattern ─────────────────────────────────────────

    async def get_or_set(
        self,
        key: str,
        fetcher: Callable[[], Coroutine[Any, Any, Any]],
        ttl: int = TTL_DEFAULT,
    ) -> Any:
        """
        Cache-aside pattern: get from cache, or fetch and store.

        Includes stampede prevention: if multiple coroutines request the
        same key simultaneously, only one fetches from the database.

        Args:
            key: Cache key
            fetcher: Async function that fetches the data on cache miss
            ttl: Cache TTL in seconds

        Returns:
            Cached or freshly fetched data
        """
        # Try cache first
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Stampede prevention: check if another coroutine is already fetching
        inflight_key = f"__inflight__:{key}"
        if inflight_key in self._inflight:
            try:
                return await self._inflight[inflight_key]
            except Exception:
                pass  # Fall through to fetch ourselves

        # Create a future for this fetch
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._inflight[inflight_key] = future

        try:
            data = await fetcher()
            if data is not None:
                await self.set(key, data, ttl=ttl)
            future.set_result(data)
            return data
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            self._inflight.pop(inflight_key, None)

    # ── Pattern Invalidation ────────────────────────────────────────

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Uses SCAN to avoid blocking Redis on large key sets.
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
                async for key in self._redis.scan_iter(match=full_pattern, count=100):
                    await self._redis.delete(key)
                    count += 1

            self._metrics.invalidations += count
            if count:
                self._logger.info("pattern_invalidated", pattern=pattern, count=count)
            return count

        except Exception as exc:
            self._metrics.errors += 1
            self._logger.warning("invalidate_pattern_error", pattern=pattern, error=str(exc))
            return count

    # ── Versioned Cache ─────────────────────────────────────────────

    async def set_versioned(
        self,
        key: str,
        value: Any,
        version: int,
        ttl: int = TTL_DEFAULT,
    ) -> bool:
        """
        Set a versioned cache entry.

        Useful for configuration data that changes infrequently.
        Readers can check the version to avoid stale data.
        """
        versioned_key = f"{key}:v{version}"
        return await self.set(versioned_key, value, ttl=ttl)

    async def get_versioned(
        self,
        key: str,
        version: int,
    ) -> Any | None:
        """Get a versioned cache entry."""
        versioned_key = f"{key}:v{version}"
        return await self.get(versioned_key)

    # ── Namespace Support ────────────────────────────────────────────

    async def get_namespaced(
        self,
        namespace: str,
        key: str,
    ) -> Any | None:
        """Get a value from a specific namespace (prices, users, reports, etc.)."""
        return await self.get(f"{namespace}:{key}")

    async def set_namespaced(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: int = TTL_DEFAULT,
    ) -> bool:
        """Set a value in a specific namespace."""
        return await self.set(f"{namespace}:{key}", value, ttl=ttl)

    async def invalidate_namespace(self, namespace: str) -> int:
        """Invalidate all keys in a namespace."""
        return await self.invalidate_pattern(f"{namespace}:*")

    async def get_namespaced_or_set(
        self,
        namespace: str,
        key: str,
        fetcher: Callable[[], Coroutine[Any, Any, Any]],
        ttl: int = TTL_DEFAULT,
    ) -> Any:
        """Cache-aside pattern with namespace support."""
        return await self.get_or_set(
            f"{namespace}:{key}",
            fetcher=fetcher,
            ttl=ttl,
        )

    # ── Domain-Specific Helpers ─────────────────────────────────────

    async def cache_worker_profile(self, worker_id: str, data: dict) -> bool:
        return await self.set_namespaced("users", worker_id, data, ttl=TTL_PROFILES)

    async def get_worker_profile(self, worker_id: str) -> dict | None:
        return await self.get_namespaced("users", worker_id)

    async def cache_intelligence(self, product_id: str, data: dict) -> bool:
        return await self.set_namespaced("intelligence", product_id, data, ttl=TTL_INTELLIGENCE)

    async def get_intelligence(self, product_id: str) -> dict | None:
        return await self.get_namespaced("intelligence", product_id)

    async def cache_market_prices(self, market_id: str, data: dict) -> bool:
        return await self.set_namespaced("prices", market_id, data, ttl=TTL_MARKET_PRICES)

    async def get_market_prices(self, market_id: str) -> dict | None:
        return await self.get_namespaced("prices", market_id)

    async def cache_report(self, report_id: str, data: dict) -> bool:
        return await self.set_namespaced("reports", report_id, data, ttl=TTL_REPORTS)

    async def get_report(self, report_id: str) -> dict | None:
        return await self.get_namespaced("reports", report_id)

    # ── Metrics ─────────────────────────────────────────────────────

    def get_metrics(self) -> CacheMetrics:
        """Get current cache metrics."""
        return self._metrics

    def get_metrics_dict(self) -> dict[str, Any]:
        """Get metrics as a dictionary."""
        return self._metrics.to_dict()

    # ── Warm-up ─────────────────────────────────────────────────────

    async def warmup(self, items: list[tuple[str, Any, int]]) -> int:
        """
        Pre-populate the cache with critical data.

        Args:
            items: List of (key, value, ttl) tuples

        Returns:
            Number of items cached
        """
        count = 0
        for key, value, ttl in items:
            if await self.set(key, value, ttl=ttl):
                count += 1
        self._logger.info("cache_warmup_complete", items=count)
        return count


# ── Singleton ──────────────────────────────────────────────────────

_cache_aside: CacheAside | None = None


def get_cache_aside() -> CacheAside:
    """Get the singleton CacheAside instance."""
    global _cache_aside
    if _cache_aside is None:
        _cache_aside = CacheAside()
    return _cache_aside
