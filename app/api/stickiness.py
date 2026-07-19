"""
Stickiness / Engagement API — Gamification endpoints.

Implements the Hook Model for habit formation:
- Engagement metrics and retention signals
- Streak tracking with protection (forgiveness mechanics)
- Badge system with 18 Swahili badges
- Level progression (Mwanafunzi → Legend)
- Variable rewards (surprise elements)
- Aha moment tracking (60-second activation)
- Social proof (anonymized peer comparison)

Anti-shame design: No public leaderboards, all comparisons positive and anonymized.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services import stickiness_service

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/stickiness", tags=["Stickiness & Engagement"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class AhaMomentRequest(BaseModel):
    """Track an aha moment for a user."""
    user_id: UUID = Field(..., description="User ID")
    action: str = Field(
        ...,
        description="Aha moment action (e.g. 'first_sale', 'first_insight_viewed')",
        examples=["first_sale"],
    )


class ActivityRecordRequest(BaseModel):
    """Record a user activity (internal use)."""
    user_id: UUID = Field(..., description="User ID")
    xp_earned: int = Field(default=0, ge=0, description="XP earned from this action")
    actions_increment: int = Field(default=1, ge=1, description="Number of actions to record")


class EngagementResponse(BaseModel):
    """User engagement metrics."""
    user_id: str
    current_streak: int
    longest_streak: int
    level: int
    xp: int
    total_actions_30d: int
    total_xp_30d: int
    active_days_30d: int
    active_days_7d: int
    retention: dict
    aha_moments_hit: list[str]
    is_active_today: bool


class StreakResponse(BaseModel):
    """Streak status with protection info."""
    user_id: str
    current_streak: int
    longest_streak: int
    protection_available: bool
    protection_count: int
    streak_at_risk: bool
    last_active_date: str | None
    freeze_count: int
    message_sw: str
    message_en: str


class BadgeResponse(BaseModel):
    """Badge catalog with earned status."""
    user_id: str
    total_earned: int
    total_available: int
    completion_percent: float
    categories: dict
    recent_badges: list


class LevelResponse(BaseModel):
    """Level progress information."""
    user_id: str
    level: int
    level_name: str
    level_name_en: str
    level_icon: str
    xp: int
    xp_to_next: int | None
    progress_percent: float
    current_level_description: str
    current_level_description_en: str
    perks_unlocked: list[str]
    next_level: dict | None
    streak_protection_count: int


class VariableRewardResponse(BaseModel):
    """Variable reward result."""
    has_reward: bool
    reward_type: str | None = None
    title: str | None = None
    title_en: str | None = None
    message_sw: str | None = None
    message_en: str | None = None
    icon: str | None = None
    bonus_xp: int | None = None
    total_xp: int | None = None
    cooldown_remaining_hours: float | None = None


class AhaMomentResponse(BaseModel):
    """Aha moment tracking result."""
    success: bool
    is_new: bool | None = None
    action: str
    name: str | None = None
    name_sw: str | None = None
    importance: str | None = None
    xp_reward: int | None = None
    message_sw: str | None = None
    message_en: str | None = None
    error: str | None = None
    valid_actions: list[str] | None = None


class SocialProofResponse(BaseModel):
    """Anonymized social proof data."""
    user_id: str | None
    community_size: int
    active_this_week: int
    average_streak: float
    proofs: list[dict]


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/engagement", response_model=EngagementResponse)
async def get_engagement(
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get user engagement metrics.

    Returns retention signals (D1/D7/D30), streak info, level,
    activity summary, and aha moments hit.
    """
    try:
        return await stickiness_service.get_user_engagement(db, user_id)
    except Exception as e:
        logger.error("engagement_fetch_failed", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch engagement metrics",
        )


@router.get("/streak", response_model=StreakResponse)
async def get_streak(
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get streak status with protection info.

    Returns current streak, longest streak, available shields,
    and a motivational message in Swahili.
    """
    try:
        return await stickiness_service.get_streak_status(db, user_id)
    except Exception as e:
        logger.error("streak_fetch_failed", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch streak status",
        )


@router.get("/badges", response_model=BadgeResponse)
async def get_badges(
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all badges with earned/unearned status.

    Returns the full 18-badge catalog organized by category,
    with the user's earned badges highlighted.
    """
    try:
        return await stickiness_service.get_badges(db, user_id)
    except Exception as e:
        logger.error("badges_fetch_failed", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch badges",
        )


@router.get("/level", response_model=LevelResponse)
async def get_level(
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get level progress.

    Returns current level (Mwanafunzi → Legend), XP progress,
    unlocked perks, and next level info.
    """
    try:
        return await stickiness_service.get_level_progress(db, user_id)
    except Exception as e:
        logger.error("level_fetch_failed", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch level progress",
        )


@router.get("/reward", response_model=VariableRewardResponse)
async def get_reward(
    user_id: UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a variable (surprise) reward.

    Uses weighted random selection with cooldown tracking.
    The surprise element is key to the Hook Model — users don't know
    what reward they'll get, creating anticipation and dopamine.
    """
    try:
        return await stickiness_service.get_variable_reward(db, user_id)
    except Exception as e:
        logger.error("reward_fetch_failed", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to generate reward",
        )


@router.post("/aha", response_model=AhaMomentResponse)
async def track_aha(
    request: AhaMomentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Track an aha moment.

    Aha moments are critical activation events that must happen within
    60 seconds for first sale. Tracking these helps measure onboarding
    effectiveness and user activation.

    Valid actions: first_sale, first_insight_viewed, first_report_generated,
    profile_complete, second_session, week_active
    """
    try:
        return await stickiness_service.track_aha_moment(
            db, request.user_id, request.action
        )
    except Exception as e:
        logger.error(
            "aha_tracking_failed",
            user_id=str(request.user_id),
            action=request.action,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to track aha moment",
        )


@router.get("/social", response_model=SocialProofResponse)
async def get_social(
    user_id: UUID | None = Query(None, description="User ID (optional)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get anonymized social proof data.

    Anti-shame design: All comparisons are anonymized and positive.
    No negative comparisons, no exact rankings, no "you're behind" messages.
    Shows community activity, peer averages, and positive comparisons.
    """
    try:
        return await stickiness_service.get_social_proof(db, user_id)
    except Exception as e:
        logger.error("social_proof_fetch_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch social proof",
        )


@router.post("/activity")
async def record_activity(
    request: ActivityRecordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a user activity event.

    Updates engagement metrics, streak, and checks for badge eligibility.
    This is the core "Action" step in the Hook Model.
    """
    try:
        result = await stickiness_service.record_activity(
            db, request.user_id, request.xp_earned, request.actions_increment
        )
        return result
    except Exception as e:
        logger.error(
            "activity_recording_failed",
            user_id=str(request.user_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to record activity",
        )
