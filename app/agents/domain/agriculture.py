"""Agriculture Domain Agent — Crop prices, weather, supply chain.

Swahili keywords reflect East African agricultural markets:
- Nyanya (tomatoes), maharagwe (beans), viazi (potatoes)
- Soko (market), bei (price), mazao (crops)
"""

from __future__ import annotations
from typing import Any, Dict
from app.agents.domain.base import DomainAgent


class AgricultureDomainAgent(DomainAgent):
    DOMAIN_NAME = "agriculture"
    DOMAIN_KEYWORDS = [
        "crop", "farm", "harvest", "seed", "fertilizer", "livestock",
        "dairy", "maize", "wheat", "coffee", "tea", "horticulture",
        "agriculture", "agri", "irrigation", "produce", "commodity",
        "yield", "plantation", "greenhouse",
    ]
    SWAHILI_KEYWORDS = [
        "mazao", "shamba", "mvuno", "mbegu", "mbolea", "mifugo",
        "nyanya", "maharagwe", "viazi", "mahindi", "ngano",
        "kahawa", "chai", "soko", "bei", "kilimo", "umwagiliaji",
        "ugali", "sukari", "mchele", "ndizi", "machungwa",
        "chakula", "wakulima", "mkulima",
    ]
    DOMAIN_METRICS = [
        "crop_price", "yield_per_acre", "weather_impact",
        "supply_chain_latency", "market_price_volatility",
        "harvest_volume", "input_cost_index",
    ]

    # Academic grounding specific to agriculture
    ACADEMIC_GROUNDING = {
        "ECO": ["ECO_202", "ECO_203", "ECO_315"],
        "STA": ["STA_342", "STA_346"],
    }

    def __init__(self):
        super().__init__(
            name="AgricultureDomain",
            capabilities=[
                "crop_price_tracking",
                "weather_impact_analysis",
                "supply_chain_optimization",
                "harvest_forecasting",
                "agricultural_market_intelligence",
                "commodity_index_tracking",
                "input_cost_analysis",
                "agricultural_risk_assessment",
            ],
        )

    def _analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Agriculture-specific analysis with Swahili market context.

        Args:
            payload: Event payload containing analysis parameters.

        Returns:
            Analysis results with detected crops, market signals, and
            ECO/STA-grounded recommendations.
        """
        base: Dict[str, Any] = super()._analyze(payload)

        # Detect crop type from Swahili/English keywords
        text = str(payload).lower()
        detected_crops = []
        crop_map = {
            "nyanya": "tomatoes", "maharagwe": "beans", "viazi": "potatoes",
            "mahindi": "maize", "ngano": "wheat", "kahawa": "coffee",
            "chai": "tea", "sukari": "sugar", "mchele": "rice",
            "ndizi": "bananas", "machungwa": "oranges",
        }
        for sw, en in crop_map.items():
            if sw in text or en in text:
                detected_crops.append({"swahili": sw, "english": en})

        base.update({
            "analysis_type": "agricultural_market_analysis",
            "detected_crops": detected_crops,
            "market_signals": {
                "price_trend": "stable",  # Would be computed from real data
                "supply_index": 0.75,
                "demand_index": 0.82,
                "seasonal_factor": "planting_season",
            },
            "recommendations": [
                "Monitor price movements for detected crops",
                "Track weather patterns affecting supply",
                "Analyze input cost trends (fertilizer, seeds)",
            ],
        })
        return base

    def _process_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process agricultural transaction with commodity validation."""
        base = super()._process_transaction(payload)

        # Agricultural-specific validations
        amount = payload.get("amount", 0)
        if amount > 1000000:
            base["validations"].append("large_transaction_flag")
        if amount < 10:
            base["validations"].append("micro_transaction")

        base["domain_context"] = "agricultural_commodity"
        return base
