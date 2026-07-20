"""
Intelligence Pipeline — Core Orchestration.

Factory functions for creating intelligence pipeline orchestrators,
drift monitoring integration, and harness wiring.

Domain agents, planners, and aggregators live in pipeline_intelligence.py.
Data queries live in pipeline_data.py.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.agents.long_horizon import (
    LongHorizonOrchestrator,
    SubAgentDelegator,
)
from app.agents.loops import EventStore
from app.agents.pipeline_agents import (
    CompetitorAgent,
    CreditAnalysisAgent,
    DistributionAgent,
    MarketDataAgent,
)
from app.agents.pipeline_planners import (
    CompetitorPlanner,
    CompetitorResultAggregator,
    CreditScoringPlanner,
    CreditResultAggregator,
    DistributionPlanner,
    DistributionResultAggregator,
    MarketAnalysisPlanner,
    MarketResultAggregator,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Factory Functions — Create Domain-Specific Orchestrators
# ════════════════════════════════════════════════════════════════════


def create_market_analysis_flow(
    event_store: EventStore | None = None,
) -> LongHorizonOrchestrator:
    """Create a market analysis orchestrator."""
    delegator = SubAgentDelegator()
    delegator.register_agent(MarketDataAgent())

    return LongHorizonOrchestrator(
        name="MarketAnalysisFlow",
        planner=MarketAnalysisPlanner(),
        delegator=delegator,
        aggregator=MarketResultAggregator(),
        max_parallel=3,
        event_store=event_store,
    )


def create_credit_scoring_flow(
    event_store: EventStore | None = None,
) -> LongHorizonOrchestrator:
    """Create a credit scoring orchestrator."""
    delegator = SubAgentDelegator()
    delegator.register_agent(CreditAnalysisAgent())

    return LongHorizonOrchestrator(
        name="CreditScoringFlow",
        planner=CreditScoringPlanner(),
        delegator=delegator,
        aggregator=CreditResultAggregator(),
        max_parallel=2,
        event_store=event_store,
    )


def create_distribution_analysis_flow(
    event_store: EventStore | None = None,
) -> LongHorizonOrchestrator:
    """Create a distribution analysis orchestrator."""
    delegator = SubAgentDelegator()
    delegator.register_agent(DistributionAgent())

    return LongHorizonOrchestrator(
        name="DistributionAnalysisFlow",
        planner=DistributionPlanner(),
        delegator=delegator,
        aggregator=DistributionResultAggregator(),
        max_parallel=2,
        event_store=event_store,
    )


def create_competitor_analysis_flow(
    event_store: EventStore | None = None,
) -> LongHorizonOrchestrator:
    """Create a competitor analysis orchestrator."""
    delegator = SubAgentDelegator()
    delegator.register_agent(CompetitorAgent())

    return LongHorizonOrchestrator(
        name="CompetitorAnalysisFlow",
        planner=CompetitorPlanner(),
        delegator=delegator,
        aggregator=CompetitorResultAggregator(),
        max_parallel=2,
        event_store=event_store,
    )


def create_all_intelligence_flows(
    event_store: EventStore | None = None,
) -> dict[str, LongHorizonOrchestrator]:
    """Create all intelligence pipeline orchestrators."""
    return {
        "market_analysis": create_market_analysis_flow(event_store),
        "credit_scoring": create_credit_scoring_flow(event_store),
        "distribution_analysis": create_distribution_analysis_flow(event_store),
        "competitor_analysis": create_competitor_analysis_flow(event_store),
    }


# ════════════════════════════════════════════════════════════════════
# Drift Monitoring Integration — Wire CUSUM to the intelligence pipeline
# ════════════════════════════════════════════════════════════════════


class IntelligenceDriftMonitor:
    """Wires CUSUM drift detection to the intelligence pipeline.

    Monitors key metrics across all intelligence products:
    - Alama Score accuracy (credit model performance)
    - Revenue prediction error (market model performance)
    - Data distribution shifts (feature drift)
    - GDP estimation accuracy (macro model performance)

    When drift is detected, alerts are generated in Swahili:
        "Soko la nyanya limebadilika — bei imepanda 30%"

    And automatic retraining is triggered via the task queue.
    """

    def __init__(self):
        from app.services.drift_detector import ModelDriftMonitor

        self.monitor = ModelDriftMonitor()
        self._setup_metrics()
        self._last_alerts: dict[str, Any] = {}

    def _setup_metrics(self) -> None:
        """Configure CUSUM detectors for key intelligence metrics."""
        self.monitor.add_metric(
            "alama_score_accuracy",
            baseline_mean=0.85,
            baseline_std=0.05,
            delta=1.0,
            h=4.0,
        )
        self.monitor.add_metric(
            "revenue_prediction_error",
            baseline_mean=0.10,
            baseline_std=0.03,
            delta=1.0,
            h=4.0,
        )
        self.monitor.add_metric(
            "feature_distribution_shift",
            baseline_mean=0.0,
            baseline_std=0.05,
            delta=0.8,
            h=3.5,
        )
        self.monitor.add_metric(
            "gdp_estimation_error",
            baseline_mean=0.05,
            baseline_std=0.02,
            delta=1.0,
            h=4.0,
        )

    async def check_alama_score(self, predicted_score: int, actual_outcome: int) -> None:
        """Check Alama Score prediction accuracy and detect drift."""
        error = abs(predicted_score - actual_outcome) / 550.0
        accuracy = max(0, 1 - error)
        self.monitor.update("alama_score_accuracy", accuracy)

    async def check_revenue_prediction(
        self, predicted_revenue: float, actual_revenue: float
    ) -> None:
        """Check revenue prediction accuracy."""
        if actual_revenue > 0:
            error = abs(predicted_revenue - actual_revenue) / actual_revenue
            self.monitor.update("revenue_prediction_error", error)

    async def check_feature_distribution(
        self, feature_name: str, current_mean: float, baseline_mean: float
    ) -> None:
        """Check for data distribution shift in a feature."""
        if baseline_mean > 0:
            shift = abs(current_mean - baseline_mean) / baseline_mean
            self.monitor.update("feature_distribution_shift", shift)

    async def check_gdp_estimation(
        self, estimated_gdp: float, reference_gdp: float
    ) -> None:
        """Check GDP estimation accuracy against reference."""
        if reference_gdp > 0:
            error = abs(estimated_gdp - reference_gdp) / reference_gdp
            self.monitor.update("gdp_estimation_error", error)

    def get_status(self) -> dict[str, Any]:
        """Get current drift monitoring status across all metrics."""
        return self.monitor.get_overall_status()

    def get_alerts(self, limit: int = 20) -> list:
        """Get recent drift alerts."""
        return self.monitor.get_all_alerts(limit=limit)

    def generate_swahili_alert(self, metric_name: str, drift_pct: float, product: str) -> str:
        """Generate a Swahili drift alert message."""
        direction = "imepanda" if drift_pct > 0 else "imepungua"
        abs_pct = abs(drift_pct)

        if "price" in product.lower() or "soko" in product.lower():
            return f"Soko la {product} limebadilika — bei {direction} {abs_pct:.0f}%"
        elif "alama" in product.lower() or "credit" in product.lower():
            return f"Alama za mikopo zimebadilika — utabiri {direction} {abs_pct:.0f}%"
        elif "gdp" in product.lower():
            return f"GDP ya soko la informal imebadilika — makadirio {direction} {abs_pct:.0f}%"
        elif "revenue" in product.lower() or "mapato" in product.lower():
            return f"Mapato ya biashara yamebadilika — makadirio {direction} {abs_pct:.0f}%"
        else:
            return f"Data ya {product} imebadilika — thamani {direction} {abs_pct:.0f}%"


# Singleton instance for use across the application
_intelligence_drift_monitor: IntelligenceDriftMonitor | None = None


def get_intelligence_drift_monitor() -> IntelligenceDriftMonitor:
    """Get or create the singleton drift monitor for the intelligence pipeline."""
    global _intelligence_drift_monitor
    if _intelligence_drift_monitor is None:
        _intelligence_drift_monitor = IntelligenceDriftMonitor()
    return _intelligence_drift_monitor


# Type aliases for import convenience
MarketAnalysisFlow = LongHorizonOrchestrator
CreditScoringFlow = LongHorizonOrchestrator
DistributionAnalysisFlow = LongHorizonOrchestrator
CompetitorAnalysisFlow = LongHorizonOrchestrator


# ════════════════════════════════════════════════════════════════════
# Harness Integration — Wire DataPipelineHarness to intelligence flows
# ════════════════════════════════════════════════════════════════════


def create_harnessed_flows(
    event_store: EventStore | None = None,
    harness: Any | None = None,
) -> dict[str, Any]:
    """
    Create all intelligence flows wrapped with DataPipelineHarness.

    Each flow is wrapped in a HarnessedIntelligenceFlow that adds:
    - Input deduplication
    - Input/output quality scoring
    - Drift detection
    - Metrics collection (quality, drift, latency)
    - Auto-retrain on critical drift
    """
    from app.agents.harness.data_harness import (
        HarnessedIntelligenceFlow,
        get_data_pipeline_harness,
    )

    flows = create_all_intelligence_flows(event_store=event_store)
    h = harness or get_data_pipeline_harness()

    drift_monitor = get_intelligence_drift_monitor()
    h.add_alert_hook(lambda alert: _forward_drift_to_monitor(drift_monitor, alert))

    harnessed = {}
    for name, orch in flows.items():
        harnessed[name] = HarnessedIntelligenceFlow(
            orchestrator=orch,
            pipeline_name=name,
            harness=h,
        )

    logger.info(
        "harnessed_intelligence_flows_created",
        flows=list(harnessed.keys()),
        drift_monitoring=True,
    )
    return harnessed


async def _forward_drift_to_monitor(
    drift_monitor: IntelligenceDriftMonitor,
    alert: Any,
) -> None:
    """Forward a harness DriftAlert to the intelligence drift monitor."""
    try:
        pipeline = getattr(alert, "pipeline_name", "")
        drift_type = getattr(alert, "drift_type", "")
        magnitude = getattr(alert, "drift_magnitude", 0.0)

        if pipeline == "credit_scoring":
            drift_monitor.monitor.update("alama_score_accuracy", 1.0 - magnitude)
        elif pipeline == "market_analysis":
            drift_monitor.monitor.update("revenue_prediction_error", magnitude)
        elif pipeline in ("distribution_analysis", "competitor_analysis"):
            drift_monitor.monitor.update("feature_distribution_shift", magnitude)

        if getattr(alert, "severity", "") == "critical":
            swahili_msg = drift_monitor.generate_swahili_alert(
                pipeline, magnitude * 100, pipeline,
            )
            logger.warning(
                "swahili_drift_alert",
                message=swahili_msg,
                pipeline=pipeline,
                severity="critical",
            )
    except Exception as exc:
        logger.debug("drift_forward_error", error=str(exc))


# ── Singleton harnessed flows ──
_harnessed_flows: dict[str, Any] | None = None


def get_harnessed_intelligence_flows(
    event_store: EventStore | None = None,
) -> dict[str, Any]:
    """Get or create singleton harnessed intelligence flows."""
    global _harnessed_flows
    if _harnessed_flows is None:
        _harnessed_flows = create_harnessed_flows(event_store=event_store)
    return _harnessed_flows
