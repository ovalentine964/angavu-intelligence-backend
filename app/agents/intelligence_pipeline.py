"""
Intelligence Pipeline — Backward-Compatible Re-Export Shim.

Decomposed into:
- pipeline_data.py          — Database query helpers (695 lines)
- pipeline_agents.py        — Domain agent implementations (~450 lines)
- pipeline_planners.py      — Task planners and result aggregators (~250 lines)
- pipeline_core.py          — Factory functions, drift monitoring (~340 lines)
- pipeline_intelligence.py  — Re-export shim for agents + planners

All existing imports from `app.agents.intelligence_pipeline` continue to work.
"""

from __future__ import annotations

# Agents
from app.agents.pipeline_agents import (
    CompetitorAgent,
    CreditAnalysisAgent,
    DistributionAgent,
    MarketDataAgent,
)

# Planners & aggregators
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

# Factory functions, drift monitoring, harness integration
from app.agents.pipeline_core import (
    CompetitorAnalysisFlow,
    CreditScoringFlow,
    DistributionAnalysisFlow,
    IntelligenceDriftMonitor,
    MarketAnalysisFlow,
    create_all_intelligence_flows,
    create_competitor_analysis_flow,
    create_credit_scoring_flow,
    create_distribution_analysis_flow,
    create_harnessed_flows,
    create_market_analysis_flow,
    get_harnessed_intelligence_flows,
    get_intelligence_drift_monitor,
)

__all__ = [
    # Agents
    "MarketDataAgent",
    "CreditAnalysisAgent",
    "DistributionAgent",
    "CompetitorAgent",
    # Planners
    "MarketAnalysisPlanner",
    "CreditScoringPlanner",
    "DistributionPlanner",
    "CompetitorPlanner",
    # Aggregators
    "MarketResultAggregator",
    "CreditResultAggregator",
    "DistributionResultAggregator",
    "CompetitorResultAggregator",
    # Factory functions
    "create_market_analysis_flow",
    "create_credit_scoring_flow",
    "create_distribution_analysis_flow",
    "create_competitor_analysis_flow",
    "create_all_intelligence_flows",
    "create_harnessed_flows",
    "get_harnessed_intelligence_flows",
    # Drift monitoring
    "IntelligenceDriftMonitor",
    "get_intelligence_drift_monitor",
    # Type aliases
    "MarketAnalysisFlow",
    "CreditScoringFlow",
    "DistributionAnalysisFlow",
    "CompetitorAnalysisFlow",
]
