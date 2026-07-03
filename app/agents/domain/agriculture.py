"""Agriculture Domain Agent — Crop prices, weather, supply chain."""

from __future__ import annotations
from typing import List
from app.agents.domain.base import DomainAgent


class AgricultureDomainAgent(DomainAgent):
    DOMAIN_NAME = "agriculture"
    DOMAIN_KEYWORDS = [
        "crop", "farm", "harvest", "seed", "fertilizer", "livestock",
        "dairy", "maize", "wheat", "coffee", "tea", "horticulture",
        "agriculture", "agri", "irrigation",
    ]

    def __init__(self):
        super().__init__(
            name="AgricultureDomain",
            capabilities=[
                "crop_price_tracking",
                "weather_impact_analysis",
                "supply_chain_optimization",
                "harvest_forecasting",
                "agricultural_market_intelligence",
            ],
        )
