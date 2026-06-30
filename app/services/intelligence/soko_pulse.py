"""
Soko Pulse — FMCG Demand Forecasting Service.

Real-time demand patterns from informal markets:
- What sells, where, when, seasonal trends
- Price intelligence across markets
- Demand forecasting with confidence intervals

Buyers: FMCG companies (Unilever, Coca-Cola, P&G, EABL, etc.)
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.intelligence_products import SokoPulseReport
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.intelligence.cache import intelligence_cache

logger = structlog.get_logger(__name__)
settings = get_settings()


class SokoPulseService:
    """
    FMCG demand forecasting service.

    Generates demand intelligence from anonymized transaction data.
    Enforces k-anonymity (k≥10) on all outputs.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def generate_demand_forecast(
        self,
        product_category: str,
        product_name: Optional[str] = None,
        region: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        tier: str = "standard",
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate FMCG demand forecasting intelligence.

        Args:
            product_category: Category to analyze (food, household, etc.)
            product_name: Specific product or None for category-level
            region: Geographic region or None for national
            period_start: Analysis start (default: 90 days ago)
            period_end: Analysis end (default: today)
            tier: Pricing tier (standard/premium/enterprise)
            buyer_id: Buyer requesting this data

        Returns:
            Intelligence dict or None if k-anonymity not met
        """
        # Check cache
        cached = await intelligence_cache.get(
            "soko_pulse",
            category=product_category,
            product=product_name,
            region=region,
            start=str(period_start),
            end=str(period_end),
            tier=tier,
        )
        if cached:
            return cached

        # Default period
        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=90)

        # Query transactions
        query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.item_category == product_category,
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )

        if product_name:
            query = query.where(Transaction.item == product_name)

        # Apply region filter
        user_ids = None
        if region:
            user_query = select(User.id).where(
                and_(
                    User.location_geohash.like(f"{region}%"),
                    User.is_active == True,
                    User.consent_data_sharing == True,
                )
            )
            result = await self.db.execute(user_query)
            user_ids = [row[0] for row in result.all()]
            if not user_ids:
                return None
            query = query.where(Transaction.user_id.in_(user_ids))

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        if not transactions:
            return None

        # k-anonymity check
        unique_users = set(t.user_id for t in transactions)
        k = len(unique_users)
        passes, k_value = self.anonymizer.check_k_anonymity(k)
        if not passes:
            logger.warning("soko_pulse_k_anonymity_failed", k=k, threshold=settings.K_ANONYMITY_THRESHOLD)
            return None

        # Aggregate metrics
        amounts = [t.amount for t in transactions]
        quantities = [t.quantity or 0 for t in transactions]
        unit_prices = [t.unit_price for t in transactions if t.unit_price and t.unit_price > 0]

        total_volume = sum(quantities)
        days_in_period = (period_end - period_start).days or 1
        avg_daily_volume = total_volume / days_in_period

        # Day-of-week pattern
        dow_data = defaultdict(lambda: {"volume": 0, "amount": 0, "count": 0})
        for t in transactions:
            dow = t.timestamp.strftime("%a")
            dow_data[dow]["volume"] += t.quantity or 0
            dow_data[dow]["amount"] += t.amount
            dow_data[dow]["count"] += 1

        avg_dow_amount = np.mean([d["amount"] for d in dow_data.values()]) if dow_data else 1
        dow_pattern = {
            dow: round(data["amount"] / max(avg_dow_amount, 1), 2)
            for dow, data in dow_data.items()
        }

        # Monthly trend
        monthly = defaultdict(lambda: {"volume": 0, "amount": 0, "count": 0})
        for t in transactions:
            m = t.timestamp.strftime("%Y-%m")
            monthly[m]["volume"] += t.quantity or 0
            monthly[m]["amount"] += t.amount
            monthly[m]["count"] += 1

        monthly_trend = [
            {"month": m, "volume": d["volume"], "revenue": round(d["amount"], 2)}
            for m, d in sorted(monthly.items())
        ]

        # Demand trend (compare last 30 days to previous 30 days)
        mid_date = period_end - timedelta(days=30)
        recent = [t for t in transactions if t.timestamp >= datetime.combine(mid_date, datetime.min.time())]
        older = [t for t in transactions if t.timestamp < datetime.combine(mid_date, datetime.min.time())]

        recent_vol = sum(t.quantity or 0 for t in recent)
        older_vol = sum(t.quantity or 0 for t in older)

        if older_vol > 0:
            change_pct = (recent_vol - older_vol) / older_vol * 100
            if change_pct > 5:
                demand_trend = "rising"
            elif change_pct < -5:
                demand_trend = "declining"
            else:
                demand_trend = "stable"
        else:
            demand_trend = "stable"
            change_pct = 0

        # Price intelligence
        avg_price = round(float(np.mean(unit_prices)), 2) if unit_prices else 0
        min_price = round(float(np.min(unit_prices)), 2) if unit_prices else 0
        max_price = round(float(np.max(unit_prices)), 2) if unit_prices else 0
        median_price = round(float(np.median(unit_prices)), 2) if unit_prices else 0

        # Price trend
        if unit_prices and len(recent) > 10 and len(older) > 10:
            recent_prices = [t.unit_price for t in recent if t.unit_price and t.unit_price > 0]
            older_prices = [t.unit_price for t in older if t.unit_price and t.unit_price > 0]
            if recent_prices and older_prices:
                price_change = (np.mean(recent_prices) - np.mean(older_prices)) / np.mean(older_prices) * 100
                if price_change > 3:
                    price_trend = "rising"
                elif price_change < -3:
                    price_trend = "declining"
                else:
                    price_trend = "stable"
            else:
                price_trend = "stable"
                price_change = 0
        else:
            price_trend = "stable"
            price_change = 0

        # Seasonal factor (simplified — compare to overall average)
        seasonal_factor = round(avg_daily_volume / max(total_volume / max(days_in_period, 1), 1), 2)

        # Forecast (simple exponential smoothing for standard tier)
        forecast = None
        if tier in ("premium", "enterprise") and len(monthly_trend) >= 3:
            volumes = [m["volume"] for m in monthly_trend]
            alpha = 0.3
            smoothed = volumes[0]
            for v in volumes[1:]:
                smoothed = alpha * v + (1 - alpha) * smoothed

            # Simple confidence interval
            residuals = [v - smoothed for v in volumes]
            std_err = float(np.std(residuals)) if len(residuals) > 1 else smoothed * 0.1

            forecast = {
                "forecasted_volume": round(smoothed, 0),
                "confidence_interval_low": round(max(0, smoothed - 1.96 * std_err), 0),
                "confidence_interval_high": round(smoothed + 1.96 * std_err, 0),
                "forecast_method": "exponential_smoothing",
                "mape": round(float(np.mean(np.abs(np.array(residuals) / np.array(volumes)))) * 100, 1) if volumes else None,
            }

        # Peak demand days
        daily_volumes = defaultdict(float)
        for t in transactions:
            daily_volumes[t.timestamp.strftime("%Y-%m-%d")] += t.quantity or 0
        sorted_days = sorted(daily_volumes.items(), key=lambda x: x[1], reverse=True)
        peak_days = [d[0] for d in sorted_days[:5]]

        # Apply differential privacy to revenue metrics
        dp_total_volume = round(self.anonymizer.add_laplace_noise(total_volume, sensitivity=100), 0)
        dp_avg_daily = round(self.anonymizer.add_laplace_noise(avg_daily_volume, sensitivity=50), 2)

        # Build response
        response = {
            "product": "soko_pulse",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, k / 50),
            "confidence_level": min(1.0, len(transactions) / 100),
            "region": region or "national",
            "product_category": product_category,
            "product_name": product_name or "all",
            "time_period": f"{period_start} to {period_end}",
            "total_volume": max(0, dp_total_volume),
            "avg_daily_volume": max(0, dp_avg_daily),
            "demand_trend": demand_trend,
            "forecast": forecast,
            "price_intelligence": {
                "avg_price": avg_price,
                "min_price": min_price,
                "max_price": max_price,
                "median_price": median_price,
                "price_trend": price_trend,
                "price_change_pct": round(price_change, 1),
                "unit": "KES",
            },
            "day_of_week_pattern": dow_pattern,
            "monthly_trend": monthly_trend,
            "peak_demand_days": peak_days,
            "vendor_count": k,
            "stockout_frequency": None,  # Would need inventory data
            "seasonal_factor": seasonal_factor,
            "seasonal_events": [],
            "users_included": k,
            "data_points": len(transactions),
            "tier": tier,
        }

        # Cache
        await intelligence_cache.set(
            "soko_pulse", response,
            category=product_category,
            product=product_name,
            region=region,
            start=str(period_start),
            end=str(period_end),
            tier=tier,
        )

        logger.info(
            "soko_pulse_generated",
            category=product_category,
            region=region,
            k=k,
            transactions=len(transactions),
        )

        return response
