"""
Worker feature models — Tithe, Goals, Loans, Mindset.

Supports Msaidizi's core worker-facing features:
1. TitheRecord — Giving/tithe tracking with consistency scoring
2. GoalRecord — Goal planning with milestones and streaks
3. LoanRecord — Loan management with ROI and repayment tracking
4. MindsetLesson — 56 voice lessons across 6 modules
5. RichHabitScore — Daily wealth-building habit scores
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


# =========================================================================
# 1. TitheRecord — Giving & Tithe Tracking
# =========================================================================


class TitheRecord(Base):
    """
    Individual giving record — tithe, offering, zakat, harambee, charity.

    Tracks giving for consistency scoring, abundance pattern analysis,
    and monthly/annual reporting. Data is confession-level sensitive.
    """

    __tablename__ = "tithe_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Float, nullable=False, doc="Giving amount in local currency")
    currency = Column(
        String(3), nullable=False, default="KES",
        doc="ISO currency code (KES, UGX, TZS, NGN)",
    )
    category = Column(
        Enum(
            "tithe", "offering", "zakat", "harambee", "charity",
            "building_fund", "missions", "custom",
            name="giving_category_enum",
        ),
        nullable=False,
        default="offering",
        doc="Giving category",
    )
    custom_category_name = Column(
        String(100), nullable=True,
        doc="Custom category label when category=custom",
    )
    recipient = Column(
        String(200), nullable=True,
        doc="Church, mosque, person, or community name",
    )
    giving_date = Column(
        Date, nullable=False,
        doc="Date the giving occurred",
    )
    input_method = Column(
        Enum("voice", "manual", "mpesa_parse", name="giving_input_method_enum"),
        nullable=False,
        default="manual",
    )
    voice_transcript = Column(Text, nullable=True, doc="Raw voice input if applicable")
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_tithe_user_date", "user_id", "giving_date"),
        Index("idx_tithe_user_category", "user_id", "category"),
        Index("idx_tithe_created", "created_at"),
    )


# =========================================================================
# 2. GoalRecord — Goal Planning & Tracking
# =========================================================================


class GoalRecord(Base):
    """
    A worker's financial goal with milestones, streaks, and progress.

    Supports categories: business, personal, savings, debt.
    One primary goal + up to 2 queued goals per user.
    """

    __tablename__ = "goal_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal_type = Column(
        Enum("business", "personal", "savings", "debt", name="goal_type_enum"),
        nullable=False,
    )
    title = Column(String(200), nullable=False, doc="Goal title (e.g., 'Kununua friji')")
    title_sw = Column(String(200), nullable=True, doc="Swahili title")
    description = Column(Text, nullable=True)
    target_amount = Column(Float, nullable=False, doc="Target amount in KES")
    current_amount = Column(
        Float, nullable=False, default=0,
        doc="Amount saved/applied so far",
    )
    currency = Column(String(3), nullable=False, default="KES")

    # Timeline
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deadline = Column(Date, nullable=True, doc="Target completion date")
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Status and priority
    status = Column(
        Enum("active", "paused", "completed", "abandoned", name="goal_status_enum"),
        nullable=False,
        default="active",
        index=True,
    )
    priority = Column(
        Enum("primary", "queued", "completed", name="goal_priority_enum"),
        nullable=False,
        default="primary",
    )

    # Milestones stored as JSON array
    # [{"pct": 25, "amount": 3750, "reached": true, "date": "2026-09-15"}, ...]
    milestones = Column(JSON, nullable=True, doc="25/50/75/100% milestone tracking")

    # Weekly/daily targets
    weekly_target = Column(Float, nullable=True, doc="Recommended weekly savings")
    daily_target = Column(Float, nullable=True, doc="Recommended daily savings")

    # Streak tracking
    current_streak = Column(Integer, nullable=False, default=0, doc="Consecutive save days")
    best_streak = Column(Integer, nullable=False, default=0, doc="Best-ever streak")
    last_save_date = Column(Date, nullable=True)

    # Deeper purpose
    deeper_purpose = Column(
        String(300), nullable=True,
        doc="Why this goal matters (e.g., 'Kusomesha watoto wangu')",
    )

    # Auto-save settings
    auto_save_enabled = Column(Boolean, default=False)
    auto_save_percentage = Column(Float, nullable=True, doc="% of transactions to auto-save")
    auto_save_min_transaction = Column(Float, nullable=True, doc="Min txn amount to trigger")
    auto_save_cap = Column(Float, nullable=True, doc="Max auto-save per transaction")

    # Weekly history
    # [{"week": "2026-W26", "target": 375, "actual": 400}, ...]
    weekly_history = Column(JSON, nullable=True)

    # Sharing
    is_public = Column(Boolean, default=False, doc="Whether goal is shared with accountability partner")

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_goal_user_status", "user_id", "status"),
        Index("idx_goal_user_priority", "user_id", "priority"),
        Index("idx_goal_created", "created_at"),
    )


class GoalContribution(Base):
    """Individual contribution toward a goal."""

    __tablename__ = "goal_contributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("goal_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Float, nullable=False)
    source = Column(
        Enum("manual", "auto_save", "mpesa", name="contribution_source_enum"),
        nullable=False,
        default="manual",
    )
    recorded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_contrib_goal_date", "goal_id", "recorded_at"),
    )


# =========================================================================
# 3. LoanRecord — Loan Management
# =========================================================================


class LoanRecord(Base):
    """
    Loan record with purpose verification, ROI tracking, and repayment.

    Supports loans from any source (M-Shwari, KCB, chama, manual).
    Integrates with Alama Score for creditworthiness updates.
    """

    __tablename__ = "loan_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Loan details
    source = Column(
        Enum(
            "msaidizi", "mshwari", "kcb_mpesa", "chama", "bank", "mfi", "manual",
            name="loan_source_enum",
        ),
        nullable=False,
        default="manual",
    )
    principal = Column(Float, nullable=False, doc="Loan principal in KES")
    interest_rate = Column(
        Float, nullable=False, default=0,
        doc="Interest rate as decimal (e.g., 0.15 = 15%)",
    )
    total_due = Column(Float, nullable=False, doc="Principal + interest")
    amount_repaid = Column(Float, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="KES")

    # Purpose
    purpose = Column(
        Enum(
            "stock", "equipment", "emergency", "education",
            "improvement", "other",
            name="loan_purpose_enum",
        ),
        nullable=False,
    )
    purpose_details = Column(
        JSON, nullable=True,
        doc='{"items": "nguo za watoto", "expected_roi": 1.5, "timeline_days": 30}',
    )

    # Status
    status = Column(
        Enum(
            "active", "completed", "defaulted", "restructured",
            name="loan_status_enum",
        ),
        nullable=False,
        default="active",
        index=True,
    )

    # Timeline
    disbursed_at = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(Date, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ROI tracking
    sales_attributed = Column(
        Float, nullable=True, default=0,
        doc="Total sales attributed to this loan",
    )
    last_roi_check = Column(DateTime(timezone=True), nullable=True)

    # Repayment plan
    repayment_type = Column(
        Enum("fixed", "flexible", "earnings_linked", name="repayment_type_enum"),
        nullable=False,
        default="flexible",
    )
    repayment_frequency = Column(
        Enum("daily", "weekly", "biweekly", "monthly", name="repayment_freq_enum"),
        nullable=True,
        default="weekly",
    )
    repayment_amount_per_period = Column(Float, nullable=True)

    # Commitment
    commitment_made = Column(Boolean, default=False)
    commitment_text = Column(Text, nullable=True, doc="e.g., 'KSh 500 kila Jumatatu na Alhamisi'")

    # Streak
    current_repayment_streak = Column(Integer, default=0)
    best_repayment_streak = Column(Integer, default=0)

    # Alama Score impact
    alama_score_at_start = Column(Integer, nullable=True)
    alama_score_impact = Column(Integer, nullable=True, doc="Points gained/lost")

    # Default risk
    default_probability = Column(Float, nullable=True, doc="Predicted PD 0-1")
    risk_level = Column(
        Enum("low", "medium", "high", "critical", name="loan_risk_enum"),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_loan_user_status", "user_id", "status"),
        Index("idx_loan_due", "due_date"),
        Index("idx_loan_created", "created_at"),
    )


class LoanRepayment(Base):
    """Individual repayment transaction toward a loan."""

    __tablename__ = "loan_repayments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("loan_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Float, nullable=False)
    method = Column(
        Enum("auto_set_aside", "manual", "mpesa", "cash", name="repayment_method_enum"),
        nullable=False,
        default="manual",
    )
    streak_day = Column(Integer, nullable=True, doc="Streak count at time of repayment")
    suggested = Column(Boolean, default=False, doc="Was this a system-suggested repayment?")
    accepted = Column(Boolean, nullable=True, doc="Did user accept the suggestion?")
    recorded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_repay_loan_date", "loan_id", "recorded_at"),
    )


class LoanROICheckin(Base):
    """Periodic ROI check-in for a loan."""

    __tablename__ = "loan_roi_checkins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("loan_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sales_attributed = Column(Float, nullable=False, default=0)
    checkin_date = Column(Date, nullable=False)
    checkin_type = Column(
        Enum("auto", "manual", "voice", name="roi_checkin_type_enum"),
        nullable=False,
        default="manual",
    )
    notes = Column(Text, nullable=True)
    recorded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# =========================================================================
# 4. MindsetLesson — Voice Lesson Content & Delivery
# =========================================================================


class MindsetLesson(Base):
    """
    A single mindset lesson from the 56-lesson curriculum.

    6 modules based on: Magic of Thinking Big, Think and Grow Rich,
    Richest Man in Babylon, Atomic Habits, Psychology of Money,
    and Giving & Abundance.
    """

    __tablename__ = "mindset_lessons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_number = Column(
        Integer, nullable=False,
        doc="Module 1-6",
    )
    lesson_number = Column(
        Integer, nullable=False,
        doc="Lesson number within module (1-based)",
    )
    title_en = Column(String(200), nullable=False, doc="English title")
    title_sw = Column(String(200), nullable=False, doc="Swahili title")
    description = Column(Text, nullable=True)
    source_book = Column(
        String(200), nullable=True,
        doc="Source book (e.g., 'The Magic of Thinking Big')",
    )
    key_takeaway = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=True, doc="Estimated duration in minutes")
    audio_url = Column(String(500), nullable=True, doc="URL to audio file")
    content_text = Column(Text, nullable=True, doc="Lesson text content")
    order_index = Column(
        Integer, nullable=False,
        doc="Global ordering across all modules (1-56)",
    )

    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("module_number >= 1 AND module_number <= 6", name="ck_module_range"),
        UniqueConstraint("module_number", "lesson_number", name="uq_module_lesson"),
        Index("idx_lesson_order", "order_index"),
        Index("idx_lesson_module", "module_number", "lesson_number"),
    )


class MindsetLessonProgress(Base):
    """Tracks which lessons a user has completed."""

    __tablename__ = "mindset_lesson_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mindset_lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_listened_at = Column(DateTime(timezone=True), nullable=True)
    listen_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson"),
        Index("idx_progress_user", "user_id", "completed"),
    )


# =========================================================================
# 5. RichHabitScore — Daily Wealth-Building Habits
# =========================================================================


class RichHabitScore(Base):
    """
    Daily rich habits score (0-100) tracking 10 wealth-building habits.

    Habits: record_sales, check_balance, save_money, avoid_waste,
    give, learn, set_goal, review_day, help_peer, no_debt.
    """

    __tablename__ = "rich_habit_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score_date = Column(Date, nullable=False, doc="Date of the score")

    # Individual habit flags
    record_sales = Column(Boolean, default=False)
    check_balance = Column(Boolean, default=False)
    save_money = Column(Boolean, default=False)
    avoid_waste = Column(Boolean, default=False)
    give = Column(Boolean, default=False)
    learn = Column(Boolean, default=False)
    set_goal = Column(Boolean, default=False)
    review_day = Column(Boolean, default=False)
    help_peer = Column(Boolean, default=False)
    no_debt = Column(Boolean, default=False)

    # Computed score
    total_score = Column(Integer, nullable=False, default=0, doc="0-100")

    # Streak
    current_streak = Column(Integer, nullable=False, default=0)
    best_streak = Column(Integer, nullable=False, default=0)

    # Level (1-5 based on cumulative performance)
    level = Column(Integer, nullable=False, default=1)

    # Milestones achieved
    # ["first_1000_saved", "week_strong", ...]
    milestones = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "score_date", name="uq_user_score_date"),
        Index("idx_habit_user_date", "user_id", "score_date"),
        Index("idx_habit_score", "total_score"),
    )
