"""
Tests for Self-Improving Agent Loop System.

Tests the ReflexionEngine, LearningSystem, and all three
domain-specific loops (Content Quality, Customer Satisfaction,
Revenue Optimization).

Covers:
- ReflexionEngine execute → critique → revise → accept flow
- LearningSystem performance tracking and pattern detection
- ContentQualityLoop generation with quality evaluation
- CustomerSatisfactionLoop feedback processing
- RevenueOptimizationLoop metrics analysis
- EventBus integration
- Edge cases and error handling
"""

from __future__ import annotations

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.autonomous.reflexion import (
    AdaptiveReviser,
    Critic,
    Executor,
    HeuristicCritic,
    ReflexionConfig,
    ReflexionEngine,
    ReflexionResult,
    ReflexionStatus,
    create_reflexion_engine,
)
from app.autonomous.learning import (
    AgentLearningProfile,
    FailureAnalyzer,
    LearningSystem,
    MetricType,
    PatternType,
    PerformanceTracker,
    PromptOptimizer,
)
from app.autonomous.loops.content_quality import (
    ContentExecutor,
    ContentQualityCritic,
    ContentQualityLoop,
    ContentReviser,
    ContentRequest,
    ContentType,
    QualityDimension,
)
from app.autonomous.loops.customer_satisfaction import (
    CustomerFeedback,
    CustomerSatisfactionLoop,
    FeedbackChannel,
    IssueCategory,
    SatisfactionCritic,
    SatisfactionExecutor,
    Sentiment,
    SentimentAnalyzer,
    SentimentAnalysis,
)
from app.autonomous.loops.revenue_optimization import (
    OptimizationGoal,
    OptimizationOpportunity,
    PricingStrategy,
    RevenueAnalyzer,
    RevenueMetrics,
    RevenueOptimizationCritic,
    RevenueOptimizationExecutor,
    RevenueOptimizationLoop,
    StrategyGenerator,
)


# ════════════════════════════════════════════════════════════════════
# ReflexionEngine Tests
# ════════════════════════════════════════════════════════════════════


class MockExecutor:
    """Mock executor that returns configurable results."""

    def __init__(self, results: list = None):
        self._results = results or [{"success": True, "data": "test output"}]
        self._call_count = 0

    async def execute(self, task, context=None):
        result = self._results[min(self._call_count, len(self._results) - 1)]
        self._call_count += 1
        return dict(result)


class MockCritic:
    """Mock critic that returns configurable scores."""

    def __init__(self, scores: list = None):
        self._scores = scores or [0.9]
        self._call_count = 0

    async def critique(self, task, result, attempt_number):
        score = self._scores[min(self._call_count, len(self._scores) - 1)]
        self._call_count += 1
        return {
            "score": score,
            "issues": [] if score >= 0.7 else ["low quality"],
            "suggestions": [] if score >= 0.7 else ["improve quality"],
        }


