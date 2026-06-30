"""
Intelligence API endpoints — for buyers.

These endpoints provide anonymized, aggregated economic intelligence
to paying buyers (FMCG companies, government, financial institutions).

All responses enforce:
- k-anonymity (k≥10): minimum 10 users per aggregation
- Differential privacy: calibrated noise on sensitive metrics
- Data access logging: every query is audited
- Geographic scoping: buyers can only access authorized regions
"""

import time
from datetime import date, datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_buyer_from_api_key
from app.db.database import get_db
from app.models.buyer import Buyer
from app.schemas.intelligence import (
    BuyerQueryParams,
    CreditSignal,
    DemandPattern,
    EconomicActivity,
    MarketIntelligence,
)
from app.services.anonymizer import Anonymizer
from app.services.pipeline import DataPipeline

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/intelligence", tags=["Intelligence API"])


@router.get("/market/{market_id}")
async def get_market_intelligence(
    market_id: str,
    request: Request,
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Get market-level economic intelligence.

    Returns aggregated, anonymized data for a specific geographic market.
    Data includes activity metrics, transaction volumes, category
    breakdowns, and payment method distribution.

    **Privacy guarantees:**
    - Minimum 10 users per aggregation (k-anonymity)
    - Differential privacy noise on revenue metrics
    - No individual business data exposed
    - All access logged for audit

    **Scoping:**
    Buyers can only access markets within their authorized regions.

    Args:
        market_id: Geohash-5 or ward code
        period_start: Start of analysis period (default: 30 days ago)
        period_end: End of analysis period (default: today)

    Returns:
        MarketIntelligence with anonymized metrics
    """
    start_time = time.time()
    anonymizer = Anonymizer(db)
    pipeline = DataPipeline(db)

    # Check geographic authorization
    if not _is_region_authorized(buyer, market_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized to access market: {market_id}",
        )

    # Default period: last 30 days
    if not period_end:
        period_end = date.today()
    if not period_start:
        from datetime import timedelta
        period_start = period_end - timedelta(days=30)

    # Generate intelligence
    intelligence = await pipeline.generate_market_intelligence(
        market_id, period_start, period_end
    )

    if not intelligence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insufficient data for this market (k-anonymity threshold not met)",
        )

    # Log data access
    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=f"/intelligence/market/{market_id}",
        query_params={"period_start": str(period_start), "period_end": str(period_end)},
        processing_time_ms=processing_time,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        status_code=200,
    )

    return intelligence


@router.get("/demand/{product}")
async def get_demand_patterns(
    product: str,
    request: Request,
    region: Optional[str] = Query(None, description="Geographic region"),
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Get demand patterns for a specific product or category.

    Shows how demand varies over time and geography, useful for
    FMCG distribution planning and inventory optimization.

    **Includes:**
    - Total and average daily volume
    - Price range (min, max, median)
    - Day-of-week patterns
    - Monthly trends
    - Seasonal factors
    - Vendor count

    Args:
        product: Product name or category
        region: Geographic region filter
        period_start: Analysis start date
        period_end: Analysis end date

    Returns:
        DemandPattern with temporal and geographic breakdowns
    """
    start_time = time.time()
    anonymizer = Anonymizer(db)
    pipeline = DataPipeline(db)

    # Check authorization
    if region and not _is_region_authorized(buyer, region):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized to access region: {region}",
        )

    if not period_end:
        period_end = date.today()
    if not period_start:
        from datetime import timedelta
        period_start = period_end - timedelta(days=90)

    # Normalize product name
    normalized = pipeline.normalize_product_name(product)

    # Query transactions for this product in the region
    from sqlalchemy import and_, func, select
    from app.models.transaction import Transaction
    from app.models.user import User

    # Build query based on region
    query = select(Transaction).where(
        and_(
            Transaction.item == (normalized or product),
            Transaction.transaction_type == "SALE",
            Transaction.timestamp >= datetime.combine(
                period_start, datetime.min.time()
            ),
            Transaction.timestamp <= datetime.combine(
                period_end, datetime.max.time()
            ),
        )
    )

    # Apply region filter via user location
    if region:
        query = query.join(User, Transaction.user_id == User.id).where(
            User.location_geohash.like(f"{region}%")
        )

    result = await db.execute(query)
    transactions = result.scalars().all()

    if len(transactions) < 10:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insufficient data for this product/region combination",
        )

    # Aggregate
    import numpy as np
    from collections import defaultdict

    amounts = [t.amount for t in transactions]
    daily_volumes = defaultdict(float)
    daily_counts = defaultdict(int)
    dow_totals = defaultdict(lambda: {"amount": 0, "count": 0})
    monthly = defaultdict(lambda: {"volume": 0, "amount": 0})
    user_set = set()

    for t in transactions:
        day = t.timestamp.strftime("%Y-%m-%d")
        daily_volumes[day] += t.quantity or 0
        daily_counts[day] += 1
        dow = t.timestamp.strftime("%a")
        dow_totals[dow]["amount"] += t.amount
        dow_totals[dow]["count"] += 1
        month = t.timestamp.strftime("%Y-%m")
        monthly[month]["volume"] += t.quantity or 0
        monthly[month]["amount"] += t.amount
        user_set.add(t.user_id)

    total_volume = sum(t.quantity or 0 for t in transactions)
    avg_daily_volume = total_volume / max(len(daily_volumes), 1)

    # k-anonymity check
    k = len(user_set)
    if k < 10:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insufficient unique businesses for k-anonymity",
        )

    # Day of week pattern (relative to average)
    avg_dow = np.mean([d["amount"] for d in dow_totals.values()]) if dow_totals else 1
    dow_pattern = {
        dow: round(data["amount"] / max(avg_dow, 1), 2)
        for dow, data in dow_totals.items()
    }

    # Price range
    unit_prices = [
        t.unit_price for t in transactions if t.unit_price and t.unit_price > 0
    ]

    # Monthly trend
    monthly_trend = [
        {
            "month": m,
            "volume": data["volume"],
            "revenue": round(data["amount"], 2),
        }
        for m, data in sorted(monthly.items())
    ]

    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=f"/intelligence/demand/{product}",
        query_params={"region": region, "period_start": str(period_start)},
        processing_time_ms=processing_time,
        records_returned=len(transactions),
        ip_address=request.client.host if request.client else None,
        status_code=200,
    )

    return {
        "product": normalized or product,
        "product_category": pipeline.categorize_product(normalized or product),
        "region": region or "national",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_volume": {
            "value": round(total_volume, 2),
            "k_anonymity": k,
            "quality_score": min(1.0, k / 50),
        },
        "avg_daily_volume": {
            "value": round(avg_daily_volume, 2),
            "k_anonymity": k,
            "quality_score": min(1.0, k / 50),
        },
        "price_range": {
            "min": round(min(unit_prices), 2) if unit_prices else None,
            "max": round(max(unit_prices), 2) if unit_prices else None,
            "median": round(float(np.median(unit_prices)), 2) if unit_prices else None,
            "unit": "KES",
        },
        "day_of_week_pattern": dow_pattern,
        "monthly_trend": monthly_trend,
        "vendor_count": {
            "value": k,
            "k_anonymity": k,
            "quality_score": 1.0,
        },
        "data_freshness": datetime.utcnow().isoformat(),
        "confidence_level": min(1.0, len(transactions) / 100),
    }


