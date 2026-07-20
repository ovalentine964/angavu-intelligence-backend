"""
Onboarding ORM models for database persistence.

Maps to 'autonomous_onboarding_flows' and 'autonomous_onboarding_steps' tables.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class OnboardingFlowDB(Base):
    """Persistent onboarding flow storage."""

    __tablename__ = "autonomous_onboarding_flows"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    client_id = Column(String(100), nullable=False, index=True)
    client_name = Column(String(200), nullable=False)
    product_tier = Column(String(50), nullable=True, default="standard")
    status = Column(String(20), nullable=False, default="created", index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    target_completion = Column(DateTime(timezone=True), nullable=True)
    satisfaction_score = Column(Float, nullable=True, default=0.0)
    feedback = Column(Text, nullable=True, default="")
    extra_data = Column("metadata", JSON, nullable=True, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    steps = relationship(
        "OnboardingStepDB",
        back_populates="flow",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OnboardingStepDB.order",
    )

    __table_args__ = (
        Index("ix_autonomous_onboarding_status_created", "status", "created_at"),
    )

    @property
    def progress_pct(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status == "completed")
        return round(done / len(self.steps) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "flow_id": self.id,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "product_tier": self.product_tier,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "steps": [s.to_dict() for s in (self.steps or [])],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "satisfaction_score": self.satisfaction_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OnboardingStepDB(Base):
    """Individual step in an onboarding flow."""

    __tablename__ = "autonomous_onboarding_steps"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:8])
    flow_id = Column(
        String(32),
        ForeignKey("autonomous_onboarding_flows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True, default="")
    order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    assigned_to = Column(String(100), nullable=True, default="")
    due_days = Column(Integer, nullable=True, default=3)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True, default="")
    extra_data = Column("metadata", JSON, nullable=True, default=dict)

    flow = relationship("OnboardingFlowDB", back_populates="steps")

    def to_dict(self) -> dict:
        return {
            "step_id": self.id,
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "due_days": self.due_days,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
