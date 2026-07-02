"""
Background task worker for Biashara Intelligence.

Run as: python -m app.worker

This module starts the TaskQueue worker loop, which processes
background jobs from the Redis queue (report generation, model
training, data aggregation, etc.).
"""

import asyncio
import logging
import signal
import sys

import structlog

from app.config import get_settings
from app.db.database import close_db, init_db
from app.services.task_queue import get_task_queue

settings = get_settings()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("worker")

# Graceful shutdown flag
_shutdown = asyncio.Event()


def _handle_signal(sig: int, frame) -> None:
    logger.info("signal_received", signal=sig)
    _shutdown.set()


async def main() -> None:
    """Main worker entry point."""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("worker_starting", env=settings.APP_ENV)

    # Initialize database (needed for task handlers that write results)
    await init_db()

    # Connect task queue
    queue = get_task_queue()
    await queue.connect()

    # Import task handlers so they register via @register_handler
    import app.services.task_handlers  # noqa: F401

    # Start processing
    await queue.start_worker()
    logger.info("worker_ready")

    # Wait for shutdown signal
    await _shutdown.wait()

    # Cleanup
    logger.info("worker_shutting_down")
    await queue.close()
    await close_db()
    logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