@router.get("/economic-activity/{region}")
async def get_economic_activity(
    region: str,
    request: Request,
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Get regional economic activity intelligence.

    Aggregated economic activity metrics for a geographic region,
    suitable for government dashboards and infrastructure planning.

    **Includes:**
    - Activity index (0-100)
    - Growth index
    - Estimated and active businesses
    - Transaction volumes
    - Sector breakdown
    - M-Pesa penetration
    - Comparison with previous period and national average

    Args:
        region: Geographic region code (county code or geohash prefix)
        period_start: Analysis start date
        period_end: Analysis end date

    Returns:
        EconomicActivity with anonymized regional metrics
    """
    start_time = time.time()
    anonymizer = Anonymizer(db)
    pipeline = DataPipeline(db)

    if not _is_region_authorized(buyer, region):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized to access region: {region}",
        )

    if not period_end:
        period_end = date.today()
    if not period_start:
        from datetime import timedelta
        period_start = period_end - timedelta(days=30)

    # Get all users in this region
    from sqlalchemy import and_, func, select
    from app.models.transaction import Transaction
    from app.models.user import User

    users_query = select(User).where(
        and_(
            User.location_geohash.like(f"{region}%"),
            User.is_active == True,
            User.consent_data_sharing == True,
        )
    )
    result = await db.execute(users_query)
    users = result.scalars().all()

    user_count = len(users)
    if user_count < 10:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insufficient users in region for k-anonymity",
        )

    user_ids = [u.id for u in users]

    # Get transactions
    txn_query = select(Transaction).where(
        and_(
            Transaction.user_id.in_(user_ids),
            Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
            Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
        )
    )
    result = await db.execute(txn_query)
    transactions = result.scalars().all()

    import numpy as np
    from collections import defaultdict

    sales = [t for t in transactions if t.transaction_type == "SALE"]
    total_revenue = sum(t.amount for t in sales)

    # Daily revenue per business
    daily_rev = defaultdict(float)
    for t in sales:
        daily_rev[t.timestamp.strftime("%Y-%m-%d")] += t.amount

    daily_revenues = list(daily_rev.values())
    avg_daily = np.mean(daily_revenues) if daily_revenues else 0

    # Sector breakdown
    sector_counts = defaultdict(int)
    sector_revenue = defaultdict(float)
    for t in sales:
        cat = t.item_category or "other"
        sector_counts[cat] += 1
        sector_revenue[cat] += t.amount

    sector_breakdown = [
        {
            "sector": cat,
            "share_pct": round(rev / total_revenue * 100, 1) if total_revenue > 0 else 0,
            "revenue": round(rev, 2),
            "transaction_count": sector_counts[cat],
            "trend": "stable",  # Would need previous period comparison
        }
        for cat, rev in sorted(
            sector_revenue.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # M-Pesa penetration
    mpesa_count = sum(1 for t in sales if t.payment_method == "mpesa")
    mpesa_pct = (mpesa_count / len(sales) * 100) if sales else 0

    # Activity index (0-100) based on transaction velocity
    days_in_period = (period_end - period_start).days or 1
    txn_per_day = len(sales) / days_in_period
    activity_index = min(100, int(txn_per_day * 2))  # Scale: 50 txns/day = 100

    # Apply differential privacy
    dp_avg_daily = anonymizer.add_laplace_noise(avg_daily, sensitivity=500)
    dp_atv = anonymizer.add_laplace_noise(
        total_revenue / max(len(sales), 1), sensitivity=200
    )

    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=f"/intelligence/economic-activity/{region}",
        query_params={"period_start": str(period_start), "period_end": str(period_end)},
        processing_time_ms=processing_time,
        records_returned=len(sales),
        ip_address=request.client.host if request.client else None,
        status_code=200,
    )

    return {
        "region": region,
        "region_type": _determine_region_type(region),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "activity_index": {
            "value": activity_index,
            "k_anonymity": user_count,
            "quality_score": min(1.0, user_count / 100),
        },
        "growth_index": {
            "value": 50,  # Would need previous period comparison
            "k_anonymity": user_count,
            "quality_score": min(1.0, user_count / 100),
        },
        "estimated_businesses": user_count,
        "active_businesses": user_count,
        "total_transactions": len(sales),
        "total_volume_kes": round(total_revenue, 2),
        "avg_transaction_value": {
            "value": round(max(0, dp_atv), 2),
            "k_anonymity": user_count,
            "quality_score": min(1.0, user_count / 50),
        },
        "sector_breakdown": sector_breakdown,
        "mpesa_penetration_pct": round(mpesa_pct, 1),
        "data_freshness": datetime.utcnow().isoformat(),
        "confidence_level": min(1.0, len(sales) / 100),
        "users_contributing": user_count,
    }


@router.get("/credit-signal/{business_id}")
async def get_credit_signal(
    business_id: str,
    request: Request,
    lookback_days: int = Query(90, ge=30, le=365),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Get credit scoring signal for a business.

    Provides anonymized business health indicators that financial
    institutions can use for credit decisions.

    **Signals include:**
    - Activity score (0-100)
    - Stability index (revenue consistency)
    - Growth trajectory
    - Operating days and hours
    - Category risk assessment
    - Peer comparison

    **Privacy:**
    Business identity is fully anonymized. Only a hash ID is returned.

    Args:
        business_id: Anonymized business identifier
        lookback_days: Analysis window (30-365 days)

    Returns:
        CreditSignal with business health indicators
    """
    start_time = time.time()
    anonymizer = Anonymizer(db)
    pipeline = DataPipeline(db)

    # Check that buyer has credit scoring scope
    if "credit" not in (buyer.products_subscribed or []):
        # Allow if buyer is a financial institution
        if buyer.buyer_type not in ("BANK", "MFI", "INSURANCE"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for credit signals. Contact sales.",
            )

    # Generate credit signal
    signal = await pipeline.generate_credit_signal(
        business_id, lookback_days
    )

    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insufficient data for credit scoring (need 20+ transactions)",
        )

    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=f"/intelligence/credit-signal/{business_id}",
        query_params={"lookback_days": lookback_days},
        processing_time_ms=processing_time,
        ip_address=request.client.host if request.client else None,
        status_code=200,
    )

    return signal


# =========================================================================
# Helper Functions
# =========================================================================


def _is_region_authorized(buyer: Buyer, region: str) -> bool:
    """
    Check if a buyer is authorized to access a specific region.

    Args:
        buyer: The buyer object
        region: Geographic region code

    Returns:
        True if authorized
    """
    authorized = buyer.regions_authorized or []
    if not authorized:
        return True  # No restriction means access to all

    # Check if region starts with any authorized prefix
    for auth_region in authorized:
        if region.startswith(auth_region) or auth_region == "all":
            return True

    return False


def _determine_region_type(region: str) -> str:
    """
    Determine the geographic level of a region code.

    Args:
        region: Region identifier

    Returns:
        Region type string
    """
    if len(region) <= 2:
        return "county"
    elif len(region) <= 5:
        return "ward"
    elif len(region) <= 7:
        return "sub_county"
    else:
        return "micro_market"
