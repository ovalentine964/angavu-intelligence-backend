"""
Intelligence Product model — pre-computed intelligence for buyers.

Architecture: arch_backend.md §2.5
- Products generated on schedule, not on-demand
- Stored as JSON blobs for fast retrieval
"""
import uuid
from datetime import datetime, UTC

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, JSON, Date, Text, Index
)

from app.db.database import Base


class IntelligenceProduct(Base):
    """Pre-computed intelligence product for a region/category."""
    __tablename__ = "intelligence_products"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_type = Column(String(50), nullable=False, index=True)  # soko_pulse | alama_score | angavu_pulse | jamii_insights | distribution_gap | tax_base
    region = Column(String(10), nullable=False, index=True)  # geohash-5
    category = Column(String(100), nullable=True, index=True)  # product category
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    data = Column(JSON, nullable=False)  # The actual intelligence payload
    status = Column(String(20), default="ready")  # pending | processing | ready | failed
    version = Column(Integer, default=1)
    data_points = Column(Integer, default=0)  # How many transactions contributed
    confidence = Column(Integer, default=0)  # 0-100 confidence score
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_intel_type_region_cat", "product_type", "region", "category"),
        Index("idx_intel_status", "status", "product_type"),
    )
