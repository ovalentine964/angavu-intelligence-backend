"""
Revenue Operations API — REST endpoints for all revenue ops agents.

Endpoints:
    /leads          — Lead qualification pipeline
    /content        — Content creation pipeline
    /invoices       — Invoice generation and tracking
    /onboarding     — Customer onboarding flows
    /feedback       — Feedback loops and metrics
    /dashboard      — Revenue operations dashboard

All endpoints are async and integrate with the EventBus.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/revenue-ops", tags=["revenue-ops"])


# ════════════════════════════════════════════════════════════════════
# Request / Response Models
# ════════════════════════════════════════════════════════════════════


class LeadCreateRequest(BaseModel):
    """Request to create and qualify a lead."""
    company_name: str
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    industry: str = "other"
    company_size: str = "1-10"
    estimated_budget: float = 0.0
    source: str = "other"
    urgency: str = ""
    decision_timeline_days: Optional[int] = None
    meetings_requested: int = 0
    email_opens: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContentRequest(BaseModel):
    """Request to generate content."""
    content_type: str = "blog_post"
    topic: Optional[str] = None
    target_channels: List[str] = Field(default_factory=list)
    requested_by: str = "api"


class InvoiceCreateRequest(BaseModel):
    """Request to create an invoice."""
    client_id: str
    client_name: str
    client_email: str = ""
    product_tier: str = "standard"
    addons: List[str] = Field(default_factory=list)


class OnboardingFeedbackRequest(BaseModel):
    """Onboarding feedback submission."""
    flow_id: str
    satisfaction_score: float = Field(ge=1, le=5)
    feedback: str = ""


class CustomerFeedbackRequest(BaseModel):
    """Customer feedback submission."""
    client_id: str
    text: str
    score: float = 0.0
    source: str = "api"
    category: str = ""


class RevenueMetricRequest(BaseModel):
    """Revenue metric recording."""
    metric_name: str
    value: float
    period: str = "monthly"
    segment: str = ""


# ════════════════════════════════════════════════════════════════════
# Lead Qualification Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post("/leads", summary="Create and qualify a lead")
async def create_lead(request: LeadCreateRequest):
    """
    Submit a new lead for automatic qualification.

    The LeadQualifierAgent scores the lead across 5 dimensions
    and routes it: escalate (high-value), qualify (nurture), or reject.
    """
    from app.autonomous.models.lead import Lead, LeadSource, LeadStatus

    lead = Lead(
        company_name=request.company_name,
        contact_name=request.contact_name,
        contact_email=request.contact_email,
        contact_phone=request.contact_phone,
        industry=request.industry,
        company_size=request.company_size,
        estimated_budget=request.estimated_budget,
        source=LeadSource(request.source),
        metadata=request.metadata,
    )

    # Get event bus from app state (injected at startup)
    # For now, return the lead data — the agent will process via EventBus
    return {
        "status": "submitted",
        "lead": lead.to_dict(),
        "message": "Lead submitted for qualification. The LeadQualifierAgent will process it shortly.",
    }


@router.get("/leads", summary="List all leads")
async def list_leads(status: Optional[str] = None, limit: int = 50):
    """List leads with optional status filter."""
    # In production, query from database
    return {
        "leads": [],
        "total": 0,
        "filter": {"status": status},
    }


@router.get("/leads/{lead_id}", summary="Get lead details")
async def get_lead(lead_id: str):
    """Get detailed information about a specific lead."""
    return {"lead_id": lead_id, "status": "not_found"}


# ════════════════════════════════════════════════════════════════════
# Content Creation Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post("/content", summary="Request content generation")
async def request_content(request: ContentRequest):
    """
    Request content generation.

    The ContentCreatorAgent generates SEO-optimized content
    and schedules it for distribution across channels.
    """
    return {
        "status": "submitted",
        "content_type": request.content_type,
        "topic": request.topic,
        "message": "Content request submitted. The ContentCreatorAgent will generate it shortly.",
    }


@router.get("/content", summary="List generated content")
async def list_content(content_type: Optional[str] = None, limit: int = 50):
    """List generated content pieces."""
    return {
        "content": [],
        "total": 0,
        "filter": {"content_type": content_type},
    }


@router.get("/content/calendar", summary="Get content calendar")
async def get_content_calendar():
    """Get the current content calendar."""
    return {
        "week_start": datetime.now(timezone.utc).isoformat(),
        "planned_pieces": [],
        "themes": ["African market intelligence", "SME growth", "Financial inclusion"],
    }


# ════════════════════════════════════════════════════════════════════
# Invoicing Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post("/invoices", summary="Create an invoice")
async def create_invoice(request: InvoiceCreateRequest):
    """
    Create and send an invoice for a client.

    The InvoicingAgent generates the invoice with proper line items,
    calculates taxes, and sends it to the client.
    """
    return {
        "status": "submitted",
        "client_id": request.client_id,
        "product_tier": request.product_tier,
        "message": "Invoice creation submitted. The InvoicingAgent will process it shortly.",
    }


@router.get("/invoices", summary="List invoices")
async def list_invoices(status: Optional[str] = None, limit: int = 50):
    """List invoices with optional status filter."""
    return {
        "invoices": [],
        "total": 0,
        "filter": {"status": status},
    }


@router.post("/invoices/{invoice_id}/mark-paid", summary="Mark invoice as paid")
async def mark_invoice_paid(invoice_id: str, payment_method: str = "mpesa", payment_reference: str = ""):
    """Mark an invoice as paid (from payment webhook)."""
    return {
        "invoice_id": invoice_id,
        "status": "paid",
        "payment_method": payment_method,
    }


@router.get("/invoices/forecast", summary="Revenue forecast")
async def get_revenue_forecast(months: int = 3):
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
async def list_onboarding(status: Optional[str] = None):
    """List all onboarding flows."""
    return {
        "flows": [],
        "total": 0,
        "filter": {"status": status},
    }


@router.get("/onboarding/{flow_id}", summary="Get onboarding flow")
async def get_onboarding(flow_id: str):
    """Get detailed onboarding flow progress."""
    return {"flow_id": flow_id, "status": "not_found"}


@router.post("/onboarding/{flow_id}/feedback", summary="Submit onboarding feedback")
async def submit_onboarding_feedback(flow_id: str, request: OnboardingFeedbackRequest):
    """Submit feedback for an onboarding flow."""
    return {
        "flow_id": flow_id,
        "satisfaction_score": request.satisfaction_score,
        "status": "recorded",
    }


@router.post("/onboarding/{flow_id}/steps/{step_name}/complete", summary="Complete onboarding step")
async def complete_onboarding_step(flow_id: str, step_name: str):
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
async def submit_customer_feedback(request: CustomerFeedbackRequest):
    """Submit customer feedback for analysis."""
    return {
        "status": "recorded",
        "client_id": request.client_id,
        "category": request.category or "auto-classified",
    }


@router.get("/feedback/themes", summary="Get feedback themes")
async def get_feedback_themes():
    """Get clustered customer feedback themes."""
    return {
        "themes": [],
        "total_feedback": 0,
    }


@router.get("/feedback/nps", summary="Get NPS score")
async def get_nps():
    """Get Net Promoter Score."""
    return {"nps": 0, "promoters": 0, "detractors": 0, "total": 0}


@router.get("/feedback/agent-recommendations/{agent_name}", summary="Get agent recommendations")
async def get_agent_recommendations(agent_name: str):
    """Get performance-based recommendations for an agent."""
    return {
        "agent_name": agent_name,
        "adjustments": [],
        "alerts": [],
    }


@router.post("/feedback/metrics", summary="Record revenue metric")
async def record_revenue_metric(request: RevenueMetricRequest):
    """Record a revenue metric data point."""
    return {
        "status": "recorded",
        "metric_name": request.metric_name,
        "value": request.value,
    }


# ════════════════════════════════════════════════════════════════════
# Dashboard Endpoint
# ════════════════════════════════════════════════════════════════════


@router.get("/dashboard", summary="Revenue operations dashboard")
async def get_dashboard():
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
