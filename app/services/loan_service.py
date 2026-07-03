"""
Loan Manager Service — Record, track, predict, and manage loans.

Core capabilities for Africa's informal economy workers:
- Record loans with purpose verification (research: <8% default with verification)
- ROI tracking: Is the loan generating returns for business loans?
- Repayment scheduling with behavioral nudges
- Default risk prediction using Polars-based analysis
- Purpose alignment verification
- Alama Score (credit scoring) integration

Behavioral economics principles applied:
- Commitment devices (written pledges increase follow-through 33%)
- Social proof (peer comparison motivates repayment)
- Loss aversion (frame non-payment as losing Alama Score points)
- Streak protection (consistency bias for daily/weekly payments)
- Endowed progress effect (show closeness to completion)
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import polars as pl
import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loan import (
    BEHAVIORAL_NUDGES,
    PURPOSE_CATEGORIES,
    Loan,
    LoanRepayment,
    PurposeVerification,
)

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Swahili Translations
# ═══════════════════════════════════════════════════════════════════════════════

SWAHILI_MESSAGES = {
    "loan_recorded": {
        "sw": "Mkopo wako wa KSh {amount:,.0f} umerekodiwa. Jumla ya kurejesha: KSh {total:,.0f} ifikapo {due}. Malipo ya {freq}: KSh {payment:,.0f}.",
        "en": "Your loan of KSh {amount:,.0f} recorded. Total to repay: KSh {total:,.0f} by {due}. {freq} payment: KSh {payment:,.0f}.",
    },
    "repayment_success": {
        "sw": "Umelipa KSh {amount:,.0f}. Baki: KSh {remaining:,.0f} ({pct}%). Streak: siku {streak}.",
        "en": "Paid KSh {amount:,.0f}. Remaining: KSh {remaining:,.0f} ({pct}%). Streak: {streak} days.",
    },
    "loan_completed": {
        "sw": "Hongera! Umemaliza mkopo wako! Alama Score yako imeongezeka pointi {points}!",
        "en": "Congratulations! Loan completed! Your Alama Score increased by {points} points!",
    },
    "default_warning": {
        "sw": "Wiki 2 bila malipo. Je, kuna tatizo? Tuongee — tunaweza kubadilisha mpango.",
        "en": "2 weeks without payment. Is there a problem? Let's talk — we can adjust the plan.",
    },
    "purpose_drift_detected": {
        "sw": "Tumeona umetumia pesa ya mkopo kwa mambo mengine. Hii inaweza kuathiri malipo yako na Alama Score.",
        "en": "We noticed loan funds were used for other purposes. This may affect your repayment and Alama Score.",
    },
    "high_risk_alert": {
        "sw": "Hatari ya kutolipa imeongezeka. Lipa KSh {amount:,.0f} leo ili kuepuka kupunguza Alama Score yako.",
        "en": "Default risk increased. Pay KSh {amount:,.0f} today to avoid losing Alama Score points.",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# record_loan — Record a new loan with purpose verification
# ═══════════════════════════════════════════════════════════════════════════════


async def record_loan(
    db: AsyncSession,
    user_id: UUID,
    amount: float,
    purpose: str,
    lender: str,
    interest_rate: float,
    start_date: date,
    end_date: date,
    purpose_subcategory: Optional[str] = None,
    purpose_description: Optional[str] = None,
    repayment_frequency: str = "weekly",
    commitment_text: Optional[str] = None,
    accountability_partner_id: Optional[UUID] = None,
    currency: str = "KES",
) -> Dict[str, Any]:
    """
    Record a new loan with purpose verification and behavioral nudges.

    Automatically:
    - Calculates total due (principal + interest)
    - Generates suggested repayment schedule
    - Creates purpose verification record
    - Runs initial default risk assessment
    - Prompts commitment device if not provided

    Args:
        db: Async database session
        user_id: Worker's UUID
        amount: Loan principal
        purpose: Category (Business, Personal, Emergency, Education)
        lender: Loan source (M-Shwari, KCB, chama, etc.)
        interest_rate: Rate as decimal (0.15 = 15%)
        start_date: Disbursement date
        end_date: Expected repayment date
        purpose_subcategory: Subcategory within purpose
        purpose_description: Free-text description
        repayment_frequency: daily, weekly, biweekly, monthly
        commitment_text: Written commitment pledge
        accountability_partner_id: Optional partner UUID
        currency: ISO currency code

    Returns:
        Loan details with schedule and initial risk assessment
    """
    # Validate purpose category
    if purpose not in PURPOSE_CATEGORIES:
        valid = list(PURPOSE_CATEGORIES.keys())
        return {
            "error": f"Invalid purpose '{purpose}'. Must be one of: {valid}",
            "error_sw": f"Madhumuni si sahihi. Lazima iwe moja ya: {valid}",
        }

    # Validate dates
    if end_date <= start_date:
        return {
            "error": "end_date must be after start_date",
            "error_sw": "tarehe ya mwisho lazima iwe baada ya tarehe ya kuanza",
        }

    # Calculate total due
    total_due = round(amount * (1 + interest_rate), 2)

    # Calculate suggested payment
    days_to_due = max(1, (end_date - start_date).days)
    weeks_to_due = max(1, days_to_due / 7)

    if repayment_frequency == "daily":
        suggested_payment = round(total_due / days_to_due, 0)
    elif repayment_frequency == "weekly":
        suggested_payment = round(total_due / weeks_to_due, 0)
    elif repayment_frequency == "biweekly":
        suggested_payment = round(total_due / max(1, weeks_to_due / 2), 0)
    else:  # monthly
        months_to_due = max(1, days_to_due / 30)
        suggested_payment = round(total_due / months_to_due, 0)

    # Create loan record
    loan = Loan(
        user_id=user_id,
        amount=amount,
        currency=currency,
        purpose=purpose,
        purpose_subcategory=purpose_subcategory,
        purpose_description=purpose_description,
        lender=lender,
        interest_rate=interest_rate,
        start_date=start_date,
        end_date=end_date,
        total_due=total_due,
        amount_repaid=0.0,
        status="active",
        repayment_frequency=repayment_frequency,
        suggested_payment_amount=suggested_payment,
        commitment_text=commitment_text,
        commitment_date=datetime.now(timezone.utc) if commitment_text else None,
        accountability_partner_id=accountability_partner_id,
    )
    db.add(loan)
    await db.flush()

    # Create purpose verification record
    cat_info = PURPOSE_CATEGORIES[purpose]
    expected_roi = None
    if cat_info["expected_roi_range"][1] > 0:
        expected_roi = round(
            (cat_info["expected_roi_range"][0] + cat_info["expected_roi_range"][1]) / 2 * 100,
            1,
        )

    pv = PurposeVerification(
        loan_id=loan.id,
        purpose_category=purpose,
        purpose_subcategory=purpose_subcategory,
        declared_purpose=purpose_description or f"{purpose} - {purpose_subcategory or 'general'}",
        verification_status="pending",
        expected_roi_pct=expected_roi,
        purpose_alignment_score=1.0,  # Start optimistic
    )
    db.add(pv)

    # Run initial risk assessment
    risk = await _assess_risk(db, loan)

    # Build commitment device prompt if no commitment made
    nudge = None
    if not commitment_text:
        nudge = {
            "type": "commitment_device",
            "prompt_sw": BEHAVIORAL_NUDGES["commitment_device"]["prompt_sw"].format(
                amount=suggested_payment, frequency=repayment_frequency
            ),
            "prompt_en": BEHAVIORAL_NUDGES["commitment_device"]["prompt_en"].format(
                amount=suggested_payment, frequency=repayment_frequency
            ),
        }

    return {
        "loan_id": str(loan.id),
        "amount": amount,
        "interest_rate": interest_rate,
        "total_due": total_due,
        "purpose": purpose,
        "purpose_sw": cat_info["sw"],
        "lender": lender,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "repayment_frequency": repayment_frequency,
        "suggested_payment": suggested_payment,
        "risk_assessment": risk,
        "purpose_verification": {
            "status": "pending",
            "expected_roi_pct": expected_roi,
        },
        "commitment_device": nudge,
        "message_sw": SWAHILI_MESSAGES["loan_recorded"]["sw"].format(
            amount=amount, total=total_due, due=end_date,
            freq=repayment_frequency, payment=suggested_payment,
        ),
        "message_en": SWAHILI_MESSAGES["loan_recorded"]["en"].format(
            amount=amount, total=total_due, due=end_date,
            freq=repayment_frequency, payment=suggested_payment,
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# record_repayment — Record a repayment with behavioral nudges
# ═══════════════════════════════════════════════════════════════════════════════


async def record_repayment(
    db: AsyncSession,
    loan_id: UUID,
    amount: float,
    date: date,
    method: str = "manual",
    notes: Optional[str] = None,
    nudge_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Record a repayment toward a loan.

    Updates streak tracking, detects completion, generates behavioral
    nudges based on context (streak milestones, almost done, etc.),
    and calculates Alama Score impact.

    Args:
        db: Async database session
        loan_id: Loan UUID
        amount: Repayment amount
        date: Date of repayment
        method: Payment method (manual, mpesa, cash, etc.)
        notes: Optional notes
        nudge_type: Nudge that prompted this repayment

    Returns:
        Repayment confirmation with status, nudges, and Alama Score impact
    """
    result = await db.execute(select(Loan).where(Loan.id == loan_id))
    loan = result.scalar_one_or_none()
    if not loan:
        return {"error": "Loan not found", "error_sw": "Mkopo haujapatikana"}

    if loan.status != "active":
        return {
            "error": f"Loan is {loan.status}, cannot record repayment",
            "error_sw": f"Mkopo ni {loan.status}, hawezi kurekodi malipo",
        }

    if amount <= 0:
        return {"error": "Amount must be positive", "error_sw": "Kiasi lazima kiwe chanya"}

    # Record repayment
    repayment = LoanRepayment(
        loan_id=loan_id,
        amount=amount,
        date=date,
        method=method,
        notes=notes,
        was_suggested=(method == "auto_set_aside"),
        nudge_type=nudge_type,
    )
    db.add(repayment)

    # Update streak
    if loan.last_repayment_date:
        days_since = (date - loan.last_repayment_date).days
        if days_since <= 2:  # Allow 1-day gap
            loan.current_streak += 1
        else:
            loan.current_streak = 1
    else:
        loan.current_streak = 1

    loan.last_repayment_date = date
    if loan.current_streak > loan.best_streak:
        loan.best_streak = loan.current_streak

    # Update amount repaid
    new_repaid = round(loan.amount_repaid + amount, 2)
    loan.amount_repaid = new_repaid

    # Check completion
    completed = new_repaid >= loan.total_due
    alama_impact = 0
    if completed:
        loan.status = "completed"
        loan.completed_at = datetime.now(timezone.utc)
        alama_impact = 20  # Full repayment bonus
    else:
        # Partial progress Alama impact
        progress_pct = (new_repaid / loan.total_due) * 100
        if progress_pct >= 75:
            alama_impact = 15
        elif progress_pct >= 50:
            alama_impact = 10
        elif progress_pct >= 25:
            alama_impact = 5

    loan.alama_score_impact = (loan.alama_score_impact or 0) + alama_impact

    # Generate contextual nudges
    remaining = max(0, loan.total_due - new_repaid)
    progress_pct = round((new_repaid / loan.total_due) * 100, 1)
    nudges = []

    if completed:
        nudges.append({
            "type": "loan_completed",
            "message_sw": SWAHILI_MESSAGES["loan_completed"]["sw"].format(points=alama_impact),
            "message_en": SWAHILI_MESSAGES["loan_completed"]["en"].format(points=alama_impact),
        })
    else:
        # Almost done nudge (endowed progress effect)
        if remaining < (loan.suggested_payment_amount or 0) * 2:
            nudges.append({
                "type": "end_effect",
                "message_sw": BEHAVIORAL_NUDGES["end_effect"]["template_sw"].format(
                    remaining=f"{remaining:,.0f}"
                ),
                "message_en": BEHAVIORAL_NUDGES["end_effect"]["template_en"].format(
                    remaining=f"{remaining:,.0f}"
                ),
            })
        # Streak milestone nudge
        if loan.current_streak >= 7:
            nudges.append({
                "type": "streak_protection",
                "message_sw": BEHAVIORAL_NUDGES["streak_protection"]["template_sw"].format(
                    streak=loan.current_streak
                ),
                "message_en": BEHAVIORAL_NUDGES["streak_protection"]["template_en"].format(
                    streak=loan.current_streak
                ),
            })
        # Social proof (periodic)
        if loan.current_repayment_streak == 10 or (new_repaid > 0 and progress_pct == 50):
            nudges.append({
                "type": "social_proof",
                "message_sw": BEHAVIORAL_NUDGES["social_proof"]["template_sw"].format(pct=78),
                "message_en": BEHAVIORAL_NUDGES["social_proof"]["template_en"].format(pct=78),
            })

    # Record streak on repayment
    repayment.streak_day = loan.current_streak

    # Update repayment streak on loan
    loan.current_repayment_streak = loan.current_streak

    return {
        "loan_id": str(loan.id),
        "amount_paid": amount,
        "total_repaid": new_repaid,
        "total_due": loan.total_due,
        "remaining": round(remaining, 2),
        "progress_pct": progress_pct,
        "streak": loan.current_streak,
        "best_streak": loan.best_streak,
        "completed": completed,
        "alama_score_impact": alama_impact,
        "nudges": nudges,
        "message_sw": SWAHILI_MESSAGES["repayment_success"]["sw"].format(
            amount=amount, remaining=remaining, pct=progress_pct, streak=loan.current_streak,
        ),
        "message_en": SWAHILI_MESSAGES["repayment_success"]["en"].format(
            amount=amount, remaining=remaining, pct=progress_pct, streak=loan.current_streak,
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# get_loan_status — Get loan status and ROI
# ═══════════════════════════════════════════════════════════════════════════════


async def get_loan_status(
    db: AsyncSession,
    loan_id: UUID,
) -> Dict[str, Any]:
    """
    Get comprehensive loan status including ROI, risk, and behavioral data.

    Returns:
    - Financial status (principal, repaid, remaining, progress)
    - ROI tracking for Business loans
    - Risk assessment
    - Repayment streak and history
    - Behavioral nudges
    - Swahili/English voice summaries
    """
    result = await db.execute(select(Loan).where(Loan.id == loan_id))
    loan = result.scalar_one_or_none()
    if not loan:
        return {"error": "Loan not found", "error_sw": "Mkopo haujapatikana"}

    remaining = max(0, loan.total_due - loan.amount_repaid)
    progress_pct = round(
        (loan.amount_repaid / loan.total_due) * 100, 1
    ) if loan.total_due > 0 else 0

    # Days remaining
    today = date.today()
    days_remaining = (loan.end_date - today).days
    overdue = days_remaining < 0

    # ROI calculation for business loans
    roi = None
    if loan.purpose == "Business" and loan.sales_attributed and loan.sales_attributed > 0:
        roi_value = loan.sales_attributed - loan.amount
        roi_pct = round((roi_value / loan.amount) * 100, 1) if loan.amount > 0 else 0
        roi = {
            "sales_attributed": loan.sales_attributed,
            "profit": round(roi_value, 2),
            "roi_pct": roi_pct,
            "status": "profitable" if roi_value > 0 else "not_yet_profitable",
            "status_sw": "in faida" if roi_value > 0 else "bado haijafikia faida",
        }

    # Risk assessment
    risk = await _assess_risk(db, loan)

    # Recent repayments
    repayments_result = await db.execute(
        select(LoanRepayment)
        .where(LoanRepayment.loan_id == loan.id)
        .order_by(LoanRepayment.date.desc())
        .limit(10)
    )
    recent_repayments = [
        {
            "amount": r.amount,
            "date": str(r.date),
            "method": r.method,
            "streak_day": r.streak_day,
        }
        for r in repayments_result.scalars().all()
    ]

    # Generate nudges based on current state
    nudges = []
    if overdue and loan.status == "active":
        nudges.append({
            "type": "loss_aversion",
            "message_sw": SWAHILI_MESSAGES["high_risk_alert"]["sw"].format(
                amount=loan.suggested_payment_amount or 0
            ),
            "message_en": SWAHILI_MESSAGES["high_risk_alert"]["en"].format(
                amount=loan.suggested_payment_amount or 0
            ),
        })
    elif loan.current_streak >= 7:
        nudges.append({
            "type": "streak_protection",
            "message_sw": BEHAVIORAL_NUDGES["streak_protection"]["template_sw"].format(
                streak=loan.current_streak
            ),
            "message_en": BEHAVIORAL_NUDGES["streak_protection"]["template_en"].format(
                streak=loan.current_streak
            ),
        })

    return {
        "loan_id": str(loan.id),
        "amount": loan.amount,
        "interest_rate": loan.interest_rate,
        "total_due": loan.total_due,
        "amount_repaid": loan.amount_repaid,
        "remaining": round(remaining, 2),
        "progress_pct": progress_pct,
        "purpose": loan.purpose,
        "purpose_sw": PURPOSE_CATEGORIES.get(loan.purpose, {}).get("sw", loan.purpose),
        "lender": loan.lender,
        "status": loan.status,
        "start_date": str(loan.start_date),
        "end_date": str(loan.end_date),
        "days_remaining": days_remaining,
        "overdue": overdue,
        "repayment_frequency": loan.repayment_frequency,
        "suggested_payment": loan.suggested_payment_amount,
        "streak": loan.current_streak,
        "best_streak": loan.best_streak,
        "roi": roi,
        "risk": risk,
        "alama_score_impact": loan.alama_score_impact or 0,
        "commitment_text": loan.commitment_text,
        "recent_repayments": recent_repayments,
        "nudges": nudges,
        "voice_summary_sw": (
            f"Mkopo: KSh {loan.amount:,.0f} kutoka {loan.lender}. "
            f"Umelipa: KSh {loan.amount_repaid:,.0f} ya KSh {loan.total_due:,.0f} ({progress_pct}%). "
            f"Baki: KSh {remaining:,.0f}. "
            f"{'Siku ' + str(days_remaining) + ' zimebaki.' if days_remaining > 0 else 'Umepitwa na wakati!' if overdue else ''}"
        ),
        "voice_summary_en": (
            f"Loan: KSh {loan.amount:,.0f} from {loan.lender}. "
            f"Repaid: KSh {loan.amount_repaid:,.0f} of KSh {loan.total_due:,.0f} ({progress_pct}%). "
            f"Remaining: KSh {remaining:,.0f}. "
            f"{'Days remaining: ' + str(days_remaining) + '.' if days_remaining > 0 else 'Overdue!' if overdue else ''}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# get_default_risk — Analyze default risk using Polars
# ═══════════════════════════════════════════════════════════════════════════════


async def get_default_risk(
    db: AsyncSession,
    user_id: UUID,
) -> Dict[str, Any]:
    """
    Analyze default risk for a user across all active loans using Polars.

    Uses Polars DataFrame operations for:
    - Portfolio-level risk aggregation
    - Repayment pattern analysis
    - Purpose-based risk weighting
    - Behavioral feature extraction

    Returns:
    - Overall risk score and level
    - Per-loan risk breakdown
    - Alama Score impact projection
    - Recommended actions with behavioral nudges
    """
    # Fetch all active loans for user
    result = await db.execute(
        select(Loan).where(
            and_(Loan.user_id == user_id, Loan.status == "active")
        )
    )
    loans = result.scalars().all()

    if not loans:
        return {
            "user_id": str(user_id),
            "risk_score": 0.0,
            "risk_level": "none",
            "message_sw": "Huna mkopo wowote unaofanya kazi.",
            "message_en": "You have no active loans.",
        }

    # Fetch all repayments for these loans
    loan_ids = [loan.id for loan in loans]
    repayments_result = await db.execute(
        select(LoanRepayment).where(LoanRepayment.loan_id.in_(loan_ids))
    )
    repayments = repayments_result.scalars().all()

    # Build Polars DataFrames for analysis
    today = date.today()

    loans_data = {
        "loan_id": [str(l.id) for l in loans],
        "amount": [l.amount for l in loans],
        "total_due": [l.total_due for l in loans],
        "amount_repaid": [l.amount_repaid for l in loans],
        "interest_rate": [l.interest_rate for l in loans],
        "purpose": [l.purpose for l in loans],
        "start_date": [l.start_date for l in loans],
        "end_date": [l.end_date for l in loans],
        "days_active": [(today - l.start_date).days for l in loans],
        "days_to_due": [(l.end_date - today).days for l in loans],
        "current_streak": [l.current_streak for l in loans],
        "best_streak": [l.best_streak for l in loans],
        "suggested_payment": [l.suggested_payment_amount or 0 for l in loans],
    }

    loans_df = pl.DataFrame(loans_data)

    # Calculate derived features
    loans_df = loans_df.with_columns([
        # Repayment progress percentage
        (pl.col("amount_repaid") / pl.col("total_due") * 100).alias("repayment_pct"),
        # Daily repayment rate
        (pl.col("amount_repaid") / pl.col("days_active").clip(lower_bound=1)).alias("daily_repay_rate"),
        # Required daily rate to finish on time
        ((pl.col("total_due") - pl.col("amount_repaid")) / pl.col("days_to_due").clip(lower_bound=1)).alias("required_daily_rate"),
    ])

    # Repayment frequency analysis
    repayments_data = {
        "loan_id": [str(r.loan_id) for r in repayments],
        "amount": [r.amount for r in repayments],
        "date": [r.date for r in repayments],
        "method": [r.method for r in repayments],
    }

    if repayments_data["loan_id"]:
        repay_df = pl.DataFrame(repayments_data)

        # Calculate average days between payments per loan
        repay_freq = (
            repay_df.sort(["loan_id", "date"])
            .with_columns([
                pl.col("date").diff().over("loan_id").alias("days_between"),
            ])
            .group_by("loan_id")
            .agg([
                pl.col("days_between").mean().alias("avg_days_between_payments"),
                pl.col("amount").mean().alias("avg_payment_amount"),
                pl.col("amount").count().alias("payment_count"),
            ])
        )

        loans_df = loans_df.join(repay_freq, on="loan_id", how="left")
    else:
        loans_df = loans_df.with_columns([
            pl.lit(None).alias("avg_days_between_payments"),
            pl.lit(None).alias("avg_payment_amount"),
            pl.lit(0).alias("payment_count"),
        ])

    # Fill nulls
    loans_df = loans_df.with_columns([
        pl.col("avg_days_between_payments").fill_null(999),
        pl.col("avg_payment_amount").fill_null(0),
        pl.col("payment_count").fill_null(0),
    ])

    # Calculate risk score per loan
    purpose_risk_map = {
        "Business": -0.05,
        "Personal": 0.03,
        "Emergency": 0.08,
        "Education": -0.02,
    }

    risk_scores = []
    for row in loans_df.iter_rows(named=True):
        score = 0.30  # Base risk

        # Repayment progress reduces risk
        pct = row["repayment_pct"]
        if pct >= 75:
            score -= 0.20
        elif pct >= 50:
            score -= 0.15
        elif pct >= 25:
            score -= 0.08

        # Streak reduces risk
        streak = row["current_streak"]
        if streak >= 14:
            score -= 0.10
        elif streak >= 7:
            score -= 0.05

        # Purpose modifier
        score += purpose_risk_map.get(row["purpose"], 0)

        # Overdue increases risk
        days_to_due = row["days_to_due"]
        if days_to_due < 0:
            score += 0.15 + min(0.10, abs(days_to_due) * 0.005)
        elif days_to_due < 7:
            score += 0.05

        # No repayment yet after 7+ days
        if row["days_active"] > 7 and row["repayment_pct"] == 0:
            score += 0.10

        # Repayment pace vs required
        if row["required_daily_rate"] > 0 and row["daily_repay_rate"] > 0:
            pace_ratio = row["daily_repay_rate"] / row["required_daily_rate"]
            if pace_ratio < 0.5:
                score += 0.08
            elif pace_ratio > 1.2:
                score -= 0.05

        # Clamp
        score = max(0.0, min(1.0, score))
        risk_scores.append(round(score, 3))

    loans_df = loans_df.with_columns([
        pl.Series("risk_score", risk_scores),
    ])

    # Assign risk levels
    loans_df = loans_df.with_columns([
        pl.when(pl.col("risk_score") < 0.2).then(pl.lit("low"))
        .when(pl.col("risk_score") < 0.4).then(pl.lit("medium"))
        .when(pl.col("risk_score") < 0.6).then(pl.lit("high"))
        .otherwise(pl.lit("critical"))
        .alias("risk_level"),
    ])

    # Portfolio-level risk (weighted by amount)
    total_amount = loans_df["amount"].sum()
    portfolio_risk = (
        loans_df.select(
            (pl.col("risk_score") * pl.col("amount")).sum() / total_amount
        ).item()
        if total_amount > 0 else 0.0
    )

    # Update loan records with risk scores
    for row in loans_df.iter_rows(named=True):
        loan_id = row["loan_id"]
        await db.execute(
            update(Loan)
            .where(Loan.id == loan_id)
            .values(
                default_probability=row["risk_score"],
                risk_level=row["risk_level"],
                risk_last_updated=datetime.now(timezone.utc),
            )
        )

    # Determine overall risk level
    if portfolio_risk < 0.2:
        overall_level = "low"
    elif portfolio_risk < 0.4:
        overall_level = "medium"
    elif portfolio_risk < 0.6:
        overall_level = "high"
    else:
        overall_level = "critical"

    # Alama Score impact
    critical_count = loans_df.filter(pl.col("risk_level") == "critical").height
    high_count = loans_df.filter(pl.col("risk_level") == "high").height
    alama_impact = 0
    if critical_count > 0:
        alama_impact = -30 * critical_count
    elif high_count > 0:
        alama_impact = -15 * high_count

    # Generate recommended actions
    actions = []
    worst_loan = loans_df.sort("risk_score", descending=True).head(1)
    if not worst_loan.is_empty():
        wl = worst_loan.to_dicts()[0]
        if wl["risk_level"] in ("high", "critical"):
            actions.append({
                "action": "make_payment",
                "priority": "urgent",
                "loan_id": wl["loan_id"],
                "amount": wl["suggested_payment"],
                "message_sw": SWAHILI_MESSAGES["high_risk_alert"]["sw"].format(
                    amount=wl["suggested_payment"]
                ),
                "message_en": SWAHILI_MESSAGES["high_risk_alert"]["en"].format(
                    amount=wl["suggested_payment"]
                ),
            })
        if wl["current_streak"] >= 7:
            actions.append({
                "action": "protect_streak",
                "priority": "high",
                "loan_id": wl["loan_id"],
                "message_sw": BEHAVIORAL_NUDGES["streak_protection"]["template_sw"].format(
                    streak=wl["current_streak"]
                ),
                "message_en": BEHAVIORAL_NUDGES["streak_protection"]["template_en"].format(
                    streak=wl["current_streak"]
                ),
            })

    # Build per-loan breakdown
    loan_details = []
    for row in loans_df.iter_rows(named=True):
        loan_details.append({
            "loan_id": row["loan_id"],
            "amount": row["amount"],
            "purpose": row["purpose"],
            "repayment_pct": round(row["repayment_pct"], 1),
            "risk_score": row["risk_score"],
            "risk_level": row["risk_level"],
            "days_to_due": row["days_to_due"],
            "streak": row["current_streak"],
        })

    return {
        "user_id": str(user_id),
        "portfolio_risk_score": round(portfolio_risk, 3),
        "portfolio_risk_level": overall_level,
        "active_loans": len(loans),
        "alama_score_impact": alama_impact,
        "loan_details": loan_details,
        "recommended_actions": actions,
        "nudges": [
            nudge for nudge in [
                {
                    "type": "loss_aversion",
                    "condition": overall_level in ("high", "critical"),
                    "message_sw": BEHAVIORAL_NUDGES["loss_aversion"]["template_sw"].format(
                        points=abs(alama_impact)
                    ),
                    "message_en": BEHAVIORAL_NUDGES["loss_aversion"]["template_en"].format(
                        points=abs(alama_impact)
                    ),
                },
            ] if nudge.get("condition", True)
        ],
        "analysis_method": "polars_dataframe",
        "features_analyzed": [
            "repayment_progress", "streak", "purpose_risk",
            "overdue_status", "repayment_pace", "portfolio_weight",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# get_purpose_verification — Verify loan purpose alignment
# ═══════════════════════════════════════════════════════════════════════════════


async def get_purpose_verification(
    db: AsyncSession,
    loan_id: UUID,
) -> Dict[str, Any]:
    """
    Verify loan purpose alignment and track ROI for Business loans.

    Research shows default rate drops to <8% with purpose verification.
    This function:
    - Retrieves purpose verification status
    - Calculates ROI alignment for Business loans
    - Detects purpose drift (funds used for other purposes)
    - Generates accountability nudges

    Returns:
    - Verification status and alignment score
    - ROI tracking data for Business loans
    - Drift detection results
    - Behavioral nudge for accountability
    """
    # Get loan
    loan_result = await db.execute(select(Loan).where(Loan.id == loan_id))
    loan = loan_result.scalar_one_or_none()
    if not loan:
        return {"error": "Loan not found", "error_sw": "Mkopo haujapatikana"}

    # Get purpose verification record
    pv_result = await db.execute(
        select(PurposeVerification).where(PurposeVerification.loan_id == loan_id)
    )
    pv = pv_result.scalar_one_or_none()
    if not pv:
        return {
            "error": "No purpose verification record found",
            "error_sw": "Hakuna rekodi ya uthibitisho wa madhumuni",
        }

    cat_info = PURPOSE_CATEGORIES.get(pv.purpose_category, {})

    # ROI tracking for Business loans
    roi_tracking = None
    if pv.purpose_category == "Business":
        expected_roi_range = cat_info.get("expected_roi_range", (0, 0))
        actual_roi = pv.actual_roi_pct or 0
        expected_roi = pv.expected_roi_pct or 0

        roi_tracking = {
            "expected_roi_pct": expected_roi,
            "actual_roi_pct": actual_roi,
            "on_track": actual_roi >= expected_roi_range[0] * 100 if expected_roi_range[0] > 0 else None,
            "history": pv.roi_tracking or [],
            "last_update": str(pv.last_roi_update) if pv.last_roi_update else None,
        }

    # Drift analysis
    drift_analysis = {
        "detected": pv.drift_detected,
        "severity": pv.drift_severity or "none",
        "details": pv.drift_details,
        "detected_at": str(pv.drift_detected_at) if pv.drift_detected_at else None,
    }

    # Generate accountability nudge
    nudge = None
    if pv.verification_status == "pending":
        nudge = {
            "type": "purpose_alignment",
            "message_sw": BEHAVIORAL_NUDGES["purpose_alignment"]["template_sw"].format(
                purpose=cat_info.get("sw", pv.purpose_category)
            ),
            "message_en": BEHAVIORAL_NUDGES["purpose_alignment"]["template_en"].format(
                purpose=cat_info.get("en", pv.purpose_category)
            ),
        }
    elif pv.drift_detected:
        nudge = {
            "type": "purpose_drift",
            "message_sw": SWAHILI_MESSAGES["purpose_drift_detected"]["sw"],
            "message_en": SWAHILI_MESSAGES["purpose_drift_detected"]["en"],
        }

    return {
        "loan_id": str(loan_id),
        "purpose_category": pv.purpose_category,
        "purpose_category_sw": cat_info.get("sw", pv.purpose_category),
        "purpose_subcategory": pv.purpose_subcategory,
        "declared_purpose": pv.declared_purpose,
        "verification_status": pv.verification_status,
        "verification_method": pv.verification_method,
        "verified_at": str(pv.verified_at) if pv.verified_at else None,
        "purpose_alignment_score": pv.purpose_alignment_score,
        "roi_tracking": roi_tracking,
        "drift_analysis": drift_analysis,
        "expected_behavior": {
            "description_sw": cat_info.get("description_sw", ""),
            "description_en": cat_info.get("description_en", ""),
            "expected_roi_range": cat_info.get("expected_roi_range"),
        },
        "nudge": nudge,
        "default_rate_with_verification": "<8%",
        "default_rate_without_verification": "~15-20%",
        "insight_sw": (
            f"Uthibitisho wa madhumuni unapunguza hatari ya kutolipa hadi chini ya 8%. "
            f"{'Mkopo wako uko njiani.' if pv.purpose_alignment_score and pv.purpose_alignment_score > 0.7 else 'Tafadhali hakikisha unatumia mkopo kwa madhumuni yake.'}"
        ),
        "insight_en": (
            f"Purpose verification reduces default risk to below 8%. "
            f"{'Your loan is on track.' if pv.purpose_alignment_score and pv.purpose_alignment_score > 0.7 else 'Please ensure the loan is used for its intended purpose.'}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# get_repayment_schedule — Generate repayment schedule
# ═══════════════════════════════════════════════════════════════════════════════


async def get_repayment_schedule(
    db: AsyncSession,
    loan_id: UUID,
) -> Dict[str, Any]:
    """
    Generate a repayment schedule with multiple options.

    Provides daily, weekly, and flexible payment plans
    with behavioral nudge context for each option.

    Returns:
    - Remaining balance and due date
    - Multiple schedule options (daily, weekly, flexible)
    - Current plan vs recommended
    - Behavioral framing for each option
    """
    result = await db.execute(select(Loan).where(Loan.id == loan_id))
    loan = result.scalar_one_or_none()
    if not loan:
        return {"error": "Loan not found", "error_sw": "Mkopo haujapatikana"}

    remaining = max(0, loan.total_due - loan.amount_repaid)
    if remaining <= 0:
        return {
            "loan_id": str(loan.id),
            "status": "completed",
            "status_sw": "Imekamilika",
            "message_sw": "Mkopo wako umekwishalipwa!",
            "message_en": "Your loan is fully repaid!",
        }

    today = date.today()
    days_to_due = max(1, (loan.end_date - today).days)
    weeks_to_due = max(1, days_to_due / 7)
    months_to_due = max(1, days_to_due / 30)

    daily_amount = round(remaining / days_to_due, 0)
    weekly_amount = round(remaining / weeks_to_due, 0)
    biweekly_amount = round(remaining / max(1, weeks_to_due / 2), 0)
    monthly_amount = round(remaining / months_to_due, 0)

    # Build detailed schedule for current frequency
    schedule_items = []
    running_balance = remaining
    freq = loan.repayment_frequency or "weekly"

    if freq == "daily":
        periods = days_to_due
        per_period = daily_amount
    elif freq == "weekly":
        periods = round(weeks_to_due)
        per_period = weekly_amount
    elif freq == "biweekly":
        periods = round(weeks_to_due / 2)
        per_period = biweekly_amount
    else:
        periods = round(months_to_due)
        per_period = monthly_amount

    for i in range(min(periods, 12)):  # Cap at 12 items for display
        if freq == "daily":
            pay_date = today + timedelta(days=i + 1)
        elif freq == "weekly":
            pay_date = today + timedelta(weeks=i + 1)
        elif freq == "biweekly":
            pay_date = today + timedelta(weeks=(i + 1) * 2)
        else:
            pay_date = today + timedelta(days=(i + 1) * 30)

        payment = min(per_period, running_balance)
        running_balance = max(0, running_balance - payment)

        schedule_items.append({
            "period": i + 1,
            "date": str(pay_date),
            "amount": round(payment, 0),
            "remaining_after": round(running_balance, 0),
        })

        if running_balance <= 0:
            break

    # Loss aversion framing
    loss_frame = None
    if loan.alama_score_impact is not None and loan.alama_score_impact >= 0:
        potential_loss = max(10, loan.alama_score_impact)
        loss_frame = {
            "message_sw": BEHAVIORAL_NUDGES["loss_aversion"]["template_sw"].format(
                points=potential_loss
            ),
            "message_en": BEHAVIORAL_NUDGES["loss_aversion"]["template_en"].format(
                points=potential_loss
            ),
        }

    return {
        "loan_id": str(loan.id),
        "remaining": round(remaining, 2),
        "due_date": str(loan.end_date),
        "days_remaining": days_to_due,
        "current_plan": {
            "frequency": freq,
            "amount": loan.suggested_payment_amount,
        },
        "options": {
            "daily": {
                "amount": daily_amount,
                "periods": days_to_due,
                "total": round(daily_amount * days_to_due, 2),
                "nudge_sw": f"Lipa KSh {daily_amount:,.0f} kila siku. Njia rahisi!",
                "nudge_en": f"Pay KSh {daily_amount:,.0f} daily. Easiest path!",
            },
            "weekly": {
                "amount": weekly_amount,
                "periods": round(weeks_to_due),
                "total": round(weekly_amount * round(weeks_to_due), 2),
                "nudge_sw": f"Lipa KSh {weekly_amount:,.0f} kila wiki. Inayofaa!",
                "nudge_en": f"Pay KSh {weekly_amount:,.0f} weekly. Practical!",
            },
            "biweekly": {
                "amount": biweekly_amount,
                "periods": round(weeks_to_due / 2),
                "total": round(biweekly_amount * round(weeks_to_due / 2), 2),
                "nudge_sw": f"Lipa KSh {biweekly_amount:,.0f} kila wiki 2.",
                "nudge_en": f"Pay KSh {biweekly_amount:,.0f} every 2 weeks.",
            },
            "monthly": {
                "amount": monthly_amount,
                "periods": round(months_to_due),
                "total": round(monthly_amount * round(months_to_due), 2),
                "nudge_sw": f"Lipa KSh {monthly_amount:,.0f} kila mwezi.",
                "nudge_en": f"Pay KSh {monthly_amount:,.0f} monthly.",
            },
        },
        "detailed_schedule": schedule_items,
        "loss_aversion_nudge": loss_frame,
        "end_effect_nudge": {
            "type": "end_effect",
            "visible": remaining < (loan.suggested_payment_amount or 0) * 3,
            "message_sw": BEHAVIORAL_NUDGES["end_effect"]["template_sw"].format(
                remaining=f"{remaining:,.0f}"
            ),
            "message_en": BEHAVIORAL_NUDGES["end_effect"]["template_en"].format(
                remaining=f"{remaining:,.0f}"
            ),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Internal Helpers
# ═══════════════════════════════════════════════════════════════════════════════


async def _assess_risk(db: AsyncSession, loan: Loan) -> Dict[str, Any]:
    """Internal risk assessment for a single loan."""
    today = date.today()
    days_active = max(0, (today - loan.start_date).days)
    repayment_pct = (loan.amount_repaid / loan.total_due * 100) if loan.total_due > 0 else 0
    days_to_due = (loan.end_date - today).days
    streak = loan.current_streak or 0

    # Base risk
    risk_score = 0.30

    # Repayment progress
    if repayment_pct >= 75:
        risk_score -= 0.20
    elif repayment_pct >= 50:
        risk_score -= 0.15
    elif repayment_pct >= 25:
        risk_score -= 0.08

    # Streak
    if streak >= 14:
        risk_score -= 0.10
    elif streak >= 7:
        risk_score -= 0.05

    # Purpose modifier
    cat_info = PURPOSE_CATEGORIES.get(loan.purpose, {})
    risk_score += cat_info.get("default_risk_modifier", 0)

    # Overdue
    if days_to_due < 0:
        risk_score += 0.15
    elif days_to_due < 7:
        risk_score += 0.05

    # No repayment after 7+ days
    if days_active > 7 and repayment_pct == 0:
        risk_score += 0.10

    risk_score = max(0.0, min(1.0, risk_score))

    if risk_score < 0.2:
        risk_level = "low"
    elif risk_score < 0.4:
        risk_level = "medium"
    elif risk_score < 0.6:
        risk_level = "high"
    else:
        risk_level = "critical"

    # Alama Score impact
    alama_impact = 0
    if loan.status == "completed":
        alama_impact = 20
    elif repayment_pct >= 75:
        alama_impact = 15
    elif repayment_pct >= 50:
        alama_impact = 10
    elif repayment_pct >= 25:
        alama_impact = 5
    if risk_level == "critical":
        alama_impact = -30

    # Update loan risk fields
    loan.default_probability = round(risk_score, 3)
    loan.risk_level = risk_level
    loan.risk_last_updated = datetime.now(timezone.utc)

    return {
        "risk_score": round(risk_score, 3),
        "risk_level": risk_level,
        "alama_score_impact": alama_impact,
        "features": {
            "days_active": days_active,
            "repayment_pct": round(repayment_pct, 1),
            "streak": streak,
            "days_to_due": days_to_due,
            "purpose": loan.purpose,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy Wrappers — Backward compatibility with worker_features.py
# ═══════════════════════════════════════════════════════════════════════════════


async def record_loan_legacy(
    db: AsyncSession,
    user_id: UUID,
    principal: float,
    interest_rate: float,
    purpose: str,
    source: str = "manual",
    purpose_details: Optional[Dict] = None,
    disbursed_at: Optional[datetime] = None,
    due_date: Optional[date] = None,
    repayment_type: str = "flexible",
    repayment_frequency: str = "weekly",
    commitment_text: Optional[str] = None,
    currency: str = "KES",
) -> Dict[str, Any]:
    """Legacy wrapper for backward compatibility with worker_features.py."""
    from app.models.worker_features import LoanRecord

    total_due = round(principal * (1 + interest_rate), 2)
    if due_date is None:
        due_date = date.today() + timedelta(days=30)

    days_to_due = max(1, (due_date - date.today()).days)
    weeks_to_due = max(1, days_to_due / 7)
    if repayment_frequency == "daily":
        suggested_amount = round(total_due / days_to_due, 0)
    elif repayment_frequency == "weekly":
        suggested_amount = round(total_due / weeks_to_due, 0)
    else:
        suggested_amount = round(total_due / max(1, weeks_to_due), 0)

    loan = LoanRecord(
        user_id=user_id,
        source=source,
        principal=principal,
        interest_rate=interest_rate,
        total_due=total_due,
        amount_repaid=0,
        currency=currency,
        purpose=purpose,
        purpose_details=purpose_details,
        status="active",
        disbursed_at=disbursed_at or datetime.now(timezone.utc),
        due_date=due_date,
        repayment_type=repayment_type,
        repayment_frequency=repayment_frequency,
        repayment_amount_per_period=suggested_amount,
        commitment_made=bool(commitment_text),
        commitment_text=commitment_text,
    )
    db.add(loan)
    await db.flush()

    risk = await predict_default_risk_legacy(db, loan)

    return {
        "loan_id": str(loan.id),
        "principal": principal,
        "interest_rate": interest_rate,
        "total_due": total_due,
        "purpose": purpose,
        "due_date": str(due_date),
        "repayment_frequency": repayment_frequency,
        "suggested_payment": suggested_amount,
        "risk_assessment": risk,
        "message_sw": (
            f"Mkopo wako wa KSh {principal:,.0f} umerekodiwa. "
            f"Jumla ya kurejesha: KSh {total_due:,.0f} ifikapo {due_date}. "
            f"Malipo ya {repayment_frequency}: KSh {suggested_amount:,.0f}."
        ),
        "message_en": (
            f"Your loan of KSh {principal:,.0f} recorded. "
            f"Total to repay: KSh {total_due:,.0f} by {due_date}. "
            f"{repayment_frequency.title()} payment: KSh {suggested_amount:,.0f}."
        ),
    }


async def get_loan_status_legacy(
    db: AsyncSession,
    user_id: UUID,
    loan_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Legacy wrapper for backward compatibility with worker_features.py."""
    from app.models.worker_features import LoanRecord as LegacyLoan, LoanRepayment as LegacyRepayment

    if loan_id:
        result = await db.execute(
            select(LegacyLoan).where(
                and_(LegacyLoan.id == loan_id, LegacyLoan.user_id == user_id)
            )
        )
    else:
        result = await db.execute(
            select(LegacyLoan).where(
                and_(LegacyLoan.user_id == user_id, LegacyLoan.status == "active")
            ).order_by(LegacyLoan.created_at.desc()).limit(1)
        )

    loan = result.scalar_one_or_none()
    if not loan:
        return {"error": "No active loan found"}

    remaining = max(0, loan.total_due - loan.amount_repaid)
    progress_pct = round((loan.amount_repaid / loan.total_due) * 100, 1) if loan.total_due > 0 else 0

    roi = None
    if loan.purpose in ("stock", "equipment", "improvement") and loan.sales_attributed:
        roi_value = loan.sales_attributed - loan.principal
        roi_pct = round((roi_value / loan.principal) * 100, 1) if loan.principal > 0 else 0
        roi = {
            "sales_attributed": loan.sales_attributed,
            "profit": round(roi_value, 2),
            "roi_pct": roi_pct,
            "status": "profitable" if roi_value > 0 else "not_yet_profitable",
        }

    days_remaining = (loan.due_date - date.today()).days if loan.due_date else None
    overdue = days_remaining is not None and days_remaining < 0

    risk = await predict_default_risk_legacy(db, loan)

    repayments_result = await db.execute(
        select(LegacyRepayment)
        .where(LegacyRepayment.loan_id == loan.id)
        .order_by(LegacyRepayment.recorded_at.desc())
        .limit(10)
    )
    recent_repayments = [
        {
            "amount": r.amount,
            "method": r.method,
            "date": str(r.recorded_at.date()) if r.recorded_at else None,
        }
        for r in repayments_result.scalars().all()
    ]

    return {
        "loan_id": str(loan.id),
        "source": loan.source,
        "principal": loan.principal,
        "interest_rate": loan.interest_rate,
        "total_due": loan.total_due,
        "amount_repaid": loan.amount_repaid,
        "remaining": round(remaining, 2),
        "progress_pct": progress_pct,
        "purpose": loan.purpose,
        "status": loan.status,
        "due_date": str(loan.due_date) if loan.due_date else None,
        "days_remaining": days_remaining,
        "overdue": overdue,
        "repayment_streak": loan.current_repayment_streak,
        "best_streak": loan.best_repayment_streak,
        "roi": roi,
        "risk": risk,
        "recent_repayments": recent_repayments,
        "voice_summary_sw": (
            f"Mkopo: KSh {loan.principal:,.0f}. "
            f"Umelipa: KSh {loan.amount_repaid:,.0f} ya KSh {loan.total_due:,.0f} ({progress_pct}%). "
            f"Baki: KSh {remaining:,.0f}. "
            f"{'Siku ' + str(days_remaining) + ' zimebaki.' if days_remaining and days_remaining > 0 else 'Umepitwa na wakati!' if overdue else ''}"
        ),
    }


async def predict_default_risk_legacy(
    db: AsyncSession,
    loan,
) -> Dict[str, Any]:
    """Legacy risk prediction for LoanRecord model."""
    today = date.today()
    days_active = (today - loan.disbursed_at.date()).days if loan.disbursed_at else 0
    repayment_pct = (loan.amount_repaid / loan.total_due * 100) if loan.total_due > 0 else 0
    days_to_due = (loan.due_date - today).days if loan.due_date else 30
    streak = loan.current_repayment_streak or 0

    risk_score = 0.30
    if repayment_pct >= 75:
        risk_score -= 0.20
    elif repayment_pct >= 50:
        risk_score -= 0.15
    elif repayment_pct >= 25:
        risk_score -= 0.08

    if streak >= 14:
        risk_score -= 0.10
    elif streak >= 7:
        risk_score -= 0.05

    purpose_risk = {
        "stock": -0.05, "equipment": -0.05, "improvement": -0.03,
        "emergency": 0.08, "education": 0.03, "other": 0.05,
    }
    risk_score += purpose_risk.get(loan.purpose, 0)

    if days_to_due < 0:
        risk_score += 0.15
    elif days_to_due < 7:
        risk_score += 0.05

    if days_active > 7 and repayment_pct == 0:
        risk_score += 0.10

    risk_score = max(0.0, min(1.0, risk_score))

    if risk_score < 0.2:
        risk_level = "low"
    elif risk_score < 0.4:
        risk_level = "medium"
    elif risk_score < 0.6:
        risk_level = "high"
    else:
        risk_level = "critical"

    loan.default_probability = round(risk_score, 3)
    loan.risk_level = risk_level

    alama_impact = 0
    if loan.status == "completed":
        alama_impact = 20
    elif repayment_pct >= 75:
        alama_impact = 15
    elif repayment_pct >= 50:
        alama_impact = 10
    elif repayment_pct >= 25:
        alama_impact = 5
    if risk_level == "critical":
        alama_impact = -30

    return {
        "risk_score": round(risk_score, 3),
        "risk_level": risk_level,
        "alama_score_impact": alama_impact,
        "features": {
            "days_active": days_active,
            "repayment_pct": round(repayment_pct, 1),
            "streak": streak,
            "days_to_due": days_to_due,
            "purpose": loan.purpose,
        },
    }