class TestReflexionEngine:
    """Test the core ReflexionEngine."""

    @pytest.mark.asyncio
    async def test_immediate_accept(self):
        """Engine should accept on first attempt if quality is high."""
        engine = ReflexionEngine(
            executor=MockExecutor([{"success": True, "data": "great"}]),
            critic=MockCritic([0.9]),
            config=ReflexionConfig(quality_threshold=0.7),
        )
        result = await engine.run({"test": True})

        assert result.status == ReflexionStatus.ACCEPTED
        assert result.attempt_count == 1
        assert result.final_score >= 0.7

    @pytest.mark.asyncio
    async def test_retry_then_accept(self):
        """Engine should retry and accept when quality improves."""
        engine = ReflexionEngine(
            executor=MockExecutor([
                {"success": True, "data": "poor"},
                {"success": True, "data": "better"},
            ]),
            critic=MockCritic([0.4, 0.8]),
            reviser=AdaptiveReviser(),
            config=ReflexionConfig(quality_threshold=0.7, max_attempts=3),
        )
        result = await engine.run({"test": True})

        assert result.status == ReflexionStatus.ACCEPTED
        assert result.attempt_count == 2
        assert result.improvement_delta > 0

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Engine should stop at max retries and use best attempt."""
        engine = ReflexionEngine(
            executor=MockExecutor([{"success": True, "data": "x"}]),
            critic=MockCritic([0.3, 0.35, 0.4]),
            reviser=AdaptiveReviser(),
            config=ReflexionConfig(quality_threshold=0.8, max_attempts=3),
        )
        result = await engine.run({"test": True})

        assert result.status == ReflexionStatus.MAX_RETRIES
        assert result.attempt_count == 3
        assert result.final_score == 0.4  # Best score

    @pytest.mark.asyncio
    async def test_execution_failure(self):
        """Engine should handle execution failures gracefully."""
        engine = ReflexionEngine(
            executor=MockExecutor([{"success": False, "error": "boom"}]),
            critic=MockCritic([0.0]),
            config=ReflexionConfig(quality_threshold=0.7, max_attempts=1),
        )
        result = await engine.run({"test": True})

        assert result.attempt_count == 1
        assert result.final_score == 0.0

    @pytest.mark.asyncio
    async def test_executor_exception(self):
        """Engine should catch executor exceptions."""
        class FailingExecutor:
            async def execute(self, task, context=None):
                raise RuntimeError("executor exploded")

        engine = ReflexionEngine(
            executor=FailingExecutor(),
            critic=MockCritic([0.0]),
            config=ReflexionConfig(max_attempts=1),
        )
        result = await engine.run({"test": True})

        assert result.attempt_count == 1
        assert result.attempts[0].execution_success is False

    @pytest.mark.asyncio
    async def test_no_reviser_uses_auto_inject(self):
        """Engine should auto-inject critique when no reviser provided."""
        engine = ReflexionEngine(
            executor=MockExecutor([{"success": True, "data": "x"}]),
            critic=MockCritic([0.4, 0.8]),
            reviser=None,
            config=ReflexionConfig(quality_threshold=0.7, max_attempts=2),
        )
        result = await engine.run({"test": True})

        assert result.status == ReflexionStatus.ACCEPTED
        assert result.attempts[0].revision_applied is True

    @pytest.mark.asyncio
    async def test_history_tracking(self):
        """Engine should track loop history."""
        engine = ReflexionEngine(
            executor=MockExecutor(),
            critic=MockCritic(),
            config=ReflexionConfig(max_attempts=1),
        )

        await engine.run({"task": 1})
        await engine.run({"task": 2})

        history = engine.get_history()
        assert len(history) == 2

        stats = engine.get_stats()
        assert stats["total_loops"] == 2

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Engine should respect timeout configuration."""
        class SlowExecutor:
            async def execute(self, task, context=None):
                await asyncio.sleep(0.5)
                return {"success": True, "data": "slow"}

        engine = ReflexionEngine(
            executor=SlowExecutor(),
            critic=MockCritic([0.3, 0.3]),
            reviser=AdaptiveReviser(),
            config=ReflexionConfig(
                quality_threshold=0.8,
                max_attempts=5,
                timeout_seconds=0.1,  # Very short timeout
            ),
        )
        result = await engine.run({"test": True})

        # Should stop due to timeout
        assert result.status in (ReflexionStatus.FAILED, ReflexionStatus.MAX_RETRIES)


class TestHeuristicCritic:
    """Test the default HeuristicCritic."""

    @pytest.mark.asyncio
    async def test_success_score(self):
        critic = HeuristicCritic()
        result = await critic.critique(
            {}, {"success": True, "data": "output"}, 1,
        )
        assert result["score"] >= 0.8

    @pytest.mark.asyncio
    async def test_failure_score(self):
        critic = HeuristicCritic()
        result = await critic.critique(
            {}, {"success": False, "error": "failed"}, 1,
        )
        assert result["score"] <= 0.5

    @pytest.mark.asyncio
    async def test_slow_execution_penalty(self):
        critic = HeuristicCritic()
        result = await critic.critique(
            {}, {"success": True, "data": "x", "duration_ms": 15000}, 1,
        )
        assert result["score"] < 1.0
        assert any("slow" in i.lower() for i in result["issues"])


class TestAdaptiveReviser:
    """Test the default AdaptiveReviser."""

    @pytest.mark.asyncio
    async def test_reviser_adds_context(self):
        reviser = AdaptiveReviser()
        result = await reviser.revise(
            {"original": True},
            {"score": 0.5, "issues": ["slow"], "suggestions": ["speed up"]},
            [],
        )
        assert "_reflexion_context" in result["revised_task"]
        assert "plan" in result


