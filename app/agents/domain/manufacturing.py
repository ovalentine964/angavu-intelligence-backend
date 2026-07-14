"""Manufacturing Domain Agent — Production, quality, supply chain.

Swahili keywords reflect East African manufacturing:
- Kiwanda (factory), uzalishaji (production), ubora (quality)
- Ghafi (raw), bidhaa (goods), viwandani (industrial)
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from app.agents.domain.base import DomainAgent


class ManufacturingDomainAgent(DomainAgent):
    DOMAIN_NAME = "manufacturing"
    DOMAIN_KEYWORDS = [
        "manufacturing", "factory", "production", "assembly",
        "quality", "waste", "raw_material", "fmcg", "goods",
        "output", "capacity", "oee", "defect", "batch",
        "supply_chain", "procurement", "warehouse",
    ]
    SWAHILI_KEYWORDS = [
        "kiwanda", "uzalishaji", "ubora", "ghafi", "bidhaa",
        "viwandani", "takataka", "gharama", "uzito",
        "vifaa", "usambazaji", "agizo", "stoo",
        "kazi", "mfanyakazi", "mashine",
    ]
    DOMAIN_METRICS = [
        "production_output", "defect_rate", "oee_score",
        "capacity_utilization", "waste_percentage", "cycle_time",
        "throughput", "quality_pass_rate",
    ]

    # STA 346 (SPC) is especially critical for manufacturing
    ACADEMIC_GROUNDING = {
        "ECO": ["ECO_202", "ECO_203"],
        "STA": ["STA_342", "STA_346"],  # SPC control charts
    }

    def __init__(self):
        super().__init__(
            name="ManufacturingDomain",
            capabilities=[
                "production_optimization",
                "quality_monitoring",
                "supply_chain_analysis",
                "fmcg_distribution_intelligence",
                "spc_monitoring",
                "defect_root_cause_analysis",
                "capacity_planning",
                "procurement_optimization",
            ],
        )

    def _query_service_data(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query ManufacturingAgent service for real production analysis."""
        if not self._transaction_service:
            return None

        transactions = payload.get("transactions", [])
        period_days = payload.get("period_days", 30)

        if not transactions:
            return None

        try:
            analysis = self._transaction_service.analyze_production(transactions, period_days)
            return analysis
        except Exception as exc:
            self._domain_logger.warning("service_query_failed", error=str(exc))
            return None

    def _analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Manufacturing analysis with SPC quality control grounding."""
        base = super()._analyze(payload)

        text = str(payload).lower()
        # Detect manufacturing sub-sector
        sub_sector = "general"
        if "fmcg" in text or "consumer" in text:
            sub_sector = "fmcg"
        elif "food" in text or "chakula" in text:
            sub_sector = "food_processing"
        elif "textile" in text or "nguo" in text:
            sub_sector = "textiles"
        elif "construction" in text or "ujenzi" in text:
            sub_sector = "construction_materials"

        # Use real data from service if available
        real_data = base.get("real_data", {})
        if real_data:
            waste_analysis = real_data.get("waste_analysis", {})
            market_signals = {
                "capacity_utilization": real_data.get("capacity_utilization", 0),
                "defect_trend": waste_analysis.get("defect_trend", "unknown"),
                "input_cost_trend": "unknown",
                "demand_outlook": "unknown",
                "total_revenue": real_data.get("total_revenue", 0),
                "waste_rate_pct": waste_analysis.get("waste_rate_pct", 0),
            }
            recommendations = real_data.get("recommendations", [
                f"Apply SPC monitoring to {sub_sector} production line",
                "Track defect rates with p-charts (STA 346)",
                "Monitor input cost trends for procurement planning",
            ])
        else:
            market_signals = {
                "capacity_utilization": 0,
                "defect_trend": "unknown",
                "input_cost_trend": "unknown",
                "demand_outlook": "unknown",
            }
            recommendations = [
                "Connect production data for real analysis",
                "Record manufacturing output to get personalized insights",
            ]

        base.update({
            "analysis_type": "manufacturing_intelligence",
            "sub_sector": sub_sector,
            "quality_control": {
                "method": "spc_control_charts",  # STA 346
                "charts": ["xbar", "ewma", "cusum", "p_chart"],
                "control_limits": "3_sigma",
                "western_electric_rules": True,
            },
            "market_signals": market_signals,
            "recommendations": recommendations,
        })
        return base

    def _process_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process manufacturing transaction with quality checks."""
        base = super()._process_transaction(payload)

        quantity = payload.get("quantity", 0)
        defects = payload.get("defects", 0)
        if quantity > 0 and defects > 0:
            defect_rate = defects / quantity
            base["quality_check"] = {
                "defect_rate": round(defect_rate * 100, 2),
                "status": "acceptable" if defect_rate < 0.03 else "high_defect_rate",
                "method": "p_chart",  # STA 346
            }
            if defect_rate > 0.05:
                base["validations"].append("alert:critical_defect_rate")

        base["domain_context"] = "manufacturing_output"
        return base
