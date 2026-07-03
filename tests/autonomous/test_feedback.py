"""
Tests for the Feedback Loop Manager.

Tests cover:
- Agent performance tracking and recommendations
- Customer feedback classification and sentiment
- Revenue metric recording and dashboard
- Strategy adjustment generation
"""

import pytest
from app.autonomous.feedback import (
    FeedbackLoopManager,
    AgentPerformanceMetric,
    CustomerFeedbackSignal,
    RevenueMetric,
)


@pytest.fixture
def manager():
    """Create a FeedbackLoopManager for testing."""
    return FeedbackLoopManager()


# ── Loop 1: Agent Performance Tests ────────────────────────────────


class TestAgentPerformance:
    """Test agent performance tracking."""

    def test_record_performance(self, manager):
        """Test recording agent performance."""
        manager.record_agent_performance("LeadQualifier", success=True, latency_ms=45)
        manager.record_agent_performance("LeadQualifier", success=True, latency_ms=50)
        manager.record_agent_performance("LeadQualifier", success=False, latency_ms=100, error="timeout")

        metrics = manager.get_agent_performance("LeadQualifier")
        assert metrics.total_actions == 3
        assert metrics.successful_actions == 2
        assert metrics.failed_actions == 1
        assert abs(metrics.success_rate - 2/3) < 0.01

    def test_performance_metrics_empty(self, manager):
        """Test performance metrics for unknown agent."""
        metrics = manager.get_agent_performance("UnknownAgent")
        assert metrics.total_actions == 0
        assert metrics.success_rate == 0.0

    def test_performance_latency_tracking(self, manager):
        """Test latency tracking."""
        for i in range(10):
            manager.record_agent_performance("TestAgent", success=True, latency_ms=10 + i)

        metrics = manager.get_agent_performance("TestAgent")
        assert metrics.avg_latency_ms > 0
        assert metrics.p95_latency_ms >= metrics.avg_latency_ms

    def test_recommendations_high_error_rate(self, manager):
        """Test recommendations when error rate is high."""
        # Create high error rate
        for _ in range(8):
            manager.record_agent_performance("BadAgent", success=False, latency_ms=100)
        for _ in range(2):
            manager.record_agent_performance("BadAgent", success=True, latency_ms=50)

        recs = manager.get_agent_recommendations("BadAgent")
        assert len(recs["adjustments"]) > 0
        assert "high_error_rate" in recs["alerts"]

    def test_recommendations_overconfident(self, manager):
        """Test recommendations when agent is overconfident."""
        # High confidence but low success
        for _ in range(7):
            manager.record_agent_performance("OverconfidentAgent", success=False, latency_ms=100, confidence=0.9)
        for _ in range(3):
            manager.record_agent_performance("OverconfidentAgent", success=True, latency_ms=50, confidence=0.9)

        recs = manager.get_agent_recommendations("OverconfidentAgent")
        assert "overconfident" in recs["alerts"]

    def test_recommendations_healthy_agent(self, manager):
        """Test recommendations for a healthy agent."""
        for _ in range(10):
            manager.record_agent_performance("HealthyAgent", success=True, latency_ms=50, confidence=0.85)

        recs = manager.get_agent_recommendations("HealthyAgent")
        assert len(recs["alerts"]) == 0

    def test_performance_window_limit(self, manager):
        """Test that performance records are limited to 1000."""
        for i in range(1100):
            manager.record_agent_performance("WindowAgent", success=True, latency_ms=50)

        # Should only keep last 1000
        assert len(manager._agent_metrics["WindowAgent"]) == 1000


# ── Loop 2: Customer Feedback Tests ────────────────────────────────


class TestCustomerFeedback:
    """Test customer feedback tracking."""

    def test_record_feedback(self, manager):
        """Test recording customer feedback."""
        signal = manager.record_customer_feedback(
            client_id="c1",
            text="Great product, I love it!",
            score=5,
            source="onboarding",
        )

        assert signal.client_id == "c1"
        assert signal.score == 5
        assert signal.sentiment > 0  # Positive sentiment

    def test_auto_classify_feature_request(self, manager):
        """Test auto-classification of feature requests."""
        signal = manager.record_customer_feedback(
            client_id="c1",
            text="I wish you could add more chart types",
        )
        assert signal.category == "feature_request"

    def test_auto_classify_bug(self, manager):
        """Test auto-classification of bug reports."""
        signal = manager.record_customer_feedback(
            client_id="c1",
            text="The app doesn't work on my phone, it's broken",
        )
        assert signal.category == "bug"

    def test_auto_classify_praise(self, manager):
        """Test auto-classification of praise."""
        signal = manager.record_customer_feedback(
            client_id="c1",
            text="Amazing service, thank you so much!",
        )
        assert signal.category == "praise"

    def test_auto_classify_complaint(self, manager):
        """Test auto-classification of complaints."""
        signal = manager.record_customer_feedback(
            client_id="c1",
            text="This is terrible and frustrating",
        )
        assert signal.category == "complaint"

    def test_auto_classify_pricing(self, manager):
        """Test auto-classification of pricing feedback."""
        signal = manager.record_customer_feedback(
            client_id="c1",
            text="The price is too expensive for what you get",
        )
        assert signal.category == "pricing_feedback"

    def test_sentiment_scoring(self, manager):
        """Test sentiment scoring."""
        positive = manager.record_customer_feedback(client_id="c1", text="Great amazing excellent")
        negative = manager.record_customer_feedback(client_id="c2", text="Bad terrible frustrating")
        neutral = manager.record_customer_feedback(client_id="c3", text="Hello world")

        assert positive.sentiment > 0
        assert negative.sentiment < 0
        assert neutral.sentiment == 0

    def test_feedback_themes(self, manager):
        """Test feedback theme clustering."""
        manager.record_customer_feedback("c1", "I want more charts", category="feature_request")
        manager.record_customer_feedback("c2", "Add dark mode please", category="feature_request")
        manager.record_customer_feedback("c3", "App is slow", category="bug")

        themes = manager.get_feedback_themes()
        assert len(themes) >= 2
        # Feature requests should be top theme
        assert themes[0]["category"] == "feature_request"
        assert themes[0]["count"] == 2

    def test_nps_score(self, manager):
        """Test NPS calculation."""
        # 3 promoters (9-10)
        manager.record_customer_feedback("c1", "Amazing", score=10)
        manager.record_customer_feedback("c2", "Great", score=9)
        manager.record_customer_feedback("c3", "Love it", score=10)
        # 1 passive (7-8)
        manager.record_customer_feedback("c4", "OK", score=7)
        # 1 detractor (0-6)
        manager.record_customer_feedback("c5", "Bad", score=3)

        nps = manager.get_nps_score()
        assert nps["promoters"] == 3
        assert nps["detractors"] == 1
        assert nps["passives"] == 1
        assert nps["nps"] == 40.0  # (3-1)/5 * 100

    def test_nps_empty(self, manager):
        """Test NPS with no feedback."""
        nps = manager.get_nps_score()
        assert nps["nps"] == 0
        assert nps["total"] == 0

    def test_feedback_window_limit(self, manager):
        """Test that feedback is limited to 5000."""
        for i in range(5100):
            manager.record_customer_feedback(f"c{i}", "test feedback")

        assert len(manager._customer_feedback) == 5000


