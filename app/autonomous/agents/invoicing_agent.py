"""
Invoicing Automation Agent — Auto-generates invoices and tracks payments.

Lifecycle:
    observe → Qualified lead or service delivery event
    think   → Determine invoice items, pricing, and terms
    act     → Generate invoice, send to client, track status
    reflect → Learn from payment patterns for revenue forecasting

Capabilities:
    - Auto-generate invoices from service contracts
    - Track payment status (draft → sent → paid / overdue)
    - Send automated payment reminders
    - Revenue forecasting from invoice pipeline
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)
from app.autonomous.models.invoice import Invoice, InvoiceItem, InvoiceStatus

logger = structlog.get_logger(__name__)

# ── Pricing configuration ──────────────────────────────────────────

# Product tier pricing (KES per month)
TIER_PRICING: Dict[str, Dict[str, Any]] = {
    "standard": {
        "base_price": 15_000,
        "description": "Angavu Standard — Market intelligence for SMEs",
        "features": ["daily_reports", "price_alerts", "basic_analytics"],
    },
    "professional": {
        "base_price": 45_000,
        "description": "Angavu Professional — Advanced analytics & forecasting",
        "features": ["daily_reports", "price_alerts", "advanced_analytics", "credit_scoring", "custom_dashboards"],
    },
    "enterprise": {
        "base_price": 150_000,
        "description": "Angavu Enterprise — Full platform + dedicated support",
        "features": ["all_professional", "api_access", "custom_integrations", "dedicated_am", "executive_reports"],
    },
}

# Add-on pricing
ADDON_PRICING: Dict[str, float] = {
    "extra_users": 2_000,         # per additional user
    "api_access": 10_000,         # monthly
    "custom_reports": 5_000,      # per custom report template
    "data_export": 3_000,         # monthly
    "priority_support": 8_000,    # monthly
}

# Payment terms
PAYMENT_TERMS_DAYS = 30  # Net 30
REMINDER_SCHEDULE = [7, 3, 1]  # Days before due: send reminders
OVERDUE_REMINDER_DAYS = [1, 3, 7, 14, 30]  # Days after due


class InvoicingAgent(BiasharaAgent):
    """
    Autonomous invoicing and payment tracking agent.

    Subscribes to: lead.qualified, onboarding.completed, invoice.overdue
    Publishes:     invoice.drafted, invoice.sent, invoice.paid, invoice.overdue

    Manages the full invoice lifecycle and provides revenue forecasting.
    """

    def __init__(self):
        super().__init__(
            name="InvoicingAgent",
            role="Invoice generation and payment tracking specialist",
            capabilities=[
                "invoice_generation",
                "payment_tracking",
                "payment_reminders",
                "revenue_forecasting",
            ],
        )
        # Invoice store (in-memory; wire to DB in production)
        self._invoices: Dict[str, Invoice] = {}
        # Invoice counter for numbering
        self._invoice_counter: int = 0

    # ── Lifecycle ───────────────────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Filter for invoicing-related events."""
        await super().observe(event)
        if event.event_type not in (
            EventType.LEAD_QUALIFIED,
            EventType.ONBOARDING_COMPLETED,
            EventType.INVOICE_OVERDUE,
            EventType.INVOICE_SENT,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Decide what invoicing action to take.

        Analysis:
        1. If qualified lead → draft invoice for their tier
        2. If onboarding completed → draft first invoice
        3. If invoice overdue → send reminder or escalate
        4. If invoice sent → check for payment
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        event_type = event_data.get("event_type", "")

        if event_type == EventType.LEAD_QUALIFIED.value:
            # Draft invoice for qualified lead
            lead = payload.get("lead", {})
            tier = lead.get("metadata", {}).get("product_tier", "standard")
            return AgentDecision(
                action="draft_invoice",
                parameters={
                    "client_id": lead.get("lead_id", ""),
                    "client_name": lead.get("company_name", ""),
                    "client_email": lead.get("contact_email", ""),
                    "product_tier": tier,
                    "addons": lead.get("metadata", {}).get("addons", []),
                },
                confidence=0.90,
                reasoning=f"Drafting invoice for qualified lead '{lead.get('company_name', '')}' — {tier} tier.",
            )

        elif event_type == EventType.ONBOARDING_COMPLETED.value:
            # Draft first invoice after onboarding
            client_id = payload.get("client_id", "")
            client_name = payload.get("client_name", "")
            tier = payload.get("product_tier", "standard")
            return AgentDecision(
                action="draft_invoice",
                parameters={
                    "client_id": client_id,
                    "client_name": client_name,
                    "product_tier": tier,
                    "addons": [],
                },
                confidence=0.95,
                reasoning=f"Drafting first invoice for onboarded client '{client_name}'.",
            )

        elif event_type == EventType.INVOICE_OVERDUE.value:
            # Handle overdue invoice
            invoice_id = payload.get("invoice_id", "")
            return AgentDecision(
                action="send_reminder",
                parameters={
                    "invoice_id": invoice_id,
                },
                confidence=0.85,
                reasoning=f"Sending payment reminder for overdue invoice {invoice_id}.",
            )

        else:
            # Check all sent invoices for overdue status
            return AgentDecision(
                action="check_payments",
                parameters={},
                confidence=0.80,
                reasoning="Checking all sent invoices for payment status.",
            )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Execute the invoicing action.
        """
        start = time.time()

        try:
            action = decision.action
            params = decision.parameters
            events_to_publish = []

            if action == "draft_invoice":
                result = await self._draft_invoice(params, events_to_publish)
            elif action == "send_reminder":
                result = await self._send_reminder(params, events_to_publish)
            elif action == "check_payments":
                result = await self._check_payments(events_to_publish)
            else:
                result = {"error": f"Unknown action: {action}"}

            duration_ms = (time.time() - start) * 1000

            return AgentResult(
                success="error" not in result,
                data=result,
                duration_ms=duration_ms,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=[
                    AgentEvent(
                        event_type=EventType.PIPELINE_ERROR,
                        source=self.name,
                        payload={"error": str(exc), "phase": "invoicing"},
                    )
                ],
            )

    async def reflect(self, result: AgentResult) -> None:
        """Learn from payment patterns."""
        await super().reflect(result)

        if result.success:
            data = result.data or {}
            self.memory.remember({
                "event_type": "invoicing_action",
                "action": data.get("action"),
                "invoice_id": data.get("invoice_id"),
            })

    # ── Invoice operations ──────────────────────────────────────────

    async def _draft_invoice(
        self,
        params: Dict[str, Any],
        events: List[AgentEvent],
    ) -> Dict[str, Any]:
        """Draft a new invoice for a client."""
        self._invoice_counter += 1
        invoice_number = f"ANG-{datetime.now(timezone.utc).year}-{self._invoice_counter:04d}"

        client_id = params.get("client_id", "")
        client_name = params.get("client_name", "")
        client_email = params.get("client_email", "")
        tier = params.get("product_tier", "standard")
        addons = params.get("addons", [])

        # Build line items
        tier_config = TIER_PRICING.get(tier, TIER_PRICING["standard"])
        items = [
            InvoiceItem(
                description=tier_config["description"],
                quantity=1.0,
                unit_price=tier_config["base_price"],
                tax_rate=0.16,
            )
        ]

        # Add-on items
        for addon in addons:
            addon_price = ADDON_PRICING.get(addon, 0)
            if addon_price > 0:
                items.append(InvoiceItem(
                    description=f"Add-on: {addon.replace('_', ' ').title()}",
                    quantity=1.0,
                    unit_price=addon_price,
                    tax_rate=0.16,
                ))

        # Create invoice
        invoice = Invoice(
            invoice_number=invoice_number,
            client_id=client_id,
            client_name=client_name,
            client_email=client_email,
            items=items,
            due_date=datetime.now(timezone.utc) + timedelta(days=PAYMENT_TERMS_DAYS),
            notes=f"Product tier: {tier}. Payment terms: Net {PAYMENT_TERMS_DAYS}.",
        )
        invoice.calculate_totals()
        invoice.status = InvoiceStatus.DRAFT

        # Store
        self._invoices[invoice.invoice_id] = invoice

        # Emit draft event
        events.append(AgentEvent(
            event_type=EventType.INVOICE_DRAFTED,
            source=self.name,
            payload={
                "invoice": invoice.to_dict(),
                "invoice_id": invoice.invoice_id,
                "client_id": client_id,
                "total": invoice.total,
            },
        ))

        # Auto-send (in production, integrate with email service)
        invoice.status = InvoiceStatus.SENT
        invoice.sent_at = datetime.now(timezone.utc)
        events.append(AgentEvent(
            event_type=EventType.INVOICE_SENT,
            source=self.name,
            payload={
                "invoice_id": invoice.invoice_id,
                "invoice_number": invoice.invoice_number,
                "client_id": client_id,
                "client_email": client_email,
                "total": invoice.total,
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            },
        ))

        self._logger.info(
            "invoice_drafted_and_sent",
            invoice_id=invoice.invoice_id,
            invoice_number=invoice_number,
            client=client_name,
            total=invoice.total,
        )

        return {
            "action": "draft_invoice",
            "invoice_id": invoice.invoice_id,
            "invoice_number": invoice_number,
            "client_name": client_name,
            "total": round(invoice.total, 2),
            "status": invoice.status.value,
        }

    async def _send_reminder(
        self,
        params: Dict[str, Any],
        events: List[AgentEvent],
    ) -> Dict[str, Any]:
        """Send a payment reminder for an overdue invoice."""
        invoice_id = params.get("invoice_id", "")
        invoice = self._invoices.get(invoice_id)

        if not invoice:
            return {"error": f"Invoice {invoice_id} not found"}

        invoice.reminder_count += 1
        invoice.last_reminder_at = datetime.now(timezone.utc)

        self._logger.info(
            "payment_reminder_sent",
            invoice_id=invoice_id,
            invoice_number=invoice.invoice_number,
            reminder_count=invoice.reminder_count,
            days_overdue=invoice.days_overdue,
        )

        return {
            "action": "send_reminder",
            "invoice_id": invoice_id,
            "invoice_number": invoice.invoice_number,
            "reminder_count": invoice.reminder_count,
            "days_overdue": invoice.days_overdue,
        }

    async def _check_payments(
        self,
        events: List[AgentEvent],
    ) -> Dict[str, Any]:
        """Check all sent invoices for overdue status."""
        overdue_count = 0
        total_outstanding = 0.0

        for invoice in self._invoices.values():
            if invoice.status == InvoiceStatus.SENT and invoice.is_overdue:
                invoice.status = InvoiceStatus.OVERDUE
                overdue_count += 1
                total_outstanding += invoice.total

                events.append(AgentEvent(
                    event_type=EventType.INVOICE_OVERDUE,
                    source=self.name,
                    payload={
                        "invoice_id": invoice.invoice_id,
                        "invoice_number": invoice.invoice_number,
                        "client_id": invoice.client_id,
                        "total": invoice.total,
                        "days_overdue": invoice.days_overdue,
                    },
                ))

        self._logger.info(
            "payment_check_complete",
            total_invoices=len(self._invoices),
            overdue_count=overdue_count,
            total_outstanding=round(total_outstanding, 2),
        )

        return {
            "action": "check_payments",
            "total_invoices": len(self._invoices),
            "overdue_count": overdue_count,
            "total_outstanding": round(total_outstanding, 2),
        }

    # ── Revenue forecasting ─────────────────────────────────────────

    def get_revenue_forecast(self, months: int = 3) -> Dict[str, Any]:
        """
        Generate revenue forecast from invoice pipeline.

        Uses historical payment patterns and current pipeline
        to project future revenue.
        """
        total_pipeline = 0.0
        total_paid = 0.0
        total_overdue = 0.0
        monthly_recurring = 0.0

        for invoice in self._invoices.values():
            if invoice.status == InvoiceStatus.PAID:
                total_paid += invoice.total
            elif invoice.status == InvoiceStatus.OVERDUE:
                total_overdue += invoice.total
            elif invoice.status == InvoiceStatus.SENT:
                total_pipeline += invoice.total
                monthly_recurring += invoice.total  # Assume monthly recurring

        # Simple projection
        projected_revenue = monthly_recurring * months

        return {
            "current_month": {
                "paid": round(total_paid, 2),
                "outstanding": round(total_pipeline, 2),
                "overdue": round(total_overdue, 2),
            },
            "monthly_recurring_revenue": round(monthly_recurring, 2),
            "projected_revenue": round(projected_revenue, 2),
            "projection_months": months,
            "invoice_count": len(self._invoices),
        }

    def mark_paid(
        self,
        invoice_id: str,
        payment_method: str = "mpesa",
        payment_reference: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Mark an invoice as paid (called from payment webhook)."""
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            return None

        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.now(timezone.utc)
        invoice.payment_method = payment_method
        invoice.payment_reference = payment_reference

        self._logger.info(
            "invoice_marked_paid",
            invoice_id=invoice_id,
            invoice_number=invoice.invoice_number,
            total=invoice.total,
            payment_method=payment_method,
        )

        return invoice.to_dict()
