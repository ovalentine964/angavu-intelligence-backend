"""
Per-endpoint rate limiting using Redis.

Architecture: arch_backend.md §7
"""
from typing import Optional
from fastapi import Request, HTTPException
import structlog

logger = structlog.get_logger(__name__)


class RateLimiter:
    """Redis-backed rate limiter with sliding window."""

    def __init__(self, redis_client, requests: int = 100, window: int = 3600):
        self.redis = redis_client
        self.requests = requests
        self.window = window

    async def __call__(self, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate:{request.url.path}:{client_ip}"
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, self.window)
        if current > self.requests:
            raise HTTPException(
                429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(self.window)},
            )


def create_rate_limiter(requests: int = 100, window: int = 3600):
    """Factory for rate limiter dependencies."""
    from app.db.redis import get_redis
    import asyncio

    _limiter = None

    async def _get_limiter():
        nonlocal _limiter
        if _limiter is None:
            r = await get_redis()
            _limiter = RateLimiter(r, requests, window)
        return _limiter

    async def rate_limit(request: Request):
        limiter = await _get_limiter()
        await limiter(request)

    return rate_limit