# ════════════════════════════════════════════════════════════════════
# LearningSystem Tests
# ════════════════════════════════════════════════════════════════════


class TestPerformanceTracker:
    """Test the PerformanceTracker."""

    def test_record_and_query(self):
        tracker = PerformanceTracker()
        tracker.record("agent1", "task1", MetricType.SUCCESS_RATE, 1.0)
        tracker.record("agent1", "task2", MetricType.SUCCESS_RATE, 0.0)

        records = tracker.get_records(agent_name="agent1")
        assert len(records) == 2

    def test_agent_stats(self):
        tracker = PerformanceTracker()
        for i in range(10):
            tracker.record("agent1", "task1", MetricType.SUCCESS_RATE, 1.0 if i < 7 else 0.0)

        stats = tracker.get_agent_stats("agent1")
        assert stats["record_count"] == 10
        assert stats["success_rate"]["mean"] == 0.7

    def test_trend_detection(self):
        tracker = PerformanceTracker()
        # Declining performance
        for i in range(10):
            tracker.record("agent1", "task1", MetricType.SUCCESS_RATE, 1.0 if i < 5 else 0.0)

        trend = tracker.get_trend("agent1", MetricType.SUCCESS_RATE)
        assert trend == "degrading"


class TestFailureAnalyzer:
    """Test the FailureAnalyzer."""

    def test_recurring_error_detection(self):
        analyzer = FailureAnalyzer()
        for _ in range(4):
            analyzer.record_error("agent1", "task1", "Connection timeout")

        patterns = analyzer.analyze("agent1")
        recurring = [p for p in patterns if p.pattern_type == PatternType.RECURRING_ERROR]
        assert len(recurring) > 0

    def test_high_failure_task_detection(self):
        analyzer = FailureAnalyzer()
        for _ in range(6):
            analyzer.record_error("agent1", "task1", "Error")

        patterns = analyzer.analyze("agent1")
        consistent = [p for p in patterns if p.pattern_type == PatternType.CONSISTENT_FAILURE]
        assert len(consistent) > 0


class TestLearningSystem:
    """Test the full LearningSystem."""

    def test_record_success_and_failure(self):
        system = LearningSystem()
        system.record_success("agent1", "task1", 0.9, 1000)
        system.record_failure("agent1", "task2", "timeout")

        profile = system.get_profile("agent1")
        assert profile.total_executions == 2

    def test_profile_generation(self):
        system = LearningSystem()
        for i in range(10):
            system.record_success("agent1", "task1", 0.8, 1500)

        profile = system.get_profile("agent1")
        assert profile.success_rate == 1.0
        assert profile.avg_quality_score == 0.8

    def test_pattern_detection(self):
        system = LearningSystem()
        for _ in range(5):
            system.record_failure("agent1", "task1", "Same error")

        patterns = system.detect_patterns("agent1")
        assert len(patterns) > 0

    def test_suggest_adjustments(self):
        system = LearningSystem()
        # Low success rate
        for _ in range(5):
            system.record_failure("agent1", "task1", "error")

        adjustments = system.suggest_adjustments("agent1")
        assert len(adjustments) > 0

    def test_system_stats(self):
        system = LearningSystem()
        system.record_success("agent1", "task1", 0.9, 1000)
        system.record_success("agent2", "task2", 0.8, 2000)

        stats = system.get_system_stats()
        assert stats["agent_count"] == 2


# ════════════════════════════════════════════════════════════════════
# ContentQualityLoop Tests
# ════════════════════════════════════════════════════════════════════


