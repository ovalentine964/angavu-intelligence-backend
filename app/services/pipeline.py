"""
Data Pipeline — Clean → Aggregate → Intelligence

The pipeline transforms raw transaction data from devices into
structured intelligence products for buyers. It runs in stages:

1. Validation & Cleaning: Fix malformed data, normalize product names
2. Categorization: Assign business categories
3. Aggregation: Per-market, per-region, per-product
4. Intelligence Generation: Trends, forecasts, anomalies
5. Buyer Packaging: Format for specific buyer needs
"""

import hashlib
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.intelligence import (
    AnonymizedMetric,
    CreditSignal,
    DemandPattern,
    EconomicActivity,
    MarketIntelligence,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# Product name normalization map
PRODUCT_NORMALIZATION = {
    # Food staples
    "mchele": "rice",
    "wali": "rice",
    "unga": "maize_flour",
    "unga wa muhogo": "cassava_flour",
    "sukari": "sugar",
    "mafuta": "cooking_oil",
    "maembe": "mangoes",
    "ndizi": "bananas",
    "nyama": "meat",
    "samaki": "fish",
    "maziwa": "milk",
    "chai": "tea",
    "kahawa": "coffee",
    "mkate": "bread",
    "mayai": "eggs",
    "nyanya": "tomatoes",
    "vitunguu": "onions",
    "sukuma": "kale",
    "sukuma wiki": "kale",
    "pilipili": "chili",
    "karoti": "carrots",
    "viazi": "potatoes",
    "maharagwe": "beans",
    "dengu": "lentils",
    # Household
    "sabuni": "soap",
    "dawa": "medicine",
    "mafuta ya mwanga": "paraffin",
    "charcoal": "charcoal",
    "kuni": "firewood",
}

# Category mapping
CATEGORY_MAP = {
    "food": [
        "rice", "maize_flour", "cassava_flour", "sugar", "cooking_oil",
        "mangoes", "bananas", "meat", "fish", "milk", "tea", "coffee",
        "bread", "eggs", "tomatoes", "onions", "kale", "chili",
        "carrots", "potatoes", "beans", "lentils",
    ],
    "household": ["soap", "paraffin", "charcoal", "firewood"],
    "health": ["medicine"],
}


class DataPipeline:
    """
    Transforms raw transaction data into intelligence products.

    This is the core analytics engine of Msaidizi. It takes raw
    transaction records and produces anonymized, aggregated intelligence
    that buyers can consume.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Stage 1: Cleaning & Normalization
    # =========================================================================

    def normalize_product_name(self, raw_name: Optional[str]) -> Optional[str]:
        """
        Normalize product names to standard English identifiers.

        Converts Sheng/Swahili product names to consistent English keys.
        This ensures "mchele", "wali", and "rice" all map to the same product.

        Args:
            raw_name: Raw product name from transaction

        Returns:
            Normalized product name, or None if input is None
        """
        if not raw_name:
            return None
        cleaned = raw_name.strip().lower()
        return PRODUCT_NORMALIZATION.get(cleaned, cleaned)

    def categorize_product(self, product_name: str) -> str:
        """
        Assign a business category to a product.

        Args:
            product_name: Normalized product name

        Returns:
            Category string (food, household, health, other)
        """
        for category, products in CATEGORY_MAP.items():
            if product_name in products:
                return category
        return "other"

    async def clean_transactions(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch and clean transactions for a user.

        Normalizes product names, fills in missing categories,
        and removes obviously invalid records.

        Returns:
            List of cleaned transaction dictionaries
        """
        query = select(Transaction).where(Transaction.user_id == user_id)
        if start_date:
            query = query.where(
                Transaction.timestamp >= datetime.combine(
                    start_date, datetime.min.time(), tzinfo=timezone.utc
                )
            )
        if end_date:
            query = query.where(
                Transaction.timestamp <= datetime.combine(
                    end_date, datetime.max.time(), tzinfo=timezone.utc
                )
            )
        query = query.order_by(Transaction.timestamp)

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        cleaned = []
        for txn in transactions:
            normalized_item = self.normalize_product_name(txn.item)
            category = txn.item_category or self.categorize_product(
                normalized_item or ""
            )

            cleaned.append({
                "id": str(txn.id),
                "user_id": str(txn.user_id),
                "transaction_type": txn.transaction_type,
                "item": normalized_item,
                "item_category": category,
                "quantity": txn.quantity or 0,
                "unit": txn.unit,
                "unit_price": txn.unit_price,
                "amount": txn.amount,
                "profit": txn.profit,
                "payment_method": txn.payment_method,
                "recorded_via": txn.recorded_via,
                "confidence_score": txn.confidence_score or 1.0,
                "timestamp": txn.timestamp,
                "location_geohash": txn.location_geohash,
            })

        logger.info(
            "transactions_cleaned",
            user_id=str(user_id),
            count=len(cleaned),
        )
        return cleaned

    # =========================================================================
    # Stage 2: Aggregation
    # =========================================================================

    async def aggregate_user_metrics(
        self,
        user_id: str,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        """
        Aggregate transaction metrics for a single user over a period.

        Returns:
            Dictionary with aggregated metrics
        """
        transactions = await self.clean_transactions(
            user_id, period_start, period_end
        )

        if not transactions:
            return {
                "total_sales": 0,
                "total_purchases": 0,
                "total_expenses": 0,
                "gross_profit": 0,
                "net_profit": 0,
                "transaction_count": 0,
                "avg_transaction_value": 0,
                "profit_margin_pct": 0,
                "top_products": [],
                "daily_breakdown": [],
            }

        # Aggregate by type
        sales = [t for t in transactions if t["transaction_type"] == "SALE"]
        purchases = [t for t in transactions if t["transaction_type"] == "PURCHASE"]
        expenses = [t for t in transactions if t["transaction_type"] == "EXPENSE"]

        total_sales = sum(t["amount"] for t in sales)
        total_purchases = sum(t["amount"] for t in purchases)
        total_expenses = sum(t["amount"] for t in expenses)
        gross_profit = total_sales - total_purchases
        net_profit = total_sales - total_purchases - total_expenses

        # Top products by revenue
        product_revenue = defaultdict(float)
        product_qty = defaultdict(float)
        product_profit = defaultdict(float)
        product_count = defaultdict(int)

        for t in sales:
            if t["item"]:
                product_revenue[t["item"]] += t["amount"]
                product_qty[t["item"]] += t["quantity"]
                product_profit[t["item"]] += t.get("profit", 0) or 0
                product_count[t["item"]] += 1

        top_products = sorted(
            [
                {
                    "item": item,
                    "revenue": rev,
                    "quantity_sold": product_qty[item],
                    "profit": product_profit[item],
                    "transaction_count": product_count[item],
                    "avg_price": rev / max(product_count[item], 1),
                }
                for item, rev in product_revenue.items()
            ],
            key=lambda x: x["revenue"],
            reverse=True,
        )[:10]

        # Daily breakdown
        daily = defaultdict(lambda: {"sales": 0, "count": 0})
        for t in sales:
            day_key = t["timestamp"].strftime("%Y-%m-%d")
            daily[day_key]["sales"] += t["amount"]
            daily[day_key]["count"] += 1

        daily_breakdown = [
            {"date": d, "sales": v["sales"], "count": v["count"]}
            for d, v in sorted(daily.items())
        ]

        return {
            "total_sales": total_sales,
            "total_purchases": total_purchases,
            "total_expenses": total_expenses,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "transaction_count": len(transactions),
            "avg_transaction_value": (
                total_sales / len(sales) if sales else 0
            ),
            "profit_margin_pct": (
                (net_profit / total_sales * 100) if total_sales > 0 else 0
            ),
            "top_products": top_products,
            "daily_breakdown": daily_breakdown,
        }

    async def aggregate_market_metrics(
        self,
        location_geohash: str,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        """
        Aggregate metrics for all users in a geographic market.

        This is the foundation for buyer-facing intelligence products.
        Only includes data from users who consented to data sharing.

        Returns:
            Aggregated market metrics with k-anonymity check
        """
        # Get consenting users in this market area
        users_query = select(User).where(
            and_(
                User.location_geohash.like(f"{location_geohash}%"),
                User.is_active == True,
                User.consent_data_sharing == True,
            )
        )
        result = await self.db.execute(users_query)
        users = result.scalars().all()

        # k-anonymity check
        if len(users) < settings.K_ANONYMITY_THRESHOLD:
            logger.info(
                "k_anonymity_insufficient",
                geohash=location_geohash,
                user_count=len(users),
                threshold=settings.K_ANONYMITY_THRESHOLD,
            )
            return {
                "status": "suppressed",
                "reason": "k-anonymity threshold not met",
                "min_users": settings.K_ANONYMITY_THRESHOLD,
                "actual_users": len(users),
            }

        user_ids = [u.id for u in users]

        # Fetch all transactions for these users in the period
        txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(
                    period_start, datetime.min.time(), tzinfo=timezone.utc
                ),
                Transaction.timestamp <= datetime.combine(
                    period_end, datetime.max.time(), tzinfo=timezone.utc
                ),
            )
        )
        result = await self.db.execute(txn_query)
        transactions = result.scalars().all()

        if not transactions:
            return {
                "status": "no_data",
                "user_count": len(users),
            }

        # Compute aggregated metrics
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        total_revenue = sum(t.amount for t in sales)
        total_txn_count = len(sales)

        # Per-business daily revenue
        user_daily_revenue = defaultdict(lambda: defaultdict(float))
        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            user_daily_revenue[t.user_id][day] += t.amount

        daily_revenues = []
        for uid, days in user_daily_revenue.items():
            for day, rev in days.items():
                daily_revenues.append(rev)

        # Category breakdown
        category_counts = defaultdict(int)
        category_revenue = defaultdict(float)
        for t in sales:
            cat = t.item_category or "other"
            category_counts[cat] += 1
            category_revenue[cat] += t.amount

        # Payment method split
        mpesa_count = sum(1 for t in sales if t.payment_method == "mpesa")
        cash_count = sum(1 for t in sales if t.payment_method == "cash")

        return {
            "status": "ok",
            "user_count": len(users),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "total_revenue": total_revenue,
            "total_transactions": total_txn_count,
            "avg_daily_revenue_per_business": (
                np.mean(daily_revenues) if daily_revenues else 0
            ),
            "median_daily_revenue": (
                np.median(daily_revenues) if daily_revenues else 0
            ),
            "avg_transaction_value": (
                total_revenue / total_txn_count if total_txn_count > 0 else 0
            ),
            "category_breakdown": {
                cat: {
                    "count": category_counts[cat],
                    "revenue": category_revenue[cat],
                    "share_pct": (
                        category_revenue[cat] / total_revenue * 100
                        if total_revenue > 0
                        else 0
                    ),
                }
                for cat in sorted(
                    category_revenue.keys(),
                    key=lambda c: category_revenue[c],
                    reverse=True,
                )
            },
            "payment_methods": {
                "mpesa_pct": (
                    mpesa_count / total_txn_count * 100
                    if total_txn_count > 0
                    else 0
                ),
                "cash_pct": (
                    cash_count / total_txn_count * 100
                    if total_txn_count > 0
                    else 0
                ),
            },
            "k_anonymity": len(users),
        }

    # =========================================================================
    # Stage 3: Intelligence Generation
    # =========================================================================

    def apply_differential_privacy(
        self,
        value: float,
        sensitivity: float = 1.0,
    ) -> float:
        """
        Add Laplacian noise for differential privacy.

        Ensures that individual data points cannot be reconstructed
        from aggregate statistics.

        Args:
            value: The true aggregate value
            sensitivity: Query sensitivity (how much one person's data
                        can change the result)

        Returns:
            Noised value
        """
        epsilon = settings.DIFFERENTIAL_PRIVACY_EPSILON
        scale = sensitivity / epsilon
        noise = np.random.laplace(0, scale)
        return value + noise

    def compute_k_anonymity_value(self, group_size: int) -> int:
        """
        Compute the effective k-anonymity value for a group.

        If group_size < K_ANONYMITY_THRESHOLD, returns 0 (suppressed).
        Otherwise returns the group size.

        Args:
            group_size: Number of individuals in the aggregation group

        Returns:
            k-anonymity value (0 if suppressed, group_size otherwise)
        """
        if group_size < settings.K_ANONYMITY_THRESHOLD:
            return 0
        return group_size

    async def generate_market_intelligence(
        self,
        location_geohash: str,
        period_start: date,
        period_end: date,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate market-level intelligence for a geographic area.

        Applies differential privacy and k-anonymity before returning.

        Returns:
            Market intelligence dict or None if insufficient data
        """
        raw_metrics = await self.aggregate_market_metrics(
            location_geohash, period_start, period_end
        )

        if raw_metrics.get("status") != "ok":
            return None

        k = self.compute_k_anonymity_value(raw_metrics["user_count"])
        if k == 0:
            return None

        # Apply differential privacy to sensitive metrics
        dp_revenue = self.apply_differential_privacy(
            raw_metrics["avg_daily_revenue_per_business"],
            sensitivity=1000,  # max one person can affect average by ~1000 KES
        )
        dp_atv = self.apply_differential_privacy(
            raw_metrics["avg_transaction_value"],
            sensitivity=500,
        )

        return {
            "market_id": location_geohash,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "active_businesses": raw_metrics["user_count"],
            "total_transactions": raw_metrics["total_transactions"],
            "total_revenue_kes": round(raw_metrics["total_revenue"], 2),
            "avg_daily_revenue": {
                "value": round(max(0, dp_revenue), 2),
                "k_anonymity": k,
                "quality_score": min(1.0, k / 50),
            },
            "avg_transaction_value": {
                "value": round(max(0, dp_atv), 2),
                "k_anonymity": k,
                "quality_score": min(1.0, k / 50),
            },
            "category_breakdown": raw_metrics["category_breakdown"],
            "payment_methods": raw_metrics["payment_methods"],
            "data_freshness": datetime.now(timezone.utc).isoformat(),
        }

    async def generate_credit_signal(
        self,
        user_id: str,
        lookback_days: int = 90,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a credit scoring signal for a specific business.

        This is the core product for financial institution buyers.
        Provides anonymized business health indicators.

        Args:
            user_id: The business/user to score
            lookback_days: Number of days to analyze

        Returns:
            Credit signal dict or None if insufficient data
        """
        period_end = date.today()
        period_start = period_end - timedelta(days=lookback_days)

        transactions = await self.clean_transactions(
            user_id, period_start, period_end
        )

        sales = [t for t in transactions if t["transaction_type"] == "SALE"]

        if len(sales) < 20:  # Need minimum data points
            return None

        # Activity score (0-100) based on transaction frequency
        unique_days = len(set(
            t["timestamp"].strftime("%Y-%m-%d") for t in sales
        ))
        activity_score = min(100, int(unique_days / lookback_days * 100 * 1.5))

        # Revenue stability (coefficient of variation)
        daily_revenue = defaultdict(float)
        for t in sales:
            day = t["timestamp"].strftime("%Y-%m-%d")
            daily_revenue[day] += t["amount"]

        revenues = list(daily_revenue.values())
        if len(revenues) > 1:
            mean_rev = np.mean(revenues)
            std_rev = np.std(revenues)
            cv = std_rev / mean_rev if mean_rev > 0 else 1.0
            stability = max(0, 1 - cv)
        else:
            stability = 0.5

        # Growth trajectory
        if len(revenues) >= 14:
            first_half = np.mean(revenues[: len(revenues) // 2])
            second_half = np.mean(revenues[len(revenues) // 2 :])
            if second_half > first_half * 1.1:
                growth = "growing"
            elif second_half < first_half * 0.9:
                growth = "declining"
            else:
                growth = "stable"
        else:
            growth = "stable"

        # Operating consistency
        days_with_sales = unique_days
        total_days = lookback_days
        operating_consistency = days_with_sales / total_days

        total_revenue = sum(t["amount"] for t in sales)
        avg_daily = total_revenue / max(unique_days, 1)

        return {
            "business_hash": hashlib.sha256(
                str(user_id).encode()
            ).hexdigest()[:16],
            "activity_score": activity_score,
            "stability_index": round(stability, 3),
            "growth_trajectory": growth,
            "avg_daily_transactions": round(len(sales) / max(unique_days, 1), 1),
            "avg_daily_revenue_kes": round(avg_daily, 2),
            "operating_days_per_week": round(unique_days / (lookback_days / 7), 1),
            "revenue_consistency": round(stability, 3),
            "category_risk": "low" if stability > 0.7 else (
                "medium" if stability > 0.4 else "high"
            ),
            "data_points": len(sales),
            "data_period_days": lookback_days,
            "confidence": round(min(1.0, len(sales) / 100), 2),
        }

    # =========================================================================
    # Stage 4: Trend Analysis
    # =========================================================================

    async def compute_trends(
        self,
        user_id: str,
        weeks: int = 4,
    ) -> Dict[str, Any]:
        """
        Compute business trends over the specified number of weeks.

        Returns:
            Dictionary with trend indicators for key metrics
        """
        end_date = date.today()
        start_date = end_date - timedelta(weeks=weeks * 2)

        transactions = await self.clean_transactions(
            user_id, start_date, end_date
        )

        sales = [t for t in transactions if t["transaction_type"] == "SALE"]
        if not sales:
            return {"trends": [], "has_data": False}

        midpoint = end_date - timedelta(weeks=weeks)
        recent = [t for t in sales if t["timestamp"].date() >= midpoint]
        older = [t for t in sales if t["timestamp"].date() < midpoint]

        trends = []

        # Revenue trend
        recent_rev = sum(t["amount"] for t in recent)
        older_rev = sum(t["amount"] for t in older)
        if older_rev > 0:
            rev_change = (recent_rev - older_rev) / older_rev * 100
        else:
            rev_change = 100 if recent_rev > 0 else 0

        trends.append({
            "metric": "revenue",
            "current_value": round(recent_rev, 2),
            "previous_value": round(older_rev, 2),
            "change_pct": round(rev_change, 1),
            "direction": (
                "up" if rev_change > 5
                else "down" if rev_change < -5
                else "stable"
            ),
        })

        # Transaction count trend
        recent_count = len(recent)
        older_count = len(older)
        if older_count > 0:
            count_change = (recent_count - older_count) / older_count * 100
        else:
            count_change = 100 if recent_count > 0 else 0

        trends.append({
            "metric": "transaction_count",
            "current_value": recent_count,
            "previous_value": older_count,
            "change_pct": round(count_change, 1),
            "direction": (
                "up" if count_change > 5
                else "down" if count_change < -5
                else "stable"
            ),
        })

        # Average transaction value trend
        recent_atv = recent_rev / max(recent_count, 1)
        older_atv = older_rev / max(older_count, 1)
        if older_atv > 0:
            atv_change = (recent_atv - older_atv) / older_atv * 100
        else:
            atv_change = 0

        trends.append({
            "metric": "avg_transaction_value",
            "current_value": round(recent_atv, 2),
            "previous_value": round(older_atv, 2),
            "change_pct": round(atv_change, 1),
            "direction": (
                "up" if atv_change > 5
                else "down" if atv_change < -5
                else "stable"
            ),
        })

        return {"trends": trends, "has_data": True}

    async def detect_anomalies(
        self,
        user_id: str,
        lookback_days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Detect anomalous transactions or patterns.

        Flags things like:
        - Unusually large transactions (>3 standard deviations)
        - Sudden drops in transaction volume
        - New product categories
        - Unusual operating hours

        Returns:
            List of detected anomalies
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        transactions = await self.clean_transactions(
            user_id, start_date, end_date
        )

        sales = [t for t in transactions if t["transaction_type"] == "SALE"]
        if len(sales) < 10:
            return []

        anomalies = []
        amounts = [t["amount"] for t in sales]
        mean_amount = np.mean(amounts)
        std_amount = np.std(amounts)

        # Check for unusually large transactions
        for t in sales:
            if std_amount > 0:
                z_score = (t["amount"] - mean_amount) / std_amount
                if z_score > 3:
                    anomalies.append({
                        "type": "large_transaction",
                        "severity": "info",
                        "description": (
                            f"Unusually large sale of KES {t['amount']:.0f} "
                            f"(avg: KES {mean_amount:.0f})"
                        ),
                        "timestamp": t["timestamp"].isoformat(),
                        "item": t["item"],
                        "amount": t["amount"],
                    })

        # Check for daily volume drops
        daily_counts = defaultdict(int)
        for t in sales:
            daily_counts[t["timestamp"].strftime("%Y-%m-%d")] += 1

        if len(daily_counts) >= 7:
            counts = list(daily_counts.values())
            mean_count = np.mean(counts)
            std_count = np.std(counts)

            for day, count in daily_counts.items():
                if std_count > 0 and count < mean_count - 2 * std_count:
                    anomalies.append({
                        "type": "low_volume_day",
                        "severity": "warning",
                        "description": (
                            f"Only {count} sales on {day} "
                            f"(avg: {mean_count:.0f})"
                        ),
                        "date": day,
                        "count": count,
                    })

        return anomalies
