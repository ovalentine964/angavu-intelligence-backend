"""
Customer onboarding models.

Onboarding lifecycle:
    Created → In Progress → Completed / Stalled

Each onboarding flow has steps that track the customer's
progress from signed contract to fully operational.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class OnboardingStatus(str, Enum):
    """Onboarding lifecycle states."""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    STALLED = "stalled"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Individual step states."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass
class OnboardingStep:
    """
    A single step in the onboarding flow.

    Steps are templates that get instantiated per customer.
    """
    step_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    description: str = ""
    order: int = 0
    status: StepStatus = StepStatus.PENDING
    assigned_to: str = ""           # team member or "auto"
    due_days: int = 3               # days after onboarding start
    completed_at: Optional[datetime] = None
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
            "due_days": self.due_days,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "notes": self.notes,
        }


@dataclass
class OnboardingFlow:
    """
    A customer onboarding flow.

    Auto-generated based on the client's contract and product tier.
    Tracks progress through a series of steps from contract signing
    to full operational status.

    Attributes:
        flow_id: Unique identifier
        client_id: Client (lead_id or user_id)
        client_name: Client company name
        product_tier: Which Angavu product they purchased
        status: Overall onboarding status
        steps: Ordered list of onboarding steps
        started_at: When onboarding began
        completed_at: When all steps were done
        target_completion: Expected completion date
        satisfaction_score: Post-onboarding CSAT (1-5)
        feedback: Client feedback text
        metadata: Arbitrary extra data
    """
    flow_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    client_id: str = ""
    client_name: str = ""
    product_tier: str = "standard"  # standard | professional | enterprise
    status: OnboardingStatus = OnboardingStatus.CREATED
    steps: List[OnboardingStep] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    target_completion: Optional[datetime] = None
    satisfaction_score: float = 0.0
    feedback: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def progress_pct(self) -> float:
        """Calculate completion percentage."""
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return round(done / len(self.steps) * 100, 1)

    @property
    def current_step(self) -> Optional[OnboardingStep]:
        """Get the first incomplete step."""
        for step in sorted(self.steps, key=lambda s: s.order):
            if step.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS):
                return step
        return None

    @property
    def is_stalled(self) -> bool:
        """Check if onboarding is stalled (no progress in 7+ days)."""
        if self.status in (OnboardingStatus.COMPLETED, OnboardingStatus.CANCELLED):
            return False
        completed_steps = [s for s in self.steps if s.completed_at]
        if not completed_steps:
            # No steps completed yet — check if started > 7 days ago
            if self.started_at:
                return (datetime.now(timezone.utc) - self.started_at).days > 7
            return False
        last_activity = max(s.completed_at for s in completed_steps)
        return (datetime.now(timezone.utc) - last_activity).days > 7

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "product_tier": self.product_tier,
            "status": self.status.value,
            "progress_pct": self.progress_pct,
            "steps": [s.to_dict() for s in self.steps],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "satisfaction_score": self.satisfaction_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OnboardingFlow:
        """Reconstruct from dictionary."""
        steps = [
            OnboardingStep(
                step_id=s.get("step_id", ""),
                name=s.get("name", ""),
                description=s.get("description", ""),
                order=s.get("order", 0),
                status=StepStatus(s.get("status", "pending")),
                assigned_to=s.get("assigned_to", ""),
                due_days=s.get("due_days", 3),
                notes=s.get("notes", ""),
            )
            for s in data.get("steps", [])
        ]
        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(data["started_at"])
        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"])
        return cls(
            flow_id=data.get("flow_id", uuid.uuid4().hex[:12]),
            client_id=data.get("client_id", ""),
            client_name=data.get("client_name", ""),
            product_tier=data.get("product_tier", "standard"),
            status=OnboardingStatus(data.get("status", "created")),
            steps=steps,
            started_at=started_at,
            completed_at=completed_at,
            satisfaction_score=data.get("satisfaction_score", 0.0),
            feedback=data.get("feedback", ""),
            metadata=data.get("metadata", {}),
        )


def create_default_onboarding_steps(product_tier: str = "standard") -> List[OnboardingStep]:
    """
    Generate default onboarding steps based on product tier.

    Enterprise gets more steps (dedicated integration, custom training).
    Standard gets a streamlined flow.
    """
    base_steps = [
        OnboardingStep(name="Welcome Email", description="Send welcome email with getting-started guide", order=1, due_days=0, assigned_to="auto"),
        OnboardingStep(name="Account Setup", description="Create client account and configure access", order=2, due_days=1, assigned_to="auto"),
        OnboardingStep(name="Data Integration", description="Connect client data sources (M-Pesa, POS, etc.)", order=3, due_days=3, assigned_to="tech_team"),
        OnboardingStep(name="Initial Training", description="Product walkthrough and key features demo", order=4, due_days=5, assigned_to="success_team"),
        OnboardingStep(name="First Report Delivery", description="Deliver first intelligence report", order=5, due_days=7, assigned_to="auto"),
        OnboardingStep(name="30-Day Check-in", description="Follow up on satisfaction and gather feedback", order=6, due_days=30, assigned_to="success_team"),
    ]

    if product_tier == "enterprise":
        enterprise_steps = [
            OnboardingStep(name="Dedicated Account Manager", description="Assign dedicated AM and schedule kickoff", order=2, due_days=1, assigned_to="success_team"),
            OnboardingStep(name="Custom Integration Planning", description="Plan custom API integrations and data pipelines", order=4, due_days=5, assigned_to="tech_team"),
            OnboardingStep(name="Custom Dashboard Setup", description="Build custom analytics dashboard", order=6, due_days=10, assigned_to="tech_team"),
            OnboardingStep(name="Executive Review", description="Present initial findings to client leadership", order=8, due_days=14, assigned_to="success_team"),
        ]
        # Merge: interleave enterprise steps with base
        base_steps = base_steps[:2] + enterprise_steps[:1] + base_steps[2:4] + enterprise_steps[1:3] + base_steps[4:] + enterprise_steps[3:]
        # Re-order
        for i, step in enumerate(base_steps):
            step.order = i + 1

    elif product_tier == "professional":
        pro_steps = [
            OnboardingStep(name="Advanced Configuration", description="Configure advanced analytics and alerts", order=4, due_days=5, assigned_to="tech_team"),
            OnboardingStep(name="Custom Report Templates", description="Set up custom report templates", order=6, due_days=8, assigned_to="auto"),
        ]
        base_steps = base_steps[:4] + pro_steps + base_steps[4:]
        for i, step in enumerate(base_steps):
            step.order = i + 1

    return base_steps
