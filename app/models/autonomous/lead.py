"""
Lead models for autonomous revenue operations.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class LeadDB(Base):
    """Sales lead tracked by autonomous operations."""
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    company = Column(String(200), nullable=True)
    status = Column(String(20), default="new")  # new, contacted, qualified, proposal, won, lost
    source = Column(String(50), nullable=True)  # referral, website, cold_outreach, etc.
    score = Column(Float, default=0.0)  # Lead score 0-100
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
