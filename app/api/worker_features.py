"""
Worker Features API — Tithe, Goals, Loans, Mindset.

Endpoints for Msaidizi's core worker-facing features:
- POST /tithe/record — Record giving
- GET  /tithe/report — Giving report
- POST /goals/create — Create goal
- GET  /goals/progress — Goal progress
- POST /loans/record — Record loan
- GET  /loans/status — Loan status
- GET  /mindset/lesson — Today's lesson
- GET  /mindset/score — Rich habits score
"""

from datetime import date
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services import tithe_service, goal_service, loan_service, mindset_service

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/worker", tags=["Worker Features"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request/Response Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class TitheRecordRequest(BaseModel):
    user_id: UUID
    amount: float = Field(..., gt=0)
    category: str = Field(default="offering")
    currency: str = Field(default="KES", max_length=3)
    custom_category_name: Optional[str] = None
    recipient: Optional[str] = None
    giving_date: Optional[date] = None
    input_method: str = Field(default="manual")
    voice_transcript: Optional[str] = None
    notes: Optional[str] = None


class TitheReportRequest(BaseModel):
    user_id: UUID
    period: str = Field(default="monthly")
    year: Optional[int] = None
    month: Optional[int] = None


class GoalCreateRequest(BaseModel):
    user_id: UUID
    goal_type: str = Field(..., description="business, personal, savings, or debt")
    title: str = Field(..., max_length=200)
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(default=0, ge=0)
    title_sw: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[date] = None
    deeper_purpose: Optional[str] = None
    currency: str = Field(default="KES", max_length=3)


class GoalProgressRequest(BaseModel):
    user_id: UUID
    goal_id: Optional[UUID] = None


class LoanRecordRequest(BaseModel):
    user_id: UUID
    principal: float = Field(..., gt=0)
    interest_rate: float = Field(..., ge=0)
    purpose: str = Field(..., description="stock, equipment, emergency, education, improvement, other")
    source: str = Field(default="manual")
    purpose_details: Optional[dict] = None
    disbursed_at: Optional[str] = None
    due_date: Optional[date] = None
    repayment_type: str = Field(default="flexible")
    repayment_frequency: str = Field(default="weekly")
    commitment_text: Optional[str] = None
    currency: str = Field(default="KES", max_length=3)


class LoanStatusRequest(BaseModel):
    user_id: UUID
    loan_id: Optional[UUID] = None


class HabitUpdateRequest(BaseModel):
    user_id: UUID
    habit_key: str
    completed: bool = True


