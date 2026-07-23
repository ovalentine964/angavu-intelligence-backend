"""
Buyer rate limiting — Redis sliding window per buyer per day.

Architecture: arch_backend.md §7.2
"""
from datetime import UTC, datetime

import redis.asyncio as redis
import structlog

from app.models.buyer import BUYER_TIERS

logger = structlog.get_logger(__name__)


class BuyerRateLimiter:
    """Per-buyer rate limiting using Redis counter."""

    def __init__(self, r: redis.Redis):
        self.redis = r

    async def check_and_consume(self, buyer_id: str, tier: str, count: int = 1) -> bool:
        """Check rate limit and consume tokens. Returns True if allowed."""
        limits = BUYER_TIERS.get(tier, BUYER_TIERS["starter"])
        window_key = f"buyer_rate:{buyer_id}:{datetime.now(UTC).strftime('%Y%m%d')}"

        current = await self.redis.incrby(window_key, count)
        if current == count:  # First request in window
            await self.redis.expire(window_key, 86400)

        return current <= limits["daily_limit"]

    async def get_remaining(self, buyer_id: str, tier: str) -> int:
        """Get remaining queries for today."""
        limits = BUYER_TIERS.get(tier, BUYER_TIERS["starter"])
        window_key = f"buyer_rate:{buyer_id}:{datetime.now(UTC).strftime('%Y%m%d')}"
        current = await self.redis.get(window_key)
        used = int(current) if current else 0
        return max(0, limits["daily_limit"] - used)
