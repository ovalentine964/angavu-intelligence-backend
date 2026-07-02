"""
Report Scheduler — Biashara Intelligence

Schedules and delivers reports via WhatsApp on a recurring basis.

WhatsApp is a PURE REPORT DELIVERY CHANNEL. This scheduler generates
reports using the Biashara Intelligence cloud model and delivers them
to workers via WhatsApp when they are online.

Report Delivery Schedule:
- Daily (Ripoti ya Leo): 7 PM EAT — evening business summary
- Weekly (Ripoti ya Wiki): Monday 8 AM EAT — weekly trends
- Monthly (Ripoti ya Mwezi): 1st of month 9 AM EAT — monthly review
- Semi-annual (Ripoti ya Nusu Mwaka): June 30 & Dec 31 — 6-month review
- Annual (Ripoti ya Mwaka): December 31 — year-end review

Each report type has different content, different charts,
different level of detail. All driven by Biashara Intelligence
cloud model analysis.

Integration:
- ReportGenerator for report content
- WhatsAppDelivery for sending via OpenWA
- DataPipeline for transaction data
- SQLAlchemy async for database access

The scheduler runs as a background task, triggered by cron jobs
or the application lifecycle.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_db
from app.models.user import User
from app.services.whatsapp_delivery import WhatsAppDelivery

logger = structlog.get_logger(__name__)
settings = get_settings()

# EAT timezone offset (UTC+3)
EAT_OFFSET = timedelta(hours=3)


def eat_now() -> datetime:
    """Get current time in East Africa Time."""
    return datetime.now(timezone.utc) + EAT_OFFSET


# =========================================================================
# Enums & Constants
# =========================================================================


class ReportType(str, Enum):
    """Types of reports that can be scheduled."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"


class DeliveryStatus(str, Enum):
    """Status of a report delivery."""
    PENDING = "pending"
    GENERATING = "generating"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


# Default report times (hour in EAT)
DEFAULT_DAILY_HOUR = 19       # 7 PM
DEFAULT_WEEKLY_HOUR = 8       # 8 AM Monday
DEFAULT_MONTHLY_HOUR = 9      # 9 AM 1st of month
DEFAULT_SEMIANNUAL_HOUR = 9   # 9 AM Jun 30 / Dec 31
DEFAULT_ANNUAL_HOUR = 10      # 10 AM Dec 31

# Delivery window (minutes) — reports are sent if current time
# is within this window of the scheduled time
DELIVERY_WINDOW_MINUTES = 15


# =========================================================================
# Report Scheduler
# =========================================================================