# ═══════════════════════════════════════════════════════════════════════════════
# Tithe & Giving Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/tithe/record")
async def record_giving(
    request: TitheRecordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a giving entry (tithe, offering, zakat, harambee, charity).

    Returns the recorded entry, monthly total, consistency score,
    and an encouragement message in Swahili and English.
    """
    try:
        result = await tithe_service.record_giving(
            db=db,
            user_id=request.user_id,
            amount=request.amount,
            category=request.category,
            currency=request.currency,
            custom_category_name=request.custom_category_name,
            recipient=request.recipient,
            giving_date=request.giving_date,
            input_method=request.input_method,
            voice_transcript=request.voice_transcript,
            notes=request.notes,
        )
        return result
    except Exception as e:
        logger.error("tithe_record_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to record giving")


@router.get("/tithe/report")
async def giving_report(
    user_id: UUID,
    period: str = Query("monthly", regex="^(monthly|annual)$"),
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a giving report for a period.

    Returns total giving, breakdown by category, consistency score,
    comparison with previous period, and best month (for annual).
    """
    try:
        result = await tithe_service.get_giving_report(
            db=db,
            user_id=user_id,
            period=period,
            year=year,
            month=month,
        )
        return result
    except Exception as e:
        logger.error("tithe_report_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate report")


# ═══════════════════════════════════════════════════════════════════════════════
# Goal Planning Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/goals/create")
async def create_goal(
    request: GoalCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new financial goal with auto-generated milestones.

    Supports categories: business, personal, savings, debt.
    Auto-generates daily/weekly targets and 25/50/75/100% milestones.
    """
    try:
        result = await goal_service.create_goal(
            db=db,
            user_id=request.user_id,
            goal_type=request.goal_type,
            title=request.title,
            target_amount=request.target_amount,
            current_amount=request.current_amount,
            title_sw=request.title_sw,
            description=request.description,
            deadline=request.deadline,
            deeper_purpose=request.deeper_purpose,
            currency=request.currency,
        )
        return result
    except Exception as e:
        logger.error("goal_create_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to create goal")


@router.get("/goals/progress")
async def goal_progress(
    user_id: UUID,
    goal_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get goal progress with streak, milestones, and time-to-goal prediction.

    Defaults to the user's primary active goal if goal_id not specified.
    Returns voice-friendly summaries in Swahili and English.
    """
    try:
        result = await goal_service.get_goal_progress(
            db=db,
            user_id=user_id,
            goal_id=goal_id,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("goal_progress_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get goal progress")


# ═══════════════════════════════════════════════════════════════════════════════
# Loan Intelligence Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/loans/record")
async def record_loan(
    request: LoanRecordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a loan with purpose verification and repayment plan.

    Automatically calculates total due, suggested payments,
    and runs initial default risk prediction.
    """
    try:
        disbursed_at = None
        if request.disbursed_at:
            from datetime import datetime
            disbursed_at = datetime.fromisoformat(request.disbursed_at)

        result = await loan_service.record_loan(
            db=db,
            user_id=request.user_id,
            principal=request.principal,
            interest_rate=request.interest_rate,
            purpose=request.purpose,
            source=request.source,
            purpose_details=request.purpose_details,
            disbursed_at=disbursed_at,
            due_date=request.due_date,
            repayment_type=request.repayment_type,
            repayment_frequency=request.repayment_frequency,
            commitment_text=request.commitment_text,
            currency=request.currency,
        )
        return result
    except Exception as e:
        logger.error("loan_record_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to record loan")


@router.get("/loans/status")
async def loan_status(
    user_id: UUID,
    loan_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get loan status with ROI tracking, repayment summary, and risk assessment.

    Returns streak info, recent repayments, and voice-friendly summaries.
    """
    try:
        result = await loan_service.get_loan_status(
            db=db,
            user_id=user_id,
            loan_id=loan_id,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("loan_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get loan status")


# ═══════════════════════════════════════════════════════════════════════════════
# Wealth Mindset Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/mindset/lesson")
async def todays_lesson(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get today's mindset lesson for a user.

    Returns the next uncompleted lesson from the 56-lesson curriculum
    across 6 modules. Includes module progress and greeting messages.
    """
    try:
        result = await mindset_service.get_today_lesson(
            db=db,
            user_id=user_id,
        )
        return result
    except Exception as e:
        logger.error("mindset_lesson_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get lesson")


@router.get("/mindset/score")
async def rich_habits_score(
    user_id: UUID,
    score_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get rich habits score (0-100) for a given date.

    Tracks 10 daily wealth-building habits:
    record_sales, check_balance, save_money, avoid_waste,
    give, learn, set_goal, review_day, help_peer, no_debt.

    Returns score, streak, level, and habit breakdown.
    """
    try:
        result = await mindset_service.get_rich_habits_score(
            db=db,
            user_id=user_id,
            score_date=score_date,
        )
        return result
    except Exception as e:
        logger.error("mindset_score_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get score")


@router.post("/mindset/habit")
async def update_habit(
    request: HabitUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update a single habit and recalculate today's score."""
    try:
        result = await mindset_service.update_habit(
            db=db,
            user_id=request.user_id,
            habit_key=request.habit_key,
            completed=request.completed,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("habit_update_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update habit")
