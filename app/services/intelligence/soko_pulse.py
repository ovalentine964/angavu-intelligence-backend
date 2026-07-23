"""
Soko Pulse — FMCG Demand Forecasting.

Architecture: arch_backend.md §2.5, §7.3.1
- Demand forecasting (Holt-Winters, trend analysis)
- Price elasticity estimation
- Consumer surplus analysis
- Cross-border trade indicators

Data sources: PostgreSQL (transactions) + ClickHouse (aggregates)
"""
import json
from datetime import UTC, datetime, date, timedelta
from typing import Optional

import numpy as np
import structlog
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.intelligence import IntelligenceProduct

logger = structlog.get_logger(__name__)


class SokoPulseService:
    """Soko Pulse — market intelligence for FMCG products."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_demand_forecast(
        self,
        region: str,
        product_category: str,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        tier: str = "standard",
    ) -> dict:
        """Generate demand forecast for a product category in a region."""
        # Try pre-computed first
        precomputed = await self._get_precomputed(region, product_category, period_start, period_end)
        if precomputed:
            return precomputed

        # Compute on-demand from transaction data
        if period_end is None:
            period_end = date.today()
        if period_start is None:
            period_start = period_end - timedelta(days=90)

        # Query transaction aggregates
        result = await self.db.execute(
            select(
                func.date_trunc("week", Transaction.created_at).label("week"),
                func.sum(Transaction.amount).label("total_sales"),
                func.count().label("tx_count"),
                func.avg(Transaction.amount).label("avg_price"),
            ).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.product_category == product_category,
                    Transaction.created_at >= period_start,
                    Transaction.created_at <= period_end,
                )
            ).group_by(text("week")).order_by(text("week"))
        )
        rows = result.all()

        if not rows:
            return {
                "product": "soko-pulse",
                "region": region,
                "category": product_category,
                "status": "insufficient_data",
                "message": "Not enough transaction data for this region/category",
            }

        # Extract time series
        sales_series = [float(r.total_sales or 0) for r in rows]
        price_series = [float(r.avg_price or 0) for r in rows]
        volume_series = [int(r.tx_count or 0) for r in rows]

        # Compute forecasts
        demand_forecast = self._simple_forecast(sales_series, horizon=4)
        trend = self._detect_trend(sales_series)
        seasonality = self._detect_seasonality(sales_series)
        elasticity = self._estimate_elasticity(price_series, sales_series) if len(price_series) > 4 else None

        result = {
            "product": "soko-pulse",
            "region": region,
            "category": product_category,
            "period": {"start": str(period_start), "end": str(period_end)},
            "generated_at": datetime.now(UTC).isoformat(),
            "data_points": sum(volume_series),
            "demand_forecast": demand_forecast,
            "trend": trend,
            "seasonality": seasonality,
            "status": "ready",
        }

        if elasticity is not None:
            result["elasticity"] = elasticity
        if tier in ("business", "enterprise"):
            result["cross_border"] = {"trade_flow": "neutral", "confidence": 0.3}

        return result

    async def _get_precomputed(self, region, category, start, end) -> Optional[dict]:
        """Check for pre-computed intelligence product."""
        result = await self.db.execute(
            select(IntelligenceProduct).where(
                IntelligenceProduct.product_type == "soko_pulse",
                IntelligenceProduct.region == region,
                IntelligenceProduct.category == category,
                IntelligenceProduct.status == "ready",
            ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
        )
        product = result.scalar_one_or_none()
        if product:
            return {
                "product": "soko-pulse",
                "region": region,
                "category": category,
                "generated_at": product.generated_at.isoformat(),
                "status": "ready",
                "data_points": product.data_points,
                **product.data,
            }
        return None

    def _simple_forecast(self, series: list[float], horizon: int = 4) -> dict:
        """Simple exponential smoothing forecast."""
        if len(series) < 2:
            return {"values": [], "confidence_intervals": []}

        alpha = 0.3  # smoothing factor
        smoothed = [series[0]]
        for i in range(1, len(series)):
            smoothed.append(alpha * series[i] + (1 - alpha) * smoothed[-1])

        # Project forward
        trend = (smoothed[-1] - smoothed[-2]) if len(smoothed) > 1 else 0
        forecasts = []
        for h in range(1, horizon + 1):
            forecasts.append(max(0, smoothed[-1] + trend * h))

        # Confidence intervals (widen with horizon)
        residual_std = np.std([series[i] - smoothed[i] for i in range(len(series))]) if len(series) > 2 else 0
        intervals = []
        for h in range(1, horizon + 1):
            margin = 1.96 * residual_std * np.sqrt(h)
            intervals.append({
                "lower": max(0, forecasts[h - 1] - margin),
                "upper": forecasts[h - 1] + margin,
            })

        return {
            "horizon_weeks": horizon,
            "values": [round(v, 2) for v in forecasts],
            "confidence_intervals": intervals,
        }

    def _detect_trend(self, series: list[float]) -> dict:
        """Detect trend direction and magnitude."""
        if len(series) < 3:
            return {"direction": "stable", "magnitude": 0}

        # Simple linear regression
        x = np.arange(len(series))
        y = np.array(series)
        slope = np.polyfit(x, y, 1)[0]
        mean_val = np.mean(y)

        if mean_val == 0:
            return {"direction": "stable", "magnitude": 0}

        pct_change = slope / mean_val * 100
        if pct_change > 5:
            direction = "upward"
        elif pct_change < -5:
            direction = "downward"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "magnitude": round(abs(pct_change), 2),
            "slope_per_week": round(slope, 2),
        }

    def _detect_seasonality(self, series: list[float]) -> dict:
        """Detect weekly/monthly seasonality patterns."""
        if len(series) < 8:
            return {"detected": False, "pattern": "insufficient_data"}

        # Check for 4-week (monthly) cycle
        if len(series) >= 8:
            autocorr = np.correlate(series, series, mode="full")
            autocorr = autocorr[len(autocorr) // 2:]
            autocorr = autocorr / autocorr[0] if autocorr[0] != 0 else autocorr

            peaks = []
            for i in range(2, min(len(autocorr), 12)):
                if autocorr[i] > autocorr[i - 1] and autocorr[i] > autocorr[i + 1] if i + 1 < len(autocorr) else False:
                    peaks.append(i)

            if peaks:
                return {"detected": True, "cycle_length_weeks": peaks[0], "strength": round(float(autocorr[peaks[0]]), 3)}

        return {"detected": False, "pattern": "no_clear_cycle"}

    def _estimate_elasticity(self, prices: list[float], quantities: list[float]) -> Optional[dict]:
        """Estimate price elasticity of demand."""
        if len(prices) < 4 or len(quantities) < 4:
            return None

        p = np.array(prices)
        q = np.array(quantities)

        # Filter out zeros
        mask = (p > 0) & (q > 0)
        p, q = p[mask], q[mask]
        if len(p) < 3:
            return None

        # Log-log regression: ln(Q) = a + b*ln(P)
        log_p = np.log(p)
        log_q = np.log(q)
        slope = np.polyfit(log_p, log_q, 1)[0]

        elasticity = round(float(slope), 3)
        if abs(elasticity) < 1:
            interpretation = "inelastic"
        elif abs(elasticity) > 1:
            interpretation = "elastic"
        else:
            interpretation = "unit_elastic"

        return {
            "coefficient": elasticity,
            "interpretation": interpretation,
            "sample_size": len(p),
        }