class TestContentQualityCritic:
    """Test the ContentQualityCritic."""

    @pytest.mark.asyncio
    async def test_high_quality_content(self):
        critic = ContentQualityCritic()
        result = await critic.critique(
            {"keywords": ["business", "intelligence"], "tone": "professional"},
            {
                "success": True,
                "data": {
                    "title": "Business Intelligence: Key Insights for Growth",
                    "body": (
                        "# Business Intelligence\n\n"
                        "Understanding business intelligence is essential for modern enterprises. "
                        "According to research, data-driven companies are 23% more profitable.\n\n"
                        "## Key Findings\n\n"
                        "- Market trends show 15% growth\n"
                        "- Customer engagement improved by 23%\n\n"
                        "## Recommendations\n\n"
                        "1. Implement data-driven decision making\n"
                        "2. Contact Angavu Intelligence for a personalized assessment. "
                        "Sign up for our weekly reports.\n"
                    ),
                    "word_count": 80,
                },
            },
            1,
        )
        assert result["score"] > 0.5
        assert "dimension_scores" in result

    @pytest.mark.asyncio
    async def test_empty_content(self):
        critic = ContentQualityCritic()
        result = await critic.critique(
            {},
            {"success": True, "data": {"title": "", "body": "", "word_count": 0}},
            1,
        )
        assert result["score"] < 0.5

    @pytest.mark.asyncio
    async def test_failed_generation(self):
        critic = ContentQualityCritic()
        result = await critic.critique(
            {}, {"success": False, "error": "API error"}, 1,
        )
        assert result["score"] == 0.0


class TestContentExecutor:
    """Test the ContentExecutor."""

    @pytest.mark.asyncio
    async def test_generate_content(self):
        executor = ContentExecutor()
        result = await executor.execute({
            "content_type": "blog_post",
            "topic": "Market Intelligence",
            "keywords": ["market", "intelligence"],
            "tone": "professional",
        })
        assert result["success"] is True
        assert "body" in result["data"]
        assert result["data"]["word_count"] > 0

    @pytest.mark.asyncio
    async def test_with_reflexion_feedback(self):
        executor = ContentExecutor()
        result = await executor.execute({
            "content_type": "blog_post",
            "topic": "Test",
            "_reflexion_feedback": {"suggestions": ["Add more data"]},
        })
        assert result["success"] is True


class TestContentQualityLoop:
    """Test the full ContentQualityLoop."""

    @pytest.mark.asyncio
    async def test_generate_content(self):
        loop = ContentQualityLoop(quality_threshold=0.5)
        request = ContentRequest(
            content_type=ContentType.BLOG_POST,
            topic="Business Intelligence",
            keywords=["business", "intelligence", "analytics"],
        )
        result = await loop.generate(request)

        assert isinstance(result, ReflexionResult)
        assert result.attempt_count >= 1
        assert result.final_result is not None

    @pytest.mark.asyncio
    async def test_learning_integration(self):
        loop = ContentQualityLoop(quality_threshold=0.3)
        request = ContentRequest(topic="Test Topic")

        await loop.generate(request)

        stats = loop.get_stats()
        assert "engine_stats" in stats
        assert "learning_stats" in stats


# ════════════════════════════════════════════════════════════════════
# CustomerSatisfactionLoop Tests
# ════════════════════════════════════════════════════════════════════


