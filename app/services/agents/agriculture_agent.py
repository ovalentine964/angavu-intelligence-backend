"""
AgricultureAgent — Domain intelligence for farmers, fish traders, food processors.

Capabilities:
    - Seasonal planning and crop cycle tracking
    - Yield tracking (kg per acre per season)
    - Market price predictions (seasonal patterns)
    - Input cost optimization (fertilizer, seed, pesticide ROI)
    - Post-harvest loss tracking
    - Crop rotation recommendations
    - Weather integration (future)

Tier: 2 (Domain) — activated when worker type is FARMER
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# ── Crop Calendar (Kenya-specific) ──────────────────────────────────

CROP_CALENDAR: Dict[str, Dict[str, Any]] = {
    "maize": {
        "planting_months": [3, 4, 10],  # March-April (long rains), October (short rains)
        "harvest_months": [8, 9, 2],     # Aug-Sep, Feb
        "growing_season_days": 120,
        "avg_yield_kg_per_acre": 1200,
        "peak_price_months": [1, 2, 9, 10],  # Before harvest
        "low_price_months": [8, 9, 3, 4],    # During harvest
    },
    "beans": {
        "planting_months": [3, 4, 10],
        "harvest_months": [7, 8, 1],
        "growing_season_days": 90,
        "avg_yield_kg_per_acre": 600,
        "peak_price_months": [1, 2, 6, 7],
        "low_price_months": [7, 8, 1, 2],
    },
    "tomatoes": {
        "planting_months": [1, 2, 5, 6, 9, 10],
        "harvest_months": [4, 5, 8, 9, 12, 1],
        "growing_season_days": 75,
        "avg_yield_kg_per_acre": 8000,
        "peak_price_months": [6, 7, 8],
        "low_price_months": [1, 2, 11, 12],
    },
    "kale_sukuma": {
        "planting_months": list(range(1, 13)),  # Year-round
        "harvest_months": list(range(1, 13)),
        "growing_season_days": 45,
        "avg_yield_kg_per_acre": 15000,
        "peak_price_months": [6, 7, 8],
        "low_price_months": [3, 4, 11],
    },
    "potatoes": {
        "planting_months": [1, 2, 5, 6, 9, 10],
        "harvest_months": [4, 5, 8, 9, 12, 1],
        "growing_season_days": 100,
        "avg_yield_kg_per_acre": 5000,
        "peak_price_months": [5, 6, 11, 12],
        "low_price_months": [1, 2, 7, 8],
    },
    "onions": {
        "planting_months": [3, 4, 7, 8],
        "harvest_months": [7, 8, 11, 12],
        "growing_season_days": 105,
        "avg_yield_kg_per_acre": 6000,
        "peak_price_months": [1, 2, 3, 9, 10],
        "low_price_months": [7, 8, 12],
    },
    "rice": {
        "planting_months": [4, 5, 10, 11],
        "harvest_months": [8, 9, 2, 3],
        "growing_season_days": 120,
        "avg_yield_kg_per_acre": 1800,
        "peak_price_months": [1, 2, 6, 7],
        "low_price_months": [8, 9, 3],
    },
    "cassava": {
        "planting_months": [3, 4, 10, 11],
        "harvest_months": list(range(1, 13)),  # Can stay in ground 12+ months
        "growing_season_days": 300,
        "avg_yield_kg_per_acre": 6000,
        "peak_price_months": [6, 7, 8, 9],
        "low_price_months": [1, 2, 3],
    },
}


class AgricultureAgent:
    """
    Specialized intelligence for agricultural workers.

    Analyzes farming activities, sales, and input costs to provide
    seasonal planning, yield tracking, and price optimization.
    """

    name = "AgricultureAgent"
    role = "Agricultural business intelligence specialist"
    tier = 2
    worker_types = ["farmer", "fish_trader", "food_processor"]

    def __init__(self):
        self._logger = logger.bind(agent=self.name)

    # ── Farm Analysis ───────────────────────────────────────────────

    def analyze_farm(
        self,
        transactions: List[Dict[str, Any]],
        period_days: int = 365,
    ) -> Dict[str, Any]:
        """
        Analyze farming transactions for agricultural insights.

        Args:
            transactions: Transaction dicts (sales, purchases/expenses)
            period_days: Analysis window

        Returns:
            Dict with agriculture-specific analytics
        """
        if not transactions:
            return self._empty_analysis()

        sales = [
            t for t in transactions
            if t.get("transaction_type") == "SALE"
        ]
        expenses = [
            t for t in transactions
            if t.get("transaction_type") in ("PURCHASE", "EXPENSE")
        ]

        # Revenue from sales
        total_revenue = sum(t.get("amount", 0) for t in sales)
        total_expenses = sum(t.get("amount", 0) for t in expenses)
        total_profit = total_revenue - total_expenses

        # Crop analysis
        crop_analysis = self._analyze_crops(sales)

        # Input cost analysis
        input_costs = self._analyze_input_costs(expenses)

        # Seasonal patterns
        seasonal_patterns = self._analyze_seasonal_patterns(sales)

        # ROI analysis
        roi = self._calculate_roi(total_revenue, total_expenses, input_costs)

        return {
            "period_days": period_days,
            "sale_count": len(sales),
            "expense_count": len(expenses),
            "total_revenue": round(total_revenue, 2),
            "total_expenses": round(total_expenses, 2),
            "total_profit": round(total_profit, 2),
            "profit_margin_pct": round(
                (total_profit / total_revenue * 100) if total_revenue > 0 else 0, 1
            ),
            "crop_analysis": crop_analysis,
            "input_costs": input_costs,
            "seasonal_patterns": seasonal_patterns,
            "roi": roi,
        }

    def _analyze_crops(
        self, sales: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze performance per crop."""
        crop_data: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"revenue": 0, "qty": 0, "count": 0}
        )
        for t in sales:
            item = (t.get("item") or "Unknown").lower()
            crop_data[item]["revenue"] += t.get("amount", 0)
            crop_data[item]["qty"] += t.get("quantity", 0) or 0
            crop_data[item]["count"] += 1

        ranked = sorted(
            crop_data.items(), key=lambda x: x[1]["revenue"], reverse=True
        )
        return [
            {
                "crop": name,
                "revenue": round(d["revenue"], 2),
                "quantity_kg": round(d["qty"], 1),
                "sales_count": int(d["count"]),
                "avg_price_per_kg": round(
                    d["revenue"] / d["qty"], 2
                ) if d["qty"] > 0 else 0,
            }
            for name, d in ranked[:10]
        ]

    def _analyze_input_costs(
        self, expenses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze farming input costs."""
        categories: Dict[str, float] = defaultdict(float)
        for t in expenses:
            item = (t.get("item") or "other").lower()
            # Categorize common farming inputs
            if any(kw in item for kw in ["seed", "mbegu"]):
                categories["seeds"] += t.get("amount", 0)
            elif any(kw in item for kw in ["fertilizer", "mbolea", "dap", "can"]):
                categories["fertilizer"] += t.get("amount", 0)
            elif any(kw in item for kw in ["pesticide", "dawa", "chemical", "herbicide"]):
                categories["pesticides"] += t.get("amount", 0)
            elif any(kw in item for kw in ["labour", "labor", "kazi", "worker"]):
                categories["labour"] += t.get("amount", 0)
            elif any(kw in item for kw in ["transport", "fare", "gari"]):
                categories["transport"] += t.get("amount", 0)
            else:
                categories["other"] += t.get("amount", 0)

        total = sum(categories.values())
        return {
            "breakdown": {k: round(v, 2) for k, v in categories.items()},
            "total": round(total, 2),
            "pct_breakdown": {
                k: round(v / total * 100, 1) if total > 0 else 0
                for k, v in categories.items()
            },
        }

    def _analyze_seasonal_patterns(
        self, sales: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze sales patterns by month/season."""
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        month_data: Dict[int, float] = defaultdict(float)
        for t in sales:
            ts = t.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                month_data[ts.month] += t.get("amount", 0)

        pattern = {}
        for m in range(1, 13):
            if month_data.get(m, 0) > 0:
                pattern[month_names[m - 1]] = round(month_data[m], 2)

        best_month = max(month_data.items(), key=lambda x: x[1]) if month_data else None
        worst_month = min(
            ((k, v) for k, v in month_data.items() if v > 0),
            key=lambda x: x[1],
            default=None,
        ) if month_data else None

        return {
            "by_month": pattern,
            "best_month": month_names[best_month[0] - 1] if best_month else None,
            "worst_month": month_names[worst_month[0] - 1] if worst_month else None,
        }

    def _calculate_roi(
        self,
        revenue: float,
        expenses: float,
        input_costs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate return on investment for farming."""
        breakdown = input_costs.get("breakdown", {})
        seeds = breakdown.get("seeds", 0)
        fertilizer = breakdown.get("fertilizer", 0)
        pesticides = breakdown.get("pesticides", 0)
        input_total = seeds + fertilizer + pesticides

        roi_pct = ((revenue - expenses) / input_total * 100) if input_total > 0 else None

        return {
            "total_input_cost": round(input_total, 2),
            "roi_pct": round(roi_pct, 1) if roi_pct else None,
            "revenue_per_ksh_input": round(
                revenue / input_total, 2
            ) if input_total > 0 else None,
        }

    # ── Crop Calendar & Planning ────────────────────────────────────

    def get_crop_calendar(
        self, current_month: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get planting/harvest calendar for the current month.

        Returns what to plant now, what's being harvested,
        and price expectations.
        """
        if current_month is None:
            current_month = datetime.now(timezone.utc).month

        planting_now = []
        harvesting_now = []
        peak_prices = []

        for crop, info in CROP_CALENDAR.items():
            if current_month in info["planting_months"]:
                planting_now.append({
                    "crop": crop,
                    "harvest_in_days": info["growing_season_days"],
                    "expected_yield_kg": info["avg_yield_kg_per_acre"],
                })
            if current_month in info["harvest_months"]:
                harvesting_now.append(crop)
            if current_month in info["peak_price_months"]:
                peak_prices.append(crop)

        return {
            "current_month": current_month,
            "planting_now": planting_now,
            "harvesting_now": harvesting_now,
            "peak_prices_now": peak_prices,
        }

    # ── Recommendations ─────────────────────────────────────────────

    def get_recommendations(
        self,
        analysis: Dict[str, Any],
        language: str = "en",
    ) -> List[Dict[str, str]]:
        """Generate agriculture-specific recommendations."""
        recs = []

        # Profit margin
        margin = analysis.get("profit_margin_pct", 0)
        if margin < 20:
            recs.append({
                "category": "profitability",
                "title": "Low profit margin" if language == "en" else "Faida ndogo",
                "message": (
                    f"Profit margin is {margin:.0f}%. "
                    "Review input costs — can you find cheaper seeds or fertilizer? "
                    "Consider selling at peak price months."
                    if language == "en" else
                    f"Faida ni {margin:.0f}%. "
                    "Kagua gharama — unaweza kupata mbegu au mbolea bei nafuu? "
                    "Fikiria kuuza wakati wa bei za juu."
                ),
                "priority": "high",
            })

        # Input cost optimization
        input_costs = analysis.get("input_costs", {})
        pct = input_costs.get("pct_breakdown", {})
        if pct.get("labour", 0) > 40:
            recs.append({
                "category": "costs",
                "title": "High labour costs" if language == "en" else "Gharama za juu za kazi",
                "message": (
                    f"Labour is {pct['labour']:.0f}% of expenses. "
                    "Consider group farming or mechanization to reduce costs."
                    if language == "en" else
                    f"Kazi ni {pct['labour']:.0f}% ya gharama. "
                    "Fikiria kilimo cha kikundi au mashine kupunguza gharama."
                ),
                "priority": "medium",
            })

        # Seasonal planning
        calendar = self.get_crop_calendar()
        planting = calendar.get("planting_now", [])
        if planting:
            crops = ", ".join(p["crop"] for p in planting[:3])
            recs.append({
                "category": "planning",
                "title": "Planting season" if language == "en" else "Msimu wa kupanda",
                "message": (
                    f"Good time to plant: {crops}. "
                    "Prepare your land and source seeds early."
                    if language == "en" else
                    f"Wakati mzuri wa kupanda: {crops}. "
                    "Andaa shamba yako na upate mbegu mapema."
                ),
                "priority": "medium",
            })

        # Price timing
        peak_crops = calendar.get("peak_prices_now", [])
        if peak_crops:
            crops = ", ".join(peak_crops[:3])
            recs.append({
                "category": "pricing",
                "title": "Peak prices now" if language == "en" else "Bei za juu sasa",
                "message": (
                    f"Prices are high for: {crops}. "
                    "If you have stock, this is a good time to sell."
                    if language == "en" else
                    f"Bei ni za juu kwa: {crops}. "
                    "Kama una bidhaa, huu ni wakati mzuri wa kuuza."
                ),
                "priority": "medium",
            })

        # Diversification
        crops = analysis.get("crop_analysis", [])
        if len(crops) == 1:
            recs.append({
                "category": "diversification",
                "title": "Diversify your crops" if language == "en" else "Tofautisha mazao yako",
                "message": (
                    "You're growing only one crop. Diversification reduces risk — "
                    "if prices drop, you'll still have income from other crops."
                    if language == "en" else
                    "Unalima zao moja tu. Utofautishaji unapunguza hatari — "
                    "bei ikishuka, bado utaona mapato kutoka mazao mengine."
                ),
                "priority": "medium",
            })

        return recs

    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "period_days": 0,
            "sale_count": 0,
            "expense_count": 0,
            "total_revenue": 0,
            "total_expenses": 0,
            "total_profit": 0,
            "profit_margin_pct": 0,
            "crop_analysis": [],
            "input_costs": {"breakdown": {}, "total": 0, "pct_breakdown": {}},
            "seasonal_patterns": {"by_month": {}, "best_month": None, "worst_month": None},
            "roi": {"total_input_cost": 0, "roi_pct": None, "revenue_per_ksh_input": None},
        }
