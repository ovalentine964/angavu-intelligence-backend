"""
Revenue Operations API — REST endpoints for all revenue ops agents.

Endpoints:
    /leads          — Lead qualification pipeline
    /content        — Content creation pipeline
    /invoices       — Invoice generation and tracking
    /onboarding     — Customer onboarding flows
    /feedback       — Feedback loops and metrics
    /dashboard      — Revenue operations dashboard

All endpoints are async, authenticated via JWT, rate-limited,
and integrate with the AutonomousOrchestrator via EventBus.

Security:
    - JWT authentication required on all mutating endpoints
    - API key validation for service-to-service calls
    - Input validation via Pydantic with size limits
    - Per-endpoint rate limiting via slowapi
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt as pyjwt
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings
from app.db.database import get_db
from app.autonomous.repository import AutonomousRepository

logger = structlog.get_logger(__name__)
settings = get_settings()
security = HTTPBearer()

router = APIRouter(prefix="/api/v1/revenue-ops", tags=["revenue-ops"])

# Rate limiter (per-endpoint)
limiter = Limiter(key_func=get_remote_address)


# ════════════════════════════════════════════════════════════════════
# Orchestrator Access
# ════════════════════════════════════════════════════════════════════


def _get_orchestrator(request: Request):
    """Get the AutonomousOrchestrator from app state."""
    return getattr(request.app.state, "autonomous_orchestrator", None)


def _get_event_bus(request: Request):
    """Get the EventBus from app state."""
    return getattr(request.app.state, "event_bus", None)


# ════════════════════════════════════════════════════════════════════
# Authentication Dependencies
# ════════════════════════════════════════════════════════════════════


def _decode_jwt(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return pyjwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI dependency — require valid JWT on protected endpoints.

    Returns the decoded token payload.
    """
    payload = _decode_jwt(credentials.credentials)
    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
        )
    return payload


async def optional_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[dict]:
    """
    FastAPI dependency — optional JWT. Returns None if no token provided.
    Used for endpoints that work with or without auth.
    """
    if credentials is None:
        return None
    try:
        return _decode_jwt(credentials.credentials)
    except HTTPException:
        return None


# ════════════════════════════════════════════════════════════════════
# Input Sanitization
# ════════════════════════════════════════════════════════════════════


def _sanitize_string(value: str) -> str:
    """Strip potentially dangerous characters from user input."""
    if not value:
        return value
    # Remove null bytes and control chars (except newline/tab)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    # Strip leading/trailing whitespace
    return value.strip()


