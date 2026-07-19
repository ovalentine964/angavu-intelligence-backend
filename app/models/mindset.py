"""
Mindset models — Wealth Mindset feature for Angavu Intelligence.

Dedicated model file for the mindset feature including:
- MindsetLesson — 56 voice lessons across 6 modules
- UserLessonProgress — Lesson completion tracking
- RichHabitsScore — Daily wealth-building habit scores
- Affirmation — Daily affirmations in Swahili and English
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID

from app.db.database import Base


class MindsetLesson(Base):
    """
    A single mindset lesson from the 56-lesson curriculum.

    6 modules based on: Magic of Thinking Big, Think and Grow Rich,
    Richest Man in Babylon, Atomic Habits, Psychology of Money,
    and Giving & Abundance.
    """

    __tablename__ = "mindset_lessons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_number = Column(Integer, nullable=False, doc="Module 1-6")
    lesson_number = Column(Integer, nullable=False, doc="Lesson number within module (1-based)")
    title_en = Column(String(200), nullable=False, doc="English title")
    title_sw = Column(String(200), nullable=False, doc="Swahili title")
    description = Column(Text, nullable=True)
    source_book = Column(String(200), nullable=True, doc="Source book")
    key_takeaway = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=True, doc="Estimated duration in minutes")
    difficulty = Column(
        Integer, nullable=False, default=1,
        doc="Difficulty level 1-3 (1=easy, 2=medium, 3=hard)",
    )
    audio_url = Column(String(500), nullable=True, doc="URL to audio file")
    content_text = Column(Text, nullable=True, doc="Lesson text content")
    order_index = Column(Integer, nullable=False, doc="Global ordering across all modules (1-56)")
    is_active = Column(Boolean, default=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("module_number >= 1 AND module_number <= 6", name="ck_module_range"),
        CheckConstraint("difficulty >= 1 AND difficulty <= 3", name="ck_difficulty_range"),
        UniqueConstraint("module_number", "lesson_number", name="uq_module_lesson"),
        Index("idx_lesson_order", "order_index"),
        Index("idx_lesson_module", "module_number", "lesson_number"),
        {"extend_existing": True},
    )


class UserLessonProgress(Base):
    """Tracks which lessons a user has completed with scoring."""

    __tablename__ = "user_lesson_progress"

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
    score = Column(Integer, nullable=True, doc="Comprehension score 0-100")
    notes = Column(Text, nullable=True, doc="User notes on the lesson")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson_progress"),
        Index("idx_user_progress", "user_id", "completed"),
    )


class RichHabitsScore(Base):
    """
    Daily rich habits score (0-100) tracking 10 wealth-building habits.

    Habits: record_sales, check_balance, save_money, avoid_waste,
    give, learn, set_goal, review_day, help_peer, no_debt.
    """

    __tablename__ = "rich_habits_scores"

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

    # Streak tracking
    current_streak = Column(Integer, nullable=False, default=0)
    best_streak = Column(Integer, nullable=False, default=0)

    # Level (1-5 based on cumulative performance)
    level = Column(Integer, nullable=False, default=1)

    # Milestones achieved
    milestones = Column(JSON, nullable=True, doc='e.g. ["first_1000_saved", "week_strong"]')

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "score_date", name="uq_user_score_date"),
        Index("idx_habits_user_date", "user_id", "score_date"),
        Index("idx_habits_score", "total_score"),
    )


class Affirmation(Base):
    """
    Daily affirmations sourced from wealth mindset books.

    Available in Swahili and English, categorized by theme.
    Rotated daily so users get a fresh affirmation each day.
    """

    __tablename__ = "affirmations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text_en = Column(Text, nullable=False, doc="English affirmation text")
    text_sw = Column(Text, nullable=False, doc="Swahili affirmation text")
    category = Column(
        String(50), nullable=False,
        doc="Category: belief, wealth, habits, savings, giving, compound",
    )
    source_book = Column(String(200), nullable=True, doc="Source book title")
    is_active = Column(Boolean, default=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_affirmation_category", "category"),
        Index("idx_affirmation_active", "is_active"),
    )
