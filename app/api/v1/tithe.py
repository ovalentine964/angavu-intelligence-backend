"""
Tithe Tracker API — Dedicated endpoints for giving tracking.

Endpoints:
    POST /api/v1/tithe/record    — Record a tithe/giving
    GET  /api/v1/tithe/report    — Get giving report (weekly/monthly/yearly)
    GET  /api/v1/tithe/abundance — Get abundance pattern analysis
    GET  /api/v1/tithe/consistency — Get giving consistency score

All responses include Swahili and English messages.
"""

from datetime import date
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services import tithe_service

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/tithe", tags=["Tithe Tracker"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class TitheRecordRequest(BaseModel):
    """Request schema for recording a tithe/giving entry."""

    user_id: UUID = Field(..., description="User UUID")
    amount: float = Field(..., gt=0, description="Giving amount (must be > 0)")
    currency: str = Field(
        default="KES", max_length=3, min_length=3,
        description="ISO currency code (KES, UGX, TZS, NGN)",
    )
    method: str = Field(
        default="manual",
        description="Input method: 'manual', 'voice', or 'mpesa_parse'",
        pattern="^(manual|voice|mpesa_parse)$",
    )
    recipient: Optional[str] = Field(
        default=None, max_length=200,
        description="Church, mosque, person, or community name",
    )
    purpose: str = Field(
        default="offering",
        description=(
            "Giving category: 'tithe', 'offering', 'zakat', 'harambee', "
            "'charity', 'building_fund', 'missions', 'custom'"
        ),
        pattern="^(tithe|offering|zakat|harambee|charity|building_fund|missions|custom)$",
    )
    giving_date: Optional[date] = Field(
        default=None,
        description="Date of giving (YYYY-MM-DD). Defaults to today.",
    )
    custom_category_name: Optional[str] = Field(
        default=None, max_length=100,
        description="Custom category label when purpose='custom'",
    )
    voice_transcript: Optional[str] = Field(
        default=None,
        description="Raw voice input transcription, if applicable",
    )
    notes: Optional[str] = Field(default=None, description="Optional notes")


class TitheRecordResponse(BaseModel):
    """Response after recording a tithe."""

    record_id: str
    amount: float
    currency: str
    category: str
    recipient: Optional[str]
    giving_date: str
    month_total: float
    consistency: dict
    encouragement: Optional[dict]


class TitheReportResponse(BaseModel):
    """Response for a giving report."""

    period: str
    period_type: str
    total_given: float
    currency: str
    by_category: dict
    by_recipient: dict
    record_count: int
    consistency: dict
    best_month: Optional[dict]
    previous_period_total: float
    change_from_previous: float
    change_pct: Optional[float]
    message_sw: str
    message_en: str


class AbundanceResponse(BaseModel):
    """Response for abundance pattern analysis."""

    status: str
    months_analyzed: Optional[int]
    income_trend: Optional[str]
    giving_trend: Optional[str]
    avg_giving_pct: Optional[float]
    abundance_score: Optional[float]
    pattern: Optional[str]
    creditworthiness_signal: Optional[str]
    monthly_data: Optional[list]
    insight: dict


