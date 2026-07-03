"""
Goal Planner API — Accountability-driven goal tracking endpoints.

Endpoints:
    POST /goals/create          — Create a goal (supports voice input)
    PUT  /goals/{goal_id}/progress — Update goal progress
    GET  /goals/{goal_id}       — Get goal details
    GET  /goals/{goal_id}/prediction — Time-to-goal prediction
    GET  /goals/{goal_id}/obstacles  — Obstacle analysis
    GET  /goals/accountability  — Accountability partner report
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services import goal_service

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/goals", tags=["Goal Planner"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request/Response Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class GoalCreateRequest(BaseModel):
    """Create a new goal. Supports voice-created goals via voice_transcript."""
    user_id: UUID
    title: str = Field(default="", max_length=200, description="Goal title (auto-parsed if voice_transcript provided)")
    category: str = Field(default="personal", description="business, personal, savings, or debt")
    target_amount: float = Field(..., gt=0, description="Target amount in local currency")
    target_date: Optional[date] = Field(None, description="Target completion date")
    description: Optional[str] = None
    title_sw: Optional[str] = Field(None, description="Swahili translation of title")
    deeper_purpose: Optional[str] = Field(None, description="Why this goal matters")
    what_i_lose: Optional[str] = Field(None, description="What you lose by not achieving this")
    milestones: Optional[List[dict]] = Field(None, description="Custom milestones (auto-generated if omitted)")
    commitment_declaration: Optional[str] = Field(None, description="Public commitment statement")
    accountability_partner_id: Optional[UUID] = Field(None, description="Accountability partner user ID")
    voice_transcript: Optional[str] = Field(None, description="Raw voice input for parsing")
    currency: str = Field(default="KES", max_length=3)


class GoalProgressUpdateRequest(BaseModel):
    """Update progress toward a goal."""
    user_id: UUID
    amount: float = Field(..., gt=0, description="Contribution amount")
    notes: Optional[str] = Field(None, description="Notes about this contribution")
    source: str = Field(default="manual", description="manual, voice, mpesa, or auto_save")
    voice_transcript: Optional[str] = Field(None, description="Raw voice input")
    mood: Optional[str] = Field(None, description="motivated, neutral, or struggling")
    entry_date: Optional[date] = Field(None, description="Date of contribution (defaults to today)")


class MilestoneResponse(BaseModel):
    percentage: int
    title: str
    title_sw: Optional[str]
    target_amount: float
    completed: bool
    completed_at: Optional[str]


class PredictionResponse(BaseModel):
    status: str
    weekly_rate: Optional[float] = None
    trend: Optional[str] = None
    weeks_remaining: Optional[float] = None
    expected_date: Optional[str] = None
    best_case_date: Optional[str] = None
    worst_case_date: Optional[str] = None
    ahead_of_schedule: Optional[bool] = None
    confidence: Optional[str] = None
    message_sw: Optional[str] = None
    message_en: Optional[str] = None


class ObstacleResponse(BaseModel):
    type: str
    severity: str
    detail_sw: Optional[str] = None
    detail_en: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Goal Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/create", summary="Create a goal")
async def create_goal(
    request: GoalCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new goal with auto-generated milestones and commitment device.

    Supports voice-created goals — pass voice_transcript and the system
    will parse natural language (Swahili/English) to extract goal details.

    Categories: business, personal, savings, debt

    Behavioral features:
    - Commitment device (public declaration)
    - Accountability partner linking
    - Loss aversion triggers (what_i_lose)
    - Auto-generated daily/weekly targets
    """
    try:
        result = await goal_service.create_goal(
            db=db,
            user_id=request.user_id,
            title=request.title,
            category=request.category,
            target_amount=request.target_amount,
            target_date=request.target_date,
            description=request.description,
            title_sw=request.title_sw,
            deeper_purpose=request.deeper_purpose,
            what_i_lose=request.what_i_lose,
            milestones=request.milestones,
            commitment_declaration=request.commitment_declaration,
            accountability_partner_id=request.accountability_partner_id,
            voice_transcript=request.voice_transcript,
            currency=request.currency,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        logger.info("goal_created", goal_id=result.get("goal_id"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("goal_create_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create goal")


@router.put("/{goal_id}/progress", summary="Update goal progress")
async def update_progress(
    goal_id: UUID,
    request: GoalProgressUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a progress entry toward a goal.

    Handles:
    - Streak tracking (consecutive contribution days)
    - Milestone detection (25/50/75/100% celebrations)
    - Completion detection
    - Behavioral nudge generation
    - Time-to-goal prediction update

    Returns encouragement in Swahili and English.
    """
    try:
        result = await goal_service.update_progress(
            db=db,
            goal_id=goal_id,
            user_id=request.user_id,
            amount=request.amount,
            notes=request.notes,
            source=request.source,
            voice_transcript=request.voice_transcript,
            mood=request.mood,
            entry_date=request.entry_date,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        logger.info("goal_progress_updated", goal_id=str(goal_id), amount=request.amount)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("goal_progress_update_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update progress")


@router.get("/{goal_id}", summary="Get goal details")
async def get_goal(
    goal_id: UUID,
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed goal progress including:
    - Current amount and percentage
    - Streak status
    - Milestone completion
    - Recent entries
    - Time-to-goal prediction
    - Voice-friendly summaries (Swahili & English)
    """
    try:
        result = await goal_service.get_goal_progress(
            db=db,
            goal_id=goal_id,
            user_id=user_id,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("goal_get_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get goal")


@router.get("/{goal_id}/prediction", summary="Time-to-goal prediction")
async def get_prediction(
    goal_id: UUID,
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Predict time-to-goal using Polars rolling average analysis.

    Returns:
    - Expected completion date
    - Best/worst case scenarios
    - Weekly savings rate trend (increasing/stable/decreasing)
    - Whether ahead or behind schedule
    - Confidence level based on data availability
    """
    try:
        result = await goal_service.get_time_to_goal(
            db=db,
            goal_id=goal_id,
            user_id=user_id,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("goal_prediction_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to predict time to goal")


@router.get("/{goal_id}/obstacles", summary="Obstacle analysis")
async def get_obstacles(
    goal_id: UUID,
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze contribution patterns to identify potential obstacles.

    Detects:
    - Inconsistent contribution patterns
    - Declining contribution amounts
    - Weekend vs weekday gaps
    - Recent inactivity streaks
    - Overall risk level (low/medium/high)

    Returns actionable recommendations in Swahili and English.
    """
    try:
        result = await goal_service.get_obstacle_analysis(
            db=db,
            goal_id=goal_id,
            user_id=user_id,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("goal_obstacles_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to analyze obstacles")


@router.get("/accountability", summary="Accountability report")
async def get_accountability_report(
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate an accountability partner report across all active goals.

    Shows:
    - Overall progress grade (A-F)
    - Goal-by-goal breakdown
    - Streak and consistency scores
    - Commitment adherence
    - Social proof (how many peers have goals)
    - Weekly report card

    Designed as Msaidizi's accountability partner feature —
    research shows 95% goal completion with accountability vs 65% without.
    """
    try:
        result = await goal_service.get_accountability_report(
            db=db,
            user_id=user_id,
        )
        return result
    except Exception as e:
        logger.error("accountability_report_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate accountability report")
