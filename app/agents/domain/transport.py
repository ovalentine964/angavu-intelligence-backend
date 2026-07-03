"""Transport Domain Agent — Route optimization, fleet management."""

from __future__ import annotations
from app.agents.domain.base import DomainAgent


class TransportDomainAgent(DomainAgent):
    DOMAIN_NAME = "transport"
    DOMAIN_KEYWORDS = [
        "transport", "logistics", "fleet", "route", "boda_boda",
        "matatu", "delivery", "shipping", "freight", "vehicle",
    ]

    def __init__(self):
        super().__init__(
            name="TransportDomain",
            capabilities=[
                "route_optimization",
                "fleet_management",
                "delivery_tracking",
                "transport_cost_analysis",
            ],
        )
