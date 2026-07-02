"""
ManufacturingAgent — Domain intelligence for jua kali workshops, furniture makers, welders.

Capabilities:
    - Production cycle tracking
    - Raw material management and cost tracking
    - Distribution optimization
    - Production cost calculation (materials + labour)
    - Order tracking and management
    - Waste/scrap tracking
    - Bulk order pricing
    - Capacity utilization

Tier: 2 (Domain) — activated when worker type is MANUFACTURING
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class ManufacturingAgent:
    """
    Specialized intelligence for manufacturing/craft workers.

    Analyzes production costs, material usage, and order patterns
    to optimize pricing, waste reduction, and capacity planning.
    """

    name = "ManufacturingAgent"
    role = "Manufacturing business intelligence specialist"
    tier = 2
    worker_types = ["jua_kali", "furniture_maker", "welder", "brick_maker", "potter"]

    def __init__(self):
        self._logger = logger.bind(agent=self.name)

    # ── Production Analysis ─────────────────────────────────────────

    def analyze_production(
        self,
        transactions: List[Dict[str, Any]],
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Analyze manufacturing transactions for production insights.

        Args:
            transactions: Transaction dicts
            period_days: Analysis window

        Returns:
            Dict with manufacturing-specific analytics
        """
        if not transactions:
            return self._empty_analysis()

        sales = [
            t for t in transactions
            if t.get("transaction_type") == "SALE"
        ]
        materials = [
            t for t in transactions
            if t.get("transaction_type") in ("PURCHASE", "EXPENSE")
        ]

        # Product performance
        product_analysis = self._analyze_products(sales)

        # Material costs
        material_analysis = self._analyze_materials(materials)

        # Production cost per unit
        cost_analysis = self._analyze_production_costs(sales, materials)

        # Order patterns
        order_patterns = self._analyze_orders(sales)

        # Waste analysis
        waste_analysis = self._analyze_waste(sales, materials)

        total_revenue = sum(t.get("amount", 0) for t in sales)
        total_materials = sum(t.get("amount", 0) for t in materials)

        return {
            "period_days": period_days,
            "order_count": len(sales),
            "material_purchase_count": len(materials),
            "total_revenue": round(total_revenue, 2),
            "total_material_costs": round(total_materials, 2),
            "gross_profit": round(total_revenue - total_materials, 2),
            "gross_margin_pct": round(
                ((total_revenue - total_materials) / total_revenue * 100)
                if total_revenue > 0 else 0, 1
            ),
            "product_analysis": product_analysis,
            "material_analysis": material_analysis,
            "cost_analysis": cost_analysis,
            "order_patterns": order_patterns,
            "waste_analysis": waste_analysis,
        }

    def _analyze_products(
        self, sales: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze performance per product."""
        product_data: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"revenue": 0, "profit": 0, "qty": 0, "count": 0}
        )
        for t in sales:
            item = t.get("item", "Unknown Product")
            product_data[item]["revenue"] += t.get("amount", 0)
            product_data[item]["profit"] += t.get("profit", 0) or 0
            product_data[item]["qty"] += t.get("quantity", 0) or 0
            product_data[item]["count"] += 1

        ranked = sorted(
            product_data.items(), key=lambda x: x[1]["revenue"], reverse=True
        )
        return [
            {
                "product": name,
                "revenue": round(d["revenue"], 2),
                "profit": round(d["profit"], 2),
                "units_produced": round(d["qty"], 1),
                "order_count": int(d["count"]),
                "avg_price": round(
                    d["revenue"] / d["qty"], 2
                ) if d["qty"] > 0 else 0,
                "margin_pct": round(
                    d["profit"] / d["revenue"] * 100, 1
                ) if d["revenue"] > 0 else 0,
            }
            for name, d in ranked[:15]
        ]

    def _analyze_materials(
        self, materials: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze raw material costs and usage."""
        material_costs: Dict[str, float] = defaultdict(float)
        material_qty: Dict[str, float] = defaultdict(float)

        for t in materials:
            item = t.get("item", "Unknown Material")
            material_costs[item] += t.get("amount", 0)
            material_qty[item] += t.get("quantity", 0) or 0

        total = sum(material_costs.values())
        ranked = sorted(material_costs.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_material_cost": round(total, 2),
            "breakdown": [
                {
                    "material": name,
                    "cost": round(cost, 2),
                    "pct_of_total": round(cost / total * 100, 1) if total > 0 else 0,
                    "quantity": round(material_qty[name], 1),
                }
                for name, cost in ranked[:10]
            ],
        }

    def _analyze_production_costs(
        self,
        sales: List[Dict[str, Any]],
        materials: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calculate production cost per product."""
        total_materials = sum(t.get("amount", 0) for t in materials)
        total_revenue = sum(t.get("amount", 0) for t in sales)
        total_units = sum(t.get("quantity", 0) or 0 for t in sales)

        # Estimate labour as 30-40% of (revenue - materials)
        labour_estimate = max(0, (total_revenue - total_materials) * 0.35)
        total_cost = total_materials + labour_estimate

        cost_per_unit = total_cost / total_units if total_units > 0 else None

        return {
            "total_production_cost": round(total_cost, 2),
            "material_cost": round(total_materials, 2),
            "labour_cost_estimate": round(labour_estimate, 2),
            "cost_per_unit": round(cost_per_unit, 2) if cost_per_unit else None,
            "revenue_per_unit": round(
                total_revenue / total_units, 2
            ) if total_units > 0 else None,
        }

    def _analyze_orders(
        self, sales: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze order patterns."""
        # Order value distribution
        values = [t.get("amount", 0) for t in sales if t.get("amount", 0) > 0]
        if not values:
            return {"avg_order": 0, "median_order": 0, "large_orders": 0}

        large_threshold = statistics.mean(values) * 2 if values else 0
        large_orders = sum(1 for v in values if v >= large_threshold)

        return {
            "avg_order": round(statistics.mean(values), 2),
            "median_order": round(statistics.median(values), 2),
            "min_order": round(min(values), 2),
            "max_order": round(max(values), 2),
            "large_orders": large_orders,
            "large_order_threshold": round(large_threshold, 2),
        }

    def _analyze_waste(
        self,
        sales: List[Dict[str, Any]],
        materials: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Estimate material waste rate."""
        total_materials = sum(t.get("amount", 0) for t in materials)
        total_revenue = sum(t.get("amount", 0) for t in sales)
        total_profit = sum(t.get("profit", 0) or 0 for t in sales)

        # Estimate waste as material cost minus (revenue - profit)
        expected_material_use = total_revenue - total_profit
        estimated_waste = max(0, total_materials - expected_material_use)
        waste_rate = (estimated_waste / total_materials * 100) if total_materials > 0 else 0

        return {
            "total_materials": round(total_materials, 2),
            "estimated_waste": round(estimated_waste, 2),
            "waste_rate_pct": round(waste_rate, 1),
        }

    # ── Recommendations ─────────────────────────────────────────────

    def get_recommendations(
        self,
        analysis: Dict[str, Any],
        language: str = "en",
    ) -> List[Dict[str, str]]:
        """Generate manufacturing-specific recommendations."""
        recs = []

        # Margin
        margin = analysis.get("gross_margin_pct", 0)
        if margin < 30:
            recs.append({
                "category": "pricing",
                "title": "Low margins" if language == "en" else "Faida ndogo",
                "message": (
                    f"Gross margin is {margin:.0f}%. "
                    "Review material costs — can you buy in bulk for discounts? "
                    "Consider raising prices for custom work."
                    if language == "en" else
                    f"Faida ni {margin:.0f}%. "
                    "Kagua gharama za vifaa — unaweza kununua kwa wingi kwa punguzo? "
                    "Fikiria kupandisha bei kwa maalum."
                ),
                "priority": "high",
            })

        # Waste
        waste = analysis.get("waste_analysis", {})
        waste_rate = waste.get("waste_rate_pct", 0)
        if waste_rate > 15:
            recs.append({
                "category": "waste",
                "title": "High material waste" if language == "en" else "Upote mkubwa wa vifaa",
                "message": (
                    f"Estimated waste is {waste_rate:.0f}% of materials. "
                    "Review cutting/production techniques. "
                    "Sell or repurpose scrap materials."
                    if language == "en" else
                    f"Upote ni {waste_rate:.0f}% ya vifaa. "
                    "Kagua mbinu za kukata/uzalishaji. "
                    "Uza au tumia tena vifaa vya taka."
                ),
                "priority": "high",
            })

        # Top product
        products = analysis.get("product_analysis", [])
        if products:
            top = products[0]
            recs.append({
                "category": "focus",
                "title": "Best product" if language == "en" else "Bidhaa bora",
                "message": (
                    f"'{top['product']}' earns KSh {top['revenue']:,.0f} "
                    f"with {top['margin_pct']:.0f}% margin. "
                    "Focus production capacity on this."
                    if language == "en" else
                    f"'{top['product']}' inalipa KSh {top['revenue']:,.0f} "
                    f"na faida ya {top['margin_pct']:.0f}%. "
                    "Zingatia uwezo wa uzalishaji hapa."
                ),
                "priority": "medium",
            })

        # Material sourcing
        materials = analysis.get("material_analysis", {})
        breakdown = materials.get("breakdown", [])
        if breakdown and len(breakdown) >= 2:
            top_material = breakdown[0]
            if top_material.get("pct_of_total", 0) > 50:
                recs.append({
                    "category": "materials",
                    "title": "Bulk buying opportunity" if language == "en" else "Fursa ya kununua kwa wingi",
                    "message": (
                        f"'{top_material['material']}' is {top_material['pct_of_total']:.0f}% "
                        "of material costs. Buy in bulk for better prices."
                        if language == "en" else
                        f"'{top_material['material']}' ni {top_material['pct_of_total']:.0f}% "
                        "ya gharama za vifaa. Nunua kwa wingi kwa bei bora."
                    ),
                    "priority": "medium",
                })

        # Large orders
        orders = analysis.get("order_patterns", {})
        large = orders.get("large_orders", 0)
        if large > 0:
            recs.append({
                "category": "orders",
                "title": "Large order opportunities" if language == "en" else "Fursa za maagizo makubwa",
                "message": (
                    f"You had {large} large orders. "
                    "Consider offering bulk discounts to attract more."
                    if language == "en" else
                    f"Ulikuwa na maagizo makubwa {large}. "
                    "Fikiria kutoa punguzo la wingi kuvutia zaidi."
                ),
                "priority": "medium",
            })

        return recs

    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "period_days": 0,
            "order_count": 0,
            "material_purchase_count": 0,
            "total_revenue": 0,
            "total_material_costs": 0,
            "gross_profit": 0,
            "gross_margin_pct": 0,
            "product_analysis": [],
            "material_analysis": {"total_material_cost": 0, "breakdown": []},
            "cost_analysis": {
                "total_production_cost": 0, "material_cost": 0,
                "labour_cost_estimate": 0, "cost_per_unit": None,
                "revenue_per_unit": None,
            },
            "order_patterns": {"avg_order": 0, "median_order": 0, "large_orders": 0},
            "waste_analysis": {"total_materials": 0, "estimated_waste": 0, "waste_rate_pct": 0},
        }