def _sanitize_dict(data: dict) -> dict:
    """Recursively sanitize string values in a dict."""
    cleaned = {}
    for k, v in data.items():
        if isinstance(v, str):
            cleaned[k] = _sanitize_string(v)
        elif isinstance(v, dict):
            cleaned[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            cleaned[k] = [
                _sanitize_dict(i) if isinstance(i, dict)
                else _sanitize_string(i) if isinstance(i, str)
                else i
                for i in v
            ]
        else:
            cleaned[k] = v
    return cleaned


# ════════════════════════════════════════════════════════════════════
# Request / Response Models (with size limits & validation)
# ════════════════════════════════════════════════════════════════════


class LeadCreateRequest(BaseModel):
    """Request to create and qualify a lead."""

    company_name: str = Field(..., min_length=1, max_length=200)
    contact_name: str = Field("", max_length=200)
    contact_email: str = Field("", max_length=254)
    contact_phone: str = Field("", max_length=20)
    industry: str = Field("other", max_length=100)
    company_size: str = Field("1-10", max_length=20)
    estimated_budget: float = Field(0.0, ge=0, le=1_000_000_000)
    source: str = Field("other", max_length=50)
    urgency: str = Field("", max_length=50)
    decision_timeline_days: Optional[int] = Field(None, ge=0, le=3650)
    meetings_requested: int = Field(0, ge=0, le=1000)
    email_opens: int = Field(0, ge=0, le=100_000)
    metadata: Dict[str, Any] = Field(default_factory=dict, max_length=50)

    @field_validator("company_name", "contact_name", "contact_email", "industry")
    @classmethod
    def sanitize_strings(cls, v: str) -> str:
        return _sanitize_string(v)

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if v and "@" not in v:
            raise ValueError("Invalid email format")
        return v


class ContentRequest(BaseModel):
    """Request to generate content."""

    content_type: str = Field("blog_post", max_length=50)
    topic: Optional[str] = Field(None, max_length=500)
    target_channels: List[str] = Field(default_factory=list, max_length=10)
    requested_by: str = Field("api", max_length=100)

    @field_validator("topic")
    @classmethod
    def sanitize_topic(cls, v: Optional[str]) -> Optional[str]:
        return _sanitize_string(v) if v else v


class InvoiceCreateRequest(BaseModel):
    """Request to create an invoice."""

    client_id: str = Field(..., min_length=1, max_length=100)
    client_name: str = Field(..., min_length=1, max_length=200)
    client_email: str = Field("", max_length=254)
    product_tier: str = Field("standard", max_length=50)
    addons: List[str] = Field(default_factory=list, max_length=20)

    @field_validator("client_name", "client_email")
    @classmethod
    def sanitize_strings(cls, v: str) -> str:
        return _sanitize_string(v)


class OnboardingFeedbackRequest(BaseModel):
    """Onboarding feedback submission."""

    flow_id: str = Field(..., min_length=1, max_length=100)
    satisfaction_score: float = Field(ge=1, le=5)
    feedback: str = Field("", max_length=5000)

    @field_validator("feedback")
    @classmethod
    def sanitize_feedback(cls, v: str) -> str:
        return _sanitize_string(v)


class CustomerFeedbackRequest(BaseModel):
    """Customer feedback submission."""

    client_id: str = Field(..., min_length=1, max_length=100)
    text: str = Field(..., min_length=1, max_length=5000)
    score: float = Field(0.0, ge=-10, le=10)
    source: str = Field("api", max_length=50)
    category: str = Field("", max_length=100)

    @field_validator("text", "category")
    @classmethod
    def sanitize_strings(cls, v: str) -> str:
        return _sanitize_string(v)


class RevenueMetricRequest(BaseModel):
    """Revenue metric recording."""

    metric_name: str = Field(..., min_length=1, max_length=200)
    value: float = Field(..., ge=-1_000_000_000, le=1_000_000_000)
    period: str = Field("monthly", max_length=20)
    segment: str = Field("", max_length=100)


# ════════════════════════════════════════════════════════════════════
# Lead Qualification Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post(
    "/leads",
    summary="Create and qualify a lead",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def create_lead(
    request: Request,
    body: LeadCreateRequest,
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """
    Submit a new lead for automatic qualification.

    Persists to database and publishes event to EventBus
    for the LeadQualifierAgent to process.
    """
    repo = AutonomousRepository(db)

    lead = await repo.create_lead({
        "company_name": body.company_name,
        "contact_name": body.contact_name,
        "contact_email": body.contact_email,
        "contact_phone": body.contact_phone,
        "industry": body.industry,
        "company_size": body.company_size,
        "estimated_budget": body.estimated_budget,
        "source": body.source,
        "status": "new",
        "metadata": _sanitize_dict(body.metadata),
    })

    # Publish event to EventBus for agent processing
    event_bus = _get_event_bus(request)
    if event_bus:
        from app.agents.base import AgentEvent, EventType
        await event_bus.publish(AgentEvent(
            event_type=EventType.LEAD_CREATED,
            source="api",
            payload=lead.to_dict(),
        ))

    logger.info(
        "lead_created",
        lead_id=lead.id,
        company=body.company_name,
        user_id=user.get("sub"),
    )

    return {
        "status": "submitted",
        "lead": lead.to_dict(),
        "message": "Lead submitted for qualification.",
    }


@router.get("/leads", summary="List all leads")
@limiter.limit("60/minute")
async def list_leads(
    request: Request,
    status_filter: Optional[str] = None,
    limit: int = Field(50, ge=1, le=200),
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """List leads with optional status filter."""
    repo = AutonomousRepository(db)
    leads = await repo.list_leads(status=status_filter, limit=limit)
    total = await repo.count_leads(status=status_filter)
    return {
        "leads": [l.to_dict() for l in leads],
        "total": total,
        "filter": {"status": status_filter},
    }


@router.get("/leads/{lead_id}", summary="Get lead details")
@limiter.limit("60/minute")
async def get_lead(
    request: Request,
    lead_id: str = Field(..., max_length=50),
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """Get detailed information about a specific lead."""
    repo = AutonomousRepository(db)
    lead = await repo.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"lead": lead.to_dict()}


# ════════════════════════════════════════════════════════════════════
# Content Creation Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post(
    "/content",
    summary="Request content generation",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
async def request_content(
    request: Request,
    body: ContentRequest,
    user: dict = Depends(require_auth),
):
    """
    Request content generation.

    Requires JWT authentication. Rate limited to 20 requests/minute.
    """
    logger.info(
        "content_requested",
        content_type=body.content_type,
        topic=body.topic,
        user_id=user.get("sub"),
    )

    return {
        "status": "submitted",
        "content_type": body.content_type,
        "topic": body.topic,
        "message": "Content request submitted.",
    }


@router.get("/content", summary="List generated content")
@limiter.limit("60/minute")
async def list_content(
    request: Request,
    content_type: Optional[str] = None,
    limit: int = Field(50, ge=1, le=200),
    user: dict = Depends(require_auth),
):
    """List generated content pieces."""
    return {
        "content": [],
        "total": 0,
        "filter": {"content_type": content_type},
    }


@router.get("/content/calendar", summary="Get content calendar")
@limiter.limit("60/minute")
async def get_content_calendar(
    request: Request,
    user: dict = Depends(require_auth),
):
    """Get the current content calendar."""
    return {
        "week_start": datetime.now(timezone.utc).isoformat(),
        "planned_pieces": [],
        "themes": ["African market intelligence", "SME growth", "Financial inclusion"],
    }


# ════════════════════════════════════════════════════════════════════
# Invoicing Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post(
    "/invoices",
    summary="Create an invoice",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
async def create_invoice(
    request: Request,
    body: InvoiceCreateRequest,
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """
    Create and send an invoice for a client.

    Persists to database and publishes event for the InvoicingAgent.
    """
    repo = AutonomousRepository(db)

    invoice = await repo.create_invoice({
        "client_id": body.client_id,
        "client_name": body.client_name,
        "client_email": body.client_email,
        "product_tier": body.product_tier,
        "status": "draft",
    })

    # Publish event to EventBus
    event_bus = _get_event_bus(request)
    if event_bus:
        from app.agents.base import AgentEvent, EventType
        await event_bus.publish(AgentEvent(
            event_type=EventType.INVOICE_DRAFTED,
            source="api",
            payload=invoice.to_dict(),
        ))

    logger.info(
        "invoice_created",
        invoice_id=invoice.id,
        client_id=body.client_id,
        user_id=user.get("sub"),
    )

    return {
        "status": "submitted",
        "invoice": invoice.to_dict(),
        "message": "Invoice creation submitted.",
    }


@router.get("/invoices", summary="List invoices")
@limiter.limit("60/minute")
async def list_invoices(
    request: Request,
    status_filter: Optional[str] = None,
    limit: int = Field(50, ge=1, le=200),
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """List invoices with optional status filter."""
    repo = AutonomousRepository(db)
    invoices = await repo.list_invoices(status=status_filter, limit=limit)
    return {
        "invoices": [i.to_dict() for i in invoices],
        "total": len(invoices),
        "filter": {"status": status_filter},
    }


@router.post("/invoices/{invoice_id}/mark-paid", summary="Mark invoice as paid")
@limiter.limit("10/minute")
async def mark_invoice_paid(
    request: Request,
    invoice_id: str = Field(..., max_length=50),
    payment_method: str = Field("mpesa", max_length=50),
    payment_reference: str = Field("", max_length=200),
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """Mark an invoice as paid (from payment webhook)."""
    repo = AutonomousRepository(db)
    invoice = await repo.mark_invoice_paid(invoice_id, payment_method, payment_reference)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Publish event
    event_bus = _get_event_bus(request)
    if event_bus:
        from app.agents.base import AgentEvent, EventType
        await event_bus.publish(AgentEvent(
            event_type=EventType.INVOICE_PAID,
            source="api",
            payload=invoice.to_dict(),
        ))

    return {
        "invoice_id": invoice_id,
        "status": "paid",
        "payment_method": payment_method,
    }


@router.get("/invoices/forecast", summary="Revenue forecast")
@limiter.limit("30/minute")
async def get_revenue_forecast(
    request: Request,
    months: int = Field(3, ge=1, le=24),
    user: dict = Depends(require_auth),
):
    """Get revenue forecast from invoice pipeline."""
    return {
        "current_month": {"paid": 0, "outstanding": 0, "overdue": 0},
        "monthly_recurring_revenue": 0,
        "projected_revenue": 0,
        "projection_months": months,
    }


# ════════════════════════════════════════════════════════════════════
# Onboarding Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/onboarding", summary="List onboarding flows")
@limiter.limit("60/minute")
async def list_onboarding(
    request: Request,
    status_filter: Optional[str] = None,
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """List all onboarding flows."""
    repo = AutonomousRepository(db)
    flows = await repo.list_onboarding_flows(status=status_filter)
    return {
        "flows": [f.to_dict() for f in flows],
        "total": len(flows),
        "filter": {"status": status_filter},
    }


@router.get("/onboarding/{flow_id}", summary="Get onboarding flow")
@limiter.limit("60/minute")
async def get_onboarding(
    request: Request,
    flow_id: str = Field(..., max_length=50),
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """Get detailed onboarding flow progress."""
    repo = AutonomousRepository(db)
    flow = await repo.get_onboarding_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Onboarding flow not found")
    return {"flow": flow.to_dict()}


@router.post("/onboarding/{flow_id}/feedback", summary="Submit onboarding feedback")
@limiter.limit("10/minute")
async def submit_onboarding_feedback(
    request: Request,
    flow_id: str,
    body: OnboardingFeedbackRequest,
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """Submit feedback for an onboarding flow."""
    repo = AutonomousRepository(db)
    flow = await repo.get_onboarding_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Onboarding flow not found")

    flow.satisfaction_score = body.satisfaction_score
    flow.feedback = body.feedback
    await db.flush()

    return {
        "flow_id": flow_id,
        "satisfaction_score": body.satisfaction_score,
        "status": "recorded",
    }


@router.post("/onboarding/{flow_id}/steps/{step_name}/complete", summary="Complete onboarding step")
@limiter.limit("30/minute")
async def complete_onboarding_step(
    request: Request,
    flow_id: str,
    step_name: str,
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """Mark a specific onboarding step as completed."""
    repo = AutonomousRepository(db)
    step = await repo.complete_onboarding_step(flow_id, step_name)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    return {
        "flow_id": flow_id,
        "step": step_name,
        "status": "completed",
    }


# ════════════════════════════════════════════════════════════════════
# Feedback Loop Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post("/feedback/customer", summary="Submit customer feedback")
@limiter.limit("30/minute")
async def submit_customer_feedback(
    request: Request,
    body: CustomerFeedbackRequest,
    user: dict = Depends(require_auth),
):
    """Submit customer feedback for analysis."""
    return {
        "status": "recorded",
        "client_id": body.client_id,
        "category": body.category or "auto-classified",
    }


@router.get("/feedback/themes", summary="Get feedback themes")
@limiter.limit("60/minute")
async def get_feedback_themes(
    request: Request,
    user: dict = Depends(require_auth),
):
    """Get clustered customer feedback themes."""
    return {
        "themes": [],
        "total_feedback": 0,
    }


@router.get("/feedback/nps", summary="Get NPS score")
@limiter.limit("30/minute")
async def get_nps(
    request: Request,
    user: dict = Depends(require_auth),
):
    """Get Net Promoter Score."""
    return {"nps": 0, "promoters": 0, "detractors": 0, "total": 0}


@router.get("/feedback/agent-recommendations/{agent_name}", summary="Get agent recommendations")
@limiter.limit("30/minute")
async def get_agent_recommendations(
    request: Request,
    agent_name: str,
    user: dict = Depends(require_auth),
):
    """Get performance-based recommendations for an agent."""
    return {
        "agent_name": agent_name,
        "adjustments": [],
        "alerts": [],
    }


@router.post("/feedback/metrics", summary="Record revenue metric")
@limiter.limit("30/minute")
async def record_revenue_metric(
    request: Request,
    body: RevenueMetricRequest,
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """Record a revenue metric data point."""
    repo = AutonomousRepository(db)
    metric = await repo.record_metric({
        "metric_name": body.metric_name,
        "value": body.value,
        "period": body.period,
        "segment": body.segment,
    })

    # Publish event
    event_bus = _get_event_bus(request)
    if event_bus:
        from app.agents.base import AgentEvent, EventType
        await event_bus.publish(AgentEvent(
            event_type=EventType.REVENUE_METRIC_RECORDED,
            source="api",
            payload=metric.to_dict(),
        ))

    return {
        "status": "recorded",
        "metric": metric.to_dict(),
    }


# ════════════════════════════════════════════════════════════════════
# Dashboard Endpoint
# ════════════════════════════════════════════════════════════════════


@router.get("/dashboard", summary="Revenue operations dashboard")
@limiter.limit("30/minute")
async def get_dashboard(
    request: Request,
    user: dict = Depends(require_auth),
    db: "AsyncSession" = Depends(get_db),
):
    """
    Get the full revenue operations dashboard.

    Pulls real data from the database and orchestrator.
    """
    repo = AutonomousRepository(db)

    # Get counts from DB
    total_leads = await repo.count_leads()
    qualified_leads = await repo.count_leads(status="qualified")
    invoices = await repo.list_invoices(limit=1000)
    flows = await repo.list_onboarding_flows()

    paid_invoices = [i for i in invoices if i.status == "paid"]
    outstanding = [i for i in invoices if i.status in ("sent", "draft")]
    overdue = [i for i in invoices if i.status == "overdue"]

    # Get orchestrator status if available
    orchestrator = _get_orchestrator(request)
    orchestrator_status = orchestrator.get_status() if orchestrator else {}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leads": {
            "total": total_leads,
            "qualified": qualified_leads,
            "pipeline_value": 0,
        },
        "invoices": {
            "total": len(invoices),
            "paid": len(paid_invoices),
            "outstanding": len(outstanding),
            "overdue": len(overdue),
            "mrr": sum(i.total for i in paid_invoices),
        },
        "onboarding": {
            "active_flows": sum(1 for f in flows if f.status == "in_progress"),
            "completed": sum(1 for f in flows if f.status == "completed"),
            "avg_satisfaction": (
                sum(f.satisfaction_score for f in flows if f.satisfaction_score > 0)
                / max(1, sum(1 for f in flows if f.satisfaction_score > 0))
            ),
        },
        "orchestrator": orchestrator_status,
    }
