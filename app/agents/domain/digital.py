"""Digital Domain Agent — E-commerce, digital payments."""

from __future__ import annotations
from app.agents.domain.base import DomainAgent


class DigitalDomainAgent(DomainAgent):
    DOMAIN_NAME = "digital"
    DOMAIN_KEYWORDS = [
        "digital", "ecommerce", "e_commerce", "online", "mpesa",
        "mobile_money", "payment", "fintech", "app", "platform",
    ]

    def __init__(self):
        super().__init__(
            name="DigitalDomain",
            capabilities=[
                "digital_payment_analysis",
                "ecommerce_intelligence",
                "platform_usage_tracking",
                "fintech_market_analysis",
            ],
        )