# ── Loop 3: Revenue Metrics Tests ──────────────────────────────────


class TestRevenueMetrics:
    """Test revenue metric tracking."""

    def test_record_metric(self, manager):
        """Test recording a revenue metric."""
        metric = manager.record_revenue_metric("mrr", 150_000, "monthly")
        assert metric.metric_name == "mrr"
        assert metric.value == 150_000

    def test_revenue_dashboard(self, manager):
        """Test revenue dashboard generation."""
        manager.record_revenue_metric("mrr", 100_000, "monthly")
        manager.record_revenue_metric("mrr", 120_000, "monthly")
        manager.record_revenue_metric("churn_rate", 0.05, "monthly")

        dashboard = manager.get_revenue_dashboard()
        assert "metrics" in dashboard
        assert "trends" in dashboard
        assert "mrr" in dashboard["metrics"]
        assert "mrr" in dashboard["trends"]

    def test_revenue_trend_calculation(self, manager):
        """Test trend calculation."""
        manager.record_revenue_metric("mrr", 100_000, "monthly")
        manager.record_revenue_metric("mrr", 120_000, "monthly")

        dashboard = manager.get_revenue_dashboard()
        trend = dashboard["trends"]["mrr"]
        assert trend["direction"] == "up"
        assert trend["change_pct"] == 20.0

    def test_revenue_alert_on_decline(self, manager):
        """Test that declining metrics trigger alerts."""
        manager.record_revenue_metric("mrr", 100_000, "monthly")
        manager.record_revenue_metric("mrr", 80_000, "monthly")  # -20%

        dashboard = manager.get_revenue_dashboard()
        assert len(dashboard["alerts"]) > 0
        assert dashboard["alerts"][0]["type"] == "decline"

    def test_strategy_adjustments_mrr_decline(self, manager):
        """Test strategy adjustments when MRR declines."""
        manager.record_revenue_metric("mrr", 100_000, "monthly")
        manager.record_revenue_metric("mrr", 90_000, "monthly")  # -10%

        adjustments = manager.get_strategy_adjustments()
        assert adjustments["lead_scoring"]["action"] == "lower_thresholds"

    def test_strategy_adjustments_mrr_growth(self, manager):
        """Test strategy adjustments when MRR grows."""
        manager.record_revenue_metric("mrr", 100_000, "monthly")
        manager.record_revenue_metric("mrr", 115_000, "monthly")  # +15%

        adjustments = manager.get_strategy_adjustments()
        assert adjustments["lead_scoring"]["action"] == "raise_thresholds"

    def test_strategy_adjustments_low_conversion(self, manager):
        """Test strategy adjustments for low conversion."""
        manager.record_revenue_metric("conversion_rate", 0.05, "monthly")

        adjustments = manager.get_strategy_adjustments()
        assert adjustments["content_strategy"]["action"] == "increase_education"

    def test_metric_history_window(self, manager):
        """Test that metric history is limited."""
        for i in range(1100):
            manager.record_revenue_metric("test_metric", float(i))

        assert len(manager._metric_history["test_metric"]) == 1000


# ── EventBus Integration Tests ─────────────────────────────────────


class TestEventBusIntegration:
    """Test EventBus event creation."""

    def test_create_performance_event(self, manager):
        """Test creating a performance event."""
        event = manager.create_performance_event("TestAgent", success=True, latency_ms=50)
        assert event.event_type.value == "agent.performance.recorded"
        assert event.source == "FeedbackLoopManager"
        assert event.payload["agent_name"] == "TestAgent"

    def test_create_feedback_event(self, manager):
        """Test creating a feedback event."""
        signal = manager.record_customer_feedback("c1", "Great!", score=5)
        event = manager.create_feedback_event(signal)
        assert event.event_type.value == "customer.feedback.received"
        assert event.payload["client_id"] == "c1"

    def test_create_revenue_event(self, manager):
        """Test creating a revenue event."""
        metric = manager.record_revenue_metric("mrr", 100_000)
        event = manager.create_revenue_event(metric)
        assert event.event_type.value == "revenue.metric.recorded"
        assert event.payload["metric_name"] == "mrr"
