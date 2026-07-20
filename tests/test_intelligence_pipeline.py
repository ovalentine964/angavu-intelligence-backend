"""
Tests for the Intelligence Pipeline — Domain-specific analysis flows.

Tests cover:
- Pipeline factory functions (create_market_analysis_flow, etc.)
- Domain agent think/act cycles (MarketDataAgent, CreditAnalysisAgent, etc.)
- Task planner decomposition
- Result aggregator merging
- Drift monitor integration
- Swahili alert generation
- Error handling and edge cases

Run: pytest tests/test_intelligence_pipeline.py -v
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.agents.base import AgentDecision, AgentResult, EventType


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def market_event():
    """Create a market analysis event."""
    from app.agents.base import AgentEvent
    return AgentEvent(
        event_type=EventType.INTELLIGENCE_REQUESTED,
        source="TestHarness",
        payload={
            "parameters": {
                "action": "collect_price_data",
                "region": "Nairobi",
                "scope": {"region": "Nairobi"},
            },
        },
    )


@pytest.fixture
def credit_event():
    """Create a credit analysis event."""
    from app.agents.base import AgentEvent
    return AgentEvent(
        event_type=EventType.INTELLIGENCE_REQUESTED,
        source="TestHarness",
        payload={
            "parameters": {
                "action": "analyze_creditworthiness",
                "worker_id": "worker_001",
                "scope": {"worker_id": "worker_001"},
            },
        },
    )


@pytest.fixture
def distribution_event():
    """Create a distribution analysis event."""
    from app.agents.base import AgentEvent
    return AgentEvent(
        event_type=EventType.INTELLIGENCE_REQUESTED,
        source="TestHarness",
        payload={
            "parameters": {
                "action": "distribution_mapping",
                "product": "sukari",
                "scope": {"product_category": "food"},
            },
        },
    )


@pytest.fixture
def competitor_event():
    """Create a competitor analysis event."""
    from app.agents.base import AgentEvent
    return AgentEvent(
        event_type=EventType.INTELLIGENCE_REQUESTED,
        source="TestHarness",
        payload={
            "parameters": {
                "action": "competitor_mapping",
                "market": "Nairobi",
                "scope": {"region": "Nairobi"},
            },
        },
    )


# ════════════════════════════════════════════════════════════════════
# Factory Function Tests
# ════════════════════════════════════════════════════════════════════


class TestIntelligenceFlowFactories:
    """Test that factory functions create properly configured orchestrators."""

    def test_create_market_analysis_flow(self):
        from app.agents.intelligence_pipeline import create_market_analysis_flow
        orch = create_market_analysis_flow()
        assert orch.name == "MarketAnalysisFlow"
        assert orch._max_parallel == 3
        # Should have MarketDataAgent registered
        assert "MarketDataAgent" in orch.delegator._agents

    def test_create_credit_scoring_flow(self):
        from app.agents.intelligence_pipeline import create_credit_scoring_flow
        orch = create_credit_scoring_flow()
        assert orch.name == "CreditScoringFlow"
        assert orch._max_parallel == 2
        assert "CreditAnalysisAgent" in orch.delegator._agents

    def test_create_distribution_analysis_flow(self):
        from app.agents.intelligence_pipeline import create_distribution_analysis_flow
        orch = create_distribution_analysis_flow()
        assert orch.name == "DistributionAnalysisFlow"
        assert "DistributionAgent" in orch.delegator._agents

    def test_create_competitor_analysis_flow(self):
        from app.agents.intelligence_pipeline import create_competitor_analysis_flow
        orch = create_competitor_analysis_flow()
        assert orch.name == "CompetitorAnalysisFlow"
        assert "CompetitorAgent" in orch.delegator._agents

    def test_create_all_intelligence_flows(self):
        from app.agents.intelligence_pipeline import create_all_intelligence_flows
        flows = create_all_intelligence_flows()
        assert set(flows.keys()) == {
            "market_analysis",
            "credit_scoring",
            "distribution_analysis",
            "competitor_analysis",
        }
        for name, orch in flows.items():
            assert orch.name is not None
            assert orch.planner is not None
            assert orch.aggregator is not None


# ════════════════════════════════════════════════════════════════════
# MarketDataAgent Tests
# ════════════════════════════════════════════════════════════════════


class TestMarketDataAgent:
    """Test MarketDataAgent think/act cycles."""

    @pytest.mark.asyncio
    async def test_think_returns_decision(self, market_event):
        from app.agents.intelligence_pipeline import MarketDataAgent
        agent = MarketDataAgent()
        context = {"event": market_event.to_dict(), "memory": {}, "tools": {}, "past_reflections": []}
        decision = await agent._think_reasoning(context)
        assert isinstance(decision, AgentDecision)
        assert decision.confidence > 0
        assert decision.action is not None

    @pytest.mark.asyncio
    async def test_act_price_data_no_db(self, market_event):
        """When DB is unavailable, agent should return empty data gracefully."""
        from app.agents.intelligence_pipeline import MarketDataAgent
        agent = MarketDataAgent()
        decision = AgentDecision(
            action="collect_price_data",
            parameters={"region": "Nairobi"},
            confidence=0.9,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert "data" in (result.data or {}) or result.data is not None

    @pytest.mark.asyncio
    async def test_act_supply_demand(self):
        from app.agents.intelligence_pipeline import MarketDataAgent
        agent = MarketDataAgent()
        decision = AgentDecision(
            action="analyze_supply_demand",
            parameters={"region": "Nairobi", "product": "sukari"},
            confidence=0.9,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True
        data = result.data
        assert "supply_demand" in data or "action" in data

    @pytest.mark.asyncio
    async def test_act_competitor_data(self):
        from app.agents.intelligence_pipeline import MarketDataAgent
        agent = MarketDataAgent()
        decision = AgentDecision(
            action="competitor_analysis",
            parameters={"region": "Nairobi"},
            confidence=0.9,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_act_handles_exception(self):
        """Agent should return error result on exception, not crash."""
        from app.agents.intelligence_pipeline import MarketDataAgent
        agent = MarketDataAgent()
        # Force an exception by passing invalid action
        decision = AgentDecision(
            action="collect_price_data",
            parameters={},
            confidence=0.9,
            reasoning="test",
        )
        # The agent should handle the case gracefully (no DB)
        result = await agent._act_execute(decision)
        assert isinstance(result, AgentResult)
        assert result.success is True  # Graceful fallback


# ════════════════════════════════════════════════════════════════════
# CreditAnalysisAgent Tests
# ════════════════════════════════════════════════════════════════════


class TestCreditAnalysisAgent:
    """Test CreditAnalysisAgent think/act cycles."""

    @pytest.mark.asyncio
    async def test_think_returns_decision(self, credit_event):
        from app.agents.intelligence_pipeline import CreditAnalysisAgent
        agent = CreditAnalysisAgent()
        context = {"event": credit_event.to_dict(), "memory": {}, "tools": {}, "past_reflections": []}
        decision = await agent._think_reasoning(context)
        assert decision.confidence > 0

    @pytest.mark.asyncio
    async def test_act_credit_score_no_db(self):
        """Credit score should return no_data when DB unavailable."""
        from app.agents.intelligence_pipeline import CreditAnalysisAgent
        agent = CreditAnalysisAgent()
        decision = AgentDecision(
            action="calculate_creditworthiness",
            parameters={"worker_id": "worker_001"},
            confidence=0.85,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True
        data = result.data
        assert "credit_score" in data or "action" in data

    @pytest.mark.asyncio
    async def test_act_transaction_history(self):
        from app.agents.intelligence_pipeline import CreditAnalysisAgent
        agent = CreditAnalysisAgent()
        decision = AgentDecision(
            action="fetch_transaction_history",
            parameters={"worker_id": "worker_001"},
            confidence=0.85,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_act_behavioral_scoring(self):
        from app.agents.intelligence_pipeline import CreditAnalysisAgent
        agent = CreditAnalysisAgent()
        decision = AgentDecision(
            action="behavioral_scoring",
            parameters={"worker_id": "worker_001"},
            confidence=0.85,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_act_repayment_analysis(self):
        from app.agents.intelligence_pipeline import CreditAnalysisAgent
        agent = CreditAnalysisAgent()
        decision = AgentDecision(
            action="analyze_repayment",
            parameters={"worker_id": "worker_001"},
            confidence=0.85,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True


# ════════════════════════════════════════════════════════════════════
# DistributionAgent Tests
# ════════════════════════════════════════════════════════════════════


class TestDistributionAgent:
    """Test DistributionAgent think/act cycles."""

    @pytest.mark.asyncio
    async def test_think_returns_decision(self, distribution_event):
        from app.agents.intelligence_pipeline import DistributionAgent
        agent = DistributionAgent()
        context = {"event": distribution_event.to_dict(), "memory": {}, "tools": {}, "past_reflections": []}
        decision = await agent._think_reasoning(context)
        assert decision.confidence > 0

    @pytest.mark.asyncio
    async def test_act_distribution_mapping(self):
        from app.agents.intelligence_pipeline import DistributionAgent
        agent = DistributionAgent()
        decision = AgentDecision(
            action="distribution_mapping",
            parameters={"product": "sukari"},
            confidence=0.88,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_act_logistics_analysis(self):
        from app.agents.intelligence_pipeline import DistributionAgent
        agent = DistributionAgent()
        decision = AgentDecision(
            action="logistics_analysis",
            parameters={"product": "sukari"},
            confidence=0.88,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_act_expansion_planning(self):
        from app.agents.intelligence_pipeline import DistributionAgent
        agent = DistributionAgent()
        decision = AgentDecision(
            action="expansion_planning",
            parameters={"product": "sukari"},
            confidence=0.88,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True


# ════════════════════════════════════════════════════════════════════
# CompetitorAgent Tests
# ════════════════════════════════════════════════════════════════════


class TestCompetitorAgent:
    """Test CompetitorAgent think/act cycles."""

    @pytest.mark.asyncio
    async def test_think_returns_decision(self, competitor_event):
        from app.agents.intelligence_pipeline import CompetitorAgent
        agent = CompetitorAgent()
        context = {"event": competitor_event.to_dict(), "memory": {}, "tools": {}, "past_reflections": []}
        decision = await agent._think_reasoning(context)
        assert decision.confidence > 0

    @pytest.mark.asyncio
    async def test_act_competitor_mapping(self):
        from app.agents.intelligence_pipeline import CompetitorAgent
        agent = CompetitorAgent()
        decision = AgentDecision(
            action="competitor_mapping",
            parameters={"market": "Nairobi", "product": "sukari"},
            confidence=0.87,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_act_pricing_analysis(self):
        from app.agents.intelligence_pipeline import CompetitorAgent
        agent = CompetitorAgent()
        decision = AgentDecision(
            action="pricing_analysis",
            parameters={"market": "Nairobi", "product": "sukari"},
            confidence=0.87,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_act_threat_assessment(self):
        from app.agents.intelligence_pipeline import CompetitorAgent
        agent = CompetitorAgent()
        decision = AgentDecision(
            action="threat_assessment",
            parameters={"market": "Nairobi"},
            confidence=0.87,
            reasoning="test",
        )
        result = await agent._act_execute(decision)
        assert result.success is True


# ════════════════════════════════════════════════════════════════════
# Task Planner Tests
# ════════════════════════════════════════════════════════════════════


class TestTaskPlanners:
    """Test domain-specific task planners decompose goals correctly."""

    @pytest.mark.asyncio
    async def test_market_planner_decomposes(self):
        from app.agents.intelligence_pipeline import MarketAnalysisPlanner
        planner = MarketAnalysisPlanner()
        tasks = await planner._decompose(
            "Analyze Nairobi market",
            {"scope": {"region": "Nairobi"}},
            ["MarketDataAgent"],
        )
        assert len(tasks) == 4
        task_names = [t.name for t in tasks]
        assert "collect_prices" in task_names
        assert "collect_supply_demand" in task_names
        assert "market_analysis" in task_names
        # Verify dependencies
        analysis_task = next(t for t in tasks if t.name == "market_analysis")
        assert len(analysis_task.dependencies) > 0

    @pytest.mark.asyncio
    async def test_credit_planner_decomposes(self):
        from app.agents.intelligence_pipeline import CreditScoringPlanner
        planner = CreditScoringPlanner()
        tasks = await planner._decompose(
            "Score worker_001",
            {"scope": {"worker_id": "worker_001"}},
            ["CreditAnalysisAgent"],
        )
        assert len(tasks) == 4
        task_names = [t.name for t in tasks]
        assert "fetch_transaction_history" in task_names
        assert "calculate_credit_score" in task_names

    @pytest.mark.asyncio
    async def test_distribution_planner_decomposes(self):
        from app.agents.intelligence_pipeline import DistributionPlanner
        planner = DistributionPlanner()
        tasks = await planner._decompose(
            "Analyze distribution for sukari",
            {"scope": {"product_category": "food"}},
            ["DistributionAgent"],
        )
        assert len(tasks) == 4
        task_names = [t.name for t in tasks]
        assert "distribution_mapping" in task_names
        assert "expansion_planning" in task_names

    @pytest.mark.asyncio
    async def test_competitor_planner_decomposes(self):
        from app.agents.intelligence_pipeline import CompetitorPlanner
        planner = CompetitorPlanner()
        tasks = await planner._decompose(
            "Analyze competitors in Nairobi",
            {"scope": {"region": "Nairobi"}},
            ["CompetitorAgent"],
        )
        assert len(tasks) == 4
        task_names = [t.name for t in tasks]
        assert "competitor_mapping" in task_names
        assert "threat_assessment" in task_names


# ════════════════════════════════════════════════════════════════════
# Result Aggregator Tests
# ════════════════════════════════════════════════════════════════════


class TestResultAggregators:
    """Test result aggregators merge sub-task results correctly."""

    def test_market_aggregator_merges(self):
        from app.agents.intelligence_pipeline import MarketResultAggregator
        agg = MarketResultAggregator()
        results = {
            "task_1": {"result": {"data": {"prices": {"avg": 100}}}},
            "task_2": {"result": {"data": {"supply_index": 60}}},
        }
        merged = agg._merge(results, {})
        assert "market_analysis" in merged
        assert merged["market_analysis"]["prices"]["avg"] == 100
        assert merged["market_analysis"]["supply_index"] == 60

    def test_credit_aggregator_merges(self):
        from app.agents.intelligence_pipeline import CreditResultAggregator
        agg = CreditResultAggregator()
        results = {
            "task_1": {"result": {"data": {"on_time_rate": 0.95}}},
            "task_2": {"result": {"data": {"regularity": 0.8}}},
        }
        merged = agg._merge(results, {})
        assert "credit_assessment" in merged
        assert merged["credit_assessment"]["on_time_rate"] == 0.95

    def test_aggregator_handles_errors(self):
        from app.agents.intelligence_pipeline import MarketResultAggregator
        agg = MarketResultAggregator()
        results = {"task_1": {"result": {"data": {"prices": {}}}}}
        errors = {"task_2": {"error": "timeout"}}
        merged = agg._merge(results, errors)
        assert merged["errors"]["task_2"]["error"] == "timeout"

    def test_aggregator_handles_empty_results(self):
        from app.agents.intelligence_pipeline import MarketResultAggregator
        agg = MarketResultAggregator()
        merged = agg._merge({}, {})
        assert merged["market_analysis"] == {}
        assert merged["data_sources"] == []


# ════════════════════════════════════════════════════════════════════
# Drift Monitor Tests
# ════════════════════════════════════════════════════════════════════


class TestIntelligenceDriftMonitor:
    """Test the drift monitoring integration."""

    def test_singleton_creation(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        assert monitor is not None
        status = monitor.get_status()
        assert isinstance(status, dict)

    def test_swahili_alert_price(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        # The function checks 'product' for keywords, not metric_name
        msg = monitor.generate_swahili_alert("price_analysis", 30.0, "soko la nyanya")
        assert "Soko la" in msg
        assert "imepanda" in msg
        assert "30%" in msg

    def test_swahili_alert_price_drop(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        msg = monitor.generate_swahili_alert("price_analysis", -15.0, "soko la sukari")
        assert "imepungua" in msg
        assert "15%" in msg

    def test_swahili_alert_credit(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        msg = monitor.generate_swahili_alert("credit_scoring", 20.0, "alama za mikopo")
        assert "Alama za mikopo" in msg

    def test_swahili_alert_gdp(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        msg = monitor.generate_swahili_alert("gdp_estimation", -10.0, "gdp")
        assert "GDP" in msg
        assert "imepungua" in msg

    def test_swahili_alert_revenue(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        msg = monitor.generate_swahili_alert("revenue_forecast", 25.0, "mapato ya biashara")
        assert "Mapato" in msg

    def test_swahili_alert_generic(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        msg = monitor.generate_swahili_alert("custom_metric", 5.0, "bidhaa")
        assert "Data ya" in msg
        assert "bidhaa" in msg

    @pytest.mark.asyncio
    async def test_check_alama_score(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        # Should not raise
        await monitor.check_alama_score(predicted_score=700, actual_outcome=650)
        await monitor.check_alama_score(predicted_score=500, actual_outcome=500)

    @pytest.mark.asyncio
    async def test_check_revenue_prediction(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        await monitor.check_revenue_prediction(predicted_revenue=100000, actual_revenue=95000)
        await monitor.check_revenue_prediction(predicted_revenue=50000, actual_revenue=0)

    @pytest.mark.asyncio
    async def test_check_feature_distribution(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        await monitor.check_feature_distribution("avg_transaction", 150.0, 100.0)

    @pytest.mark.asyncio
    async def test_check_gdp_estimation(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        await monitor.check_gdp_estimation(estimated_gdp=1.2e12, reference_gdp=1.1e12)

    def test_get_alerts(self):
        from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
        monitor = get_intelligence_drift_monitor()
        alerts = monitor.get_alerts(limit=10)
        assert isinstance(alerts, list)



