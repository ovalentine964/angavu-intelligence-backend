"""
Business Reports API endpoints.

Provides daily, weekly, and AI-generated advice reports for users.
Reports are available in Swahili, English, and Sheng.
"""

from datetime import date, datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.report import (
    AdviceReport,
    DailyReport,
    WeeklyReport,
)
from app.services.report_gen import ReportGenerator

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/reports", tags=["Business Reports"])


@router.get("/{user_id}/daily", response_model=DailyReport)
async def get_daily_report(
    user_id: str,
    report_date: Optional[date] = Query(
        None,
        description="Report date (defaults to today)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get daily business summary report.

    Shows total sales, expenses, profit, top products,
    and comparison with yesterday and last week's average.

    **Delivery:**
    - WhatsApp: Formatted text message at 7 PM EAT daily
    - Telegram: Rich formatted message with inline buttons
    - SMS: Plain text summary for feature phones
    - API: Full JSON with all metrics

    Args:
        user_id: User UUID (must match authenticated user)
        report_date: Date to generate for (defaults to today)

    Returns:
        DailyReport with all business metrics
    """
    # Verify user can access this report
    if str(current_user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only access your own reports",
        )

    report_gen = ReportGenerator(db)
    report = await report_gen.generate_daily_report(
        current_user,
        report_date=report_date,
    )

    logger.info(
        "daily_report_generated",
        user_id=user_id,
        date=str(report_date or date.today()),
        sales=report.summary.total_sales,
    )

    return report


@router.get("/{user_id}/weekly", response_model=WeeklyReport)
async def get_weekly_report(
    user_id: str,
    week_end: Optional[date] = Query(
        None,
        description="End of week (defaults to today)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get weekly business trends report.

    Shows week-over-week trends, best/worst days,
    product performance, and payment method mix.

    **Generated every Monday morning.**

    Args:
        user_id: User UUID
        week_end: End date of the week (defaults to today)

    Returns:
        WeeklyReport with trends and insights
    """
    if str(current_user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only access your own reports",
        )

    report_gen = ReportGenerator(db)
    report = await report_gen.generate_weekly_report(
        current_user,
        week_end=week_end,
    )

    logger.info(
        "weekly_report_generated",
        user_id=user_id,
        week_start=str(report.week_start),
        sales=report.summary.total_sales,
    )

    return report


@router.get("/{user_id}/advice", response_model=AdviceReport)
async def get_advice_report(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get AI-generated business advice.

    Analyzes transaction patterns and generates actionable
    recommendations for improving the business.

    **Advice Categories:**
    - pricing: Adjust prices for better margins
    - inventory: Restock alerts and buying recommendations
    - operations: Operating hours, location, workflow tips
    - marketing: Customer attraction and retention
    - finance: Savings, debt management, growth investment

    Args:
        user_id: User UUID

    Returns:
        AdviceReport with prioritized recommendations
    """
    if str(current_user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only access your own reports",
        )

    report_gen = ReportGenerator(db)
    report = await report_gen.generate_advice_report(current_user)

    logger.info(
        "advice_report_generated",
        user_id=user_id,
        health_score=report.health_score,
        advice_count=len(report.advice),
    )

    return report


@router.get("/{user_id}/summary")
async def get_quick_summary(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a quick one-line business summary.

    Optimized for WhatsApp/Telegram bot responses where
    a full report isn't needed.

    Returns:
        Simple dict with today's key numbers
    """
    if str(current_user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only access your own data",
        )

    from app.services.pipeline import DataPipeline
    pipeline = DataPipeline(db)

    today = date.today()
    metrics = await pipeline.aggregate_user_metrics(
        current_user.id, today, today
    )

    lang = current_user.language or "sw"
    if lang == "sw":
        summary = (
            f"Mauzo: KES {metrics['total_sales']:,.0f} | "
            f"Faida: KES {metrics['net_profit']:,.0f} | "
            f"Transactions: {metrics['transaction_count']}"
        )
    else:
        summary = (
            f"Sales: KES {metrics['total_sales']:,.0f} | "
            f"Profit: KES {metrics['net_profit']:,.0f} | "
            f"Transactions: {metrics['transaction_count']}"
        )

    return {
        "user_id": user_id,
        "date": today.isoformat(),
        "summary": summary,
        "metrics": {
            "total_sales": metrics["total_sales"],
            "total_expenses": metrics["total_purchases"] + metrics["total_expenses"],
            "net_profit": metrics["net_profit"],
            "transaction_count": metrics["transaction_count"],
            "profit_margin_pct": metrics["profit_margin_pct"],
        },
    }
