"""
Lead ORM model for database persistence.

Maps to the 'autonomous_leads' table. Stores lead qualification
data, scores, and lifecycle state.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    String,
    Text,
)

from app.db.database import Base


class LeadDB(Base):
    """Persistent lead storage."""

    __tablename__ = "autonomous_leads"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    company_name = Column(String(200), nullable=False, index=True)
    contact_name = Column(String(200), nullable=True, default="")
    contact_email = Column(String(254), nullable=True, default="")
    contact_phone = Column(String(20), nullable=True, default="")
    industry = Column(String(100), nullable=True, default="other", index=True)
    company_size = Column(String(20), nullable=True, default="1-10")
    estimated_budget = Column(Float, nullable=True, default=0.0)
    source = Column(String(50), nullable=True, default="other")
    status = Column(String(30), nullable=False, default="new", index=True)

    # Scoring dimensions (0-100 each)
    score_company_size = Column(Float, nullable=True, default=0.0)
    score_industry_fit = Column(Float, nullable=True, default=0.0)
    score_budget_signal = Column(Float, nullable=True, default=0.0)
    score_timing = Column(Float, nullable=True, default=0.0)
    score_engagement = Column(Float, nullable=True, default=0.0)
    score_composite = Column(Float, nullable=True, default=0.0, index=True)

    notes = Column(Text, nullable=True, default="")
    tags = Column(JSON, nullable=True, default=list)
    assigned_to = Column(String(100), nullable=True, default="")
    extra_data = Column("metadata", JSON, nullable=True, default=dict)

    qualified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_autonomous_leads_status_composite", "status", "score_composite"),
    )

    def to_dict(self) -> dict:
        return {
            "lead_id": self.id,
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "industry": self.industry,
            "company_size": self.company_size,
            "estimated_budget": self.estimated_budget,
            "source": self.source,
            "status": self.status,
            "score": {
                "company_size": self.score_company_size,
                "industry_fit": self.score_industry_fit,
                "budget_signal": self.score_budget_signal,
                "timing": self.score_timing,
                "engagement": self.score_engagement,
                "composite": self.score_composite,
            },
            "tags": self.tags or [],
            "assigned_to": self.assigned_to,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
