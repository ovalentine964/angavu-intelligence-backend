"""
Transaction and Inventory models — core economic data.

Architecture: arch_backend.md §1.2, §2.6
- Vector clocks for sync conflict detection
- Deduplication via idempotency_key
"""
import uuid
from datetime import datetime, UTC

from sqlalchemy import (
    Column, String, Boolean, DateTime, Numeric, Integer, Text, JSON, ForeignKey, Index
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Transaction(Base):
    """Financial transaction recorded by a worker."""
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String(64), unique=True, nullable=True, index=True)
    tx_type = Column(String(20), nullable=False)  # sale | purchase | expense
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="KES")
    description = Column(Text, nullable=True)
    product_name = Column(String(200), nullable=True)
    product_category = Column(String(100), nullable=True, index=True)
    quantity = Column(Integer, default=1)
    payment_method = Column(String(50), default="cash")
    location_geohash = Column(String(10), nullable=True, index=True)
    vector_clock = Column(JSON, default=dict)
    device_timestamp = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="transactions")

    __table_args__ = (
        Index("idx_txn_user_date", "user_id", "created_at"),
        Index("idx_txn_category_region", "product_category", "location_geohash"),
    )


class Inventory(Base):
    """Product inventory tracked by a worker."""
    __tablename__ = "inventory"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    product_category = Column(String(100), nullable=True)
    quantity = Column(Integer, default=0)
    unit_price = Column(Numeric(12, 2), nullable=True)
    cost_price = Column(Numeric(12, 2), nullable=True)
    vector_clock = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="inventory")

    __table_args__ = (
        Index("idx_inventory_user_product", "user_id", "product_name"),
    )
