"""
Invoice models for automated billing.

Invoice lifecycle:
    Draft → Sent → (Paid | Overdue | Cancelled)

Supports:
    - Line items with unit pricing
    - Tax calculation
    - Payment reminders
    - Revenue forecasting aggregation
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class InvoiceStatus(str, Enum):
    """Invoice lifecycle states."""
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


@dataclass
class InvoiceItem:
    """A single line item on an invoice."""
    item_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0      # KES
    tax_rate: float = 0.16       # 16% VAT default (Kenya)
    total: float = 0.0           # quantity * unit_price * (1 + tax_rate)

    def calculate_total(self) -> float:
        """Calculate line total including tax."""
        self.total = self.quantity * self.unit_price * (1 + self.tax_rate)
        return self.total

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "description": self.description,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "tax_rate": self.tax_rate,
            "total": round(self.total, 2),
        }


@dataclass
class Invoice:
    """
    An invoice for enterprise clients.

    Attributes:
        invoice_id: Unique identifier
        invoice_number: Human-readable number (e.g., "ANG-2026-0001")
        client_id: Client identifier (lead_id or user_id)
        client_name: Client company name
        client_email: Billing email
        items: Line items
        subtotal: Sum of line items before tax
        tax_total: Total tax amount
        total: Grand total (subtotal + tax)
        currency: Currency code (default KES)
        status: Current lifecycle state
        due_date: Payment due date
        issued_at: When the invoice was created
        sent_at: When it was sent to the client
        paid_at: When payment was received
        payment_method: How the client paid
        payment_reference: Transaction reference
        reminder_count: Number of payment reminders sent
        last_reminder_at: When the last reminder was sent
        notes: Additional notes
        metadata: Arbitrary extra data
    """
    invoice_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    invoice_number: str = ""
    client_id: str = ""
    client_name: str = ""
    client_email: str = ""
    items: list[InvoiceItem] = field(default_factory=list)
    subtotal: float = 0.0
    tax_total: float = 0.0
    total: float = 0.0
    currency: str = "KES"
    status: InvoiceStatus = InvoiceStatus.DRAFT
    due_date: datetime | None = None
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    sent_at: datetime | None = None
    paid_at: datetime | None = None
    payment_method: str = ""
    payment_reference: str = ""
    reminder_count: int = 0
    last_reminder_at: datetime | None = None
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def calculate_totals(self) -> None:
        """Recalculate subtotal, tax, and total from line items."""
        self.subtotal = sum(item.quantity * item.unit_price for item in self.items)
        self.tax_total = sum(
            item.quantity * item.unit_price * item.tax_rate for item in self.items
        )
        self.total = self.subtotal + self.tax_total
        # Also update individual line totals
        for item in self.items:
            item.calculate_total()

    @property
    def is_overdue(self) -> bool:
        """Check if the invoice is past its due date."""
        if self.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.REFUNDED):
            return False
        if self.due_date is None:
            return False
        return datetime.now(UTC) > self.due_date

    @property
    def days_overdue(self) -> int:
        """Number of days past due (0 if not overdue)."""
        if not self.is_overdue or self.due_date is None:
            return 0
        return (datetime.now(UTC) - self.due_date).days

    def to_dict(self) -> dict[str, Any]:
        return {
            "invoice_id": self.invoice_id,
            "invoice_number": self.invoice_number,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "client_email": self.client_email,
            "items": [i.to_dict() for i in self.items],
            "subtotal": round(self.subtotal, 2),
            "tax_total": round(self.tax_total, 2),
            "total": round(self.total, 2),
            "currency": self.currency,
            "status": self.status.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "issued_at": self.issued_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "reminder_count": self.reminder_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Invoice:
        """Reconstruct an Invoice from a dictionary."""
        items = [
            InvoiceItem(
                item_id=i.get("item_id", ""),
                description=i.get("description", ""),
                quantity=i.get("quantity", 1.0),
                unit_price=i.get("unit_price", 0.0),
                tax_rate=i.get("tax_rate", 0.16),
                total=i.get("total", 0.0),
            )
            for i in data.get("items", [])
        ]
        due_date = None
        if data.get("due_date"):
            due_date = datetime.fromisoformat(data["due_date"])
        return cls(
            invoice_id=data.get("invoice_id", uuid.uuid4().hex[:12]),
            invoice_number=data.get("invoice_number", ""),
            client_id=data.get("client_id", ""),
            client_name=data.get("client_name", ""),
            client_email=data.get("client_email", ""),
            items=items,
            subtotal=data.get("subtotal", 0.0),
            tax_total=data.get("tax_total", 0.0),
            total=data.get("total", 0.0),
            currency=data.get("currency", "KES"),
            status=InvoiceStatus(data.get("status", "draft")),
            due_date=due_date,
            payment_method=data.get("payment_method", ""),
            payment_reference=data.get("payment_reference", ""),
            reminder_count=data.get("reminder_count", 0),
            notes=data.get("notes", ""),
            metadata=data.get("metadata", {}),
        )
