"""
Loan Intelligence Service — Record, track, predict, and manage loans.

Core capabilities:
- Record loans with purpose verification
- ROI tracking: is the loan generating returns?
- Repayment scheduling with reminders
- Default risk prediction (logistic regression)
- Integration with Alama Score
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker_features import LoanRecord, LoanRepayment, LoanROICheckin

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Repayment Nudges
# ─────────────────────────────────────────────────────────────────────────────

REPAYMENT_NUDGES = {
    "good_day": {
        "sw": "Umepata vizuri leo! Weka KSh {amount} kwa mkopo. Streak: siku {streak}.",
        "en": "Great earnings today! Set aside KSh {amount} for your loan. Streak: {streak} days.",
    },
    "bad_day": {
        "sw": "Leo imekuwa ngumu. Usijali — kesho tutajaribu tena. Mkopo baki KSh {remaining}.",
        "en": "Tough day. Don't worry — we'll try again tomorrow. Loan remaining: KSh {remaining}.",
    },
    "streak_milestone": {
        "sw": "Siku {streak} mfululizo umelipa! Usivunje rekodi yako!",
        "en": "{streak} days in a row of payments! Don't break the streak!",
    },
    "almost_done": {
        "sw": "Baki KSh {remaining} tu! Unaweza kumaliza wiki hii!",
        "en": "Only KSh {remaining} left! You can finish this week!",
    },
    "loan_complete": {
        "sw": "Hongera! Umemaliza mkopo wako! Alama Score yako imeongezeka!",
        "en": "Congratulations! You've completed your loan! Your Alama Score has increased!",
    },
    "default_warning": {
        "sw": "Wiki 2 bila malipo. Je, kuna tatizo? Tuongee — tunaweza kubadilisha mpango.",
        "en": "2 weeks without payment. Is there a problem? Let's talk — we can adjust the plan.",
    },
    "purpose_diverted": {
        "sw": "Tumeona umetumia pesa ya mkopo kwa mambo mengine. Hii inaweza kuathiri malipo yako.",
        "en": "We noticed loan funds were used for other purposes. This may affect your repayment.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Loan CRUD & Management
# ─────────────────────────────────────────────────────────────────────────────


async def record_loan(
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
    """Record a new loan with purpose and repayment plan."""

    total_due = round(principal * (1 + interest_rate), 2)

    # Auto-generate due date if not set (default: 30 days)
    if due_date is None:
        due_date = date.today() + timedelta(days=30)

    # Calculate suggested repayment
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

    # Run initial default risk prediction
    risk = await predict_default_risk(db, loan)

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


async def record_repayment(
    db: AsyncSession,
    loan_id: UUID,
    user_id: UUID,
    amount: float,
    method: str = "manual",
) -> Dict[str, Any]:
    """Record a repayment toward a loan."""

    result = await db.execute(
        select(LoanRecord).where(
            and_(LoanRecord.id == loan_id, LoanRecord.user_id == user_id)
        )
    )
    loan = result.scalar_one_or_none()
    if not loan:
        return {"error": "Loan not found"}

    # Record repayment
    repayment = LoanRepayment(
        loan_id=loan_id,
        amount=amount,
        method=method,
        suggested=(method == "auto_set_aside"),
        accepted=True,
    )
    db.add(repayment)

    # Update loan
    new_repaid = loan.amount_repaid + amount
    today = date.today()

    # Update streak
    last_repay_result = await db.execute(
        select(LoanRepayment.recorded_at)
        .where(LoanRepayment.loan_id == loan_id)
        .order_by(LoanRepayment.recorded_at.desc())
        .limit(1)
    )
    last_repay = last_repay_result.scalar_one_or_none()

    if last_repay:
        days_since = (today - last_repay.date()).days if hasattr(last_repay, 'date') else 1
        if days_since <= 1:
            loan.current_repayment_streak += 1
        elif days_since <= 2:
            # Allow 1-day gap
            loan.current_repayment_streak += 1
        else:
            loan.current_repayment_streak = 1
    else:
        loan.current_repayment_streak = 1

    if loan.current_repayment_streak > loan.best_repayment_streak:
        loan.best_repayment_streak = loan.current_repayment_streak

    loan.amount_repaid = round(new_repaid, 2)

    # Check completion
    completed = new_repaid >= loan.total_due
    if completed:
        loan.status = "completed"
        loan.completed_at = datetime.now(timezone.utc)

    # Build response
    remaining = max(0, loan.total_due - new_repaid)
    progress_pct = round((new_repaid / loan.total_due) * 100, 1)

    nudges = []
    if completed:
        nudges.append(REPAYMENT_NUDGES["loan_complete"])
    elif remaining < loan.repayment_amount_per_period * 2:
        nudges.append(REPAYMENT_NUDGES["almost_done"])
    elif loan.current_repayment_streak >= 7:
        nudges.append(REPAYMENT_NUDGES["streak_milestone"])

    return {
        "loan_id": str(loan.id),
        "amount_paid": amount,
        "total_repaid": round(new_repaid, 2),
        "total_due": loan.total_due,
        "remaining": round(remaining, 2),
        "progress_pct": progress_pct,
        "streak": loan.current_repayment_streak,
        "completed": completed,
        "nudges": nudges,
    }


async def get_loan_status(
    db: AsyncSession,
    user_id: UUID,
    loan_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Get loan status with ROI and repayment summary."""

    if loan_id:
        result = await db.execute(
            select(LoanRecord).where(
                and_(LoanRecord.id == loan_id, LoanRecord.user_id == user_id)
            )
        )
    else:
        result = await db.execute(
            select(LoanRecord).where(
                and_(LoanRecord.user_id == user_id, LoanRecord.status == "active")
            ).order_by(LoanRecord.created_at.desc()).limit(1)
        )

    loan = result.scalar_one_or_none()
    if not loan:
        return {"error": "No active loan found"}

    remaining = max(0, loan.total_due - loan.amount_repaid)
    progress_pct = round((loan.amount_repaid / loan.total_due) * 100, 1) if loan.total_due > 0 else 0

    # ROI calculation
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

    # Days remaining
    days_remaining = (loan.due_date - date.today()).days if loan.due_date else None
    overdue = days_remaining is not None and days_remaining < 0

    # Risk assessment
    risk = await predict_default_risk(db, loan)

    # Recent repayments
    repayments_result = await db.execute(
        select(LoanRepayment)
        .where(LoanRepayment.loan_id == loan.id)
        .order_by(LoanRepayment.recorded_at.desc())
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


async def record_roi_checkin(
    db: AsyncSession,
    loan_id: UUID,
    user_id: UUID,
    sales_attributed: float,
    notes: Optional[str] = None,
    checkin_type: str = "manual",
) -> Dict[str, Any]:
    """Record an ROI check-in for a loan."""

    result = await db.execute(
        select(LoanRecord).where(
            and_(LoanRecord.id == loan_id, LoanRecord.user_id == user_id)
        )
    )
    loan = result.scalar_one_or_none()
    if not loan:
        return {"error": "Loan not found"}

    checkin = LoanROICheckin(
        loan_id=loan_id,
        sales_attributed=sales_attributed,
        checkin_date=date.today(),
        checkin_type=checkin_type,
        notes=notes,
    )
    db.add(checkin)

    # Update cumulative sales on loan
    loan.sales_attributed = (loan.sales_attributed or 0) + sales_attributed
    loan.last_roi_check = datetime.now(timezone.utc)

    total_sales = loan.sales_attributed
    roi_value = total_sales - loan.principal
    roi_pct = round((roi_value / loan.principal) * 100, 1) if loan.principal > 0 else 0

    return {
        "loan_id": str(loan.id),
        "checkin_sales": sales_attributed,
        "total_sales_attributed": round(total_sales, 2),
        "roi_value": round(roi_value, 2),
        "roi_pct": roi_pct,
        "status": "profitable" if roi_value > 0 else "not_yet_profitable",
        "message_sw": (
            f"Mkopo wako umepata KSh {total_sales:,.0f} kwenye mauzo. "
            f"{'Faida: KSh ' + f'{roi_value:,.0f}' if roi_value > 0 else 'Bado haujafikia malengo.'}"
        ),
    }


async def predict_default_risk(
    db: AsyncSession,
    loan: LoanRecord,
) -> Dict[str, Any]:
    """
    Predict default risk using a simple logistic regression-inspired model.

    Features: repayment streak, days since disbursal, purpose,
    amount repaid %, days until due.
    """

    # Feature extraction
    today = date.today()
    days_active = (today - loan.disbursed_at.date()).days if loan.disbursed_at else 0
    repayment_pct = (loan.amount_repaid / loan.total_due * 100) if loan.total_due > 0 else 0
    days_to_due = (loan.due_date - today).days if loan.due_date else 30
    streak = loan.current_repayment_streak or 0

    # Simple risk scoring (logistic-inspired)
    # Base risk starts at 0.3 (30%)
    risk_score = 0.30

    # Repayment progress reduces risk
    if repayment_pct >= 75:
        risk_score -= 0.20
    elif repayment_pct >= 50:
        risk_score -= 0.15
    elif repayment_pct >= 25:
        risk_score -= 0.08

    # Streak reduces risk
    if streak >= 14:
        risk_score -= 0.10
    elif streak >= 7:
        risk_score -= 0.05

    # Purpose affects risk
    purpose_risk = {
        "stock": -0.05,       # Productive purpose
        "equipment": -0.05,   # Productive purpose
        "improvement": -0.03, # Somewhat productive
        "emergency": 0.08,    # Higher risk — no ROI
        "education": 0.03,    # Medium risk — long-term ROI
        "other": 0.05,        # Unknown purpose
    }
    risk_score += purpose_risk.get(loan.purpose, 0)

    # Overdue increases risk
    if days_to_due < 0:
        risk_score += 0.15
    elif days_to_due < 7:
        risk_score += 0.05

    # Days active without repayment increases risk
    if days_active > 7 and repayment_pct == 0:
        risk_score += 0.10

    # Clamp to [0, 1]
    risk_score = max(0.0, min(1.0, risk_score))

    # Determine risk level
    if risk_score < 0.2:
        risk_level = "low"
    elif risk_score < 0.4:
        risk_level = "medium"
    elif risk_score < 0.6:
        risk_level = "high"
    else:
        risk_level = "critical"

    # Update loan record
    loan.default_probability = round(risk_score, 3)
    loan.risk_level = risk_level

    # Alama Score impact estimation
    alama_impact = 0
    if loan.status == "completed":
        alama_impact = 20  # Full repayment bonus
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


async def get_repayment_schedule(
    db: AsyncSession,
    loan_id: UUID,
    user_id: UUID,
) -> Dict[str, Any]:
    """Generate a repayment schedule for a loan."""

    result = await db.execute(
        select(LoanRecord).where(
            and_(LoanRecord.id == loan_id, LoanRecord.user_id == user_id)
        )
    )
    loan = result.scalar_one_or_none()
    if not loan:
        return {"error": "Loan not found"}

    remaining = max(0, loan.total_due - loan.amount_repaid)
    if remaining <= 0:
        return {"status": "completed", "message": "Loan already fully repaid"}

    today = date.today()
    days_to_due = max(1, (loan.due_date - today).days) if loan.due_date else 30
    weeks_to_due = max(1, days_to_due / 7)

    # Generate schedule options
    daily_amount = round(remaining / days_to_due, 0)
    weekly_amount = round(remaining / weeks_to_due, 0)

    schedule = {
        "loan_id": str(loan.id),
        "remaining": round(remaining, 2),
        "due_date": str(loan.due_date) if loan.due_date else None,
        "days_remaining": days_to_due,
        "options": {
            "daily": {
                "amount": daily_amount,
                "periods": days_to_due,
                "total": round(daily_amount * days_to_due, 2),
            },
            "weekly": {
                "amount": weekly_amount,
                "periods": round(weeks_to_due),
                "total": round(weekly_amount * round(weeks_to_due), 2),
            },
            "flexible": {
                "min_per_payment": round(remaining * 0.05, 0),  # 5% minimum
                "suggested": loan.repayment_amount_per_period,
                "note": "Pay when you earn, minimum KSh {0:,.0f}".format(remaining * 0.05),
            },
        },
        "current_plan": {
            "type": loan.repayment_type,
            "frequency": loan.repayment_frequency,
            "amount": loan.repayment_amount_per_period,
        },
    }

    return schedule
