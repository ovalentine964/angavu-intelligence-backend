"""
Background worker — task queue + intelligence scheduler + FL aggregation.

Architecture: arch_backend.md §4.2
Runs as a separate process alongside the API server.
"""
import asyncio
import signal
import structlog

from app.config import settings
from app.db.database import close_db, init_db, async_session_factory
from app.services.task_queue import get_task_queue
from app.services.scheduler import IntelligenceScheduler

logger = structlog.get_logger("worker")
_shutdown = asyncio.Event()


def _handle_signal(sig, frame):
    logger.info("signal_received", signal=sig)
    _shutdown.set()


# ─── Task Handlers ────────────────────────────────────────────────────────────

async def handle_soko_pulse(payload: dict):
    """Generate Soko Pulse for a region."""
    async with async_session_factory() as db:
        try:
            from app.services.intelligence.soko_pulse import SokoPulseService
            service = SokoPulseService(db)
            result = await service.generate_demand_forecast(
                region=payload["region"],
                product_category=payload.get("category", "general"),
            )
            await db.commit()
            logger.info("soko_pulse_generated", region=payload["region"], status=result.get("status"))
        except Exception as e:
            await db.rollback()
            logger.error("soko_pulse_failed", region=payload["region"], error=str(e))


async def handle_angavu_pulse(payload: dict):
    """Generate Angavu Pulse for a region."""
    async with async_session_factory() as db:
        try:
            from app.services.intelligence.angavu_pulse import AngavuPulseService
            service = AngavuPulseService(db)
            result = await service.generate_pulse(
                region=payload["region"],
                period=payload.get("period", "weekly"),
            )
            await db.commit()
            logger.info("angavu_pulse_generated", region=payload["region"])
        except Exception as e:
            await db.rollback()
            logger.error("angavu_pulse_failed", region=payload["region"], error=str(e))


async def handle_jamii_insights(payload: dict):
    """Generate Jamii Insights for a region."""
    async with async_session_factory() as db:
        try:
            from app.services.intelligence.jamii_insights import JamiiInsightsService
            service = JamiiInsightsService(db)
            result = await service.generate_insights(region=payload["region"])
            await db.commit()
            logger.info("jamii_insights_generated", region=payload["region"])
        except Exception as e:
            await db.rollback()
            logger.error("jamii_insights_failed", region=payload["region"], error=str(e))


async def handle_fl_aggregation(payload: dict):
    """Trigger FL aggregation for a dialect."""
    async with async_session_factory() as db:
        try:
            from app.services.fl_service import FLService
            service = FLService(db)
            version = await service._aggregate(payload["dialect"])
            await db.commit()
            if version:
                logger.info("fl_aggregation_triggered", dialect=payload["dialect"], version=version)
        except Exception as e:
            await db.rollback()
            logger.error("fl_aggregation_failed", dialect=payload["dialect"], error=str(e))


# ─── Worker Main ──────────────────────────────────────────────────────────────

async def main():
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("worker_starting", env=settings.ENVIRONMENT)
    await init_db()

    queue = get_task_queue()
    await queue.connect()

    # Register task handlers
    queue.register_handler("generate_soko_pulse", handle_soko_pulse)
    queue.register_handler("generate_angavu_pulse", handle_angavu_pulse)
    queue.register_handler("generate_jamii_insights", handle_jamii_insights)
    queue.register_handler("fl_aggregation", handle_fl_aggregation)

    # Start scheduler
    scheduler = IntelligenceScheduler(
        db_factory=async_session_factory,
        task_queue=queue,
    )

    # Run worker, scheduler, and shutdown listener concurrently
    await asyncio.gather(
        queue.start_worker(),
        scheduler.start(),
        _shutdown.wait(),
        return_exceptions=True,
    )

    logger.info("worker_shutting_down")
    await scheduler.stop()
    await queue.close()
    await close_db()
    logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
