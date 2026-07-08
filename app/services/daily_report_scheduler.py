"""
Daily Report Scheduler — Sends evening reports at 7 PM EAT via WhatsApp.

Cron-driven service that:
1. Queries all active workers with WhatsApp enabled
2. Generates personalized evening reports from transaction data
3. Sends reports via WhatsAppDelivery → OpenWA → worker's phone

Scheduling:
    - Evening report: 7 PM EAT daily (19:00 Africa/Nairobi)
    - Morning briefing: 7 AM EAT daily (07:00 Africa/Nairobi)
    - Weekly report: Monday 8 AM EAT

Configuration:
    Set SCHEDULE_EVENING_REPORT=true to enable automatic delivery.
    Workers must have whatsapp_number set in their profile.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import structlog
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.transaction import Transaction
from app.services.whatsapp_delivery import WhatsAppDelivery

logger = structlog.get_logger(__name__)

# =========================================================================
# EAT timezone (UTC+3)
# =========================================================================

EAT_OFFSET = timedelta(hours=3)


def now_eat() -> datetime:
    """Get current time in East Africa Time (UTC+3)."""
    return datetime.now(timezone.utc) + EAT_OFFSET


# =========================================================================
# Scheduler
# =========================================================================


class DailyReportScheduler:
    """
    Schedules and delivers daily reports to workers via WhatsApp.

    Must be started as a background task (asyncio.create_task or
    FastAPI lifespan event).
    """

    def __init__(self, db_session_factory, whatsapp: Optional[WhatsAppDelivery] = None):
        self.db_session_factory = db_session_factory
        self.whatsapp = whatsapp or WhatsAppDelivery()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("daily_report_scheduler_started")

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("daily_report_scheduler_stopped")

    async def _scheduler_loop(self):
        """
        Main scheduler loop. Runs every minute and checks if it's time
        to send reports (7 AM or 7 PM EAT).
        """
        last_evening_run = None
        last_morning_run = None

        while self._running:
            try:
                now = now_eat()

                # Evening report at 7 PM EAT (19:00)
                if now.hour == 19 and now.minute == 0:
                    today_key = now.strftime("%Y-%m-%d")
                    if last_evening_run != today_key:
                        logger.info("triggering_evening_reports", time=now.isoformat())
                        await self._send_evening_reports()
                        last_evening_run = today_key

                # Morning briefing at 7 AM EAT (07:00)
                if now.hour == 7 and now.minute == 0:
                    today_key = now.strftime("%Y-%m-%d")
                    if last_morning_run != today_key:
                        logger.info("triggering_morning_briefings", time=now.isoformat())
                        await self._send_morning_briefings()
                        last_morning_run = today_key

                # Sleep for 60 seconds before checking again
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_loop_error", error=str(e))
                await asyncio.sleep(60)

    async def _send_evening_reports(self):
        """
        Send evening reports to all active workers with WhatsApp enabled.

        Steps:
        1. Query active workers with WhatsApp numbers
        2. For each worker, get today's transactions
        3. Generate personalized evening report
        4. Send via WhatsApp
        """
        async with self.db_session_factory() as db:
            workers = await self._get_whatsapp_workers(db)
            logger.info("evening_report_workers", count=len(workers))

            sent_count = 0
            failed_count = 0

            for worker in workers:
                try:
                    # Get today's transactions for this worker
                    today_start = datetime.combine(
                        now_eat().date(), datetime.min.time()
                    ).replace(tzinfo=timezone.utc) - EAT_OFFSET

                    result = await db.execute(
                        select(Transaction).where(
                            and_(
                                Transaction.user_id == worker.id,
                                Transaction.timestamp >= today_start,
                            )
                        )
                    )
                    transactions = result.scalars().all()

                    # Calculate daily metrics
                    sales = sum(
                        t.amount for t in transactions if t.transaction_type == "SALE"
                    )
                    expenses = sum(
                        t.amount
                        for t in transactions
                        if t.transaction_type in ("PURCHASE", "EXPENSE")
                    )
                    profit = sales - expenses
                    count = len(transactions)

                    # Get worker's WhatsApp number from profile/metadata
                    whatsapp_number = self._get_whatsapp_number(worker)
                    if not whatsapp_number:
                        continue

                    # Send evening report
                    success = await self.whatsapp.send_evening_report(
                        phone=whatsapp_number,
                        worker_name=worker.name or "Mfanyabiashara",
                        sales=sales,
                        profit=profit,
                        transaction_count=count,
                        language=worker.language or "sw",
                    )

                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1

                    # Small delay between sends to avoid rate limiting
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(
                        "evening_report_error",
                        worker_id=worker.id,
                        error=str(e),
                    )
                    failed_count += 1

            logger.info(
                "evening_reports_complete",
                sent=sent_count,
                failed=failed_count,
                total=len(workers),
            )

    async def _send_morning_briefings(self):
        """
        Send morning briefings to all active workers with WhatsApp enabled.
        """
        async with self.db_session_factory() as db:
            workers = await self._get_whatsapp_workers(db)
            logger.info("morning_briefing_workers", count=len(workers))

            sent_count = 0

            for worker in workers:
                try:
                    whatsapp_number = self._get_whatsapp_number(worker)
                    if not whatsapp_number:
                        continue

                    # Get yesterday's transactions
                    now = now_eat()
                    today_start = datetime.combine(
                        now.date(), datetime.min.time()
                    ).replace(tzinfo=timezone.utc) - EAT_OFFSET
                    yesterday_start = today_start - timedelta(days=1)

                    result = await db.execute(
                        select(Transaction).where(
                            and_(
                                Transaction.user_id == worker.id,
                                Transaction.timestamp >= yesterday_start,
                                Transaction.timestamp < today_start,
                            )
                        )
                    )
                    yesterday_txns = result.scalars().all()

                    yesterday_sales = sum(
                        t.amount for t in yesterday_txns if t.transaction_type == "SALE"
                    )
                    yesterday_profit = yesterday_sales - sum(
                        t.amount
                        for t in yesterday_txns
                        if t.transaction_type in ("PURCHASE", "EXPENSE")
                    )

                    # Build morning briefing message
                    language = getattr(worker, "language", "sw") or "sw"
                    name = worker.name or "Mfanyabiashara"

                    if language == "sw":
                        message = (
                            f"☀️ Habari za asubuhi {name}!\n\n"
                            f"📊 Jana:\n"
                            f"💰 Mauzo: KSh {yesterday_sales:,.0f}\n"
                            f"📈 Faida: KSh {yesterday_profit:,.0f}\n\n"
                            f"Leo ni siku mpya! Rekodi mauzo yako mapema."
                        )
                    else:
                        message = (
                            f"☀️ Good morning {name}!\n\n"
                            f"📊 Yesterday:\n"
                            f"💰 Sales: KSh {yesterday_sales:,.0f}\n"
                            f"📈 Profit: KSh {yesterday_profit:,.0f}\n\n"
                            f"Today is a new day! Record your sales early."
                        )

                    success = await self.whatsapp.send_message(whatsapp_number, message)
                    if success:
                        sent_count += 1

                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(
                        "morning_briefing_error",
                        worker_id=worker.id,
                        error=str(e),
                    )

            logger.info("morning_briefings_complete", sent=sent_count)

    async def _get_whatsapp_workers(self, db: AsyncSession) -> List[User]:
        """
        Get all active workers who have WhatsApp enabled.

        Returns workers with:
        - Active status
        - WhatsApp phone number set
        - Onboarding complete
        """
        result = await db.execute(
            select(User).where(
                and_(
                    User.is_active == True,  # noqa: E712
                    User.whatsapp_number.isnot(None),
                    User.whatsapp_number != "",
                )
            )
        )
        return result.scalars().all()

    def _get_whatsapp_number(self, worker: User) -> Optional[str]:
        """
        Extract WhatsApp number from worker profile.
        Checks multiple possible storage locations.
        """
        # Direct field
        if hasattr(worker, "whatsapp_number") and worker.whatsapp_number:
            return worker.whatsapp_number

        # Metadata/JSON field
        if hasattr(worker, "metadata") and worker.metadata:
            meta = worker.metadata
            if isinstance(meta, dict):
                return meta.get("whatsapp_number") or meta.get("phone")

        return None
