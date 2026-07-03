"""Manufacturing Domain Agent — Production, quality, supply chain."""

from __future__ import annotations
from app.agents.domain.base import DomainAgent


class ManufacturingDomainAgent(DomainAgent):
    DOMAIN_NAME = "manufacturing"
    DOMAIN_KEYWORDS = [
        "manufacturing", "factory", "production", "assembly",
        "quality", "waste", "raw_material", "fmcg", "goods",
    ]

    def __init__(self):
        super().__init__(
            name="ManufacturingDomain",
            capabilities=[
                "production_optimization",
                "quality_monitoring",
                "supply_chain_analysis",
                "fmcg_distribution_intelligence",
            ],
        )
