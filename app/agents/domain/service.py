"""Service Domain Agent — Hospitality, healthcare, education."""

from __future__ import annotations
from app.agents.domain.base import DomainAgent


class ServiceDomainAgent(DomainAgent):
    DOMAIN_NAME = "service"
    DOMAIN_KEYWORDS = [
        "service", "hospitality", "hotel", "restaurant", "healthcare",
        "clinic", "education", "school", "salon", "beauty",
    ]

    def __init__(self):
        super().__init__(
            name="ServiceDomain",
            capabilities=[
                "service_quality_tracking",
                "customer_satisfaction_analysis",
                "service_market_intelligence",
                "booking_pattern_analysis",
            ],
        )
