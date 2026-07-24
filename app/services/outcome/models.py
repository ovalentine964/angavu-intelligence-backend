"""
Outcome Engine ORM Models.

Tables:
- outcome_baselines:        30-day per-worker baseline snapshots
- outcome_baseline_metrics: Individual metric values within a baseline
- outcomes:                 Tracked outcomes (loan approved, growth, etc.)
- worker_consent:           Granular consent records
- outcome_invoices:         Billing records triggered by verified outcomes
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSON, UUID

from app.db.database import Base


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class MetricType(str, enum.Enum):
    """Business metrics tracked for baseline and outcome measurement."""
    REVENUE = "revenue"
    PROFIT_MARGIN = "profit_margin"
    INVENTORY_TURNOVER = "inventory_turnover"
    CUSTOMER_COUNT = "customer_count"
    SUPPLIER_COSTS = "supplier_costs"
    DELIVERY_COSTS = "delivery_costs"
    DEAD_STOCK_VALUE = "dead_stock_value"
    LOAN_AMOUNT = "loan_amount"


class OutcomeType(str, enum.Enum):
    """Types of outcomes we track and bill for."""
    LOAN_APPROVED = "loan_approved"
    BUSINESS_GROWTH = "business_growth"
    DEAD_STOCK_REDUCTION = "dead_stock_reduction"
    BETTER_SUPPLIER = "better_supplier"
    ROUTE_OPTIMIZED = "route_optimized"


class OutcomeStatus(str, enum.Enum):
    """Lifecycle status of an outcome."""
    PENDING = "pending"              # Outcome detected, awaiting verification
    MEASURING = "measuring"          # Actively measuring (e.g., 6-month window)
    VERIFIED = "verified"            # Outcome confirmed with sufficient confidence
    ATTRIBUTED = "attributed"        # Causally attributed to our recommendation
    INVOICED = "invoiced"            # Invoice generated
    PAID = "paid"                    # Payment received
    DISPUTED = "disputed"            # Worker disputes the outcome
    EXPIRED = "expired"              # Measurement window expired without verification
    INSUFFICIENT_CONFIDENCE = "insufficient_confidence"  # Attribution confidence too low


class InvoiceStatus(str, enum.Enum):
    """Invoice lifecycle status."""
    DRAFT = "draft"
    PENDING = "pending"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class ConsentType(str, enum.Enum):
    """Types of consent workers can grant."""
    BUSINESS_TRACKING = "business_tracking"          # Track business metrics
    OUTCOME_SHARING_BANKS = "outcome_sharing_banks"  # Share success with banks
    OUTCOME_SHARING_THIRD_PARTY = "outcome_sharing_third_party"  # Share with partners
    BILLING_AUTHORIZATION = "billing_authorization"   # Allow outcome-based billing


# ═══════════════════════════════════════════════════════════════════════════════
# Baseline Models
# ═══════════════════════════════════════════════════════════════════════════════


class Baseline(Base):
    """
    30-day baseline snapshot for a worker.

    Captures the worker's business state before any Msaidizi recommendation,
    enabling before/after comparison for outcome attribution.
    """
    __tablename__ = "outcome_baselines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Measurement window
    measurement_start = Column(
        DateTime(timezone=True), nullable=False,
        doc="Start of 30-day baseline window",
    )
    measurement_end = Column(
        DateTime(timezone=True), nullable=False,
        doc="End of 30-day baseline window",
    )

    # Snapshot status
    is_active = Column(
        Boolean, default=True, nullable=False,
        doc="Whether this is the current active baseline for the worker",
    )

    # Metadata
    transaction_count = Column(
        Integer, default=0, nullable=False,
        doc="Number of transactions in the baseline window",
    )
    data_completeness = Column(
        Float, default=0.0, nullable=False,
        doc="Fraction of days with recorded data (0.0–1.0)",
    )

    # JSON blob for flexible metric storage
    raw_data = Column(
        JSON, nullable=True,
        doc="Raw aggregated data used to compute metrics",
    )

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Relationships
    metrics = relationship("BaselineMetric", back_populates="baseline", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_outcome_baselines_worker_active", "worker_id", "is_active"),
        CheckConstraint("data_completeness >= 0.0 AND data_completeness <= 1.0", name="ck_baseline_completeness"),
    )


class BaselineMetric(Base):
    """
    Individual metric within a baseline snapshot.

    Each baseline contains multiple metrics (revenue, margin, etc.)
    measured over the 30-day window.
    """
    __tablename__ = "outcome_baseline_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    baseline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outcome_baselines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    metric_type = Column(Enum(MetricType), nullable=False)
    value = Column(Float, nullable=False, doc="Mean value over baseline period")
    std_dev = Column(Float, nullable=True, doc="Standard deviation over baseline period")
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    unit = Column(
        String(20), nullable=False, default="KES",
        doc="Unit of measurement (KES, count, ratio, percentage)",
    )

    # Trend during baseline period
    trend_direction = Column(
        String(10), nullable=True, doc="up / down / flat",
    )
    trend_slope = Column(
        Float, nullable=True,
        doc="Linear regression slope over baseline period (units/day)",
    )

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    baseline = relationship("Baseline", back_populates="metrics")

    __table_args__ = (
        Index("ix_baseline_metrics_type", "baseline_id", "metric_type"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Outcome Models
# ═══════════════════════════════════════════════════════════════════════════════


class Outcome(Base):
    """
    Tracked outcome for a worker.

    Represents a specific business outcome (loan approved, revenue growth,
    etc.) that we detected, measured, and may attribute to our recommendation.
    """
    __tablename__ = "outcomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    baseline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outcome_baselines.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Outcome classification
    outcome_type = Column(Enum(OutcomeType), nullable=False, index=True)
    status = Column(
        Enum(OutcomeStatus), default=OutcomeStatus.PENDING, nullable=False, index=True,
    )

    # Trigger information
    recommendation_id = Column(
        String(100), nullable=True,
        doc="ID of the Msaidizi recommendation that may have caused this outcome",
    )
    recommendation_type = Column(
        String(100), nullable=True,
        doc="Type of recommendation (loan_referral, inventory_advice, supplier_match, route_optimization)",
    )
    trigger_condition = Column(
        Text, nullable=True,
        doc="Human-readable description of what triggered outcome tracking",
    )

    # Measurement
    measurement_start = Column(
        DateTime(timezone=True), nullable=True,
        doc="When measurement window started",
    )
    measurement_end = Column(
        DateTime(timezone=True), nullable=True,
        doc="When measurement window ends (or ended)",
    )
    measured_value = Column(
        Float, nullable=True,
        doc="Measured outcome value (e.g., revenue increase amount)",
    )
    measured_percentage = Column(
        Float, nullable=True,
        doc="Measured outcome as percentage change from baseline",
    )
    target_value = Column(
        Float, nullable=True,
        doc="Target value that must be reached for outcome verification",
    )
    target_percentage = Column(
        Float, nullable=True,
        doc="Target percentage change for verification",
    )

    # Attribution
    attribution_confidence = Column(
        Float, nullable=True,
        doc="Confidence score (0.0–1.0) that our recommendation caused this outcome",
    )
    attribution_method = Column(
        String(50), nullable=True,
        doc="Attribution method used (propensity_score, diff_in_diff, combined)",
    )
    attribution_details = Column(
        JSON, nullable=True,
        doc="Detailed attribution analysis results",
    )

    # Financial impact
    estimated_impact_kes = Column(
        Float, nullable=True,
        doc="Estimated financial impact in KES",
    )

    # Verification
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(
        String(50), nullable=True,
        doc="Verification method (automatic, manual, hybrid)",
    )
    verification_notes = Column(Text, nullable=True)

    # Metadata
    outcome_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_outcomes_worker_type", "worker_id", "outcome_type"),
        Index("ix_outcomes_status_type", "status", "outcome_type"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Consent Model
# ═══════════════════════════════════════════════════════════════════════════════


class WorkerConsent(Base):
    """
    Granular consent record for a worker.

    Each consent type is tracked independently. Workers can grant or revoke
    any consent at any time. Only the latest record per consent type is active.
    """
    __tablename__ = "worker_consent"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    consent_type = Column(Enum(ConsentType), nullable=False)
    granted = Column(Boolean, nullable=False, doc="True = consented, False = revoked")

    # Consent versioning (for audit trail)
    consent_version = Column(
        String(20), default="1.0", nullable=False,
        doc="Version of consent terms agreed to",
    )
    consent_text_hash = Column(
        String(64), nullable=True,
        doc="SHA-256 hash of the consent text shown to the worker",
    )

    # Language the consent was presented in
    language = Column(String(5), default="sw", nullable=False)

    # Revocation
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(Text, nullable=True)

    # Metadata
    channel = Column(
        String(20), nullable=True,
        doc="Channel where consent was given (whatsapp, app, sms, voice)",
    )
    ip_address = Column(String(45), nullable=True)
    device_id = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_worker_consent_active", "worker_id", "consent_type", "granted"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Invoice Model
# ═══════════════════════════════════════════════════════════════════════════════


class Invoice(Base):
    """
    Outcome-based invoice.

    Generated when an outcome is verified with sufficient attribution
    confidence. Links to the outcome that triggered billing.
    """
    __tablename__ = "outcome_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number = Column(
        String(30), unique=True, nullable=False,
        doc="Human-readable invoice number (e.g., INV-2026-000001)",
    )
    outcome_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outcomes.id", ondelete="SET NULL"),
        nullable=True,
    )
    worker_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Amounts
    amount_kes = Column(Float, nullable=False, doc="Invoice amount in KES")
    base_fee_kes = Column(Float, nullable=True, doc="Base fee before adjustments")
    outcome_bonus_kes = Column(Float, nullable=True, doc="Outcome-linked bonus amount")
    tax_kes = Column(Float, default=0.0, nullable=False, doc="Tax amount (16% VAT)")
    total_kes = Column(Float, nullable=False, doc="Total including tax")

    # Billing model
    billing_model = Column(
        String(50), nullable=False,
        doc="How the fee is calculated (percentage_of_impact, flat_fee, savings_share)",
    )
    billing_details = Column(
        JSON, nullable=True,
        doc="Detailed breakdown of how the amount was calculated",
    )

    # Status
    status = Column(
        Enum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False, index=True,
    )

    # Dates
    issued_at = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    # Payment
    payment_method = Column(String(30), nullable=True, doc="mpesa, bank, airtel_money")
    payment_reference = Column(String(100), nullable=True)
    mpesa_receipt = Column(String(50), nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    invoice_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_outcome_invoices_worker_status", "worker_id", "status"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Attribution Control Group Model
# ═══════════════════════════════════════════════════════════════════════════════


class AttributionControlGroup(Base):
    """
    Control group member for propensity score matching.

    Stores anonymized outcome data from similar workers who did NOT
    receive a specific recommendation, enabling causal inference.
    """
    __tablename__ = "attribution_control_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    outcome_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outcomes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    control_worker_hash = Column(
        String(64), nullable=False,
        doc="SHA-256 hash of control worker ID (anonymized)",
    )

    # Matched characteristics
    business_type = Column(String(50), nullable=False)
    location_geohash = Column(String(10), nullable=True)
    baseline_revenue = Column(Float, nullable=True)
    baseline_margin = Column(Float, nullable=True)
    propensity_score = Column(
        Float, nullable=True,
        doc="Propensity score (probability of receiving recommendation)",
    )

    # Outcome for control group member
    control_outcome_value = Column(Float, nullable=True)
    control_outcome_achieved = Column(Boolean, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_attr_control_outcome", "outcome_id"),
    )