class ConsistencyResponse(BaseModel):
    """Response for consistency score."""

    score: int
    active_weeks: int
    total_weeks: int
    current_streak: int
    rating_sw: str
    rating_en: str
    stars: str


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/record", response_model=TitheRecordResponse)
async def record_tithe(
    request: TitheRecordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a tithe/giving entry.

    Records a giving entry (tithe, offering, zakat, harambee, charity, etc.)
    and returns the recorded entry with monthly total, consistency score,
    and an encouragement message in Swahili and English.

    **Giving categories:**
    - `tithe` — Regular tithe (typically 10% of income)
    - `offering` — General offering
    - `zakat` — Islamic charitable giving
    - `harambee` — Community fundraising
    - `charity` — General charitable giving
    - `building_fund` — Church/mosque building fund
    - `missions` — Missionary support
    - `custom` — Custom category (use custom_category_name field)

    **Encouragement messages** are generated based on giving history
    and include Swahili translations for voice delivery via Msaidizi.
    """
    try:
        result = await tithe_service.record_tithe(
            db=db,
            user_id=request.user_id,
            amount=request.amount,
            currency=request.currency,
            method=request.method,
            recipient=request.recipient,
            purpose=request.purpose,
            giving_date=request.giving_date,
            custom_category_name=request.custom_category_name,
            voice_transcript=request.voice_transcript,
            notes=request.notes,
        )
        return result
    except ValueError as e:
        logger.warning("tithe_validation_error", error=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("tithe_record_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record giving")


@router.get("/report")
async def giving_report(
    user_id: UUID = Query(..., description="User UUID"),
    period: str = Query(
        "monthly",
        pattern="^(weekly|monthly|yearly)$",
        description="Report period: 'weekly', 'monthly', or 'yearly'",
    ),
    year: Optional[int] = Query(None, description="Year for the report"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month (1-12) for monthly reports"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a giving report for a specified period.

    Returns total giving, breakdown by category and recipient,
    consistency score, and comparison with the previous period.

    **Period types:**
    - `weekly` — Current ISO week
    - `monthly` — Specified month (defaults to current month)
    - `yearly` — Full year (includes best giving month)

    Response includes Swahili and English summary messages
    suitable for voice delivery via Msaidizi.
    """
    try:
        result = await tithe_service.get_tithe_report(
            db=db,
            user_id=user_id,
            period=period,
            year=year,
            month=month,
        )
        return result
    except Exception as e:
        logger.error("tithe_report_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate report")


@router.get("/abundance")
async def abundance_pattern(
    user_id: UUID = Query(..., description="User UUID"),
    months: int = Query(
        6, ge=3, le=24,
        description="Number of months to analyze (3-24, default 6)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze giving patterns and produce an abundance score.

    Correlates giving consistency with income trends to detect
    abundance patterns. Research shows giving patterns predict
    creditworthiness better than bank balances.

    **Pattern types:**
    - `blessing_cycle` — Income ↑ and giving ↑ (best pattern)
    - `income_outpacing_giving` — Income ↑ but giving →
    - `faithful_giving` — Income ↓ but giving → or ↑ (strongest character signal)
    - `parallel_decline` — Both ↓ (normal during hardship)
    - `steady` — Consistent giving pattern

    **Creditworthiness signals** are derived from giving patterns:
    - `strong` — Faithful giving or blessing cycle with ≥5% giving
    - `moderate` — Abundance score ≥60
    - `weak` — Abundance score ≥30
    - `insufficient` — Not enough data or low giving

    Requires at least 3 months of income data for pattern detection.
    """
    try:
        result = await tithe_service.get_abundance_pattern(
            db=db,
            user_id=user_id,
            months=months,
        )
        return result
    except Exception as e:
        logger.error("abundance_pattern_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to analyze abundance pattern")


@router.get("/consistency")
async def consistency_score(
    user_id: UUID = Query(..., description="User UUID"),
    period_months: int = Query(
        1, ge=1, le=12,
        description="Number of months to look back (1-12, default 1)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get giving consistency score for a user.

    Measures how regularly a user gives over a period.
    Score = (weeks_with_giving / total_weeks_in_period) × 100

    **Consistency ratings:**
    - ⭐⭐⭐⭐⭐ Mtoaji wa mfano / Exemplary giver (≥90)
    - ⭐⭐⭐⭐ Mtoaji thabiti / Consistent giver (≥70)
    - ⭐⭐⭐ Mtoaji anayekua / Growing giver (≥50)
    - ⭐⭐ Mtoaji mpya / New giver (≥30)
    - ⭐ Ananza safari / Starting the journey (<30)

    The response includes the current consecutive-week streak
    and ratings in both Swahili and English.
    """
    try:
        result = await tithe_service.get_consistency_score(
            db=db,
            user_id=user_id,
            period_months=period_months,
        )
        return result
    except Exception as e:
        logger.error("consistency_score_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to calculate consistency score")
