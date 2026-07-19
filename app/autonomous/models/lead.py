"""
Lead models for the qualification pipeline.

Leads flow through:
    New → Qualifying → Qualified/Rejected/Escalated

Scoring factors:
    - Company size (employee count or revenue band)
    - Industry fit (alignment with Angavu's target markets)
    - Budget signal (explicit or inferred budget range)
    - Timing (urgency, fiscal year alignment, buying cycle)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class LeadStatus(str, Enum):
    """Lead lifecycle states."""
    NEW = "new"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    REJECTED = "rejected"
    ESCALATED = "escalated"       # High-value → sent to Valentine
    CONTACTED = "contacted"
    CONVERTED = "converted"
    LOST = "lost"


class LeadSource(str, Enum):
    """Where the lead came from."""
    WEBSITE = "website"
    REFERRAL = "referral"
    COLD_OUTREACH = "cold_outreach"
    EVENT = "event"
    PARTNER = "partner"
    INBOUND_CALL = "inbound_call"
    SOCIAL_MEDIA = "social_media"
    WHATSAPP = "whatsapp"
    OTHER = "other"


@dataclass
class LeadScore:
    """
    Multi-dimensional lead score.

    Each dimension is 0-100. The composite score is a weighted average.
    """
    company_size: float = 0.0      # 0-100: larger = higher score
    industry_fit: float = 0.0      # 0-100: better fit = higher score
    budget_signal: float = 0.0     # 0-100: clearer budget = higher score
    timing: float = 0.0            # 0-100: sooner = higher score
    engagement: float = 0.0        # 0-100: more engaged = higher score
    composite: float = 0.0         # Weighted average

    # Weights for composite calculation
    WEIGHTS = {
        "company_size": 0.25,
        "industry_fit": 0.25,
        "budget_signal": 0.20,
        "timing": 0.15,
        "engagement": 0.15,
    }

    def calculate_composite(self) -> float:
        """Calculate weighted composite score."""
        self.composite = (
            self.company_size * self.WEIGHTS["company_size"]
            + self.industry_fit * self.WEIGHTS["industry_fit"]
            + self.budget_signal * self.WEIGHTS["budget_signal"]
            + self.timing * self.WEIGHTS["timing"]
            + self.engagement * self.WEIGHTS["engagement"]
        )
        return self.composite

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_size": round(self.company_size, 1),
            "industry_fit": round(self.industry_fit, 1),
            "budget_signal": round(self.budget_signal, 1),
            "timing": round(self.timing, 1),
            "engagement": round(self.engagement, 1),
            "composite": round(self.composite, 1),
        }


@dataclass
class Lead:
    """
    A sales lead in the Angavu Intelligence pipeline.

    Attributes:
        lead_id: Unique identifier
        company_name: Name of the prospect company
        contact_name: Primary contact person
        contact_email: Contact email
        contact_phone: Contact phone
        industry: Prospect's industry
        company_size: Employee count or size band
        estimated_budget: Budget signal (monthly KES)
        source: How they found us
        status: Current lifecycle state
        score: Multi-dimensional scoring
        notes: Free-text notes
        tags: Categorization tags
        assigned_to: Who is handling this lead
        created_at: When the lead entered the system
        updated_at: Last status change
        qualified_at: When qualification completed
        metadata: Arbitrary extra data
    """
    lead_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    company_name: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    industry: str = ""
    company_size: str = ""          # "1-10", "11-50", "51-200", "200+"
    estimated_budget: float = 0.0   # Monthly KES
    source: LeadSource = LeadSource.OTHER
    status: LeadStatus = LeadStatus.NEW
    score: LeadScore = field(default_factory=LeadScore)
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    assigned_to: str = ""           # "valentine" for escalated leads
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    qualified_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "industry": self.industry,
            "company_size": self.company_size,
            "estimated_budget": self.estimated_budget,
            "source": self.source.value,
            "status": self.status.value,
            "score": self.score.to_dict(),
            "tags": self.tags,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lead:
        """Reconstruct a Lead from a dictionary."""
        score_data = data.get("score", {})
        score = LeadScore(
            company_size=score_data.get("company_size", 0),
            industry_fit=score_data.get("industry_fit", 0),
            budget_signal=score_data.get("budget_signal", 0),
            timing=score_data.get("timing", 0),
            engagement=score_data.get("engagement", 0),
            composite=score_data.get("composite", 0),
        )
        return cls(
            lead_id=data.get("lead_id", uuid.uuid4().hex[:12]),
            company_name=data.get("company_name", ""),
            contact_name=data.get("contact_name", ""),
            contact_email=data.get("contact_email", ""),
            contact_phone=data.get("contact_phone", ""),
            industry=data.get("industry", ""),
            company_size=data.get("company_size", ""),
            estimated_budget=data.get("estimated_budget", 0.0),
            source=LeadSource(data.get("source", "other")),
            status=LeadStatus(data.get("status", "new")),
            score=score,
            notes=data.get("notes", ""),
            tags=data.get("tags", []),
            assigned_to=data.get("assigned_to", ""),
            metadata=data.get("metadata", {}),
        )
