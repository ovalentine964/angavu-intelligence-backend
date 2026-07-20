"""
Revenue Metric ORM model for database persistence.

Maps to 'autonomous_revenue_metrics' table. Stores time-series
revenue metrics for dashboard and forecasting.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    String,
)

from app.db.database import Base


class RevenueMetricDB(Base):
    """Persistent revenue metric storage."""

    __tablename__ = "autonomous_revenue_metrics"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    metric_name = Column(String(200), nullable=False, index=True)
    value = Column(Float, nullable=False)
    period = Column(String(20), nullable=True, default="monthly", index=True)
    segment = Column(String(100), nullable=True, default="", index=True)
    recorded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    extra_data = Column("metadata", JSON, nullable=True, default=dict)

    __table_args__ = (
        Index(
            "ix_autonomous_metrics_name_period",
            "metric_name",
            "period",
            "recorded_at",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "metric_name": self.metric_name,
            "value": self.value,
            "period": self.period,
            "segment": self.segment,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }
