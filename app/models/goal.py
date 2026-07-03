"""
Goal Planner Models — Enhanced goal tracking with milestones and accountability.

Supports Msaidizi's accountability-driven goal planning:
1. Goal — Full goal lifecycle with behavioral nudges and commitment devices
2. GoalMilestone — Discrete milestone tracking (25/50/75/100%)
3. GoalProgressEntry — Granular progress entries with voice support

Categories: business, personal, savings, debt
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID

from app.db.database import Base


class Goal(Base):
    """
    A worker's financial or personal goal with accountability tracking.

    Designed for Africa's informal economy workers who set goals but
    rarely achieve them due to scarcity mindset and present bias.
    Msaidizi becomes the accountability partner (95% completion with
    accountability vs 65% without).
    """

    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Core goal info
    title = Column(String(200), nullable=False, doc="Goal title")
    title_sw = Column(String(200), nullable=True, doc="Swahili translation of title")
    description = Column(Text, nullable=True, doc="Detailed goal description")
    category = Column(
        Enum("business", "personal", "savings", "debt", name="goal_category_enum"),
        nullable=False,
        doc="Goal category",
    )

    # Financial tracking
    target_amount = Column(Float, nullable=False, doc="Target amount in local currency")
    current_amount = Column(
        Float, nullable=False, default=0,
        doc="Amount saved/contributed so far",
    )
    currency = Column(String(3), nullable=False, default="KES")

    # Timeline
    target_date = Column(Date, nullable=True, doc="Target completion date")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(
        Enum("active", "paused", "completed", "abandoned", name="goal_status_v2_enum"),
        nullable=False,
        default="active",
        index=True,
    )

    # Commitment device — public declaration
    commitment_declaration = Column(
        Text, nullable=True,
        doc="Public commitment statement (e.g., 'I will save KSh 500 every week')",
    )
    commitment_made_at = Column(DateTime(timezone=True), nullable=True)

    # Accountability partner
    accountability_partner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="Accountability partner user ID",
    )
    shared_with_partner = Column(Boolean, default=False)

    # Behavioral tracking
    current_streak = Column(Integer, nullable=False, default=0, doc="Consecutive contribution days")
    best_streak = Column(Integer, nullable=False, default=0)
    last_contribution_date = Column(Date, nullable=True)
    total_contributions = Column(Integer, nullable=False, default=0)

    # Weekly history for Polars analysis
    # [{"week": "2026-W26", "target": 500, "actual": 450}, ...]
    weekly_history = Column(JSON, nullable=True)

    # Deeper purpose (loss aversion trigger)
    deeper_purpose = Column(
        String(300), nullable=True,
        doc="Why this goal matters — triggers loss aversion",
    )
    what_i_lose = Column(
        String(300), nullable=True,
        doc="What the worker loses if they don't achieve this goal",
    )

    # Voice-created goal metadata
    voice_created = Column(Boolean, default=False)
    voice_transcript = Column(Text, nullable=True, doc="Raw voice input if voice-created")

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_goal_v2_user_status", "user_id", "status"),
        Index("idx_goal_v2_user_category", "user_id", "category"),
        Index("idx_goal_v2_created", "created_at"),
        CheckConstraint("target_amount > 0", name="ck_goal_v2_target_positive"),
        CheckConstraint("current_amount >= 0", name="ck_goal_v2_current_nonneg"),
    )


class GoalMilestone(Base):
    """
    Discrete milestone within a goal (25%, 50%, 75%, 100%).

    Each milestone is a celebration point that triggers encouragement
    and behavioral reinforcement.
    """

    __tablename__ = "goal_milestones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = Column(String(200), nullable=False, doc="Milestone title (e.g., '25% — Nusu ya kwanza')")
    title_sw = Column(String(200), nullable=True, doc="Swahili title")
    target_amount = Column(Float, nullable=False, doc="Amount threshold for this milestone")
    percentage = Column(Integer, nullable=False, doc="Percentage of total goal (25, 50, 75, 100)")

    # Completion tracking
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_amount = Column(Float, nullable=True, doc="Amount when milestone was reached")

    # Ordering
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("percentage >= 0 AND percentage <= 100", name="ck_milestone_pct_range"),
        CheckConstraint("target_amount > 0", name="ck_milestone_target_positive"),
        Index("idx_milestone_goal", "goal_id", "sort_order"),
    )


class GoalProgressEntry(Base):
    """
    Individual progress entry toward a goal.

    Supports voice-created entries and automatic M-Pesa parsing.
    Each entry triggers streak updates and milestone checks.
    """

    __tablename__ = "goal_progress_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount = Column(Float, nullable=False, doc="Contribution amount")
    notes = Column(Text, nullable=True, doc="Worker's notes about this contribution")
    entry_date = Column(
        Date, nullable=False,
        doc="Date of the contribution (may differ from created_at)",
    )

    # Source tracking
    source = Column(
        Enum("manual", "voice", "mpesa", "auto_save", name="progress_source_enum"),
        nullable=False,
        default="manual",
    )
    voice_transcript = Column(Text, nullable=True, doc="Raw voice input if applicable")

    # Context
    mood = Column(
        Enum("motivated", "neutral", "struggling", name="progress_mood_enum"),
        nullable=True,
        doc="Worker's self-reported mood at time of entry",
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_progress_goal_date", "goal_id", "entry_date"),
        Index("idx_progress_user_date", "user_id", "entry_date"),
        CheckConstraint("amount > 0", name="ck_progress_amount_positive"),
    )
