"""
Autonomous Operations Repository — Async database operations.

Provides CRUD operations for all autonomous domain models.
Uses SQLAlchemy async sessions from app.db.database.

Usage:
    repo = AutonomousRepository(db_session)
    lead = await repo.create_lead(lead_data)
    leads = await repo.list_leads(status="qualified", limit=50)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.autonomous.invoice import InvoiceDB, InvoiceItemDB
from app.models.autonomous.lead import LeadDB
from app.models.autonomous.metric import RevenueMetricDB
from app.models.autonomous.onboarding import OnboardingFlowDB, OnboardingStepDB

logger = structlog.get_logger(__name__)


class AutonomousRepository:
    """Async repository for autonomous operations data."""

    def __init__(self, session: AsyncSession):
        self._db = session

    # ── Leads ───────────────────────────────────────────────────────

    async def create_lead(self, data: dict[str, Any]) -> LeadDB:
        """Create a new lead record."""
        lead = LeadDB(
            company_name=data.get("company_name", ""),
            contact_name=data.get("contact_name", ""),
            contact_email=data.get("contact_email", ""),
            contact_phone=data.get("contact_phone", ""),
            industry=data.get("industry", "other"),
            company_size=data.get("company_size", "1-10"),
            estimated_budget=data.get("estimated_budget", 0.0),
            source=data.get("source", "other"),
            status=data.get("status", "new"),
            metadata=data.get("metadata", {}),
        )
        self._db.add(lead)
        await self._db.flush()
        logger.info("lead_created_db", lead_id=lead.id)
        return lead

    async def get_lead(self, lead_id: str) -> LeadDB | None:
        """Get a lead by ID."""
        result = await self._db.execute(
            select(LeadDB).where(LeadDB.id == lead_id)
        )
        return result.scalar_one_or_none()

    async def list_leads(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LeadDB]:
        """List leads with optional status filter."""
        query = select(LeadDB).order_by(desc(LeadDB.created_at))
        if status:
            query = query.where(LeadDB.status == status)
        query = query.offset(offset).limit(limit)
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def update_lead(self, lead_id: str, data: dict[str, Any]) -> LeadDB | None:
        """Update a lead record."""
        lead = await self.get_lead(lead_id)
        if not lead:
            return None
        for key, value in data.items():
            if hasattr(lead, key):
                setattr(lead, key, value)
        lead.updated_at = datetime.now(UTC)
        await self._db.flush()
        return lead

    async def count_leads(self, status: str | None = None) -> int:
        """Count leads, optionally filtered by status."""
        query = select(func.count(LeadDB.id))
        if status:
            query = query.where(LeadDB.status == status)
        result = await self._db.execute(query)
        return result.scalar() or 0

    # ── Invoices ────────────────────────────────────────────────────

    async def create_invoice(self, data: dict[str, Any]) -> InvoiceDB:
        """Create a new invoice with line items."""
        invoice = InvoiceDB(
            invoice_number=data.get("invoice_number", ""),
            client_id=data.get("client_id", ""),
            client_name=data.get("client_name", ""),
            client_email=data.get("client_email", ""),
            currency=data.get("currency", "KES"),
            status=data.get("status", "draft"),
            notes=data.get("notes", ""),
            metadata=data.get("metadata", {}),
        )
        self._db.add(invoice)
        await self._db.flush()

        # Add line items
        for item_data in data.get("items", []):
            item = InvoiceItemDB(
                invoice_id=invoice.id,
                description=item_data.get("description", ""),
                quantity=item_data.get("quantity", 1.0),
                unit_price=item_data.get("unit_price", 0.0),
                tax_rate=item_data.get("tax_rate", 0.16),
            )
            item.total = item.quantity * item.unit_price * (1 + item.tax_rate)
            self._db.add(item)

        await self._db.flush()

        # Recalculate totals
        await self._refresh_invoice_totals(invoice.id)
        logger.info("invoice_created_db", invoice_id=invoice.id)
        return invoice

    async def get_invoice(self, invoice_id: str) -> InvoiceDB | None:
        """Get an invoice by ID."""
        result = await self._db.execute(
            select(InvoiceDB).where(InvoiceDB.id == invoice_id)
        )
        return result.scalar_one_or_none()

    async def list_invoices(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InvoiceDB]:
        """List invoices with optional status filter."""
        query = select(InvoiceDB).order_by(desc(InvoiceDB.issued_at))
        if status:
            query = query.where(InvoiceDB.status == status)
        query = query.offset(offset).limit(limit)
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def mark_invoice_paid(
        self, invoice_id: str, payment_method: str = "", payment_reference: str = ""
    ) -> InvoiceDB | None:
        """Mark an invoice as paid."""
        invoice = await self.get_invoice(invoice_id)
        if not invoice:
            return None
        invoice.status = "paid"
        invoice.paid_at = datetime.now(UTC)
        invoice.payment_method = payment_method
        invoice.payment_reference = payment_reference
        await self._db.flush()
        return invoice

    async def _refresh_invoice_totals(self, invoice_id: str) -> None:
        """Recalculate invoice totals from line items."""
        invoice = await self.get_invoice(invoice_id)
        if not invoice:
            return
        subtotal = sum(i.quantity * i.unit_price for i in (invoice.items or []))
        tax_total = sum(i.quantity * i.unit_price * i.tax_rate for i in (invoice.items or []))
        invoice.subtotal = subtotal
        invoice.tax_total = tax_total
        invoice.total = subtotal + tax_total
        await self._db.flush()

    # ── Onboarding ──────────────────────────────────────────────────

    async def create_onboarding_flow(self, data: dict[str, Any]) -> OnboardingFlowDB:
        """Create a new onboarding flow with steps."""
        flow = OnboardingFlowDB(
            client_id=data.get("client_id", ""),
            client_name=data.get("client_name", ""),
            product_tier=data.get("product_tier", "standard"),
            status="created",
            metadata=data.get("metadata", {}),
        )
        self._db.add(flow)
        await self._db.flush()

        # Add steps
        for step_data in data.get("steps", []):
            step = OnboardingStepDB(
                flow_id=flow.id,
                name=step_data.get("name", ""),
                description=step_data.get("description", ""),
                order=step_data.get("order", 0),
                assigned_to=step_data.get("assigned_to", ""),
                due_days=step_data.get("due_days", 3),
            )
            self._db.add(step)

        await self._db.flush()
        logger.info("onboarding_flow_created_db", flow_id=flow.id)
        return flow

    async def get_onboarding_flow(self, flow_id: str) -> OnboardingFlowDB | None:
        """Get an onboarding flow by ID."""
        result = await self._db.execute(
            select(OnboardingFlowDB).where(OnboardingFlowDB.id == flow_id)
        )
        return result.scalar_one_or_none()

    async def list_onboarding_flows(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[OnboardingFlowDB]:
        """List onboarding flows."""
        query = select(OnboardingFlowDB).order_by(desc(OnboardingFlowDB.created_at))
        if status:
            query = query.where(OnboardingFlowDB.status == status)
        query = query.limit(limit)
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def complete_onboarding_step(
        self, flow_id: str, step_name: str
    ) -> OnboardingStepDB | None:
        """Mark an onboarding step as completed."""
        result = await self._db.execute(
            select(OnboardingStepDB).where(
                and_(
                    OnboardingStepDB.flow_id == flow_id,
                    OnboardingStepDB.name == step_name,
                )
            )
        )
        step = result.scalar_one_or_none()
        if not step:
            return None
        step.status = "completed"
        step.completed_at = datetime.now(UTC)
        await self._db.flush()

        # Check if all steps are done → complete flow
        flow = await self.get_onboarding_flow(flow_id)
        if flow:
            all_done = all(s.status in ("completed", "skipped") for s in (flow.steps or []))
            if all_done:
                flow.status = "completed"
                flow.completed_at = datetime.now(UTC)
                await self._db.flush()

        return step

    # ── Revenue Metrics ─────────────────────────────────────────────

    async def record_metric(self, data: dict[str, Any]) -> RevenueMetricDB:
        """Record a revenue metric data point."""
        metric = RevenueMetricDB(
            metric_name=data.get("metric_name", ""),
            value=data.get("value", 0.0),
            period=data.get("period", "monthly"),
            segment=data.get("segment", ""),
            metadata=data.get("metadata", {}),
        )
        self._db.add(metric)
        await self._db.flush()
        return metric

    async def get_metrics(
        self,
        metric_name: str | None = None,
        period: str | None = None,
        limit: int = 100,
    ) -> list[RevenueMetricDB]:
        """Get revenue metrics with optional filters."""
        query = select(RevenueMetricDB).order_by(desc(RevenueMetricDB.recorded_at))
        if metric_name:
            query = query.where(RevenueMetricDB.metric_name == metric_name)
        if period:
            query = query.where(RevenueMetricDB.period == period)
        query = query.limit(limit)
        result = await self._db.execute(query)
        return list(result.scalars().all())
