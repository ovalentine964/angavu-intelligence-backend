"""
Redis caching layer for intelligence products.

Provides TTL-based caching for expensive intelligence queries.
Cache keys are deterministic based on query parameters.
"""

import hashlib
import json

import redis.asyncio as redis
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Cache TTLs per product (seconds)
CACHE_TTL = {
    "soko_pulse": 3600,         # 1 hour — demand data updates frequently
    "biashara_pulse": 7200,     # 2 hours — government indices are slower-moving
    "alama_score": 1800,        # 30 min — scores change with new transactions
    "jamii_insights": 14400,    # 4 hours — inclusion metrics are stable
    "tax_base": 7200,           # 2 hours — tax estimates are periodic
    "distribution_gap": 3600,   # 1 hour — gaps change with distribution
}


class IntelligenceCache:
    """
    Redis cache for intelligence product responses.

    Uses deterministic cache keys based on product type and query parameters.
    Supports TTL-based expiration and manual invalidation.
    """

    def __init__(self):
        self._redis: redis.Redis | None = None

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return self._redis

    @staticmethod
    def _build_key(product: str, **params) -> str:
        """
        Build deterministic cache key from product type and parameters.

        Args:
            product: Product name (e.g., 'soko_pulse')
            **params: Query parameters to include in key

        Returns:
            Cache key string like 'intel:soko_pulse:abc123def'
        """
        # Sort params for deterministic keys
        sorted_params = json.dumps(params, sort_keys=True, default=str)
        param_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:16]
        return f"intel:{product}:{param_hash}"

    async def get(self, product: str, **params) -> dict | None:
        """
        Get cached intelligence response.

        Args:
            product: Product name
            **params: Query parameters

        Returns:
            Cached dict or None if cache miss
        """
        try:
            client = await self._get_client()
            key = self._build_key(product, **params)
            cached = await client.get(key)
            if cached:
                logger.info("cache_hit", product=product, key=key)
                return json.loads(cached)
            logger.info("cache_miss", product=product, key=key)
            return None
        except Exception as e:
            logger.warning("cache_get_error", product=product, error=str(e))
            return None

    async def set(
        self,
        product: str,
        data: dict,
        ttl_override: int | None = None,
        **params,
    ) -> bool:
        """
        Cache intelligence response.

        Args:
            product: Product name
            data: Response data to cache
            ttl_override: Override default TTL
            **params: Query parameters

        Returns:
            True if cached successfully
        """
        try:
            client = await self._get_client()
            key = self._build_key(product, **params)
            ttl = ttl_override or CACHE_TTL.get(product, 3600)
            await client.setex(key, ttl, json.dumps(data, default=str))
            logger.info("cache_set", product=product, key=key, ttl=ttl)
            return True
        except Exception as e:
            logger.warning("cache_set_error", product=product, error=str(e))
            return False

    async def invalidate(self, product: str, **params) -> bool:
        """
        Invalidate a specific cached response.

        Args:
            product: Product name
            **params: Query parameters

        Returns:
            True if invalidated
        """
        try:
            client = await self._get_client()
            key = self._build_key(product, **params)
            await client.delete(key)
            logger.info("cache_invalidated", product=product, key=key)
            return True
        except Exception as e:
            logger.warning("cache_invalidate_error", product=product, error=str(e))
            return False

    async def invalidate_product(self, product: str) -> int:
        """
        Invalidate all cached responses for a product type.

        Args:
            product: Product name

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._get_client()
            pattern = f"intel:{product}:*"
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                deleted = await client.delete(*keys)
                logger.info("cache_product_invalidated", product=product, count=deleted)
                return deleted
            return 0
        except Exception as e:
            logger.warning("cache_product_invalidate_error", product=product, error=str(e))
            return 0

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


    def __call__(self, ttl: int = 3600):
        """
        Allow using the cache instance as a decorator.

        Usage:
            @intelligence_cache(ttl=300)
            async def my_function(...):
                ...
        """
        import functools

        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Try cache first
                product = func.__name__
                cached = await self.get(product, **kwargs)
                if cached is not None:
                    return cached
                # Execute and cache
                result = await func(*args, **kwargs)
                if result is not None:
                    await self.set(product, result, ttl_override=ttl, **kwargs)
                return result
            return wrapper
        return decorator


# Singleton cache instance
intelligence_cache = IntelligenceCache()
