"""Retail Domain Agent — Inventory, pricing, customer behavior."""

from __future__ import annotations
from app.agents.domain.base import DomainAgent


class RetailDomainAgent(DomainAgent):
    DOMAIN_NAME = "retail"
    DOMAIN_KEYWORDS = [
        "retail", "shop", "store", "inventory", "duka", "supermarket",
        "wholesale", "mama_mboga", "dukawallah", "pos", "point_of_sale",
        "pricing", "margin", "sku",
    ]

    def __init__(self):
        super().__init__(
            name="RetailDomain",
            capabilities=[
                "inventory_optimization",
                "pricing_strategy",
                "customer_behavior_analysis",
                "demand_forecasting",
                "retail_market_intelligence",
            ],
        )
