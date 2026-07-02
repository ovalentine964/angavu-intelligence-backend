"""
Critical Mass Dashboard API.

Internal dashboard for tracking Biashara Intelligence's path to
revenue activation. Each intelligence product has a minimum worker
count before it becomes sellable. This dashboard tracks progress
toward those milestones.

Critical Mass Milestones (from critical-mass-value.md):
- Soko Pulse: 1,000 workers → Month 3
- Alama Score: 5,000 workers → Month 6
- Biashara Pulse: 10,000 workers → Month 9
- Jamii Insights: 20,000 workers → Month 12
- Tax Base: 50,000 workers → Month 18

Also tracks:
- Worker acquisition funnel
- Transaction volume by product
- Revenue activation status per product
- Geographic coverage
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.transaction import Transaction
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ─────────────────────────────────────────────────────────────────────────────
# Critical Mass Thresholds
# ─────────────────────────────────────────────────────────────────────────────

CRITICAL_MASS_THRESHOLDS = {
    "soko_pulse": {
        "name": "Soko Pulse — FMCG Demand Forecasting",
        "min_workers": 1_000,
        "min_transactions_per_day": 10_000,
        "target_month": 3,
        "revenue_potential_monthly_usd": "5K–15K",
        "status": "not_activated",
    },
    "alama_score": {
        "name": "Alama Score — Credit Scoring",
        "min_workers": 5_000,
        "min_transactions_per_day": 50_000,
        "target_month": 6,
        "revenue_potential_monthly_usd": "20K–50K",
        "status": "not_activated",
    },
    "biashara_pulse": {
        "name": "Biashara Pulse — Government MSME Activity",
        "min_workers": 10_000,
        "min_transactions_per_day": 100_000,
        "target_month": 9,
        "revenue_potential_monthly_usd": "30K–80K",
        "status": "not_activated",
    },
    "jamii_insights": {
        "name": "Jamii Insights — NGO Financial Inclusion",
        "min_workers": 20_000,
        "min_transactions_per_day": 200_000,
        "target_month": 12,
        "revenue_potential_monthly_usd": "50K–120K",
        "status": "not_activated",
    },
    "tax_base": {
        "name": "Tax Base Estimation — Government Revenue",
        "min_workers": 50_000,
        "min_transactions_per_day": 500_000,
        "target_month": 18,
        "revenue_potential_monthly_usd": "100K–300K",
        "status": "not_activated",
    },
}


@router.get("/critical-mass")
async def critical_mass_dashboard(
    db: AsyncSession = Depends(get_db),
):
    """
    Critical Mass Dashboard — Track progress toward revenue activation.

    Shows for each intelligence product:
    - Current worker count vs. minimum threshold
    - Current transaction volume vs. target
    - Activation status and progress percentage
    - Estimated time to activation at current growth rate

    This is the operational heartbeat of Biashara Intelligence's
    go-to-market strategy.
    """
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)

    # ── Total worker counts ─────────────────────────────────────────────────
    total_workers_result = await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )
    total_workers = total_workers_result.scalar() or 0

    consenting_result = await db.execute(
        select(func.count(User.id)).where(
            and_(User.is_active == True, User.consent_data_sharing == True)
        )
    )
    consenting_workers = consenting_result.scalar() or 0

    # ── Workers by type ─────────────────────────────────────────────────────
    type_result = await db.execute(
        select(User.business_type, func.count(User.id))
        .where(User.is_active == True)
        .group_by(User.business_type)
    )
    workers_by_type = {row[0]: row[1] for row in type_result.all()}

    # ── Workers by region (top 10 counties) ─────────────────────────────────
    region_result = await db.execute(
        select(
            func.substr(User.location_geohash, 1, 3).label("county_prefix"),
            func.count(User.id),
        )
        .where(
            and_(User.is_active == True, User.location_geohash.isnot(None))
        )
        .group_by("county_prefix")
        .order_by(func.count(User.id).desc())
        .limit(10)
    )
    workers_by_region = {row[0]: row[1] for row in region_result.all()}

    # ── Workers by dialect/language ─────────────────────────────────────────
    lang_result = await db.execute(
        select(User.language, func.count(User.id))
        .where(User.is_active == True)
        .group_by(User.language)
    )
    workers_by_language = {row[0]: row[1] for row in lang_result.all()}

    # ── Workers by channel ──────────────────────────────────────────────────
    channel_result = await db.execute(
        select(User.channel, func.count(User.id))
        .where(User.is_active == True)
        .group_by(User.channel)
    )
    workers_by_channel = {row[0]: row[1] for row in channel_result.all()}

    # ── Transaction volumes ─────────────────────────────────────────────────
    # Last 30 days
    txn_30d_result = await db.execute(
        select(func.count(Transaction.id))
        .where(
            and_(
                Transaction.timestamp >= datetime.combine(thirty_days_ago, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(today, datetime.max.time()),
            )
        )
    )
    txn_30d = txn_30d_result.scalar() or 0
    txn_per_day_30d = txn_30d / 30.0

    # Last 7 days
    txn_7d_result = await db.execute(
        select(func.count(Transaction.id))
        .where(
            and_(
                Transaction.timestamp >= datetime.combine(seven_days_ago, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(today, datetime.max.time()),
            )
        )
    )
    txn_7d = txn_7d_result.scalar() or 0
    txn_per_day_7d = txn_7d / 7.0

    # Transaction growth rate (7d vs previous 7d)
    fourteen_days_ago = today - timedelta(days=14)
    prev_7d_result = await db.execute(
        select(func.count(Transaction.id))
        .where(
            and_(
                Transaction.timestamp >= datetime.combine(fourteen_days_ago, datetime.min.time()),
                Transaction.timestamp < datetime.combine(seven_days_ago, datetime.min.time()),
            )
        )
    )
    prev_7d = prev_7d_result.scalar() or 0
    txn_growth_pct = (
        round((txn_7d - prev_7d) / max(prev_7d, 1) * 100, 1) if prev_7d > 0 else None
    )

    # ── Transaction volume by category ──────────────────────────────────────
    cat_result = await db.execute(
        select(
            Transaction.item_category,
            func.count(Transaction.id),
            func.sum(Transaction.amount),
        )
        .where(
            and_(
                Transaction.timestamp >= datetime.combine(thirty_days_ago, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(today, datetime.max.time()),
            )
        )
        .group_by(Transaction.item_category)
    )
    txn_by_category = {}
    for row in cat_result.all():
        cat = row[0] or "other"
        txn_by_category[cat] = {
            "count": row[1],
            "total_amount_kes": round(float(row[2] or 0), 2),
        }

    # ── Revenue activation status per product ───────────────────────────────
    product_status = {}
    for product_code, threshold in CRITICAL_MASS_THRESHOLDS.items():
        progress_pct = round(
            min(100, consenting_workers / max(threshold["min_workers"], 1) * 100), 1
        )
        txn_progress = round(
            min(100, txn_per_day_30d / max(threshold["min_transactions_per_day"], 1) * 100), 1
        )

        if consenting_workers >= threshold["min_workers"]:
            activation_status = "activated"
        elif progress_pct >= 75:
            activation_status = "near_activation"
        elif progress_pct >= 25:
            activation_status = "building"
        else:
            activation_status = "not_activated"

        product_status[product_code] = {
            "name": threshold["name"],
            "min_workers": threshold["min_workers"],
            "current_workers": consenting_workers,
            "worker_progress_pct": progress_pct,
            "min_txn_per_day": threshold["min_transactions_per_day"],
            "current_txn_per_day": round(txn_per_day_30d, 1),
            "txn_progress_pct": txn_progress,
            "target_month": threshold["target_month"],
            "revenue_potential": threshold["revenue_potential_monthly_usd"],
            "status": activation_status,
        }

    # ── Acquisition funnel metrics ──────────────────────────────────────────
    # New signups this week
    week_ago_dt = datetime.combine(seven_days_ago, datetime.min.time())
    new_weekly_result = await db.execute(
        select(func.count(User.id))
        .where(User.created_at >= week_ago_dt)
    )
    new_weekly = new_weekly_result.scalar() or 0

    # New signups this month
    month_start = today.replace(day=1)
    month_start_dt = datetime.combine(month_start, datetime.min.time())
    new_monthly_result = await db.execute(
        select(func.count(User.id))
        .where(User.created_at >= month_start_dt)
    )
    new_monthly = new_monthly_result.scalar() or 0

    # Consent rate
    consent_rate = round(
        consenting_workers / max(total_workers, 1) * 100, 1
    )

    # Data sharing funnel
    # In production: track signup → first_txn → consent → active
    active_with_txn_result = await db.execute(
        select(func.count(func.distinct(Transaction.user_id)))
        .where(
            and_(
                Transaction.timestamp >= datetime.combine(thirty_days_ago, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(today, datetime.max.time()),
            )
        )
    )
    active_with_txn = active_with_txn_result.scalar() or 0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),

        # ── Worker Counts ──────────────────────────────────────────────────
        "workers": {
            "total": total_workers,
            "consenting_data_sharing": consenting_workers,
            "active_with_transactions_30d": active_with_txn,
            "consent_rate_pct": consent_rate,
            "by_type": workers_by_type,
            "by_language": workers_by_language,
            "by_channel": workers_by_channel,
            "by_region_top10": workers_by_region,
        },

        # ── Transaction Volumes ────────────────────────────────────────────
        "transactions": {
            "last_30_days": txn_30d,
            "last_7_days": txn_7d,
            "avg_per_day_30d": round(txn_per_day_30d, 1),
            "avg_per_day_7d": round(txn_per_day_7d, 1),
            "growth_7d_pct": txn_growth_pct,
            "by_category": txn_by_category,
        },

        # ── Product Activation Status ──────────────────────────────────────
        "product_activation": product_status,

        # ── Overall Activation ─────────────────────────────────────────────
        "overall": {
            "products_activated": sum(
                1 for p in product_status.values() if p["status"] == "activated"
            ),
            "products_near": sum(
                1 for p in product_status.values() if p["status"] == "near_activation"
            ),
            "products_building": sum(
                1 for p in product_status.values() if p["status"] == "building"
            ),
            "products_not_started": sum(
                1 for p in product_status.values() if p["status"] == "not_activated"
            ),
            "total_products": len(product_status),
            "next_milestone": min(
                (
                    p for p in product_status.values()
                    if p["status"] != "activated"
                ),
                key=lambda x: x["worker_progress_pct"],
                default=None,
            ),
        },

        # ── Acquisition Funnel ─────────────────────────────────────────────
        "acquisition_funnel": {
            "new_signups_this_week": new_weekly,
            "new_signups_this_month": new_monthly,
            "activation_rate_pct": round(
                active_with_txn / max(total_workers, 1) * 100, 1
            ),
            "retention_proxy_30d": round(
                active_with_txn / max(total_workers, 1) * 100, 1
            ),
        },
    }


@router.get("/worker-growth")
async def worker_growth_trend(
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Worker growth trend over time.

    Shows daily new signups and cumulative worker count
    for tracking acquisition velocity.
    """
    today = date.today()
    start_date = today - timedelta(days=days)

    # Daily new signups
    daily_result = await db.execute(
        select(
            func.date(User.created_at).label("signup_date"),
            func.count(User.id),
        )
        .where(User.created_at >= datetime.combine(start_date, datetime.min.time()))
        .group_by("signup_date")
        .order_by("signup_date")
    )
    daily_signups = [
        {"date": str(row[0]), "new_workers": row[1]}
        for row in daily_result.all()
    ]

    # Cumulative
    cumulative = 0
    daily_with_cumulative = []
    base_count_result = await db.execute(
        select(func.count(User.id))
        .where(User.created_at < datetime.combine(start_date, datetime.min.time()))
    )
    cumulative = base_count_result.scalar() or 0

    for day in daily_signups:
        cumulative += day["new_workers"]
        daily_with_cumulative.append({
            **day,
            "cumulative_workers": cumulative,
        })

    return {
        "period": f"{start_date} to {today}",
        "days": days,
        "daily_signups": daily_with_cumulative,
        "total_new_workers": sum(d["new_workers"] for d in daily_signups),
        "avg_daily_signups": round(
            sum(d["new_workers"] for d in daily_signups) / max(days, 1), 1
        ),
        "current_total": cumulative,
    }
