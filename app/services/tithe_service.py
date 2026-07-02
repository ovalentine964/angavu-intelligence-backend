"""
Tithe & Giving Service — Track giving, score consistency, detect abundance patterns.

Core capabilities:
- Record giving (tithe, offering, zakat, harambee, charity, etc.)
- Consistency scoring algorithm (weekly-based)
- Abundance pattern: correlate giving with income over time
- Monthly/annual giving reports
- Encouragement message generation (Swahili + English)
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.worker_features import TitheRecord

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Encouragement Messages
# ─────────────────────────────────────────────────────────────────────────────

ENCOURAGEMENT_MESSAGES = {
    "first_giving": {
        "sw": "Hongera! Umeanza safari ya kutoa. Mungu awabariki!",
        "en": "Congratulations! You've started your giving journey. God bless you!",
    },
    "streak_4": {
        "sw": "Wiki 4 mfululizo! Umekuwa mtoaji wa mfano.",
        "en": "4 weeks in a row! You're an exemplary giver.",
    },
    "streak_8": {
        "sw": "Wiki 8 mfululizo! Umekuwa mtoaji thabiti sana.",
        "en": "8 weeks in a row! You're a very consistent giver.",
    },
    "streak_12": {
        "sw": "Wiki 12 mfululizo! Wewe ni mfano wa kutoa. Hongera sana!",
        "en": "12 weeks in a row! You're a model of generosity. Congratulations!",
    },
    "missed_week": {
        "sw": "Wiki hii bado — kuna bado wiki 3. Unaweza kuanza leo!",
        "en": "Not this week yet — 3 weeks left. You can start today!",
    },
    "sacrifice_giving": {
        "sw": "Hii ilikuwa sadaka ya kweli — ulitoa hata wakati mgumu. Mungu anaona moyo wako.",
        "en": "This was true sacrifice — you gave even in hard times. God sees your heart.",
    },
    "income_up_giving_up": {
        "sw": "Mapato yako yameongezeka na umeongeza kutoa pia! Mzunguko wa baraka.",
        "en": "Your income grew and you increased giving too! The blessing cycle.",
    },
    "monthly_report": {
        "sw": "Ripoti yako ya mwezi iko tayari. Umekuwa mkarimu sana!",
        "en": "Your monthly report is ready. You've been very generous!",
    },
    "annual_review": {
        "sw": "Umefikia mwaka mmoja wa kutoa thabiti. Angalia jafari ulivyokua!",
        "en": "You've completed one year of consistent giving. Look how far you've come!",
    },
    "zakat_reminder": {
        "sw": "Ramadan inakaribia. Je, umehesabu zakat yako? Msaidizi inaweza kukusaidia.",
        "en": "Ramadan is approaching. Have you calculated your zakat? Msaidizi can help.",
    },
}

CONSISTENCY_RATINGS = [
    (90, "Mtoaji wa mfano", "Exemplary giver", "⭐⭐⭐⭐⭐"),
    (70, "Mtoaji thabiti", "Consistent giver", "⭐⭐⭐⭐"),
    (50, "Mtoaji anayekua", "Growing giver", "⭐⭐⭐"),
    (30, "Mtoaji mpya", "New giver", "⭐⭐"),
    (0, "Ananza safari", "Starting the journey", "⭐"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Core Service Functions
# ─────────────────────────────────────────────────────────────────────────────


async def record_giving(
    db: AsyncSession,
    user_id: UUID,
    amount: float,
    category: str = "offering",
    currency: str = "KES",
    custom_category_name: Optional[str] = None,
    recipient: Optional[str] = None,
    giving_date: Optional[date] = None,
    input_method: str = "manual",
    voice_transcript: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a giving entry and return encouragement message."""

    if giving_date is None:
        giving_date = date.today()

    record = TitheRecord(
        user_id=user_id,
        amount=amount,
        currency=currency,
        category=category,
        custom_category_name=custom_category_name,
        recipient=recipient,
        giving_date=giving_date,
        input_method=input_method,
        voice_transcript=voice_transcript,
        notes=notes,
    )
    db.add(record)
    await db.flush()

    # Get this month's total
    month_start = giving_date.replace(day=1)
    month_total_result = await db.execute(
        select(func.sum(TitheRecord.amount)).where(
            and_(
                TitheRecord.user_id == user_id,
                TitheRecord.giving_date >= month_start,
                TitheRecord.giving_date <= giving_date,
            )
        )
    )
    month_total = month_total_result.scalar() or 0

    # Check if this is the first giving record ever
    count_result = await db.execute(
        select(func.count(TitheRecord.id)).where(TitheRecord.user_id == user_id)
    )
    total_records = count_result.scalar() or 0

    # Determine encouragement
    encouragement_key = None
    if total_records <= 1:
        encouragement_key = "first_giving"

    # Get consistency for context
    consistency = await calculate_consistency_score(db, user_id, period_months=1)

    encouragement = None
    if encouragement_key and encouragement_key in ENCOURAGEMENT_MESSAGES:
        msg = ENCOURAGEMENT_MESSAGES[encouragement_key]
        encouragement = {"key": encouragement_key, "sw": msg["sw"], "en": msg["en"]}

    return {
        "record_id": str(record.id),
        "amount": amount,
        "category": category,
        "currency": currency,
        "giving_date": str(giving_date),
        "month_total": round(month_total, 2),
        "consistency": consistency,
        "encouragement": encouragement,
    }


