"""
Transaction and Inventory models.

Transactions are the core data unit in Msaidizi. Every sale, purchase,
and expense recorded by a user becomes a transaction record. These are
the raw inputs that flow through the data pipeline to become intelligence.

Inventory tracks what products a user currently has in stock.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class Transaction(Base):
    """
    A single business transaction recorded by a user.

    Can be a SALE (money in), PURCHASE (stock acquisition), or EXPENSE
    (operational cost like transport, rent, etc.).

    Attributes:
        id: UUID primary key
        user_id: Foreign key to the user who recorded this
        transaction_type: SALE, PURCHASE, or EXPENSE
        item: Product or service name (normalized)
        item_category: Business category (food, household, transport, etc.)
        quantity: Number of units (0 for services)
        unit: Unit of measurement (kg, pieces, litres, etc.)
        unit_price: Price per unit in KES
        amount: Total amount in KES
        profit: Calculated profit (for sales only)
        payment_method: How payment was made
        customer_phone_hash: Hashed customer phone (for M-Pesa auto-record)
        mpesa_receipt: M-Pesa transaction receipt number
        recorded_via: How the transaction was recorded
        confidence_score: Quality score for voice-transcribed transactions
        source_text: Original input text/voice transcription
        timestamp: When the transaction actually occurred
        synced_at: When it was synced to cloud
        device_id: Which device recorded this
        location_geohash: Where the transaction happened
    """

    __tablename__ = "transactions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_type = Column(
        Enum("SALE", "PURCHASE", "EXPENSE", name="transaction_type_enum"),
        nullable=False,
        index=True,
    )
    item = Column(
        String(200),
        nullable=True,
        doc="Product or service name (normalized)",
    )
    item_category = Column(
        Enum(
            "food", "household", "transport", "clothing", "electronics",
            "beauty", "health", "agriculture", "services", "rent", "other",
            name="item_category_enum",
        ),
        nullable=True,
        index=True,
        doc="Business category classification",
    )
    quantity = Column(
        Float,
        nullable=True,
        default=0,
        doc="Number of units",
    )
    unit = Column(
        String(20),
        nullable=True,
        doc="Unit of measurement (kg, pieces, litres, bunch, etc.)",
    )
    unit_price = Column(
        Float,
        nullable=True,
        doc="Price per unit in KES",
    )
    amount = Column(
        Float,
        nullable=False,
        doc="Total transaction amount in KES",
    )
    profit = Column(
        Float,
        nullable=True,
        doc="Calculated profit for sales (amount - cost)",
    )
    payment_method = Column(
        Enum("mpesa", "cash", "credit", "bank", "other", name="payment_method_enum"),
        nullable=True,
        default="cash",
        doc="Payment method used",
    )
    customer_phone_hash = Column(
        String(64),
        nullable=True,
        doc="SHA-256 hash of customer phone for M-Pesa auto-record",
    )
    mpesa_receipt = Column(
        String(50),
        nullable=True,
        doc="M-Pesa transaction receipt number",
    )
    recorded_via = Column(
        Enum("text", "voice", "mpesa_auto", "ussd", "manual", name="recorded_via_enum"),
        nullable=True,
        default="manual",
        doc="How the transaction was recorded",
    )
    confidence_score = Column(
        Float,
        nullable=True,
        default=1.0,
        doc="Quality score 0-1 for voice-transcribed transactions",
    )
    source_text = Column(
        Text,
        nullable=True,
        doc="Original input text or voice transcription",
    )
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="When the transaction actually occurred",
    )
    synced_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When it was synced to cloud",
    )
    device_id = Column(
        String(100),
        nullable=True,
        doc="Device that recorded this transaction",
    )
    location_geohash = Column(
        String(12),
        nullable=True,
        doc="Geohash-5 of transaction location",
    )

    # Relationships
    user = relationship("User", back_populates="transactions")

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_transaction_amount_positive"),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_transaction_confidence_range",
        ),
        Index("idx_txn_user_time", "user_id", "timestamp"),
        Index("idx_txn_type_time", "transaction_type", "timestamp"),
        Index("idx_txn_category_time", "item_category", "timestamp"),
        Index("idx_txn_item", "item", "timestamp"),
        Index("idx_txn_location", "location_geohash", "timestamp"),
        Index("idx_txn_synced", "synced_at"),
        Index("idx_txn_mpesa", "mpesa_receipt"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction {self.id} {self.transaction_type} "
            f"KES {self.amount} item={self.item}>"
        )

    @property
    def is_sale(self) -> bool:
        return self.transaction_type == "SALE"

    @property
    def is_purchase(self) -> bool:
        return self.transaction_type == "PURCHASE"


class Inventory(Base):
    """
    User's current inventory / stock levels.

    Tracks what products a user has in stock, their cost basis,
    and when they need to restock.

    Attributes:
        id: UUID primary key
        user_id: Foreign key to the user
        item: Product name (normalized)
        category: Product category
        current_stock: Current quantity in stock
        unit: Unit of measurement
        avg_cost: Average cost per unit (rolling average)
        sell_price: Current selling price per unit
        restock_threshold: Minimum stock before alert
        last_restocked_at: When last restocked
        last_sold_at: When last sold
    """

    __tablename__ = "inventory"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item = Column(
        String(200),
        nullable=False,
        doc="Product name (normalized)",
    )
    category = Column(
        String(50),
        nullable=True,
        doc="Product category",
    )
    current_stock = Column(
        Float,
        nullable=False,
        default=0,
        doc="Current quantity in stock",
    )
    unit = Column(
        String(20),
        nullable=True,
        doc="Unit of measurement",
    )
    avg_cost = Column(
        Float,
        nullable=True,
        doc="Average cost per unit (rolling average)",
    )
    sell_price = Column(
        Float,
        nullable=True,
        doc="Current selling price per unit",
    )
    restock_threshold = Column(
        Float,
        nullable=True,
        default=0,
        doc="Minimum stock level before restock alert",
    )
    last_restocked_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_sold_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="inventory_items")

    __table_args__ = (
        Index("idx_inv_user_item", "user_id", "item", unique=True),
        Index("idx_inv_restock", "user_id", "current_stock"),
    )

    def __repr__(self) -> str:
        return f"<Inventory {self.item} stock={self.current_stock} {self.unit}>"

    @property
    def needs_restock(self) -> bool:
        """Check if item is below restock threshold."""
        if self.restock_threshold is None or self.restock_threshold <= 0:
            return False
        return self.current_stock <= self.restock_threshold

    @property
    def stock_value(self) -> float:
        """Calculate total value of current stock."""
        if self.avg_cost is None:
            return 0.0
        return self.current_stock * self.avg_cost
