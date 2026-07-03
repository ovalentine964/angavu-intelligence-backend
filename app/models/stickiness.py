"""
Stickiness / Engagement Models — Gamification and habit tracking.

Supports the Hook Model: Trigger → Action → Variable Reward → Investment.
Anti-shame design: no public leaderboards, all comparisons are anonymized.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class UserEngagement(Base):
    """
    Daily engagement tracking per user.

    Updated on every meaningful action (login, transaction, insight view).
    Used to compute DAU, MAU, D1/D7/D30 retention, and streaks.
    """

    __tablename__ = "user_engagement"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Calendar date (UTC midnight) this record covers",
    )
    daily_active = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether user was active on this date",
    )
    actions_count = Column(
        Integer,
        default=0,
        nullable=False,
        doc="Number of meaningful actions on this date",
    )
    xp_earned = Column(
        Integer,
        default=0,
        nullable=False,
        doc="XP earned on this date",
    )
    aha_moments_hit = Column(
        JSONB,
        nullable=True,
        doc="Aha moments triggered on this date (list of moment names)",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        # One record per user per day
        {"comment": "Daily engagement tracking for retention metrics"},
    )


class Badge(Base):
    """
    Badge definition — static reference data.

    All 18 badges are pre-seeded. Each has a Swahili name, English
    description, and unlock criteria.
    """

    __tablename__ = "badges"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        doc="Badge slug (e.g. 'kwanza_sale')",
    )
    swahili_name = Column(
        String(200),
        nullable=False,
        doc="Badge name in Swahili",
    )
    description = Column(
        Text,
        nullable=False,
        doc="Badge description in English",
    )
    description_sw = Column(
        Text,
        nullable=True,
        doc="Badge description in Swahili",
    )
    icon = Column(
        String(10),
        nullable=False,
        doc="Emoji icon for the badge",
    )
    category = Column(
        String(50),
        nullable=False,
        index=True,
        doc="Badge category (onboarding, consistency, growth, intelligence, financial, social, loyalty)",
    )
    criteria = Column(
        JSONB,
        nullable=False,
        doc="Unlock criteria as JSON (e.g. {'type': 'streak', 'days': 7})",
    )
    xp_reward = Column(
        Integer,
        default=0,
        nullable=False,
        doc="XP awarded when badge is earned",
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        doc="Whether this badge is currently available",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user_badges = relationship("UserBadge", back_populates="badge", lazy="dynamic")


class UserBadge(Base):
    """
    Tracks which badges a user has earned.

    One row per user-badge combination. Earned badges are never removed
    (anti-shame: badges can't be lost).
    """

    __tablename__ = "user_badges"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    badge_id = Column(
        UUID(as_uuid=True),
        ForeignKey("badges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    earned_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    notified = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether the user has been notified of earning this badge",
    )

    # Relationships
    badge = relationship("Badge", back_populates="user_badges")

    __table_args__ = (
        # One earn per badge per user
        {"comment": "Tracks earned badges per user"},
    )


class UserLevel(Base):
    """
    User's gamification level and XP.

    Levels: Mwanafunzi (1) → Mfanyakazi (2) → Mjasiriamali (3) →
            Bingwa (4) → Mzee (5) → Legend (6)
    """

    __tablename__ = "user_levels"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    level = Column(
        Integer,
        default=1,
        nullable=False,
        doc="Current level (1-6)",
    )
    xp = Column(
        Integer,
        default=0,
        nullable=False,
        doc="Total XP accumulated",
    )
    xp_to_next = Column(
        Integer,
        nullable=True,
        doc="XP needed to reach next level (null at max level)",
    )
    last_reward_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Last time a variable reward was granted",
    )
    streak_protection_count = Column(
        Integer,
        default=0,
        nullable=False,
        doc="Number of streak shields available",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        {"comment": "User gamification level and XP tracking"},
    )


class Streak(Base):
    """
    User activity streak tracking with forgiveness mechanics.

    Streak protection (shields) allow missing a day without losing the streak.
    Users earn shields at certain levels.
    """

    __tablename__ = "streaks"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    current_streak = Column(
        Integer,
        default=0,
        nullable=False,
        doc="Current consecutive active days",
    )
    longest_streak = Column(
        Integer,
        default=0,
        nullable=False,
        doc="All-time longest streak",
    )
    protection_count = Column(
        Integer,
        default=0,
        nullable=False,
        doc="Number of streak shields available",
    )
    last_active_date = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Date of last recorded activity",
    )
    protection_used_today = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether a protection was used today (prevents double-use)",
    )
    freeze_count = Column(
        Integer,
        default=0,
        nullable=False,
        doc="Total times streak was saved by protection",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        {"comment": "User activity streak with forgiveness mechanics"},
    )
