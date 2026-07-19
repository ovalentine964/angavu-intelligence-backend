"""
RetailAgent — Domain intelligence for mama mboga, dukawallah, mitumba, market traders.

Capabilities:
    - Inventory management and spoilage tracking
    - Pricing optimization (margin analysis per product)
    - Supplier tracking and comparison
    - Restock predictions based on sales velocity
    - Profit margin analysis per product
    - Market day pattern analysis
    - Product mix optimization (ABC analysis enhanced)
    - Seasonal pricing guidance

Tier: 2 (Domain) — activated when worker type is TRADER (retail)
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RetailAgent:
    """
    Specialized intelligence for retail workers.

    Analyzes sales, inventory, and purchasing data to optimize
    product mix, pricing, spoilage, and restocking.
    """

    name = "RetailAgent"
    role = "Retail business intelligence specialist"
    tier = 2
    worker_types = ["mama_mboga", "dukawallah", "vendor", "mitumba"]

    def __init__(self):
        self._logger = logger.bind(agent=self.name)

    # ── Sales & Inventory Analysis ──────────────────────────────────

    def analyze_sales(
        self,
        transactions: list[dict[str, Any]],
        inventory: list[dict[str, Any]] | None = None,
        period_days: int = 30,
    ) -> dict[str, Any]:
        """
        Analyze sales transactions for retail-specific insights.

        Args:
            transactions: Transaction dicts with item, amount, quantity, profit, etc.
            inventory: Current inventory records (optional)
            period_days: Analysis window

        Returns:
            Dict with retail-specific analytics
        """
        if not transactions:
            return self._empty_analysis()

        sales = [
            t for t in transactions
            if t.get("transaction_type") == "SALE"
        ]
        purchases = [
            t for t in transactions
            if t.get("transaction_type") == "PURCHASE"
        ]

        # Product performance
        product_analysis = self._analyze_products(sales)

        # Profit margins
        margin_analysis = self._analyze_margins(sales, purchases)

        # Daily patterns
        daily_patterns = self._analyze_daily_patterns(sales)

        # ABC classification
        abc_analysis = self._abc_classification(sales)

        # Restock predictions
        restock_predictions = self._predict_restock(
            sales, inventory or []
        )

        # Spoilage risk (for perishable items)
        spoilage_risk = self._assess_spoilage_risk(
            sales, inventory or []
        )

        total_revenue = sum(t.get("amount", 0) for t in sales)
        total_cost = sum(
            (t.get("amount", 0) - (t.get("profit", 0) or 0))
            for t in sales
            if t.get("amount", 0) > 0
        )
        total_profit = sum(t.get("profit", 0) or 0 for t in sales)

        return {
            "period_days": period_days,
            "sale_count": len(sales),
            "purchase_count": len(purchases),
            "total_revenue": round(total_revenue, 2),
            "total_cost": round(total_cost, 2),
            "total_profit": round(total_profit, 2),
            "avg_margin_pct": round(
                (total_profit / total_revenue * 100) if total_revenue > 0 else 0, 1
            ),
            "product_analysis": product_analysis,
            "margin_analysis": margin_analysis,
            "daily_patterns": daily_patterns,
            "abc_classification": abc_analysis,
            "restock_predictions": restock_predictions,
            "spoilage_risk": spoilage_risk,
        }

    def _analyze_products(
        self, sales: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Analyze performance per product."""
        product_data: dict[str, dict[str, float]] = defaultdict(
            lambda: {"revenue": 0, "profit": 0, "qty": 0, "count": 0}
        )
        for t in sales:
            item = t.get("item", "Unknown")
            product_data[item]["revenue"] += t.get("amount", 0)
            product_data[item]["profit"] += t.get("profit", 0) or 0
            product_data[item]["qty"] += t.get("quantity", 0) or 0
            product_data[item]["count"] += 1

        ranked = sorted(
            product_data.items(),
            key=lambda x: x[1]["revenue"],
            reverse=True,
        )
        return [
            {
                "product": name,
                "revenue": round(d["revenue"], 2),
                "profit": round(d["profit"], 2),
                "quantity_sold": round(d["qty"], 1),
                "transaction_count": int(d["count"]),
                "avg_price": round(
                    d["revenue"] / d["qty"], 2
                ) if d["qty"] > 0 else 0,
                "margin_pct": round(
                    d["profit"] / d["revenue"] * 100, 1
                ) if d["revenue"] > 0 else 0,
            }
            for name, d in ranked[:20]
        ]

    def _analyze_margins(
        self,
        sales: list[dict[str, Any]],
        purchases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Analyze profit margins across products."""
        margins = []
        for t in sales:
            revenue = t.get("amount", 0)
            profit = t.get("profit", 0) or 0
            if revenue > 0:
                margins.append(profit / revenue * 100)

        if not margins:
            return {"avg": 0, "median": 0, "min": 0, "max": 0}

        return {
            "avg": round(statistics.mean(margins), 1),
            "median": round(statistics.median(margins), 1),
            "min": round(min(margins), 1),
            "max": round(max(margins), 1),
            "below_10pct": sum(1 for m in margins if m < 10),
            "above_30pct": sum(1 for m in margins if m > 30),
        }

    def _analyze_daily_patterns(
        self, sales: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze sales patterns by day of week."""
        day_names = [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ]
        day_data: dict[int, dict[str, float]] = defaultdict(
            lambda: {"revenue": 0, "count": 0}
        )
        for t in sales:
            ts = t.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                dow = ts.weekday()
                day_data[dow]["revenue"] += t.get("amount", 0)
                day_data[dow]["count"] += 1

        pattern = {}
        for dow in range(7):
            d = day_data[dow]
            if d["count"] > 0:
                pattern[day_names[dow]] = {
                    "revenue": round(d["revenue"], 2),
                    "transactions": int(d["count"]),
                    "avg_sale": round(d["revenue"] / d["count"], 2),
                }

        # Find best and worst days
        best_day = max(pattern.items(), key=lambda x: x[1]["revenue"]) if pattern else None
        worst_day = min(pattern.items(), key=lambda x: x[1]["revenue"]) if pattern else None

        return {
            "by_day": pattern,
            "best_day": best_day[0] if best_day else None,
            "worst_day": worst_day[0] if worst_day else None,
        }

    def _abc_classification(
        self, sales: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        """
        ABC analysis: classify products by revenue contribution.

        A = top 80% of revenue (vital few)
        B = next 15% (important)
        C = remaining 5% (trivial many)
        """
        product_revenue: dict[str, float] = defaultdict(float)
        for t in sales:
            product_revenue[t.get("item", "Unknown")] += t.get("amount", 0)

        if not product_revenue:
            return {"A": [], "B": [], "C": []}

        sorted_products = sorted(
            product_revenue.items(), key=lambda x: x[1], reverse=True
        )
        total = sum(v for _, v in sorted_products)

        result: dict[str, list[str]] = {"A": [], "B": [], "C": []}
        cumulative = 0.0
        for name, revenue in sorted_products:
            cumulative += revenue
            pct = cumulative / total if total > 0 else 0
            if pct <= 0.80:
                result["A"].append(name)
            elif pct <= 0.95:
                result["B"].append(name)
            else:
                result["C"].append(name)

        return result

    def _predict_restock(
        self,
        sales: list[dict[str, Any]],
        inventory: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Predict when each product needs restocking."""
        # Calculate daily sales velocity per product
        product_daily: dict[str, list[float]] = defaultdict(list)
        product_dates: dict[str, set] = defaultdict(set)

        for t in sales:
            item = t.get("item", "Unknown")
            ts = t.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                day_key = ts.strftime("%Y-%m-%d")
                product_daily[item].append(t.get("quantity", 0) or 0)
                product_dates[item].add(day_key)

        predictions = []
        for item in product_daily:
            qty_sold = product_daily[item]
            active_days = len(product_dates[item])
            daily_velocity = sum(qty_sold) / max(active_days, 1)

            inv_record = next(
                (i for i in inventory if i.get("item") == item), None
            )
            current_stock = inv_record.get("current_stock", 0) if inv_record else 0

            days_until_restock = (
                current_stock / daily_velocity if daily_velocity > 0 else None
            )

            predictions.append({
                "product": item,
                "daily_velocity": round(daily_velocity, 2),
                "current_stock": current_stock,
                "days_until_restock": round(days_until_restock, 0) if days_until_restock else None,
                "needs_restock": (
                    days_until_restock is not None and days_until_restock < 3
                ),
            })

        # Sort by urgency (lowest days first)
        predictions.sort(
            key=lambda x: x["days_until_restock"] if x["days_until_restock"] is not None else 999
        )
        return predictions[:15]

    def _assess_spoilage_risk(
        self,
        sales: list[dict[str, Any]],
        inventory: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Assess spoilage risk for perishable items."""
        # Common perishable categories in Kenya
        perishable_keywords = [
            "tomato", "ndengu", "spinach", "sukuma", "kale", "cabbage",
            "onion", "potato", "banana", "mango", "avocado", "orange",
            "milk", "eggs", "meat", "fish", "mchicha", "terere",
            "managu", "kunde", "matoke", "ndizi",
        ]

        risks = []
        for inv in inventory:
            item = inv.get("item", "").lower()
            is_perishable = any(kw in item for kw in perishable_keywords)
            if not is_perishable:
                continue

            stock = inv.get("current_stock", 0)
            if stock <= 0:
                continue

            # Find sales velocity for this item
            item_sales = [
                t for t in sales
                if t.get("item", "").lower() == item
            ]
            daily_sold = sum(t.get("quantity", 0) or 0 for t in item_sales) / max(
                len(set(
                    t.get("timestamp", "")[:10]
                    for t in item_sales
                    if t.get("timestamp")
                )),
                1,
            )

            days_to_sell = stock / daily_sold if daily_sold > 0 else None
            risk_level = "low"
            if days_to_sell is not None:
                if days_to_sell > 5:
                    risk_level = "high"
                elif days_to_sell > 3:
                    risk_level = "medium"

            risks.append({
                "product": inv.get("item", "Unknown"),
                "current_stock": stock,
                "daily_velocity": round(daily_sold, 2),
                "days_to_sell": round(days_to_sell, 0) if days_to_sell else None,
                "risk_level": risk_level,
            })

        return sorted(risks, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["risk_level"]])

    # ── Recommendations ─────────────────────────────────────────────

    def get_recommendations(
        self,
        analysis: dict[str, Any],
        language: str = "en",
    ) -> list[dict[str, str]]:
        """Generate retail-specific recommendations."""
        recs = []

        # Margin optimization
        margins = analysis.get("margin_analysis", {})
        avg_margin = margins.get("avg", 0)
        if avg_margin < 15:
            recs.append({
                "category": "pricing",
                "title": "Margins are low" if language == "en" else "Faida ni ndogo",
                "message": (
                    f"Average margin is {avg_margin:.0f}%. "
                    "Review your pricing — you may be undercharging. "
                    "Check if suppliers offer better prices."
                    if language == "en" else
                    f"Faida ya wastani ni {avg_margin:.0f}%. "
                    "Kagua bei yako — unaweza kuwa unauza bei ndogo. "
                    "Angalia kama wasambazaji wanatoa bei bora."
                ),
                "priority": "high",
            })

        # Spoilage alerts
        spoilage = analysis.get("spoilage_risk", [])
        high_risk = [s for s in spoilage if s.get("risk_level") == "high"]
        if high_risk:
            items = ", ".join(s["product"] for s in high_risk[:3])
            recs.append({
                "category": "spoilage",
                "title": "Spoilage risk!" if language == "en" else "Hatari ya kuharibika!",
                "message": (
                    f"These items may spoil before selling: {items}. "
                    "Consider reducing price to clear stock faster."
                    if language == "en" else
                    f"Vitu hivi vinaweza kuharibika kabla ya kuuza: {items}. "
                    "Fikiria kupunguza bei ili kuuza haraka."
                ),
                "priority": "high",
            })

        # ABC insights
        abc = analysis.get("abc_classification", {})
        a_products = abc.get("A", [])
        if a_products:
            recs.append({
                "category": "product_mix",
                "title": "Focus on top products" if language == "en" else "Zingatia bidhaa bora",
                "message": (
                    f"Your top products ({', '.join(a_products[:3])}) generate "
                    "80% of revenue. Always keep these in stock."
                    if language == "en" else
                    f"Bidhaa zako bora ({', '.join(a_products[:3])}) zinazalisha "
                    "80% ya mapato. Kila wakati ziweke hifadhini."
                ),
                "priority": "medium",
            })

        # Best day
        patterns = analysis.get("daily_patterns", {})
        best_day = patterns.get("best_day")
        if best_day:
            recs.append({
                "category": "timing",
                "title": "Stock up for best day" if language == "en" else "Jaza bidhaa kwa siku bora",
                "message": (
                    f"{best_day} is your best sales day. "
                    "Make sure you have extra stock ready."
                    if language == "en" else
                    f"{best_day} ni siku yako bora ya mauzo. "
                    "Hakikisha una bidhaa za ziada tayari."
                ),
                "priority": "medium",
            })

        # Restock urgency
        restock = analysis.get("restock_predictions", [])
        urgent = [r for r in restock if r.get("needs_restock")]
        if urgent:
            items = ", ".join(r["product"] for r in urgent[:3])
            recs.append({
                "category": "restock",
                "title": "Restock needed" if language == "en" else "Unahitaji kujaza tena",
                "message": (
                    f"Running low on: {items}. Restock within 2 days."
                    if language == "en" else
                    f"Bidhaa zinazidi kuisha: {items}. Jaza tena ndani ya siku 2."
                ),
                "priority": "high",
            })

        return recs

    def _empty_analysis(self) -> dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "period_days": 0,
            "sale_count": 0,
            "purchase_count": 0,
            "total_revenue": 0,
            "total_cost": 0,
            "total_profit": 0,
            "avg_margin_pct": 0,
            "product_analysis": [],
            "margin_analysis": {"avg": 0, "median": 0, "min": 0, "max": 0},
            "daily_patterns": {"by_day": {}, "best_day": None, "worst_day": None},
            "abc_classification": {"A": [], "B": [], "C": []},
            "restock_predictions": [],
            "spoilage_risk": [],
        }
