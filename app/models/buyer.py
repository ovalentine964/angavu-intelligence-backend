"""
Buyer models — B2B API accounts, subscriptions, usage tracking.

Architecture: arch_backend.md §3.8, §7
"""
import uuid
from datetime import datetime, UTC

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Float, JSON, ForeignKey, Enum, Index
)
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


class BuyerTier(str, enum.Enum):
    STARTER = "starter"       # $99/mo — 1000 queries/day, 2 products
    BUSINESS = "business"     # $499/mo — 10000 queries/day, 4 products
    ENTERPRISE = "enterprise" # $2499/mo — unlimited queries, all products


BUYER_TIERS = {
    "starter": {"daily_limit": 1000, "price_per_query": 0.10, "max_products": 2},
    "business": {"daily_limit": 10000, "price_per_query": 0.05, "max_products": 4},
    "enterprise": {"daily_limit": 100000, "price_per_query": 0.02, "max_products": 999},
}


class BuyerOrg(Base):
    """Buyer organization — the B2B customer."""
    __tablename__ = "buyer_organizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=True)  # fmcg, banking, government, ngo, research
    country = Column(String(2), default="KE")
    contact_email = Column(String(255), nullable=False, unique=True)
    contact_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    api_keys = relationship("BuyerAPIKey", back_populates="buyer")
    subscriptions = relationship("BuyerSubscription", back_populates="buyer")
    usage_records = relationship("BuyerUsageRecord", back_populates="buyer")


class BuyerAPIKey(Base):
    """API key for buyer authentication."""
    __tablename__ = "buyer_api_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), ForeignKey("buyer_organizations.id"), nullable=False, index=True)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA-256 of raw key
    key_prefix = Column(String(12), nullable=False)  # First chars for identification
    org_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    buyer = relationship("BuyerOrg", back_populates="api_keys")


class BuyerSubscription(Base):
    """Buyer subscription — tier, products, billing period."""
    __tablename__ = "buyer_subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), ForeignKey("buyer_organizations.id"), nullable=False, index=True)
    tier = Column(String(20), nullable=False)  # starter | business | enterprise
    products = Column(JSON, nullable=False)  # ["soko-pulse", "alama-score", ...]
    status = Column(String(20), default="active")  # active | suspended | cancelled
    monthly_budget_usd = Column(Float, default=100.0)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    buyer = relationship("BuyerOrg", back_populates="subscriptions")


class BuyerUsageRecord(Base):
    """Per-query usage record for billing."""
    __tablename__ = "buyer_usage_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), ForeignKey("buyer_organizations.id"), nullable=False, index=True)
    product = Column(String(50), nullable=False)
    endpoint = Column(String(255), nullable=True)
    query_params = Column(JSON, nullable=True)
    response_size_bytes = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    buyer = relationship("BuyerOrg", back_populates="usage_records")

    __table_args__ = (
        Index("idx_usage_buyer_date", "buyer_id", "created_at"),
    )
