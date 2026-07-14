"""Service Domain Agent — Hospitality, healthcare, education.

Swahili keywords reflect East African service sector:
- Hoteli (hotel), mgahawa (restaurant), hospitali (hospital)
- Shule (school), saluni (salon), huduma (service)
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from app.agents.domain.base import DomainAgent


class ServiceDomainAgent(DomainAgent):
    DOMAIN_NAME = "service"
    DOMAIN_KEYWORDS = [
        "service", "hospitality", "hotel", "restaurant", "healthcare",
        "clinic", "education", "school", "salon", "beauty",
        "booking", "appointment", "patient", "student",
        "customer_service", "tourism", "entertainment",
    ]
    SWAHILI_KEYWORDS = [
        "huduma", "hoteli", "mgahawa", "hospitali", "kliniki",
        "shule", "saloni", "urembo", "uhifadhi", "mteja",
        "mgonjwa", "mwanafunzi", "utalii", "burudani",
        "afya", "elimu", "usalama", "usafi",
    ]
    DOMAIN_METRICS = [
        "customer_satisfaction", "occupancy_rate", "booking_rate",
        "service_quality_score", "patient_throughput", "enrollment_rate",
        "average_wait_time", "repeat_customer_rate",
    ]

    ACADEMIC_GROUNDING = {
        "ECO": ["ECO_202", "ECO_315"],
        "STA": ["STA_342", "STA_343"],  # A/B testing for service improvements
    }

    def __init__(self):
        super().__init__(
            name="ServiceDomain",
            capabilities=[
                "service_quality_tracking",
                "customer_satisfaction_analysis",
                "service_market_intelligence",
                "booking_pattern_analysis",
                "patient_flow_optimization",
                "enrollment_forecasting",
                "staff_scheduling_analysis",
                "service_revenue_optimization",
            ],
        )

    def _query_service_data(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query ServiceAgent service for real service analysis."""
        if not self._transaction_service:
            return None

        transactions = payload.get("transactions", [])
        period_days = payload.get("period_days", 30)

        if not transactions:
            return None

        try:
            analysis = self._transaction_service.analyze_services(transactions, period_days)
            return analysis
        except Exception as exc:
            self._domain_logger.warning("service_query_failed", error=str(exc))
            return None

    def _analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Service sector analysis with customer experience focus."""
        base = super()._analyze(payload)

        text = str(payload).lower()
        # Detect service sub-sector
        sub_sector = "general"
        if any(kw in text for kw in ["hoteli", "hotel", "hospitality", "utalii"]):
            sub_sector = "hospitality"
        elif any(kw in text for kw in ["hospitali", "kliniki", "clinic", "afya"]):
            sub_sector = "healthcare"
        elif any(kw in text for kw in ["shule", "school", "education", "elimu"]):
            sub_sector = "education"
        elif any(kw in text for kw in ["saloni", "salon", "urembo", "beauty"]):
            sub_sector = "personal_care"
        elif any(kw in text for kw in ["mgahawa", "restaurant", "food"]):
            sub_sector = "food_service"

        # Use real data from service if available
        real_data = base.get("real_data", {})
        if real_data:
            client_data = real_data.get("client_analysis", {})
            market_signals = {
                "demand_trend": "unknown",
                "customer_expectations": "rising",
                "competition_level": "moderate",
                "digital_adoption": "early_stage",
                "total_revenue": real_data.get("total_revenue", 0),
                "job_count": real_data.get("job_count", 0),
                "retention_rate": client_data.get("retention_rate_pct", 0),
            }
            recommendations = real_data.get("recommendations", [
                f"Implement A/B testing for {sub_sector} service improvements (STA 343)",
                "Track customer satisfaction with structured surveys (ECO 315)",
                "Analyze booking patterns for capacity optimization",
            ])
        else:
            market_signals = {
                "demand_trend": "unknown",
                "customer_expectations": "unknown",
                "competition_level": "unknown",
                "digital_adoption": "unknown",
            }
            recommendations = [
                "Connect service data for real analysis",
                "Record service transactions to get personalized insights",
            ]

        base.update({
            "analysis_type": "service_sector_intelligence",
            "sub_sector": sub_sector,
            "market_signals": market_signals,
            "recommendations": recommendations,
        })
        return base

    def _process_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process service transaction with satisfaction signal."""
        base = super()._process_transaction(payload)

        rating = payload.get("rating")
        if rating is not None:
            base["satisfaction_signal"] = {
                "rating": rating,
                "status": "positive" if rating >= 4 else "neutral" if rating >= 3 else "negative",
            }

        base["domain_context"] = "service_transaction"
        return base
