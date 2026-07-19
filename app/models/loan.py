"""
Loan Manager Models — Dedicated loan management with purpose verification.

Supports Africa's informal economy workers with:
- Loan tracking with purpose categories aligned to real use cases
- Purpose verification via spending analysis
- ROI tracking for productive loans
- Behavioral nudge infrastructure (commitment devices, social proof)
- Alama Score (credit scoring) integration

Purpose categories reflect actual informal worker loan patterns:
- Business: stock purchase, equipment, business expansion
- Personal: family needs, celebrations, household
- Emergency: medical, theft, natural disaster
- Education: school fees, training, skill development
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
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

# ═══════════════════════════════════════════════════════════════════════════════
# Purpose Categories — Aligned to informal worker reality
# ═══════════════════════════════════════════════════════════════════════════════

PURPOSE_CATEGORIES = {
    "Business": {
        "sw": "Biashara",
        "en": "Business",
        "subcategories": ["stock", "equipment", "expansion", "working_capital"],
        "expected_roi_range": (0.15, 0.50),
        "default_risk_modifier": -0.05,  # Productive use reduces risk
        "description_sw": "Mkopo wa biashara — unatarajia kurudi faida",
        "description_en": "Business loan — expects profit returns",
    },
    "Personal": {
        "sw": "Binafsi",
        "en": "Personal",
        "subcategories": ["family", "household", "celebration", "transport"],
        "expected_roi_range": (0.0, 0.0),
        "default_risk_modifier": 0.03,
        "description_sw": "Mkopo wa matumizi binafsi",
        "description_en": "Personal consumption loan",
    },
    "Emergency": {
        "sw": "Dharura",
        "en": "Emergency",
        "subcategories": ["medical", "theft", "disaster", "legal"],
        "expected_roi_range": (0.0, 0.0),
        "default_risk_modifier": 0.08,
        "description_sw": "Mkopo wa dharura — hakuna faida inayotarajiwa",
        "description_en": "Emergency loan — no expected ROI",
    },
    "Education": {
        "sw": "Elimu",
        "en": "Education",
        "subcategories": ["school_fees", "training", "certification", "books"],
        "expected_roi_range": (0.10, 0.30),
        "default_risk_modifier": -0.02,
        "description_sw": "Mkopo wa elimu — faida ya muda mrefu",
        "description_en": "Education loan — long-term ROI",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Nudge Templates
# ═══════════════════════════════════════════════════════════════════════════════

BEHAVIORAL_NUDGES = {
    "commitment_device": {
        "prompt_sw": "Andika ahadi yako: Nitarejesha KSh {amount} kila {frequency}",
        "prompt_en": "Write your commitment: I will repay KSh {amount} every {frequency}",
        "science": "Written commitments increase follow-through by 33% (Cialdini)",
    },
    "social_proof": {
        "template_sw": "Wafanyabiashara {pct}% waliomaliza mkopo wao walikuwa na Alama Score ya juu!",
        "template_en": "{pct}% of business owners who completed their loan had higher Alama Scores!",
        "science": "Social proof leverages conformity bias",
    },
    "loss_aversion": {
        "template_sw": "Usiporejesha, Alama Score yako itapungua pointi {points}. Fikiria fursa utakazopoteza!",
        "template_en": "If you don't repay, your Alama Score drops {points} points. Think of the opportunities you'll lose!",
        "science": "Losses feel 2x stronger than gains (Kahneman & Tversky)",
    },
    "streak_protection": {
        "template_sw": "Uko kwenye mfululizo wa siku {streak}! Usivunje rekodi — lipa leo!",
        "template_en": "You're on a {streak}-day streak! Don't break it — pay today!",
        "science": "Streak mechanics leverage consistency bias",
    },
    "end_effect": {
        "template_sw": "Baki KSh {remaining} tu! Maliza mkopo wako wiki hii!",
        "template_en": "Only KSh {remaining} left! Finish your loan this week!",
        "science": "Endowed progress effect accelerates completion",
    },
    "purpose_alignment": {
        "template_sw": "Uliomba mkopo kwa {purpose}. Je, umetumia kwa hiyo kazi? Tafadhali weka sawa.",
        "template_en": "You borrowed for {purpose}. Have you used it for that? Please verify.",
        "science": "Purpose tracking creates accountability",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Loan Model
# ═══════════════════════════════════════════════════════════════════════════════


class Loan(Base):
    """
    Core loan record with purpose verification and behavioral tracking.

    Designed for Africa's informal economy where:
    - Loans are often for business stock (expected ROI > 0)
    - Present bias causes repayment failures
    - Mental accounting helps workers earmark funds
    - Default rate target: <8% with purpose verification

    Integrates with Alama Score for credit scoring feedback loop.
    """

    __tablename__ = "loans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Loan Details ──────────────────────────────────────────────────
    amount = Column(Float, nullable=False, doc="Loan principal in local currency")
    currency = Column(String(3), nullable=False, default="KES")
    purpose = Column(
        String(50),
        nullable=False,
        doc="Purpose category: Business, Personal, Emergency, Education",
    )
    purpose_subcategory = Column(
        String(50), nullable=True,
        doc="Subcategory within purpose (e.g., stock, medical, school_fees)",
    )
    purpose_description = Column(
        Text, nullable=True,
        doc="Free-text description of intended use",
    )
    lender = Column(
        String(200), nullable=False,
        doc="Loan source: M-Shwari, KCB M-Pesa, chama, bank, manual",
    )
    interest_rate = Column(
        Float, nullable=False, default=0.0,
        doc="Interest rate as decimal (0.15 = 15%)",
    )

    # ── Timeline ──────────────────────────────────────────────────────
    start_date = Column(Date, nullable=False, doc="Loan disbursement date")
    end_date = Column(Date, nullable=False, doc="Expected full repayment date")
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # ── Status ────────────────────────────────────────────────────────
    status = Column(
        String(20),
        nullable=False,
        default="active",
        doc="active, completed, defaulted, restructured",
    )

    # ── Financial Tracking ────────────────────────────────────────────
    total_due = Column(Float, nullable=False, doc="Principal + total interest")
    amount_repaid = Column(Float, nullable=False, default=0.0)

    # ── ROI Tracking (for Business loans) ─────────────────────────────
    sales_attributed = Column(
        Float, nullable=True, default=0.0,
        doc="Total sales attributed to this loan",
    )
    roi_pct = Column(Float, nullable=True, doc="Return on investment percentage")
    last_roi_check = Column(DateTime(timezone=True), nullable=True)

    # ── Repayment Behavior ────────────────────────────────────────────
    repayment_frequency = Column(
        String(20), nullable=True, default="weekly",
        doc="daily, weekly, biweekly, monthly, flexible",
    )
    suggested_payment_amount = Column(Float, nullable=True)
    current_streak = Column(Integer, nullable=False, default=0)
    best_streak = Column(Integer, nullable=False, default=0)
    last_repayment_date = Column(Date, nullable=True)

    # ── Commitment Device ─────────────────────────────────────────────
    commitment_text = Column(
        Text, nullable=True,
        doc="Worker's written commitment (behavioral nudge)",
    )
    commitment_date = Column(DateTime(timezone=True), nullable=True)
    accountability_partner_id = Column(
        UUID(as_uuid=True), nullable=True,
        doc="Optional accountability partner (social proof)",
    )

    # ── Risk Assessment ───────────────────────────────────────────────
    default_probability = Column(Float, nullable=True, doc="Predicted PD 0-1")
    risk_level = Column(String(20), nullable=True, doc="low, medium, high, critical")
    risk_last_updated = Column(DateTime(timezone=True), nullable=True)

    # ── Alama Score Integration ───────────────────────────────────────
    alama_score_at_start = Column(Integer, nullable=True)
    alama_score_impact = Column(
        Integer, nullable=True, default=0,
        doc="Points gained/lost from this loan behavior",
    )

    # ── Behavioral Nudge State ────────────────────────────────────────
    nudges_sent = Column(
        JSON, nullable=True, default=list,
        doc="History of nudge types sent: ['commitment_device', 'streak_protection', ...]",
    )
    last_nudge_at = Column(DateTime(timezone=True), nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_loan_user_status", "user_id", "status"),
        Index("idx_loan_user_active", "user_id", "status", "end_date"),
        Index("idx_loan_purpose", "purpose"),
        Index("idx_loan_due", "end_date"),
        Index("idx_loan_created", "created_at"),
        CheckConstraint(
            "purpose IN ('Business', 'Personal', 'Emergency', 'Education')",
            name="ck_loan_purpose_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'completed', 'defaulted', 'restructured')",
            name="ck_loan_status_valid",
        ),
        CheckConstraint("amount > 0", name="ck_loan_amount_positive"),
        CheckConstraint("interest_rate >= 0", name="ck_loan_rate_non_negative"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LoanRepayment Model
# ═══════════════════════════════════════════════════════════════════════════════


class LoanRepayment(Base):
    """
    Individual repayment transaction toward a loan.

    Tracks repayment behavior for streak calculation,
    behavioral nudge timing, and Alama Score updates.
    """

    __tablename__ = "loan_repayment_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Float, nullable=False, doc="Repayment amount")
    date = Column(
        Date, nullable=False,
        doc="Date the repayment was made",
    )
    method = Column(
        String(20), nullable=False, default="manual",
        doc="manual, mpesa, auto_set_aside, cash, chama",
    )
    notes = Column(Text, nullable=True)

    # Streak context at time of repayment
    streak_day = Column(Integer, nullable=True, doc="Streak count after this repayment")
    was_suggested = Column(
        Boolean, default=False,
        doc="Was this a system-suggested repayment?",
    )

    # Behavioral context
    nudge_type = Column(
        String(50), nullable=True,
        doc="Nudge that prompted this repayment, if any",
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_repay_loan_date", "loan_id", "date"),
        Index("idx_repay_created", "created_at"),
        CheckConstraint("amount > 0", name="ck_repay_amount_positive"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PurposeVerification Model
# ═══════════════════════════════════════════════════════════════════════════════


class PurposeVerification(Base):
    """
    Tracks loan purpose verification and ROI alignment.

    Research shows: Default <8% with purpose verification.
    This model tracks whether loan funds are being used as intended,
    enabling early intervention when purpose drift is detected.

    ROI tracking for Business loans measures whether the loan
    is generating returns (sales_attributed vs principal).
    """

    __tablename__ = "purpose_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Purpose verification
    purpose_category = Column(
        String(50), nullable=False,
        doc="Business, Personal, Emergency, Education",
    )
    purpose_subcategory = Column(String(50), nullable=True)
    declared_purpose = Column(Text, nullable=False, doc="What the worker said they'd use it for")

    # Verification status
    verification_status = Column(
        String(20), nullable=False, default="pending",
        doc="pending, verified, drifted, unverifiable",
    )
    verification_method = Column(
        String(30), nullable=True,
        doc="transaction_analysis, self_report, photo_proof, agent_check",
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # ROI Tracking
    expected_roi_pct = Column(
        Float, nullable=True,
        doc="Expected ROI based on purpose category",
    )
    actual_roi_pct = Column(Float, nullable=True, doc="Actual ROI achieved")
    roi_tracking = Column(
        JSON, nullable=True,
        doc='[{"date": "2026-06-15", "sales": 2000, "cumulative_roi": 0.15}, ...]',
    )
    last_roi_update = Column(DateTime(timezone=True), nullable=True)

    # Purpose drift detection
    drift_detected = Column(Boolean, default=False)
    drift_severity = Column(
        String(20), nullable=True,
        doc="none, minor, moderate, severe",
    )
    drift_details = Column(
        Text, nullable=True,
        doc="Description of how purpose was diverted",
    )
    drift_detected_at = Column(DateTime(timezone=True), nullable=True)

    # Outcome
    purpose_alignment_score = Column(
        Float, nullable=True,
        doc="0-1 score: how well actual usage matches declared purpose",
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_pv_loan", "loan_id"),
        Index("idx_pv_status", "verification_status"),
        Index("idx_pv_drift", "drift_detected"),
        UniqueConstraint("loan_id", name="uq_pv_loan"),
    )
