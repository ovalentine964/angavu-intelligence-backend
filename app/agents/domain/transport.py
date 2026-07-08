"""Transport Domain Agent — Route optimization, fleet management.

Swahili keywords reflect East African transport:
- Boda boda (motorcycle taxi), matatu (minibus)
- Usafiri (transport), njia (route), mzigo (cargo)
"""

from __future__ import annotations
from typing import Any, Dict
from app.agents.domain.base import DomainAgent


class TransportDomainAgent(DomainAgent):
    DOMAIN_NAME = "transport"
    DOMAIN_KEYWORDS = [
        "transport", "logistics", "fleet", "route", "boda_boda",
        "matatu", "delivery", "shipping", "freight", "vehicle",
        "fuel", "mileage", "driver", "cargo", "warehouse",
        "distribution", "last_mile", "courier",
    ]
    SWAHILI_KEYWORDS = [
        "usafiri", "boda_boda", "matatu", "njia", "mzigo",
        "mzigo", "ghala", "dereva", "mafuta", "kilomita",
        "usambazaji", "barabara", "safari", "gari",
        "pikipiki", "baisikeli", "mkokoteni",
    ]
    DOMAIN_METRICS = [
        "delivery_time", "cost_per_km", "fleet_utilization",
        "on_time_rate", "fuel_efficiency", "route_optimization_score",
        "load_factor", "idle_time",
    ]

    ACADEMIC_GROUNDING = {
        "ECO": ["ECO_202", "ECO_203"],
        "STA": ["STA_342", "STA_346"],
    }

    def __init__(self):
        super().__init__(
            name="TransportDomain",
            capabilities=[
                "route_optimization",
                "fleet_management",
                "delivery_tracking",
                "transport_cost_analysis",
                "last_mile_optimization",
                "fuel_cost_analysis",
                "driver_performance_tracking",
                "cargo_manifest_analysis",
            ],
        )

    def _analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Transport-specific analysis with East African logistics context."""
        base = super()._analyze(payload)

        text = str(payload).lower()
        # Detect transport mode
        transport_mode = "unknown"
        if "boda_boda" in text or "pikipiki" in text:
            transport_mode = "motorcycle"
        elif "matatu" in text:
            transport_mode = "minibus"
        elif "gari" in text or "truck" in text:
            transport_mode = "truck"
        elif "baisikeli" in text or "bicycle" in text:
            transport_mode = "bicycle"
        elif "mkokoteni" in text or "cart" in text:
            transport_mode = "pushcart"

        base.update({
            "analysis_type": "transport_logistics_analysis",
            "transport_mode": transport_mode,
            "market_signals": {
                "demand_level": "moderate",
                "fuel_cost_trend": "stable",
                "route_efficiency": 0.78,
                "competition_intensity": "high",
            },
            "recommendations": [
                f"Optimize routes for {transport_mode} fleet",
                "Monitor fuel cost trends for cost management",
                "Analyze delivery time patterns for SLA compliance",
            ],
        })
        return base

    def _process_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process transport transaction with cost analysis."""
        base = super()._process_transaction(payload)

        amount = payload.get("amount", 0)
        distance = payload.get("distance_km")
        if distance and distance > 0:
            cost_per_km = amount / distance
            base["cost_analysis"] = {
                "cost_per_km": round(cost_per_km, 2),
                "distance_km": distance,
                "status": "efficient" if cost_per_km < 50 else "high_cost",
            }

        base["domain_context"] = "transport_service"
        return base
