"""
Refresh Token model for token family tracking.

Implements refresh token rotation: each refresh token belongs to a
"family" (identified by a family_id). When a refresh token is used,
it is marked as used and a new one is issued in the same family.

If a previously-used token in the same family is presented again
(replay attack), ALL tokens in that family are revoked — this
detects token theft.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class RefreshToken(Base):
    """
    Tracks refresh tokens for token rotation and theft detection.

    Each refresh token has:
    - family_id: groups tokens from the same initial login
    - jti: unique token ID (from JWT 'jti' claim)
    - used: whether this token has been consumed
    - revoked: whether this token (or its family) has been revoked
    """

    __tablename__ = "refresh_tokens"

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
    family_id = Column(
        String(32),
        nullable=False,
        index=True,
        doc="Token family ID — groups tokens from the same login session",
    )
    jti = Column(
        String(32),
        unique=True,
        nullable=False,
        doc="Unique JWT ID for this specific refresh token",
    )
    used = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether this token has been consumed (one-time use)",
    )
    revoked = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether this token or its family has been revoked",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    used_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When this token was consumed",
    )

    __table_args__ = (
        Index("idx_refresh_token_family", "family_id", "revoked"),
        Index("idx_refresh_token_user_active", "user_id", "revoked"),
    )

    def __repr__(self) -> str:
        return f"<RefreshToken jti={self.jti[:8]}... family={self.family_id[:8]}... used={self.used}>"
