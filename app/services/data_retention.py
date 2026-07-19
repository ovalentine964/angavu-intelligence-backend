"""
Data Retention Enforcement Service
===================================
Scheduled service that deletes data older than the configured retention period.
Required by Kenya DPA 2019, Nigeria NDPA, and POPIA.

Runs daily at 3 AM EAT (via APScheduler or cron).
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Default retention: 365 days (1 year)
DEFAULT_RETENTION_DAYS = 365

# Tables with timestamp columns for retention
RETENTION_TABLES = [
    ("transactions", "created_at"),
    ("voice_corrections", "created_at"),
    ("federated_updates", "created_at"),
    ("audit_logs", "created_at"),
    ("agent_events", "created_at"),
    ("daily_briefings", "created_at"),
]


async def enforce_retention(db: AsyncSession, retention_days: int = DEFAULT_RETENTION_DAYS):
    """
    Delete all records older than retention_days from all tracked tables.
    
    This function should be called daily via APScheduler or cron job.
    """
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    total_deleted = 0

    for table, timestamp_col in RETENTION_TABLES:
        try:
            # Use raw SQL for efficiency on large tables
            result = await db.execute(
                text(f"DELETE FROM {table} WHERE {timestamp_col} < :cutoff"),
                {"cutoff": cutoff}
            )
            deleted = result.rowcount
            if deleted > 0:
                logger.info("retention_cleanup", table=table, deleted=deleted, cutoff=cutoff.isoformat())
                total_deleted += deleted
        except Exception as e:
            # Table may not exist yet — that's OK
            logger.debug("retention_skip", table=table, error=str(e))

    await db.commit()

    if total_deleted > 0:
        logger.info("retention_complete", total_deleted=total_deleted, retention_days=retention_days)

    return total_deleted


def schedule_retention(app):
    """
    Schedule daily retention cleanup at 3 AM EAT (UTC+3).
    
    Usage:
        from app.services.data_retention import schedule_retention
        schedule_retention(app)
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()

    # 3 AM EAT = 0 AM UTC
    scheduler.add_job(
        enforce_retention,
        trigger=CronTrigger(hour=0, minute=0),  # Midnight UTC = 3 AM EAT
        id="data_retention",
        name="Data Retention Cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("retention_scheduled", time="00:00 UTC (03:00 EAT)")
    return scheduler