async def calculate_consistency_score(
    db: AsyncSession,
    user_id: UUID,
    period_months: int = 1,
) -> Dict[str, Any]:
    """
    Calculate giving consistency for a user over a period.

    Score = (weeks_with_giving / total_weeks_in_period) × 100
    """

    today = date.today()
    start_date = today - timedelta(days=period_months * 30)

    result = await db.execute(
        select(TitheRecord.giving_date).where(
            and_(
                TitheRecord.user_id == user_id,
                TitheRecord.giving_date >= start_date,
                TitheRecord.giving_date <= today,
            )
        )
    )
    giving_dates = [row[0] for row in result.all()]

    total_weeks = max(1, round(period_months * 4.33))
    # Get unique ISO weeks with giving
    active_weeks = len(set(d.isocalendar()[1] for d in giving_dates)) if giving_dates else 0
    score = min(100.0, round((active_weeks / total_weeks) * 100, 1))

    # Current streak: consecutive weeks ending at current week
    current_streak = 0
    if giving_dates:
        week_nums = sorted(set(d.isocalendar()[1] for d in giving_dates), reverse=True)
        current_iso_week = today.isocalendar()[1]
        expected = current_iso_week
        for w in week_nums:
            if w == expected:
                current_streak += 1
                expected -= 1
            elif w == expected - 1:
                # Allow one-week gap
                current_streak += 1
                expected = w - 1
            else:
                break

    # Rating
    rating_sw, rating_en, stars = "Ananza safari", "Starting the journey", "⭐"
    for threshold, sw, en, s in CONSISTENCY_RATINGS:
        if score >= threshold:
            rating_sw, rating_en, stars = sw, en, s
            break

    return {
        "score": round(score),
        "active_weeks": active_weeks,
        "total_weeks": total_weeks,
        "current_streak": current_streak,
        "rating_sw": rating_sw,
        "rating_en": rating_en,
        "stars": stars,
    }


