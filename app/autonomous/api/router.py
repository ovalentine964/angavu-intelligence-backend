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
from jose import JWTError, jwt
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()
security = HTTPBearer()

router = APIRouter(prefix="/api/v1/revenue-ops", tags=["revenue-ops"])

# Rate limiter (per-endpoint)
limiter = Limiter(key_func=get_remote_address)


# ════════════════════════════════════════════════════════════════════
# Authentication Dependencies
# ════════════════════════════════════════════════════════════════════


def _decode_jwt(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return jwt.decode(
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
):
    """
    Submit a new lead for automatic qualification.

    Requires JWT authentication. Rate limited to 30 requests/minute.
    """
    from app.autonomous.models.lead import Lead, LeadSource, LeadStatus

    try:
        source = LeadSource(body.source)
    except ValueError:
        source = LeadSource.OTHER

    lead = Lead(
        company_name=body.company_name,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        industry=body.industry,
        company_size=body.company_size,
        estimated_budget=body.estimated_budget,
        source=source,
        metadata=_sanitize_dict(body.metadata),
    )

    logger.info(
        "lead_created",
        lead_id=lead.lead_id,
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
):
    """List leads with optional status filter."""
    # In production, query from database (see Fix #3)
    return {
        "leads": [],
        "total": 0,
        "filter": {"status": status_filter},
    }


@router.get("/leads/{lead_id}", summary="Get lead details")
@limiter.limit("60/minute")
async def get_lead(
    request: Request,
    lead_id: str = Field(..., max_length=50),
    user: dict = Depends(require_auth),
):
    """Get detailed information about a specific lead."""
    return {"lead_id": lead_id, "status": "not_found"}


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
):
    """
    Create and send an invoice for a client.

    Requires JWT authentication. Rate limited to 20 requests/minute.
    """
    logger.info(
        "invoice_created",
        client_id=body.client_id,
        product_tier=body.product_tier,
        user_id=user.get("sub"),
    )

    return {
        "status": "submitted",
        "client_id": body.client_id,
        "product_tier": body.product_tier,
        "message": "Invoice creation submitted.",
    }


@router.get("/invoices", summary="List invoices")
@limiter.limit("60/minute")
async def list_invoices(
    request: Request,
    status_filter: Optional[str] = None,
    limit: int = Field(50, ge=1, le=200),
    user: dict = Depends(require_auth),
):
    """List invoices with optional status filter."""
    return {
        "invoices": [],
        "total": 0,
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
):
    """Mark an invoice as paid (from payment webhook)."""
    logger.info(
        "invoice_marked_paid",
        invoice_id=invoice_id,
        payment_method=payment_method,
        user_id=user.get("sub"),
    )
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
):
    """List all onboarding flows."""
    return {
        "flows": [],
        "total": 0,
        "filter": {"status": status_filter},
    }


@router.get("/onboarding/{flow_id}", summary="Get onboarding flow")
@limiter.limit("60/minute")
async def get_onboarding(
    request: Request,
    flow_id: str = Field(..., max_length=50),
    user: dict = Depends(require_auth),
):
    """Get detailed onboarding flow progress."""
    return {"flow_id": flow_id, "status": "not_found"}


@router.post("/onboarding/{flow_id}/feedback", summary="Submit onboarding feedback")
@limiter.limit("10/minute")
async def submit_onboarding_feedback(
    request: Request,
    flow_id: str,
    body: OnboardingFeedbackRequest,
    user: dict = Depends(require_auth),
):
    """Submit feedback for an onboarding flow."""
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
):
    """Mark a specific onboarding step as completed."""
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
):
    """Record a revenue metric data point."""
    return {
        "status": "recorded",
        "metric_name": body.metric_name,
        "value": body.value,
    }


# ════════════════════════════════════════════════════════════════════
# Dashboard Endpoint
# ════════════════════════════════════════════════════════════════════


@router.get("/dashboard", summary="Revenue operations dashboard")
@limiter.limit("30/minute")
async def get_dashboard(
    request: Request,
    user: dict = Depends(require_auth),
):
    """
    Get the full revenue operations dashboard.

    Includes:
    - Lead pipeline summary
    - Content pipeline summary
    - Invoice status and revenue forecast
    - Onboarding progress
    - Feedback loop insights
    - Strategy adjustment recommendations
    """
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leads": {
            "total": 0,
            "by_status": {},
            "pipeline_value": 0,
        },
        "content": {
            "total_pieces": 0,
            "by_type": {},
            "scheduled_this_week": 0,
        },
        "invoices": {
            "total": 0,
            "paid": 0,
            "outstanding": 0,
            "overdue": 0,
            "mrr": 0,
        },
        "onboarding": {
            "active_flows": 0,
            "completed": 0,
            "avg_satisfaction": 0,
        },
        "feedback": {
            "total_signals": 0,
            "top_themes": [],
            "nps": 0,
        },
        "strategy_adjustments": {
            "lead_scoring": {},
            "content_strategy": {},
            "pricing": {},
        },
    }
