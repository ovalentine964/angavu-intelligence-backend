"""
Onboarding flow models for autonomous user onboarding.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class OnboardingFlowDB(Base):
    """Onboarding flow definition."""
    __tablename__ = "onboarding_flows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    flow_type = Column(String(50), nullable=False)  # worker, business, enterprise
    status = Column(String(20), default="active")  # active, completed, abandoned
    current_step = Column(Integer, default=1)
    total_steps = Column(Integer, default=5)
    completion_pct = Column(Float, default=0.0)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class OnboardingStepDB(Base):
    """Individual step in an onboarding flow."""
    __tablename__ = "onboarding_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flow_id = Column(UUID(as_uuid=True), ForeignKey("onboarding_flows.id"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    step_type = Column(String(50), nullable=False)  # profile, verification, tutorial, etc.
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, in_progress, completed, skipped
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
