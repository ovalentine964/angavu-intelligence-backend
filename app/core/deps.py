"""Dependency injection for FastAPI."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.redis import get_redis


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_cache() -> redis.Redis:
    """Yield a Redis client."""
    return get_redis()
