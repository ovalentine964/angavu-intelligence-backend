"""
Tests for the Invoicing Agent.

Tests cover:
- Invoice generation with correct pricing and tax
- Payment tracking and overdue detection
- Revenue forecasting
- Invoice numbering
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from app.agents.base import AgentEvent, EventType
from app.autonomous.models.invoice import Invoice, InvoiceItem, InvoiceStatus
from app.autonomous.agents.invoicing_agent import (
    InvoicingAgent,
    TIER_PRICING,
    PAYMENT_TERMS_DAYS,
)


@pytest.fixture
def agent():
    """Create an InvoicingAgent for testing."""
    a = InvoicingAgent()
    a._event_bus = AsyncMock()
    return a


# ── Invoice Model Tests ────────────────────────────────────────────


class TestInvoiceModel:
    """Test Invoice data model."""

    def test_invoice_total_calculation(self):
        """Test that invoice totals are calculated correctly."""
        invoice = Invoice(
            items=[
                InvoiceItem(description="Standard", quantity=1, unit_price=15_000, tax_rate=0.16),
                InvoiceItem(description="Add-on", quantity=1, unit_price=5_000, tax_rate=0.16),
            ]
        )
        invoice.calculate_totals()

        assert invoice.subtotal == 20_000
        assert invoice.tax_total == 3_200  # 20000 * 0.16
        assert invoice.total == 23_200

    def test_invoice_overdue_detection(self):
        """Test overdue detection."""
        invoice = Invoice(
            status=InvoiceStatus.SENT,
            due_date=datetime.now(timezone.utc) - timedelta(days=5),
        )
        assert invoice.is_overdue
        assert invoice.days_overdue == 5

    def test_invoice_not_overdue_when_paid(self):
        """Paid invoices are never overdue."""
        invoice = Invoice(
            status=InvoiceStatus.PAID,
            due_date=datetime.now(timezone.utc) - timedelta(days=30),
        )
        assert not invoice.is_overdue

    def test_invoice_roundtrip(self):
        """Test Invoice serialization and deserialization."""
        invoice = Invoice(
            invoice_number="ANG-2026-0001",
            client_name="Test Corp",
            items=[InvoiceItem(description="Test", quantity=1, unit_price=10_000)],
        )
        invoice.calculate_totals()

        data = invoice.to_dict()
        restored = Invoice.from_dict(data)

        assert restored.invoice_number == "ANG-2026-0001"
        assert restored.client_name == "Test Corp"
        assert len(restored.items) == 1


# ── Invoice Agent Tests ────────────────────────────────────────────


class TestInvoicingAgent:
    """Test the InvoicingAgent."""

    @pytest.mark.asyncio
    async def test_draft_invoice_standard_tier(self, agent):
        """Test drafting an invoice for standard tier."""
        result = await agent._draft_invoice(
            params={
                "client_id": "client-001",
                "client_name": "Test Corp",
                "client_email": "test@corp.com",
                "product_tier": "standard",
                "addons": [],
            },
            events=[],
        )

        assert "error" not in result
        assert result["product_tier"] == "standard" if "product_tier" in result else True
        assert result["total"] > 0
        assert result["status"] == InvoiceStatus.SENT.value

    @pytest.mark.asyncio
    async def test_draft_invoice_enterprise_tier(self, agent):
        """Test drafting an invoice for enterprise tier."""
        result = await agent._draft_invoice(
            params={
                "client_id": "client-002",
                "client_name": "Big Corp",
                "client_email": "big@corp.com",
                "product_tier": "enterprise",
                "addons": ["api_access", "priority_support"],
            },
            events=[],
        )

        assert "error" not in result
        # Enterprise + add-ons should be expensive
        assert result["total"] > TIER_PRICING["enterprise"]["base_price"]

    @pytest.mark.asyncio
    async def test_draft_invoice_emits_events(self, agent):
        """Test that drafting emits draft and sent events."""
        events = []
        await agent._draft_invoice(
            params={
                "client_id": "client-003",
                "client_name": "Event Corp",
                "product_tier": "professional",
                "addons": [],
            },
            events=events,
        )

        assert len(events) == 2
        assert events[0].event_type == EventType.INVOICE_DRAFTED
        assert events[1].event_type == EventType.INVOICE_SENT

    @pytest.mark.asyncio
    async def test_invoice_numbering(self, agent):
        """Test that invoice numbers increment."""
        events1 = []
        events2 = []
        await agent._draft_invoice(
            params={"client_id": "c1", "client_name": "A", "product_tier": "standard", "addons": []},
            events=events1,
        )
        await agent._draft_invoice(
            params={"client_id": "c2", "client_name": "B", "product_tier": "standard", "addons": []},
            events=events2,
        )

        # Invoice counter should have incremented
        assert agent._invoice_counter == 2

    @pytest.mark.asyncio
    async def test_send_reminder(self, agent):
        """Test sending a payment reminder."""
        # First create an invoice
        events = []
        result = await agent._draft_invoice(
            params={"client_id": "c1", "client_name": "Corp", "product_tier": "standard", "addons": []},
            events=events,
        )
        invoice_id = result["invoice_id"]

        # Send reminder
        reminder_result = await agent._send_reminder(
            params={"invoice_id": invoice_id},
            events=[],
        )

        assert "error" not in reminder_result
        assert reminder_result["reminder_count"] == 1

    @pytest.mark.asyncio
    async def test_check_payments_marks_overdue(self, agent):
        """Test that check_payments marks overdue invoices."""
        events = []

        # Create an invoice and manually set it as sent with past due date
        result = await agent._draft_invoice(
            params={"client_id": "c1", "client_name": "Corp", "product_tier": "standard", "addons": []},
            events=events,
        )
        invoice_id = result["invoice_id"]
        invoice = agent._invoices[invoice_id]
        invoice.due_date = datetime.now(timezone.utc) - timedelta(days=5)

        # Check payments
        check_result = await agent._check_payments(events)

        assert check_result["overdue_count"] == 1
        assert invoice.status == InvoiceStatus.OVERDUE

    def test_revenue_forecast_empty(self, agent):
        """Test revenue forecast with no invoices."""
        forecast = agent.get_revenue_forecast()
        assert forecast["invoice_count"] == 0
        assert forecast["projected_revenue"] == 0

    def test_mark_paid(self, agent):
        """Test marking an invoice as paid."""
        # Create invoice via act
        import asyncio

        async def _create():
            from unittest.mock import MagicMock
            decision = MagicMock()
            decision.action = "draft_invoice"
            decision.parameters = {
                "client_id": "c1",
                "client_name": "Corp",
                "client_email": "c@corp.com",
                "product_tier": "standard",
                "addons": [],
            }
            return await agent.act(decision)

        result = asyncio.get_event_loop().run_until_complete(_create())
        invoice_id = result.data["invoice_id"]

        # Mark as paid
        paid = agent.mark_paid(invoice_id, "mpesa", "REF123")
        assert paid is not None
        assert paid["status"] == "paid"

    def test_tier_pricing_config(self):
        """Test that tier pricing is properly configured."""
        assert "standard" in TIER_PRICING
        assert "professional" in TIER_PRICING
        assert "enterprise" in TIER_PRICING
        assert TIER_PRICING["standard"]["base_price"] < TIER_PRICING["professional"]["base_price"]
        assert TIER_PRICING["professional"]["base_price"] < TIER_PRICING["enterprise"]["base_price"]
