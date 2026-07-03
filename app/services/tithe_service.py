"""
Tithe & Giving Service — Track giving, score consistency, detect abundance patterns.

Core capabilities:
- Record giving (tithe, offering, zakat, harambee, charity, etc.)
- Consistency scoring algorithm (weekly-based)
- Abundance pattern: correlate giving with income over time using Polars
- Weekly/monthly/yearly giving reports
- Encouragement message generation (Swahili + English)

Research insight: Giving patterns predict creditworthiness better than bank balances.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import polars as pl
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.tithe import TitheRecord, TitheReport, AbundancePattern

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


async def record_tithe(
    db: AsyncSession,
    user_id: UUID,
    amount: float,
    currency: str = "KES",
    method: str = "manual",
    recipient: Optional[str] = None,
    purpose: str = "offering",
    giving_date: Optional[date] = None,
    custom_category_name: Optional[str] = None,
    voice_transcript: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Record a tithe/giving entry and return encouragement message.

    Args:
        db: Async database session
        user_id: UUID of the user recording the giving
        amount: Giving amount (must be > 0)
        currency: ISO currency code (default KES)
        method: Input method — 'manual', 'voice', or 'mpesa_parse'
        recipient: Church, mosque, person, or community name
        purpose: Giving category — 'tithe', 'offering', 'zakat', 'harambee',
                 'charity', 'building_fund', 'missions', 'custom'
        giving_date: Date of giving (defaults to today)
        custom_category_name: Custom label when purpose='custom'
        voice_transcript: Raw voice input if applicable
        notes: Optional notes

    Returns:
        Dict with record details, monthly total, consistency score,
        and encouragement message in Swahili and English.
    """
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    if giving_date is None:
        giving_date = date.today()

    record = TitheRecord(
        user_id=user_id,
        amount=amount,
        currency=currency,
        category=purpose,
        custom_category_name=custom_category_name,
        recipient=recipient,
        giving_date=giving_date,
        input_method=method,
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
    consistency = await get_consistency_score(db, user_id, period_months=1)

    encouragement = None
    if encouragement_key and encouragement_key in ENCOURAGEMENT_MESSAGES:
        msg = ENCOURAGEMENT_MESSAGES[encouragement_key]
        encouragement = {"key": encouragement_key, "sw": msg["sw"], "en": msg["en"]}

    logger.info(
        "tithe_recorded",
        user_id=str(user_id),
        amount=amount,
        currency=currency,
        purpose=purpose,
        month_total=month_total,
    )

    return {
        "record_id": str(record.id),
        "amount": amount,
        "currency": currency,
        "category": purpose,
        "recipient": recipient,
        "giving_date": str(giving_date),
        "month_total": round(month_total, 2),
        "consistency": consistency,
        "encouragement": encouragement,
    }


async def get_tithe_report(
    db: AsyncSession,
    user_id: UUID,
    period: str = "monthly",
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate a giving report for a period.

    Uses Polars for fast aggregation and analysis of giving records.

    Args:
        db: Async database session
        user_id: UUID of the user
        period: 'weekly', 'monthly', or 'yearly'
        year: Year for the report (defaults to current year)
        month: Month for monthly reports (defaults to current month)

    Returns:
        Dict with total given, breakdown by category, consistency score,
        comparison with previous period, and Swahili/English summaries.
    """
    today = date.today()
    if year is None:
        year = today.year

    # Calculate period boundaries
    if period == "weekly":
        # Current ISO week
        iso_cal = today.isocalendar()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        period_label = f"{year}-W{iso_cal.week:02d}"
    elif period == "monthly":
        if month is None:
            month = today.month
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)
        week_start = period_start
        week_end = period_end
        period_label = f"{year}-{month:02d}"
    else:  # yearly
        week_start = date(year, 1, 1)
        week_end = date(year, 12, 31)
        period_label = str(year)

    # Fetch all records in period
    result = await db.execute(
        select(TitheRecord).where(
            and_(
                TitheRecord.user_id == user_id,
                TitheRecord.giving_date >= week_start,
                TitheRecord.giving_date <= week_end,
            )
        )
    )
    records = result.scalars().all()

    if not records:
        return {
            "period": period_label,
            "period_type": period,
            "total_given": 0,
            "currency": "KES",
            "by_category": {},
            "by_recipient": {},
            "record_count": 0,
            "consistency": await get_consistency_score(db, user_id),
            "previous_period_total": 0,
            "change_from_previous": 0,
            "change_pct": None,
            "message_sw": f"Hakuna kutoa kwa kipindi hiki ({period_label}).",
            "message_en": f"No giving records for this period ({period_label}).",
        }

    # Use Polars for fast aggregation
    records_data = [
        {
            "amount": r.amount,
            "category": r.category,
            "recipient": r.recipient or "Unknown",
            "giving_date": r.giving_date,
            "currency": r.currency,
        }
        for r in records
    ]
    df = pl.DataFrame(records_data)

    # Aggregate by category
    category_agg = df.group_by("category").agg(pl.col("amount").sum().alias("total"))
    by_category = {
        row["category"]: round(row["total"], 2)
        for row in category_agg.to_dicts()
    }

    # Aggregate by recipient
    recipient_agg = df.group_by("recipient").agg(pl.col("amount").sum().alias("total"))
    by_recipient = {
        row["recipient"]: round(row["total"], 2)
        for row in recipient_agg.to_dicts()
    }

    total = round(df["amount"].sum(), 2)
    record_count = len(records)

    # Consistency
    months_in_period = {"weekly": 1, "monthly": 1, "yearly": 12}.get(period, 1)
    consistency = await get_consistency_score(db, user_id, period_months=months_in_period)

    # Previous period comparison
    if period == "weekly":
        prev_start = week_start - timedelta(days=7)
        prev_end = week_start - timedelta(days=1)
    elif period == "monthly":
        prev_start = (week_start - timedelta(days=1)).replace(day=1)
        prev_end = week_start - timedelta(days=1)
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

    # Best giving month (for yearly)
    best_month = None
    if period == "yearly":
        month_agg = df.with_columns(
            pl.col("giving_date").dt.month().alias("month_num")
        ).group_by("month_num").agg(pl.col("amount").sum().alias("total"))
        if month_agg.height > 0:
            best_row = month_agg.sort("total", descending=True).head(1).to_dicts()[0]
            best_month = {
                "month": best_row["month_num"],
                "total": round(best_row["total"], 2),
            }

    return {
        "period": period_label,
        "period_type": period,
        "total_given": total,
        "currency": records[0].currency if records else "KES",
        "by_category": by_category,
        "by_recipient": by_recipient,
        "record_count": record_count,
        "consistency": consistency,
        "best_month": best_month,
        "previous_period_total": round(prev_total, 2),
        "change_from_previous": change,
        "change_pct": round((change / max(prev_total, 1)) * 100, 1) if prev_total > 0 else None,
        "message_sw": _report_message_sw(period, total, change),
        "message_en": _report_message_en(period, total, change),
    }


async def get_abundance_pattern(
    db: AsyncSession,
    user_id: UUID,
    months: int = 6,
) -> Dict[str, Any]:
    """
    Analyze giving patterns and produce an abundance score.

    Correlates giving consistency with income trends using Polars.
    Research shows giving patterns predict creditworthiness better
    than bank balances.

    Args:
        db: Async database session
        user_id: UUID of the user
        months: Number of months to analyze (default 6)

    Returns:
        Dict with income trend, giving trend, abundance score,
        pattern classification, and Swahili/English insights.
    """
    today = date.today()
    monthly_rows = []

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
        giving = float(giving_result.scalar() or 0)

        # Monthly income (from transactions)
        income_result = await db.execute(
            select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.transaction_type == "SALE",
                    Transaction.timestamp >= datetime.combine(month_start, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(month_end, datetime.max.time()),
                )
            )
        )
        income = float(income_result.scalar() or 0)

        monthly_rows.append({
            "month": str(month_start),
            "income": round(income, 2),
            "giving": round(giving, 2),
            "giving_pct": round((giving / income) * 100, 1) if income > 0 else 0.0,
        })

    # Filter to months with income data
    months_with_income = [r for r in monthly_rows if r["income"] > 0]

    if len(months_with_income) < 3:
        return {
            "status": "insufficient_data",
            "months_available": len(months_with_income),
            "months_analyzed": 0,
            "abundance_score": None,
            "pattern": "insufficient_data",
            "income_trend": None,
            "giving_trend": None,
            "avg_giving_pct": None,
            "monthly_data": monthly_rows,
            "creditworthiness_signal": "insufficient",
            "insight": {
                "sw": "Anahitaji angalau miezi 3 ya data ili kuonyesha mifumo.",
                "en": "Need at least 3 months of data to show patterns.",
            },
        }

    # Use Polars for trend analysis
    df = pl.DataFrame(months_with_income).sort("month")

    income_values = df["income"].to_list()
    giving_values = df["giving"].to_list()
    giving_pct_values = df["giving_pct"].to_list()

    income_trend = _calculate_trend(income_values)
    giving_trend = _calculate_trend(giving_values)
    avg_giving_pct = round(sum(giving_pct_values) / len(giving_pct_values), 1)

    # Calculate abundance score (0-100)
    abundance_score = _calculate_abundance_score(
        income_trend=income_trend,
        giving_trend=giving_trend,
        avg_giving_pct=avg_giving_pct,
        consistency_months=len(months_with_income),
    )

    # Classify pattern
    pattern = _classify_pattern(income_trend, giving_trend, avg_giving_pct)

    # Creditworthiness signal based on giving patterns
    creditworthiness_signal = _assess_creditworthiness(
        abundance_score=abundance_score,
        pattern=pattern,
        avg_giving_pct=avg_giving_pct,
    )

    # Generate insight
    insight = _generate_abundance_insight(income_trend, giving_trend, avg_giving_pct, pattern)

    result = {
        "status": "ok",
        "months_analyzed": len(months_with_income),
        "income_trend": income_trend,
        "giving_trend": giving_trend,
        "avg_giving_pct": avg_giving_pct,
        "abundance_score": round(abundance_score, 1),
        "pattern": pattern,
        "creditworthiness_signal": creditworthiness_signal,
        "monthly_data": monthly_rows,
        "insight": insight,
    }

    # Cache the result
    await _cache_abundance_pattern(db, user_id, months, result)

    return result


async def get_consistency_score(
    db: AsyncSession,
    user_id: UUID,
    period_months: int = 1,
) -> Dict[str, Any]:
    """
    Calculate giving consistency for a user over a period.

    Uses Polars for efficient weekly aggregation.
    Score = (weeks_with_giving / total_weeks_in_period) × 100

    Args:
        db: Async database session
        user_id: UUID of the user
        period_months: Number of months to look back (default 1)

    Returns:
        Dict with score, active weeks, current streak, and rating
        in Swahili and English.
    """
    today = date.today()
    start_date = today - timedelta(days=period_months * 30)

    result = await db.execute(
        select(TitheRecord.giving_date, TitheRecord.amount).where(
            and_(
                TitheRecord.user_id == user_id,
                TitheRecord.giving_date >= start_date,
                TitheRecord.giving_date <= today,
            )
        )
    )
    rows = result.all()

    if not rows:
        return {
            "score": 0,
            "active_weeks": 0,
            "total_weeks": max(1, round(period_months * 4.33)),
            "current_streak": 0,
            "rating_sw": "Ananza safari",
            "rating_en": "Starting the journey",
            "stars": "⭐",
        }

    # Use Polars for efficient week extraction
    df = pl.DataFrame({
        "giving_date": [r[0] for r in rows],
        "amount": [r[1] for r in rows],
    })

    # Extract ISO week numbers
    df = df.with_columns(
        pl.col("giving_date").dt.iso_week().alias("week_num"),
        pl.col("giving_date").dt.year().alias("year"),
    )

    # Unique weeks with giving
    active_weeks_df = df.select(["year", "week_num"]).unique()
    active_weeks = active_weeks_df.height

    total_weeks = max(1, round(period_months * 4.33))
    score = min(100.0, round((active_weeks / total_weeks) * 100, 1))

    # Current streak: consecutive weeks ending at current week
    current_iso_week = today.isocalendar()[1]
    current_year = today.year

    # Get sorted unique week tuples (year, week_num) descending
    week_tuples = sorted(
        active_weeks_df.to_dicts(),
        key=lambda r: (r["year"], r["week_num"]),
        reverse=True,
    )

    current_streak = 0
    expected_week = current_iso_week
    expected_year = current_year

    for wt in week_tuples:
        if wt["year"] == expected_year and wt["week_num"] == expected_week:
            current_streak += 1
            expected_week -= 1
            if expected_week < 1:
                expected_year -= 1
                expected_week = 52  # Approximate
        elif (
            wt["year"] == expected_year
            and wt["week_num"] == expected_week - 1
        ):
            # Allow one-week gap
            current_streak += 1
            expected_week = wt["week_num"] - 1
            if expected_week < 1:
                expected_year -= 1
                expected_week = 52
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


# ─────────────────────────────────────────────────────────────────────────────
# Encouragement Generator
# ─────────────────────────────────────────────────────────────────────────────


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
    consistency = await get_consistency_score(db, user_id, period_months=1)

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
# Helpers — Trend & Pattern Analysis
# ─────────────────────────────────────────────────────────────────────────────


def _calculate_trend(values: List[float]) -> str:
    """
    Simple trend: compare first half average to second half average.
    Uses Polars for efficient computation.
    """
    if len(values) < 2:
        return "stable"

    s = pl.Series("v", values)
    mid = len(values) // 2
    first_half_mean = float(s.head(mid).mean())
    second_half_mean = float(s.tail(len(values) - mid).mean())

    if second_half_mean > first_half_mean * 1.1:
        return "increasing"
    elif second_half_mean < first_half_mean * 0.9:
        return "decreasing"
    return "stable"


def _calculate_abundance_score(
    income_trend: str,
    giving_trend: str,
    avg_giving_pct: float,
    consistency_months: int,
) -> float:
    """
    Calculate abundance score (0-100) based on giving patterns.

    Components:
    - Giving as % of income (higher = better, up to 10% sweet spot)
    - Trend alignment (giving growing with income = good)
    - Data sufficiency (more months = more reliable)
    """
    # Score from giving percentage (0-40 points)
    # Sweet spot: 10% giving = max score, diminishing returns above
    if avg_giving_pct >= 10:
        pct_score = 40
    elif avg_giving_pct >= 5:
        pct_score = 30 + (avg_giving_pct - 5) * 2
    elif avg_giving_pct >= 2:
        pct_score = 15 + (avg_giving_pct - 2) * 5
    else:
        pct_score = avg_giving_pct * 7.5

    # Score from trend alignment (0-30 points)
    trend_score = 15  # default for stable
    if income_trend == "increasing" and giving_trend == "increasing":
        trend_score = 30  # blessing cycle
    elif income_trend == "decreasing" and giving_trend in ("stable", "increasing"):
        trend_score = 25  # faithful giving during hardship
    elif income_trend == "increasing" and giving_trend == "stable":
        trend_score = 20
    elif income_trend == "decreasing" and giving_trend == "decreasing":
        trend_score = 10

    # Score from consistency/data (0-30 points)
    consistency_score = min(30, consistency_months * 5)

    return min(100.0, pct_score + trend_score + consistency_score)


def _classify_pattern(
    income_trend: str,
    giving_trend: str,
    avg_giving_pct: float,
) -> str:
    """Classify the abundance pattern."""
    if income_trend == "increasing" and giving_trend == "increasing":
        return "blessing_cycle"
    elif income_trend == "increasing" and giving_trend == "stable":
        return "income_outpacing_giving"
    elif income_trend == "decreasing" and giving_trend in ("stable", "increasing"):
        return "faithful_giving"
    elif income_trend == "decreasing" and giving_trend == "decreasing":
        return "parallel_decline"
    else:
        return "steady"


def _assess_creditworthiness(
    abundance_score: float,
    pattern: str,
    avg_giving_pct: float,
) -> str:
    """
    Assess creditworthiness signal from giving patterns.

    Research insight: Consistent givers are more reliable borrowers.
    """
    if pattern == "faithful_giving":
        # Giving even when income drops = strong character signal
        return "strong"
    elif pattern == "blessing_cycle" and avg_giving_pct >= 5:
        return "strong"
    elif abundance_score >= 60:
        return "moderate"
    elif abundance_score >= 30:
        return "weak"
    return "insufficient"


def _generate_abundance_insight(
    income_trend: str,
    giving_trend: str,
    avg_giving_pct: float,
    pattern: str,
) -> Dict[str, str]:
    """Generate insight message from abundance pattern analysis."""
    insights = {
        "blessing_cycle": {
            "sw": f"Mapato yako yameongezeka na umeongeza kutoa pia! Mzunguko wa baraka. Wastani wa kutoa ni {avg_giving_pct:.1f}% ya mapato.",
            "en": f"Your income grew and you increased giving too! The blessing cycle. Average giving is {avg_giving_pct:.1f}% of income.",
        },
        "income_outpacing_giving": {
            "sw": f"Mapato yako yameongezeka lakini kutoa kumeendelea sawa. Je, ungependa kuongeza kutoa pamoja na mapato?",
            "en": f"Your income grew but giving stayed the same. Would you like to increase giving along with income?",
        },
        "faithful_giving": {
            "sw": f"Mapato yamepungua lakini bado unatoa. Hii ni sadaka ya kweli — Mungu anaona moyo wako.",
            "en": f"Income decreased but you're still giving. This is true sacrifice — God sees your heart.",
        },
        "parallel_decline": {
            "sw": f"Na mapato na kutoa vimepungua. Hii ni ya kawaida — usijali. Muhimu ni kuendelea na nidhamu.",
            "en": f"Both income and giving decreased. This is normal — don't worry. What matters is maintaining discipline.",
        },
        "steady": {
            "sw": f"Wastani wa kutoa ni {avg_giving_pct:.1f}% ya mapato. Umekuwa na nidhamu nzuri ya kutoa.",
            "en": f"Average giving is {avg_giving_pct:.1f}% of income. You've had good giving discipline.",
        },
    }
    return insights.get(pattern, insights["steady"])


def _report_message_sw(period: str, total: float, change: float) -> str:
    """Generate Swahili summary message for a report."""
    period_names = {"weekly": "wiki hii", "monthly": "mwezi huu", "yearly": "mwaka huu"}
    p = period_names.get(period, period)

    if change > 0:
        return f"Umekuwa mkarimu {p}! Umekua KES {total:,.0f}. Ongezeko la KES {change:,.0f} kuliko kipindi kilichopita."
    elif change < 0:
        return f"Umekua KES {total:,.0f} {p}. Kumesuka KES {abs(change):,.0f} kuliko kipindi kilichopita."
    else:
        return f"Umekua KES {total:,.0f} {p}. Sawa na kipindi kilichopita."


def _report_message_en(period: str, total: float, change: float) -> str:
    """Generate English summary message for a report."""
    period_names = {"weekly": "this week", "monthly": "this month", "yearly": "this year"}
    p = period_names.get(period, period)

    if change > 0:
        return f"You've been generous {p}! Given KES {total:,.0f}. That's KES {change:,.0f} more than last period."
    elif change < 0:
        return f"You gave KES {total:,.0f} {p}. That's KES {abs(change):,.0f} less than last period."
    else:
        return f"You gave KES {total:,.0f} {p}. Same as last period."


# ─────────────────────────────────────────────────────────────────────────────
# Caching Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _cache_abundance_pattern(
    db: AsyncSession,
    user_id: UUID,
    months: int,
    result: Dict[str, Any],
) -> None:
    """Cache abundance pattern analysis result."""
    try:
        # Upsert: delete old and insert new
        from sqlalchemy import delete

        await db.execute(
            delete(AbundancePattern).where(
                AbundancePattern.user_id == user_id
            )
        )

        pattern_record = AbundancePattern(
            user_id=user_id,
            analysis_months=months,
            months_with_data=result.get("months_analyzed", 0),
            income_trend=result.get("income_trend"),
            giving_trend=result.get("giving_trend"),
            avg_giving_pct=result.get("avg_giving_pct"),
            total_given=sum(r.get("giving", 0) for r in result.get("monthly_data", [])),
            total_income=sum(r.get("income", 0) for r in result.get("monthly_data", [])),
            abundance_score=result.get("abundance_score"),
            pattern=result.get("pattern"),
            monthly_data=result.get("monthly_data"),
            insight_sw=result.get("insight", {}).get("sw"),
            insight_en=result.get("insight", {}).get("en"),
            creditworthiness_signal=result.get("creditworthiness_signal"),
        )
        db.add(pattern_record)
        await db.flush()
    except Exception as e:
        logger.warning("abundance_cache_failed", user_id=str(user_id), error=str(e))
