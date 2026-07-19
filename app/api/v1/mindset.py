"""
Wealth Mindset API — Endpoints for the wealth-building mindset feature.

Provides 56 voice lessons across 6 modules, rich habits tracking,
daily affirmations, habit stacking formulas, and mastermind group
recommendations for Africa's informal economy workers.

Endpoints:
- GET  /mindset/lesson                  — Get daily personalized lesson
- GET  /mindset/habits                  — Get rich habits score (0-100)
- GET  /mindset/affirmation             — Get daily affirmation
- GET  /mindset/habits/stack            — Get habit stacking formula
- GET  /mindset/mastermind              — Get mastermind group recommendations
- POST /mindset/lesson/{lesson_id}/complete — Mark lesson as complete
"""

from datetime import date
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services import mindset_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mindset", tags=["Wealth Mindset"])


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────


class LessonCompleteRequest(BaseModel):
    """Request body for marking a lesson as complete."""
    score: int | None = Field(
        None,
        ge=0,
        le=100,
        description="Optional comprehension score (0-100)",
    )


class HabitUpdateRequest(BaseModel):
    """Request body for updating a habit."""
    habit_key: str = Field(
        ...,
        description="Habit key: record_sales, check_balance, save_money, "
                    "avoid_waste, give, learn, set_goal, review_day, help_peer, no_debt",
    )
    completed: bool = Field(True, description="Whether the habit was completed")


# ─────────────────────────────────────────────────────────────────────────────
# Lesson Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/lesson")
async def get_daily_lesson(
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get today's personalized mindset lesson.

    Returns the next uncompleted lesson from the 56-lesson curriculum
    across 6 modules. Includes module progress, greeting messages,
    and compound interest story when relevant.
    """
    try:
        result = await mindset_service.get_daily_lesson(
            db=db,
            user_id=user_id,
        )
        return result
    except Exception as e:
        logger.error("mindset_lesson_failed", error=str(e), user_id=str(user_id))
        raise HTTPException(status_code=500, detail="Failed to get daily lesson")


@router.post("/lesson/{lesson_id}/complete")
async def complete_lesson(
    lesson_id: UUID,
    user_id: UUID = Query(..., description="User ID"),
    request: LessonCompleteRequest = LessonCompleteRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a lesson as completed.

    Tracks completion count, optional comprehension score, and
    checks if the module is now complete (unlocking the next module).
    """
    try:
        result = await mindset_service.track_lesson_completion(
            db=db,
            user_id=user_id,
            lesson_id=lesson_id,
            score=request.score,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "lesson_complete_failed",
            error=str(e),
            user_id=str(user_id),
            lesson_id=str(lesson_id),
        )
        raise HTTPException(status_code=500, detail="Failed to mark lesson complete")


# ─────────────────────────────────────────────────────────────────────────────
# Rich Habits Score Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/habits")
async def get_rich_habits_score(
    user_id: UUID = Query(..., description="User ID"),
    score_date: date | None = Query(None, description="Score date (defaults to today)"),
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
        logger.error("mindset_score_failed", error=str(e), user_id=str(user_id))
        raise HTTPException(status_code=500, detail="Failed to get rich habits score")


@router.post("/habits/update")
async def update_habit(
    user_id: UUID = Query(..., description="User ID"),
    request: HabitUpdateRequest = ...,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a single habit and recalculate today's score.

    Use this to check off habits as the user completes them throughout the day.
    """
    try:
        result = await mindset_service.update_habit(
            db=db,
            user_id=user_id,
            habit_key=request.habit_key,
            completed=request.completed,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("habit_update_failed", error=str(e), user_id=str(user_id))
        raise HTTPException(status_code=500, detail="Failed to update habit")


# ─────────────────────────────────────────────────────────────────────────────
# Affirmation Endpoint
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/affirmation")
async def get_affirmation(
    language: str = Query(
        "en",
        description="Language: 'en' for English, 'sw' for Swahili",
        regex="^(en|sw)$",
    ),
    category: str | None = Query(
        None,
        description="Category filter: belief, wealth, habits, savings, giving, compound",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a daily affirmation in Swahili or English.

    Affirmations are sourced from the 5 core books and rotate daily.
    Optionally filter by category (belief, wealth, habits, savings, giving, compound).
    """
    try:
        result = await mindset_service.get_affirmation(
            db=db,
            language=language,
            category=category,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("affirmation_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get affirmation")


# ─────────────────────────────────────────────────────────────────────────────
# Habit Stacking Endpoint
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/habits/stack")
async def get_habit_stack(
    user_id: UUID = Query(..., description="User ID"),
    worker_type: str = Query(
        ...,
        description="Worker type: mama_mboga, boda_boda, duka_owner, "
                    "mitumba_vendor, mkono_worker, beautician",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get habit stacking formula for a specific worker type.

    Habit stacking (from Atomic Habits): "After X, I will do Y."
    Each worker type has a tailored daily chain of 10-12 habits
    linked to their specific work routine with timestamps.
    """
    try:
        result = await mindset_service.get_habit_stack(
            db=db,
            user_id=user_id,
            worker_type=worker_type,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("habit_stack_failed", error=str(e), worker_type=worker_type)
        raise HTTPException(status_code=500, detail="Failed to get habit stack")


# ─────────────────────────────────────────────────────────────────────────────
# Mastermind Group Endpoint
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/mastermind")
async def get_mastermind_group(
    user_id: UUID = Query(..., description="User ID"),
    worker_type: str | None = Query(
        None,
        description="Worker type (defaults to mama_mboga if not specified)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get mastermind group recommendations.

    Based on Napoleon Hill's Master Mind principle from Think and Grow Rich.
    Returns group structure, focus areas, benefits, and the compound interest
    story (KSh 50/day → KSh 1.1M in 20 years).
    """
    try:
        result = await mindset_service.get_mastermind_group(
            db=db,
            user_id=user_id,
            worker_type=worker_type,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("mastermind_failed", error=str(e), worker_type=worker_type)
        raise HTTPException(status_code=500, detail="Failed to get mastermind group")