class TestSentimentAnalyzer:
    """Test the SentimentAnalyzer."""

    def test_positive_sentiment(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("Great product, excellent service, very helpful!")
        assert result.sentiment in (Sentiment.POSITIVE, Sentiment.VERY_POSITIVE)
        assert result.score > 0

    def test_negative_sentiment(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("Terrible experience, slow and confusing, very disappointed")
        assert result.sentiment in (Sentiment.NEGATIVE, Sentiment.VERY_NEGATIVE)
        assert result.score < 0

    def test_neutral_sentiment(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("The service exists")
        assert result.sentiment == Sentiment.NEUTRAL

    def test_with_rating(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("It's okay", rating=5)
        assert result.score > 0  # Rating pulls it positive

    def test_issue_categorization(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("The report is late and the data is wrong")
        assert result.issue_category in (
            IssueCategory.DELIVERY_TIMING,
            IssueCategory.DATA_ACCURACY,
        )

    def test_key_phrases(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("Excellent amazing great service")
        assert len(result.key_phrases) > 0


class TestCustomerSatisfactionLoop:
    """Test the full CustomerSatisfactionLoop."""

    @pytest.mark.asyncio
    async def test_process_positive_feedback(self):
        loop = CustomerSatisfactionLoop(quality_threshold=0.5)
        feedback = CustomerFeedback(
            customer_id="c123",
            text="Excellent service, very helpful reports!",
            rating=5,
        )
        result = await loop.process_feedback(feedback)

        assert isinstance(result, ReflexionResult)
        assert result.attempt_count >= 1

    @pytest.mark.asyncio
    async def test_process_negative_feedback(self):
        loop = CustomerSatisfactionLoop(quality_threshold=0.3)
        feedback = CustomerFeedback(
            customer_id="c456",
            text="Terrible experience, reports are always late and wrong",
            rating=1,
        )
        result = await loop.process_feedback(feedback)

        assert result.attempt_count >= 1

    @pytest.mark.asyncio
    async def test_satisfaction_snapshot(self):
        loop = CustomerSatisfactionLoop(quality_threshold=0.3)

        # Process multiple feedback items
        for i in range(5):
            await loop.process_feedback(CustomerFeedback(
                customer_id=f"c{i}",
                text="Great service!" if i < 3 else "Poor quality",
                rating=5 if i < 3 else 1,
            ))

        snapshot = loop.get_satisfaction_snapshot()
        assert snapshot.total_feedback == 5
        assert snapshot.positive_pct > 0

    @pytest.mark.asyncio
    async def test_improvement_actions(self):
        loop = CustomerSatisfactionLoop(quality_threshold=0.3)
        await loop.process_feedback(CustomerFeedback(
            customer_id="c1",
            text="Reports are inaccurate and data is wrong",
            rating=2,
        ))

        actions = loop.get_improvement_actions()
        assert len(actions) > 0

    @pytest.mark.asyncio
    async def test_stats(self):
        loop = CustomerSatisfactionLoop(quality_threshold=0.3)
        await loop.process_feedback(CustomerFeedback(
            customer_id="c1", text="Good", rating=4,
        ))

        stats = loop.get_stats()
        assert "engine_stats" in stats
        assert "total_feedback_processed" in stats


# ════════════════════════════════════════════════════════════════════
# RevenueOptimizationLoop Tests
# ════════════════════════════════════════════════════════════════════


class TestRevenueAnalyzer:
    """Test the RevenueAnalyzer."""

    def test_high_churn_detection(self):
        analyzer = RevenueAnalyzer()
        metrics = RevenueMetrics(
            mrr=5000,
            arpu=25,
            active_customers=200,
            churn_rate=0.10,  # 10% — above 5% benchmark
        )
        opportunities = analyzer.analyze(metrics)

        churn_opps = [o for o in opportunities if o.goal == OptimizationGoal.REDUCE_CHURN]
        assert len(churn_opps) > 0
        assert churn_opps[0].estimated_impact > 0

    def test_low_conversion_detection(self):
        analyzer = RevenueAnalyzer()
        metrics = RevenueMetrics(
            mrr=5000,
            arpu=50,
            active_customers=100,
            conversion_rate=0.05,  # 5% — below 15% benchmark
        )
        opportunities = analyzer.analyze(metrics)

        conv_opps = [o for o in opportunities if o.goal == OptimizationGoal.INCREASE_CONVERSION]
        assert len(conv_opps) > 0

    def test_low_arpu_detection(self):
        analyzer = RevenueAnalyzer()
        metrics = RevenueMetrics(
            mrr=2000,
            arpu=10,  # $10 — below $50 benchmark
            active_customers=200,
        )
        opportunities = analyzer.analyze(metrics)

        arpu_opps = [o for o in opportunities if o.goal == OptimizationGoal.INCREASE_ARPU]
        assert len(arpu_opps) > 0

    def test_healthy_metrics_no_opportunities(self):
        analyzer = RevenueAnalyzer()
        metrics = RevenueMetrics(
            mrr=50000,
            arpu=100,
            active_customers=500,
            churn_rate=0.02,
            conversion_rate=0.25,
            ltv=1200,
            cac=200,
        )
        opportunities = analyzer.analyze(metrics)
        # Should have few or no opportunities for healthy metrics
        high_impact = [o for o in opportunities if o.estimated_impact > 1000]
        assert len(high_impact) == 0

    def test_historical_growth_analysis(self):
        analyzer = RevenueAnalyzer()
        current = RevenueMetrics(mrr=5000, arpu=25, active_customers=200)
        historical = [
            RevenueMetrics(mrr=4900, arpu=24, active_customers=195),
            RevenueMetrics(mrr=4800, arpu=23, active_customers=190),
        ]
        opportunities = analyzer.analyze(current, historical)

        mrr_opps = [o for o in opportunities if o.goal == OptimizationGoal.INCREASE_MRR]
        assert len(mrr_opps) > 0


class TestStrategyGenerator:
    """Test the StrategyGenerator."""

    def test_churn_strategy(self):
        generator = StrategyGenerator()
        opp = OptimizationOpportunity(
            goal=OptimizationGoal.REDUCE_CHURN,
            estimated_impact=1000,
            confidence=0.8,
        )
        strategies = generator.generate_strategies(
            [opp],
            RevenueMetrics(mrr=5000, arpu=25),
        )
        assert len(strategies) == 1
        assert strategies[0]["strategy_type"] == "churn_reduction"
        assert "ab_test" in strategies[0]

    def test_conversion_strategy(self):
        generator = StrategyGenerator()
        opp = OptimizationOpportunity(
            goal=OptimizationGoal.INCREASE_CONVERSION,
            estimated_impact=500,
        )
        strategies = generator.generate_strategies(
            [opp],
            RevenueMetrics(mrr=5000, arpu=25),
        )
        assert len(strategies) == 1
        assert strategies[0]["strategy_type"] == "conversion_optimization"

    def test_multiple_strategies(self):
        generator = StrategyGenerator()
        opps = [
            OptimizationOpportunity(goal=OptimizationGoal.REDUCE_CHURN, estimated_impact=1000),
            OptimizationOpportunity(goal=OptimizationGoal.INCREASE_ARPU, estimated_impact=800),
            OptimizationOpportunity(goal=OptimizationGoal.INCREASE_CONVERSION, estimated_impact=500),
        ]
        strategies = generator.generate_strategies(opps, RevenueMetrics(mrr=5000, arpu=25))
        assert len(strategies) == 3


class TestRevenueMetrics:
    """Test RevenueMetrics data class."""

    def test_ltv_cac_ratio(self):
        metrics = RevenueMetrics(ltv=600, cac=200)
        assert metrics.ltv_cac_ratio == 3.0

    def test_ltv_cac_ratio_zero_cac(self):
        metrics = RevenueMetrics(ltv=600, cac=0)
        assert metrics.ltv_cac_ratio == 0.0

    def test_to_dict(self):
        metrics = RevenueMetrics(mrr=5000, arpu=25, active_customers=200)
        d = metrics.to_dict()
        assert d["mrr"] == 5000
        assert "ltv_cac_ratio" in d


class TestRevenueOptimizationLoop:
    """Test the full RevenueOptimizationLoop."""

    @pytest.mark.asyncio
    async def test_optimize_with_poor_metrics(self):
        loop = RevenueOptimizationLoop(quality_threshold=0.5)
        metrics = RevenueMetrics(
            mrr=5000,
            arpu=25,
            active_customers=200,
            churn_rate=0.10,
            conversion_rate=0.05,
        )
        result = await loop.optimize(metrics)

        assert isinstance(result, ReflexionResult)
        assert result.attempt_count >= 1

    @pytest.mark.asyncio
    async def test_optimize_with_historical(self):
        loop = RevenueOptimizationLoop(quality_threshold=0.3)
        current = RevenueMetrics(mrr=5000, arpu=25, active_customers=200)
        historical = [
            RevenueMetrics(mrr=4500, arpu=22, active_customers=180),
        ]
        result = await loop.optimize(current, historical)

        assert result.attempt_count >= 1

    @pytest.mark.asyncio
    async def test_optimization_history(self):
        loop = RevenueOptimizationLoop(quality_threshold=0.3)

        await loop.optimize(RevenueMetrics(mrr=5000, arpu=25))
        await loop.optimize(RevenueMetrics(mrr=5500, arpu=27))

        history = loop.get_optimization_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_metrics_trend(self):
        loop = RevenueOptimizationLoop(quality_threshold=0.3)

        await loop.optimize(RevenueMetrics(mrr=5000, arpu=25))
        await loop.optimize(RevenueMetrics(mrr=5500, arpu=27))

        trend = loop.get_metrics_trend()
        assert trend["data_points"] == 2
        assert trend["mrr"]["trend"] == "up"

    @pytest.mark.asyncio
    async def test_stats(self):
        loop = RevenueOptimizationLoop(quality_threshold=0.3)
        await loop.optimize(RevenueMetrics(mrr=5000, arpu=25))

        stats = loop.get_stats()
        assert "engine_stats" in stats
        assert "optimization_cycles" in stats


# ════════════════════════════════════════════════════════════════════
# Integration Tests
# ════════════════════════════════════════════════════════════════════


class TestIntegration:
    """Test integration between components."""

    @pytest.mark.asyncio
    async def test_learning_system_with_all_loops(self):
        """All loops should share a learning system and record metrics."""
        learning = LearningSystem()

        content_loop = ContentQualityLoop(
            quality_threshold=0.3, learning_system=learning,
        )
        satisfaction_loop = CustomerSatisfactionLoop(
            quality_threshold=0.3, learning_system=learning,
        )
        revenue_loop = RevenueOptimizationLoop(
            quality_threshold=0.3, learning_system=learning,
        )

        # Run each loop
        await content_loop.generate(ContentRequest(topic="Test"))
        await satisfaction_loop.process_feedback(
            CustomerFeedback(customer_id="c1", text="Good", rating=4),
        )
        await revenue_loop.optimize(RevenueMetrics(mrr=5000, arpu=25))

        # Check learning system has data from all loops
        stats = learning.get_system_stats()
        assert stats["total_records"] > 0

    @pytest.mark.asyncio
    async def test_reflexion_result_structure(self):
        """ReflexionResult should have all expected fields."""
        engine = ReflexionEngine(
            executor=MockExecutor(),
            critic=MockCritic(),
            config=ReflexionConfig(max_attempts=1),
        )
        result = await engine.run({"test": True})

        d = result.to_dict()
        assert "loop_id" in d
        assert "task_name" in d
        assert "status" in d
        assert "attempt_count" in d
        assert "attempts" in d
        assert "final_score" in d
        assert "improvement_delta" in d
        assert "total_duration_ms" in d

    def test_create_reflexion_engine_factory(self):
        """Factory function should create engine with defaults."""
        engine = create_reflexion_engine(
            executor=MockExecutor(),
            quality_threshold=0.8,
            max_attempts=5,
        )
        assert engine._config.quality_threshold == 0.8
        assert engine._config.max_attempts == 5


# ════════════════════════════════════════════════════════════════════
# Edge Cases
# ════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_task(self):
        """Engine should handle empty tasks."""
        engine = ReflexionEngine(
            executor=MockExecutor(),
            critic=MockCritic(),
            config=ReflexionConfig(max_attempts=1),
        )
        result = await engine.run({})
        assert result.attempt_count == 1

    def test_learning_system_empty_profile(self):
        """Learning system should return empty profile for unknown agent."""
        system = LearningSystem()
        profile = system.get_profile("nonexistent")
        assert profile.total_executions == 0
        assert profile.success_rate == 0.0

    def test_failure_analyzer_empty(self):
        """Failure analyzer should handle empty data."""
        analyzer = FailureAnalyzer()
        patterns = analyzer.analyze("nonexistent")
        assert patterns == []

    def test_sentiment_analyzer_empty_text(self):
        """Sentiment analyzer should handle empty text."""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("")
        assert result.sentiment == Sentiment.NEUTRAL

    def test_revenue_analyzer_zero_metrics(self):
        """Revenue analyzer should handle zero metrics."""
        analyzer = RevenueAnalyzer()
        metrics = RevenueMetrics()
        opportunities = analyzer.analyze(metrics)
        # Should not crash
        assert isinstance(opportunities, list)

    @pytest.mark.asyncio
    async def test_content_critic_with_very_long_content(self):
        """Content critic should handle very long content."""
        critic = ContentQualityCritic()
        long_body = "This is a test sentence. " * 1000
        result = await critic.critique(
            {"keywords": ["test"], "tone": "professional"},
            {"success": True, "data": {"title": "Test", "body": long_body, "word_count": 5000}},
            1,
        )
        assert result["score"] > 0
