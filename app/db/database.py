"""
Async SQLAlchemy database setup.

Provides:
    - Async engine connected to PostgreSQL or SQLite
    - Session factory for request-scoped sessions
    - Base class for all ORM models
    - get_db dependency for FastAPI endpoints
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# SQLite needs different engine args than PostgreSQL
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {
    "echo": settings.DATABASE_ECHO,
}

if _is_sqlite:
    # SQLite: no connection pooling, allow multi-threaded access
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL: connection pooling (Tier 2 — Growth)
    _engine_kwargs.update({
        "pool_size": settings.DATABASE_POOL_SIZE,        # 20 max connections in pool
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,   # 10 extra when pool full
        "pool_timeout": settings.DATABASE_POOL_TIMEOUT,   # 30s wait timeout
        "pool_recycle": settings.DATABASE_POOL_RECYCLE,   # recycle every 30 min
        "pool_pre_ping": True,                            # verify before use
    })

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    **_engine_kwargs,
)

# Session factory — each request gets its own session
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session.

    Only commits when there are pending write operations (dirty/new/deleted objects).
    Read-only endpoints will not trigger an unnecessary commit.

    Usage in endpoints:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()

    The session is automatically closed after the request completes.
    """
    async with async_session_factory() as session:
        try:
            yield session
            # Only commit if there are pending changes (write operations).
            # This avoids unnecessary commits on read-only endpoints.
            if session.dirty or session.new or session.deleted:
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.

    Called on application startup. Creates all tables defined by
    models that inherit from Base. In production, use Alembic
    migrations instead.
    """
    # Enable WAL mode for SQLite (better concurrency)
    if _is_sqlite:
        async with engine.begin() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("PRAGMA journal_mode=WAL")
            )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database engine and all connections. Called on shutdown."""
    await engine.dispose()