async def get_giving_report(
    db: AsyncSession,
    user_id: UUID,
    period: str = "monthly",
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate a giving report for a period.

    period: "monthly" or "annual"
    """

    today = date.today()
    if year is None:
        year = today.year

    if period == "monthly":
        if month is None:
            month = today.month
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        period_label = f"{year}-{month:02d}"
    else:  # annual
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        period_label = str(year)

    # Get all records in period
    result = await db.execute(
        select(TitheRecord).where(
            and_(
                TitheRecord.user_id == user_id,
                TitheRecord.giving_date >= start_date,
                TitheRecord.giving_date <= end_date,
            )
        )
    )
    records = result.scalars().all()

    # Aggregate by category
    by_category: Dict[str, float] = defaultdict(float)
    total = 0.0
    for r in records:
        by_category[r.category] += r.amount
        total += r.amount

    # Consistency
    months_in_period = 12 if period == "annual" else 1
    consistency = await calculate_consistency_score(db, user_id, period_months=months_in_period)

    # Best giving month (for annual)
    best_month = None
    if period == "annual":
        month_totals: Dict[int, float] = defaultdict(float)
        for r in records:
            month_totals[r.giving_date.month] += r.amount
        if month_totals:
            best_month_num = max(month_totals, key=month_totals.get)
            best_month = {
                "month": best_month_num,
                "total": round(month_totals[best_month_num], 2),
            }

    # Previous period comparison
    if period == "monthly":
        prev_start = (start_date - timedelta(days=1)).replace(day=1)
        prev_end = start_date - timedelta(days=1)
    else:
        prev_start = date(year - 1, 1, 1)
        prev_end = date(year - 1, 12, 31)

    prev_result = await db.execute(
        select(func.sum(TitheRecord.amount)).where(
            and_(
                TitheRecord.user_id == user_id,
                TitheRecord.giving_date >= prev_start,
                TitheRecord.giving_date <= prev_end,
            )
        )
    )
    prev_total = prev_result.scalar() or 0
    change = round(total - prev_total, 2)

    return {
        "period": period_label,
        "total_given": round(total, 2),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
        "record_count": len(records),
        "consistency": consistency,
        "best_month": best_month,
        "previous_period_total": round(prev_total, 2),
        "change_from_previous": change,
        "change_pct": round((change / max(prev_total, 1)) * 100, 1) if prev_total > 0 else None,
    }


async def analyze_abundance_pattern(
    db: AsyncSession,
    user_id: UUID,
    months: int = 6,
) -> Dict[str, Any]:
    """
    Analyze correlation between giving consistency and income trends.

    Returns income trend, giving trend, and insight message.
    Only runs with sufficient data (>= 3 months).
    """

    today = date.today()
    monthly_data = []

    for i in range(months):
        month_date = today - timedelta(days=30 * i)
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1) - timedelta(days=1)

        # Monthly giving
        giving_result = await db.execute(
            select(func.sum(TitheRecord.amount)).where(
                and_(
                    TitheRecord.user_id == user_id,
                    TitheRecord.giving_date >= month_start,
                    TitheRecord.giving_date <= month_end,
                )
            )
        )
        giving = giving_result.scalar() or 0

        # Monthly income (from transactions)
        income_result = await db.execute(
            select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.transaction_type == "income",
                    Transaction.timestamp >= datetime.combine(month_start, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(month_end, datetime.max.time()),
                )
            )
        )
        income = income_result.scalar() or 0

        if income > 0:
            monthly_data.append({
                "month": str(month_start),
                "income": round(float(income), 2),
                "giving": round(float(giving), 2),
                "giving_pct": round((float(giving) / float(income)) * 100, 1),
            })

    if len(monthly_data) < 3:
        return {
            "status": "insufficient_data",
            "message_sw": "Anahitaji angalau miezi 3 ya data ili kuonyesha mifumo.",
            "message_en": "Need at least 3 months of data to show patterns.",
            "months_available": len(monthly_data),
        }

    # Simple trend analysis
    income_values = [d["income"] for d in monthly_data]
    giving_values = [d["giving"] for d in monthly_data]

    income_trend = _calculate_trend(income_values)
    giving_trend = _calculate_trend(giving_values)
    avg_giving_pct = sum(d["giving_pct"] for d in monthly_data) / len(monthly_data)

    # Generate insight
    insight = _generate_abundance_insight(income_trend, giving_trend, avg_giving_pct)

    return {
        "status": "ok",
        "months_analyzed": len(monthly_data),
        "income_trend": income_trend,
        "giving_trend": giving_trend,
        "avg_giving_pct": round(avg_giving_pct, 1),
        "monthly_data": monthly_data,
        "insight": insight,
    }


async def generate_encouragement(
    db: AsyncSession,
    user_id: UUID,
    trigger: str,
    language: str = "sw",
) -> Dict[str, Any]:
    """Generate a context-aware encouragement message."""

    if trigger in ENCOURAGEMENT_MESSAGES:
        msg = ENCOURAGEMENT_MESSAGES[trigger]
        return {
            "trigger": trigger,
            "message": msg.get(language, msg["sw"]),
            "language": language,
        }

    # Fallback: generate based on current state
    consistency = await calculate_consistency_score(db, user_id, period_months=1)

    if consistency["current_streak"] >= 12:
        trigger = "streak_12"
    elif consistency["current_streak"] >= 8:
        trigger = "streak_8"
    elif consistency["current_streak"] >= 4:
        trigger = "streak_4"

    msg = ENCOURAGEMENT_MESSAGES.get(trigger, ENCOURAGEMENT_MESSAGES["first_giving"])
    return {
        "trigger": trigger,
        "message": msg.get(language, msg["sw"]),
        "language": language,
        "consistency": consistency,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _calculate_trend(values: List[float]) -> str:
    """Simple trend: compare first half average to second half average."""
    if len(values) < 2:
        return "stable"
    mid = len(values) // 2
    first_half = sum(values[:mid]) / max(mid, 1)
    second_half = sum(values[mid:]) / max(len(values) - mid, 1)
    if second_half > first_half * 1.1:
        return "increasing"
    elif second_half < first_half * 0.9:
        return "decreasing"
    return "stable"


def _generate_abundance_insight(
    income_trend: str,
    giving_trend: str,
    avg_giving_pct: float,
) -> Dict[str, str]:
    """Generate insight message from abundance pattern analysis."""

    if income_trend == "increasing" and giving_trend == "increasing":
        return {
            "sw": f"Mapato yako yameongezeka na umeongeza kutoa pia! Mzunguko wa baraka. Wastani wa kutoa ni {avg_giving_pct:.1f}% ya mapato.",
            "en": f"Your income grew and you increased giving too! The blessing cycle. Average giving is {avg_giving_pct:.1f}% of income.",
            "pattern": "blessing_cycle",
        }
    elif income_trend == "increasing" and giving_trend == "stable":
        return {
            "sw": f"Mapato yako yameongezeka lakini kutoa kumeendelea sawa. Je, ungependa kuongeza kutoa pamoja na mapato?",
            "en": f"Your income grew but giving stayed the same. Would you like to increase giving along with income?",
            "pattern": "income_outpacing_giving",
        }
    elif income_trend == "decreasing" and giving_trend == "stable":
        return {
            "sw": f"Mapato yamepungua lakini bado unatoa. Hii ni sadaka ya kweli — Mungu anaona moyo wako.",
            "en": f"Income decreased but you're still giving. This is true sacrifice — God sees your heart.",
            "pattern": "faithful_giving",
        }
    elif income_trend == "decreasing" and giving_trend == "decreasing":
        return {
            "sw": f"Na mapato na kutoa vimepungua. Hii ni ya kawaida — usijali. Muhimu ni kuendelea na nidhamu.",
            "en": f"Both income and giving decreased. This is normal — don't worry. What matters is maintaining discipline.",
            "pattern": "parallel_decline",
        }
    else:
        return {
            "sw": f"Wastani wa kutoa ni {avg_giving_pct:.1f}% ya mapato. Umekuwa na nidhamu nzuri ya kutoa.",
            "en": f"Average giving is {avg_giving_pct:.1f}% of income. You've had good giving discipline.",
            "pattern": "steady",
        }