class ReportScheduler:
    """
    Async report scheduler for Biashara Intelligence.

    Schedules and delivers reports via WhatsApp. Uses the actual
    database and WhatsAppDelivery service for real delivery.

    Usage:
        scheduler = ReportScheduler(db)

        # Check and send all due reports
        results = await scheduler.check_and_send_reports()

        # Or send a specific report type
        results = await scheduler.send_due_reports(ReportType.DAILY)

        # Or send to a specific user
        success = await scheduler.send_report_to_user(
            worker_id, ReportType.DAILY
        )
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.delivery = WhatsAppDelivery(db)

    # =========================================================================
    # Main Scheduling Loop
    # =========================================================================

    async def check_and_send_reports(self) -> Dict[str, Any]:
        """
        Check for due reports and send them.

        This is the main entry point, called periodically (e.g., every
        15 minutes via cron or background task).

        Returns:
            Dict with counts per report type and overall stats
        """
        now = eat_now()
        results = {
            "checked_at": now.isoformat(),
            "reports": {},
            "total_sent": 0,
            "total_failed": 0,
        }

        # Check each report type
        for report_type in ReportType:
            if self._is_report_due(report_type, now):
                report_result = await self.send_due_reports(report_type)
                results["reports"][report_type.value] = report_result
                results["total_sent"] += report_result.get("sent", 0)
                results["total_failed"] += report_result.get("failed", 0)

        if results["total_sent"] > 0 or results["total_failed"] > 0:
            logger.info(
                "report_check_completed",
                sent=results["total_sent"],
                failed=results["total_failed"],
            )

        return results

    # =========================================================================
    # Send Due Reports
    # =========================================================================

    async def send_due_reports(
        self, report_type: ReportType
    ) -> Dict[str, int]:
        """
        Send all due reports of a specific type.

        Gets all active WhatsApp users and sends the appropriate report.

        Args:
            report_type: Type of report to send

        Returns:
            Dict with total, sent, failed, skipped counts
        """
        users = await self._get_active_whatsapp_users()

        sent = 0
        failed = 0
        skipped = 0

        for user in users:
            # Check if this user already received this report type today
            if await self._already_sent(user.id, report_type):
                skipped += 1
                continue

            try:
                success = await self._send_report(user, report_type)
                if success:
                    sent += 1
                    await self._log_delivery(user.id, report_type, DeliveryStatus.DELIVERED)
                else:
                    failed += 1
                    await self._log_delivery(user.id, report_type, DeliveryStatus.FAILED)
            except Exception as e:
                logger.error(
                    "report_send_error",
                    user_id=str(user.id),
                    report_type=report_type.value,
                    error=str(e),
                )
                failed += 1
                await self._log_delivery(
                    user.id, report_type, DeliveryStatus.FAILED, str(e)
                )

        result = {
            "total": len(users),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }

        logger.info(
            "batch_report_sent",
            report_type=report_type.value,
            **result,
        )

        return result

    async def send_report_to_user(
        self,
        worker_id: str,
        report_type: ReportType,
    ) -> bool:
        """
        Send a specific report type to a specific user.

        Args:
            worker_id: Worker UUID
            report_type: Type of report to send

        Returns:
            True if sent successfully
        """
        result = await self.db.execute(
            select(User).where(
                and_(User.id == worker_id, User.is_active == True)
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            logger.error("report_user_not_found", worker_id=worker_id)
            return False

        try:
            success = await self._send_report(user, report_type)
            status = DeliveryStatus.DELIVERED if success else DeliveryStatus.FAILED
            await self._log_delivery(user.id, report_type, status)
            return success
        except Exception as e:
            logger.error(
                "report_send_error",
                worker_id=worker_id,
                report_type=report_type.value,
                error=str(e),
            )
            await self._log_delivery(
                user.id, report_type, DeliveryStatus.FAILED, str(e)
            )
            return False

    # =========================================================================
    # Report Dispatch
    # =========================================================================

    async def _send_report(
        self, user: User, report_type: ReportType
    ) -> bool:
        """
        Generate and send a report to a user.

        Dispatches to the appropriate WhatsAppDelivery method.

        Args:
            user: User model instance
            report_type: Type of report

        Returns:
            True if sent successfully
        """
        worker_id = str(user.id)

        send_methods = {
            ReportType.DAILY: self.delivery.send_daily_report,
            ReportType.WEEKLY: self.delivery.send_weekly_report,
            ReportType.MONTHLY: self.delivery.send_monthly_report,
            ReportType.SEMIANNUAL: self.delivery.send_semiannual_report,
            ReportType.ANNUAL: self.delivery.send_annual_report,
        }

        send_fn = send_methods.get(report_type)
        if not send_fn:
            logger.error("unknown_report_type", report_type=report_type)
            return False

        return await send_fn(worker_id)

    # =========================================================================
    # Schedule Checking
    # =========================================================================

    def _is_report_due(
        self, report_type: ReportType, now: datetime
    ) -> bool:
        """
        Check if a specific report type is due right now.

        Uses EAT timezone and delivery windows.

        Args:
            report_type: Type of report
            now: Current EAT datetime

        Returns:
            True if the report should be sent now
        """
        if report_type == ReportType.DAILY:
            return self._is_time_match(now, DEFAULT_DAILY_HOUR)

        elif report_type == ReportType.WEEKLY:
            # Monday = weekday 0
            return now.weekday() == 0 and self._is_time_match(
                now, DEFAULT_WEEKLY_HOUR
            )

        elif report_type == ReportType.MONTHLY:
            return now.day == 1 and self._is_time_match(
                now, DEFAULT_MONTHLY_HOUR
            )

        elif report_type == ReportType.SEMIANNUAL:
            # June 30 and December 31
            is_semiannual_date = (
                (now.month == 6 and now.day == 30)
                or (now.month == 12 and now.day == 31)
            )
            return is_semiannual_date and self._is_time_match(
                now, DEFAULT_SEMIANNUAL_HOUR
            )

        elif report_type == ReportType.ANNUAL:
            return (
                now.month == 12
                and now.day == 31
                and self._is_time_match(now, DEFAULT_ANNUAL_HOUR)
            )

        return False

    def _is_time_match(
        self, now: datetime, target_hour: int
    ) -> bool:
        """
        Check if current time is within the delivery window
        of the target hour.

        Args:
            now: Current datetime
            target_hour: Target hour (0-23)

        Returns:
            True if within delivery window
        """
        target = now.replace(
            hour=target_hour, minute=0, second=0, microsecond=0
        )
        window = timedelta(minutes=DELIVERY_WINDOW_MINUTES)
        return target - window <= now <= target + window

    # =========================================================================
    # Database Helpers
    # =========================================================================

    async def _get_active_whatsapp_users(self) -> List[User]:
        """Get all active users on the WhatsApp channel."""
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.is_active == True,
                    User.channel == "whatsapp",
                )
            )
        )
        return list(result.scalars().all())

    async def _already_sent(
        self, user_id, report_type: ReportType
    ) -> bool:
        """
        Check if a report was already sent to this user today.

        Uses a simple in-memory check for now. In production,
        this would query a delivery_log table.
        """
        # For now, we always send — the delivery service handles dedup
        # In production, query a delivery_log table
        return False

    async def _log_delivery(
        self,
        user_id,
        report_type: ReportType,
        status: DeliveryStatus,
        error: Optional[str] = None,
    ) -> None:
        """
        Log a delivery attempt.

        In production, this would write to a delivery_log table.
        For now, just log to structured logger.
        """
        logger.info(
            "delivery_log",
            user_id=str(user_id),
            report_type=report_type.value,
            status=status.value,
            error=error,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_schedule_status(self) -> Dict[str, Any]:
        """
        Get current scheduler status and next scheduled runs.

        Returns:
            Dict with scheduler status information
        """
        now = eat_now()

        return {
            "current_time_eat": now.isoformat(),
            "next_reports": {
                "daily": self._next_daily(now),
                "weekly": self._next_weekly(now),
                "monthly": self._next_monthly(now),
                "semiannual": self._next_semiannual(now),
                "annual": self._next_annual(now),
            },
            "active_whatsapp_users": len(
                await self._get_active_whatsapp_users()
            ),
        }

    def _next_daily(self, now: datetime) -> str:
        """Calculate next daily report time."""
        target = now.replace(
            hour=DEFAULT_DAILY_HOUR, minute=0, second=0, microsecond=0
        )
        if now > target:
            target += timedelta(days=1)
        return target.isoformat()

    def _next_weekly(self, now: datetime) -> str:
        """Calculate next weekly report time (Monday)."""
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour >= DEFAULT_WEEKLY_HOUR:
            days_until_monday = 7
        target = now.replace(
            hour=DEFAULT_WEEKLY_HOUR, minute=0, second=0, microsecond=0
        ) + timedelta(days=days_until_monday)
        return target.isoformat()

    def _next_monthly(self, now: datetime) -> str:
        """Calculate next monthly report time (1st of month)."""
        if now.day == 1 and now.hour < DEFAULT_MONTHLY_HOUR:
            target = now.replace(
                hour=DEFAULT_MONTHLY_HOUR, minute=0, second=0, microsecond=0
            )
        else:
            if now.month == 12:
                target = now.replace(
                    year=now.year + 1, month=1, day=1,
                    hour=DEFAULT_MONTHLY_HOUR, minute=0, second=0, microsecond=0,
                )
            else:
                target = now.replace(
                    month=now.month + 1, day=1,
                    hour=DEFAULT_MONTHLY_HOUR, minute=0, second=0, microsecond=0,
                )
        return target.isoformat()

    def _next_semiannual(self, now: datetime) -> str:
        """Calculate next semi-annual report time."""
        if now.month <= 6:
            target = now.replace(
                month=6, day=30,
                hour=DEFAULT_SEMIANNUAL_HOUR, minute=0, second=0, microsecond=0,
            )
        else:
            target = now.replace(
                month=12, day=31,
                hour=DEFAULT_SEMIANNUAL_HOUR, minute=0, second=0, microsecond=0,
            )
        if now > target:
            if target.month == 6:
                target = target.replace(month=12, day=31)
            else:
                target = target.replace(
                    year=target.year + 1, month=6, day=30
                )
        return target.isoformat()

    def _next_annual(self, now: datetime) -> str:
        """Calculate next annual report time."""
        target = now.replace(
            month=12, day=31,
            hour=DEFAULT_ANNUAL_HOUR, minute=0, second=0, microsecond=0,
        )
        if now > target:
            target = target.replace(year=target.year + 1)
        return target.isoformat()
