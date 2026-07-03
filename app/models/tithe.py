"""
Tithe Tracker Models — Dedicated models for tithe/giving tracking.

Provides:
    - TitheRecord: Individual giving records (tithe, offering, zakat, harambee, charity)
    - TitheReport: Cached/computed giving reports for periods
    - AbundancePattern: Stored abundance pattern analysis results

Note: TitheRecord is the canonical giving model. The one in worker_features.py
re-exports from here for backward compatibility.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID

from app.db.database import Base


# =========================================================================
# TitheRecord — Individual Giving Record
# =========================================================================


class TitheRecord(Base):
    """
    Individual giving record — tithe, offering, zakat, harambee, charity, etc.

    Tracks giving for consistency scoring, abundance pattern analysis,
    and monthly/annual reporting. Data is confession-level sensitive.
    """

    __tablename__ = "tithe_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Float, nullable=False, doc="Giving amount in local currency")
    currency = Column(
        String(3), nullable=False, default="KES",
        doc="ISO currency code (KES, UGX, TZS, NGN)",
    )
    category = Column(
        Enum(
            "tithe", "offering", "zakat", "harambee", "charity",
            "building_fund", "missions", "custom",
            name="giving_category_enum",
        ),
        nullable=False,
        default="offering",
        doc="Giving category",
    )
    custom_category_name = Column(
        String(100), nullable=True,
        doc="Custom category label when category=custom",
    )
    recipient = Column(
        String(200), nullable=True,
        doc="Church, mosque, person, or community name",
    )
    giving_date = Column(
        Date, nullable=False,
        doc="Date the giving occurred",
    )
    input_method = Column(
        Enum("voice", "manual", "mpesa_parse", name="giving_input_method_enum"),
        nullable=False,
        default="manual",
    )
    voice_transcript = Column(Text, nullable=True, doc="Raw voice input if applicable")
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_tithe_user_date", "user_id", "giving_date"),
        Index("idx_tithe_user_category", "user_id", "category"),
        Index("idx_tithe_created", "created_at"),
    )


# =========================================================================
# TitheReport — Cached Computed Reports
# =========================================================================


class TitheReport(Base):
    """
    Cached giving report for a specific user and period.

    Stores pre-computed report data to avoid repeated aggregation queries.
    Reports are regenerated when new giving records are added.
    """

    __tablename__ = "tithe_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_type = Column(
        Enum("weekly", "monthly", "yearly", name="report_period_enum"),
        nullable=False,
        doc="Report granularity",
    )
    period_label = Column(
        String(20), nullable=False,
        doc="Human-readable period (e.g., '2026-W27', '2026-07', '2026')",
    )
    period_start = Column(Date, nullable=False, doc="Period start date")
    period_end = Column(Date, nullable=False, doc="Period end date")

    # Aggregated totals
    total_given = Column(Float, nullable=False, default=0, doc="Total giving amount")
    currency = Column(String(3), nullable=False, default="KES")
    record_count = Column(Integer, nullable=False, default=0, doc="Number of giving records")

    # Category breakdown: {"tithe": 5000, "offering": 2000, ...}
    by_category = Column(JSON, nullable=True, doc="Giving breakdown by category")

    # Recipient breakdown: {"St. Mary's Church": 5000, ...}
    by_recipient = Column(JSON, nullable=True, doc="Giving breakdown by recipient")

    # Consistency metrics
    consistency_score = Column(Float, nullable=True, doc="Consistency score 0-100")
    active_weeks = Column(Integer, nullable=True, doc="Weeks with giving in period")
    total_weeks = Column(Integer, nullable=True, doc="Total weeks in period")

    # Period comparison
    previous_period_total = Column(Float, nullable=True, doc="Previous period total giving")
    change_amount = Column(Float, nullable=True, doc="Absolute change from previous period")
    change_pct = Column(Float, nullable=True, doc="Percentage change from previous period")

    # Metadata
    computed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="When this report was last computed",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "period_type", "period_label", name="uq_tithe_report_period"),
        Index("idx_tithe_report_user", "user_id", "period_type"),
        Index("idx_tithe_report_period", "period_start", "period_end"),
    )


# =========================================================================
# AbundancePattern — Giving Pattern Analysis
# =========================================================================


class AbundancePattern(Base):
    """
    Stored abundance pattern analysis for a user.

    Correlates giving consistency with income trends to produce
    an abundance score and pattern classification. Research shows
    giving patterns predict creditworthiness better than bank balances.
    """

    __tablename__ = "abundance_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Analysis window
    analysis_months = Column(
        Integer, nullable=False, default=6,
        doc="Number of months analyzed",
    )
    months_with_data = Column(
        Integer, nullable=False, default=0,
        doc="Months with sufficient data for analysis",
    )

    # Trend signals
    income_trend = Column(
        Enum("increasing", "stable", "decreasing", name="trend_enum"),
        nullable=True,
        doc="Income trend direction",
    )
    giving_trend = Column(
        Enum("increasing", "stable", "decreasing", name="giving_trend_enum"),
        nullable=True,
        doc="Giving trend direction",
    )

    # Core metrics
    avg_giving_pct = Column(
        Float, nullable=True,
        doc="Average giving as percentage of income",
    )
    total_given = Column(Float, nullable=False, default=0, doc="Total giving in window")
    total_income = Column(Float, nullable=False, default=0, doc="Total income in window")
    currency = Column(String(3), nullable=False, default="KES")

    # Abundance score (0-100)
    abundance_score = Column(
        Float, nullable=True,
        doc="Composite abundance score (0-100)",
    )

    # Pattern classification
    pattern = Column(
        Enum(
            "blessing_cycle", "income_outpacing_giving", "faithful_giving",
            "parallel_decline", "steady", "insufficient_data",
            name="abundance_pattern_enum",
        ),
        nullable=True,
        doc="Detected abundance pattern type",
    )

    # Monthly data snapshot: [{"month": "2026-01", "income": 50000, "giving": 5000, "giving_pct": 10.0}, ...]
    monthly_data = Column(JSON, nullable=True, doc="Monthly income/giving breakdown")

    # Insight messages
    insight_sw = Column(Text, nullable=True, doc="Swahili insight message")
    insight_en = Column(Text, nullable=True, doc="English insight message")

    # Creditworthiness signal
    creditworthiness_signal = Column(
        Enum("strong", "moderate", "weak", "insufficient", name="credit_signal_enum"),
        nullable=True,
        doc="Giving-based creditworthiness signal",
    )

    # Metadata
    computed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_abundance_user", "user_id"),
        Index("idx_abundance_pattern", "pattern"),
        Index("idx_abundance_score", "abundance_score"),
        Index("idx_abundance_computed", "computed_at"),
    )
