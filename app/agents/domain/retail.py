"""Retail Domain Agent — Inventory, pricing, customer behavior.

Swahili keywords reflect East African retail landscape:
- Duka (shop), mama_mboga (vegetable vendor), dukawallah (shopkeeper)
- Bidhaa (goods), bei (price), hisabati (accounts)
"""

from __future__ import annotations

from typing import Any

from app.agents.domain.base import DomainAgent


class RetailDomainAgent(DomainAgent):
    DOMAIN_NAME = "retail"
    DOMAIN_KEYWORDS = [
        "retail", "shop", "store", "inventory", "duka", "supermarket",
        "wholesale", "mama_mboga", "dukawallah", "pos", "point_of_sale",
        "pricing", "margin", "sku", "stock", "supplier", "customer",
        "checkout", "basket", "revenue", "turnover",
    ]
    SWAHILI_KEYWORDS = [
        "duka", "bidhaa", "bei", "hisabati", "mteja", "msambazaji",
        "mama_mboga", "soko", "ununuzi", "mauzo", "stoo",
        "fursa", "biashara", "mali", "gharama", "faida",
        "wateja", "manunuzi", "uzalishaji",
    ]
    DOMAIN_METRICS = [
        "inventory_turnover", "gross_margin", "basket_size",
        "customer_footfall", "stockout_rate", "pricing_variance",
        "revenue_per_sqm", "sell_through_rate",
    ]

    ACADEMIC_GROUNDING = {
        "ECO": ["ECO_202", "ECO_203"],
        "STA": ["STA_342", "STA_346"],
    }

    def __init__(self):
        super().__init__(
            name="RetailDomain",
            capabilities=[
                "inventory_optimization",
                "pricing_strategy",
                "customer_behavior_analysis",
                "demand_forecasting",
                "retail_market_intelligence",
                "margin_optimization",
                "stockout_prediction",
                "customer_segmentation",
            ],
        )

    def _query_service_data(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Query RetailAgent service for real sales analysis."""
        if not self._transaction_service:
            return None

        transactions = payload.get("transactions", [])
        period_days = payload.get("period_days", 30)
        inventory = payload.get("inventory")

        if not transactions:
            return None

        try:
            analysis = self._transaction_service.analyze_sales(
                transactions, inventory=inventory, period_days=period_days
            )
            return analysis
        except Exception as exc:
            self._domain_logger.warning("service_query_failed", error=str(exc))
            return None

    def _analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Retail-specific analysis with East African market context."""
        base = super()._analyze(payload)

        text = str(payload).lower()
        # Detect retail channel
        channel = "unknown"
        if any(kw in text for kw in ["duka", "dukawallah", "shop"]):
            channel = "informal_retail"
        elif any(kw in text for kw in ["supermarket", "chain", "franchise"]):
            channel = "formal_retail"
        elif any(kw in text for kw in ["mama_mboga", "kiosk", "stand"]):
            channel = "micro_retail"
        elif any(kw in text for kw in ["wholesale", "distributor"]):
            channel = "wholesale"

        # Use real data from service if available
        real_data = base.get("real_data", {})
        if real_data:
            market_signals = {
                "demand_pattern": real_data.get("demand_pattern", "unknown"),
                "price_sensitivity": "high",
                "seasonal_trend": real_data.get("seasonal_trend", "normal"),
                "competition_level": "moderate",
                "total_revenue": real_data.get("total_revenue", 0),
                "total_profit": real_data.get("total_profit", 0),
                "avg_margin_pct": real_data.get("avg_margin_pct", 0),
                "sale_count": real_data.get("sale_count", 0),
            }
            recommendations = real_data.get("recommendations", [
                f"Optimize inventory for {channel} channel",
                "Monitor pricing against local competitors",
                "Track customer basket composition",
            ])
        else:
            market_signals = {
                "demand_pattern": "unavailable",
                "price_sensitivity": "unknown",
                "seasonal_trend": "unknown",
                "competition_level": "unknown",
            }
            recommendations = [
                "Connect transaction data for real analysis",
                "Record sales to get personalized retail insights",
            ]

        base.update({
            "analysis_type": "retail_intelligence",
            "channel_detected": channel,
            "market_signals": market_signals,
            "recommendations": recommendations,
        })
        return base

    def _process_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process retail transaction with margin analysis."""
        base = super()._process_transaction(payload)

        price = payload.get("price")
        cost = payload.get("cost")
        if price and cost and cost > 0:
            margin = (price - cost) / cost
            base["margin_analysis"] = {
                "margin_pct": round(margin * 100, 2),
                "status": "healthy" if margin > 0.15 else "low_margin",
            }
            if margin < 0.05:
                base["validations"].append("warning:very_low_margin")

        base["domain_context"] = "retail_transaction"
        return base
