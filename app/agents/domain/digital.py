"""Digital Domain Agent — E-commerce, digital payments, fintech.

Swahili keywords reflect East African digital economy:
- M-Pesa, malipo (payments), mtandao (network)
- Simu (phone), mkoba (wallet), pesa (money)
"""

from __future__ import annotations
from typing import Any, Dict
from app.agents.domain.base import DomainAgent


class DigitalDomainAgent(DomainAgent):
    DOMAIN_NAME = "digital"
    DOMAIN_KEYWORDS = [
        "digital", "ecommerce", "e_commerce", "online", "mpesa",
        "mobile_money", "payment", "fintech", "app", "platform",
        "api", "gateway", "transaction", "wallet", "airtime",
        "data_bundle", "subscription", "saas",
    ]
    SWAHILI_KEYWORDS = [
        "malipo", "mtandao", "simu", "mkoba", "pesa",
        "mpesa", "huduma", "teknolojia", "dijitali",
        "airtime", "data", "kifurushi", "usajili",
        "mtandao", "intaneti", "programu",
    ]
    DOMAIN_METRICS = [
        "transaction_volume", "digital_adoption_rate", "uptime",
        "api_response_time", "error_rate", "active_users",
        "transaction_value", "conversion_rate",
    ]

    ACADEMIC_GROUNDING = {
        "ECO": ["ECO_202", "ECO_203"],
        "STA": ["STA_342", "STA_343", "STA_346"],
    }

    def __init__(self):
        super().__init__(
            name="DigitalDomain",
            capabilities=[
                "digital_payment_analysis",
                "ecommerce_intelligence",
                "platform_usage_tracking",
                "fintech_market_analysis",
                "api_performance_monitoring",
                "user_engagement_analysis",
                "digital_adoption_tracking",
                "conversion_optimization",
            ],
        )

    def _analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Digital economy analysis with East African fintech context."""
        base = super()._analyze(payload)

        text = str(payload).lower()
        # Detect digital platform type
        platform_type = "unknown"
        if "mpesa" in text or "mobile_money" in text:
            platform_type = "mobile_money"
        elif "ecommerce" in text or "e_commerce" in text or "online" in text:
            platform_type = "ecommerce"
        elif "fintech" in text or "api" in text:
            platform_type = "fintech_platform"
        elif "saas" in text or "subscription" in text:
            platform_type = "saas"

        base.update({
            "analysis_type": "digital_economy_analysis",
            "platform_type": platform_type,
            "market_signals": {
                "digital_adoption_trend": "growing",
                "mobile_penetration": 0.85,
                "internet_penetration": 0.45,
                "fintech_competition": "intense",
            },
            "recommendations": [
                f"Monitor {platform_type} adoption metrics",
                "Track API performance and error rates",
                "Analyze user engagement and retention patterns",
            ],
        })
        return base

    def _process_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process digital transaction with fraud signal detection."""
        base = super()._process_transaction(payload)

        amount = payload.get("amount", 0)
        # Flag unusual digital transaction patterns
        if amount > 100000:
            base["validations"].append("high_value_digital_transaction")
        if amount == 0:
            base["validations"].append("zero_value_transaction")

        base["domain_context"] = "digital_transaction"
        return base
