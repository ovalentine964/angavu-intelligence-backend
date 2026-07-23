"""
Intelligence product scheduler.

Architecture: arch_backend.md §2.5, §4.1
Pre-computes intelligence products on schedule rather than on-demand.
"""
import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, distinct

logger = structlog.get_logger(__name__)


class IntelligenceScheduler:
    """Cron-like scheduler for intelligence product generation."""

    def __init__(self, db_factory, task_queue):
        self.db_factory = db_factory
        self.task_queue = task_queue
        self._running = False

    async def start(self):
        """Start the scheduler loop."""
        self._running = True
        logger.info("scheduler_started")
        while self._running:
            now = datetime.now(UTC)
            await self._check_and_run(now)
            await asyncio.sleep(60)

    async def stop(self):
        self._running = False
        logger.info("scheduler_stopped")

    async def _check_and_run(self, now: datetime):
        # Daily at 2 AM: Soko Pulse for all active regions
        if now.hour == 2 and now.minute == 0:
            await self._enqueue_soko_pulse_batch()

        # Weekly Monday 3 AM: Angavu Pulse
        if now.weekday() == 0 and now.hour == 3 and now.minute == 0:
            await self._enqueue_angavu_pulse_batch()

        # Monthly 1st at 4 AM: Jamii Insights
        if now.day == 1 and now.hour == 4 and now.minute == 0:
            await self._enqueue_monthly_reports()

    async def _enqueue_soko_pulse_batch(self):
        """Generate Soko Pulse for all active regions."""
        from app.models.user import User
        async with self.db_factory() as db:
            result = await db.execute(
                select(distinct(User.location_geohash)).where(
                    User.is_active == True,
                    User.consent_data_sharing == True,
                )
            )
            regions = [row[0] for row in result.all() if row[0]]

        for region in regions:
            await self.task_queue.enqueue(
                "generate_soko_pulse",
                {"region": region, "tier": "standard"},
                priority=2,
            )
        logger.info("soko_pulse_batch_enqueued", regions=len(regions))

    async def _enqueue_angavu_pulse_batch(self):
        from app.models.user import User
        async with self.db_factory() as db:
            result = await db.execute(
                select(distinct(User.location_geohash)).where(
                    User.is_active == True,
                )
            )
            regions = [row[0] for row in result.all() if row[0]]

        for region in regions:
            await self.task_queue.enqueue(
                "generate_angavu_pulse",
                {"region": region, "period": "weekly"},
                priority=2,
            )
        logger.info("angavu_pulse_batch_enqueued", regions=len(regions))

    async def _enqueue_monthly_reports(self):
        from app.models.user import User
        async with self.db_factory() as db:
            result = await db.execute(
                select(distinct(User.location_geohash)).where(
                    User.is_active == True,
                )
            )
            regions = [row[0] for row in result.all() if row[0]]

        for region in regions:
            await self.task_queue.enqueue(
                "generate_jamii_insights",
                {"region": region},
                priority=3,
            )
        logger.info("monthly_reports_enqueued", regions=len(regions))
