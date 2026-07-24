"""
Revenue metrics for autonomous operations tracking.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class RevenueMetricDB(Base):
    """Revenue metrics tracked by autonomous operations."""
    __tablename__ = "revenue_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # mrr, arr, churn, ltv, etc.
    value = Column(Float, nullable=False)
    currency = Column(String(10), default="KES")
    period = Column(String(20), nullable=True)  # daily, weekly, monthly
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
