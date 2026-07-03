"""
Invoice ORM models for database persistence.

Maps to 'autonomous_invoices' and 'autonomous_invoice_items' tables.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class InvoiceDB(Base):
    """Persistent invoice storage."""

    __tablename__ = "autonomous_invoices"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    invoice_number = Column(String(30), nullable=True, unique=True, index=True)
    client_id = Column(String(100), nullable=False, index=True)
    client_name = Column(String(200), nullable=False)
    client_email = Column(String(254), nullable=True, default="")
    subtotal = Column(Float, nullable=True, default=0.0)
    tax_total = Column(Float, nullable=True, default=0.0)
    total = Column(Float, nullable=True, default=0.0, index=True)
    currency = Column(String(10), nullable=True, default="KES")
    status = Column(String(20), nullable=False, default="draft", index=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    issued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    sent_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_method = Column(String(50), nullable=True, default="")
    payment_reference = Column(String(200), nullable=True, default="")
    reminder_count = Column(Integer, nullable=True, default=0)
    notes = Column(Text, nullable=True, default="")
    metadata = Column(JSON, nullable=True, default=dict)

    items = relationship(
        "InvoiceItemDB",
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_autonomous_invoices_status_due", "status", "due_date"),
    )

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.id,
            "invoice_number": self.invoice_number,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "client_email": self.client_email,
            "items": [i.to_dict() for i in (self.items or [])],
            "subtotal": self.subtotal,
            "tax_total": self.tax_total,
            "total": self.total,
            "currency": self.currency,
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "payment_method": self.payment_method,
            "reminder_count": self.reminder_count,
        }


class InvoiceItemDB(Base):
    """Line item on an invoice."""

    __tablename__ = "autonomous_invoice_items"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:8])
    invoice_id = Column(
        String(32),
        ForeignKey("autonomous_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description = Column(String(500), nullable=False)
    quantity = Column(Float, nullable=True, default=1.0)
    unit_price = Column(Float, nullable=True, default=0.0)
    tax_rate = Column(Float, nullable=True, default=0.16)
    total = Column(Float, nullable=True, default=0.0)

    invoice = relationship("InvoiceDB", back_populates="items")

    def to_dict(self) -> dict:
        return {
            "item_id": self.id,
            "description": self.description,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "tax_rate": self.tax_rate,
            "total": self.total,
        }
