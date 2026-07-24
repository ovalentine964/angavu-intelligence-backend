"""
Tests for the Adaptive Learning Service.

Tests feedback signal extraction, worker learning state,
aggregation, and differential privacy noise.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from app.services.adaptive_learning import (
        AdaptiveLearningService,
        AggregatedSignal,
        FeedbackSource,
        WorkerLearningState,
    )
    ADAPTIVE_LEARNING_AVAILABLE = True
except ImportError:
    ADAPTIVE_LEARNING_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not ADAPTIVE_LEARNING_AVAILABLE,
    reason="adaptive_learning import failed (missing deps)"
)


# ═══════════════════════════════════════════════════════════════════
# WORKER LEARNING STATE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestWorkerLearningState:
    """Test per-worker learning state tracking."""

    def test_init_defaults(self):
        state = WorkerLearningState(worker_id="worker_001")
        assert state.worker_id == "worker_001"
        assert state.language == "sw"
        assert state.total_signals == 0
        assert state.cumulative_outcome == 0.0
        assert state.signal_buffer == []

    def test_mean_outcome_no_signals(self):
        state = WorkerLearningState(worker_id="w1")
        assert state.mean_outcome == 0.5  # default for no data

    def test_mean_outcome_with_signals(self):
        state = WorkerLearningState(worker_id="w1")
        state.add_outcome(0.8, 0.5)
        state.add_outcome(0.6, 0.5)
        assert state.total_signals == 2
        assert state.mean_outcome == 0.7  # (0.8 + 0.6) / 2

    def test_mean_expected(self):
        state = WorkerLearningState(worker_id="w1")
        state.add_outcome(0.8, 0.6)
        state.add_outcome(0.6, 0.4)
        assert state.mean_expected == 0.5  # (0.6 + 0.4) / 2

    def test_mean_surprise(self):
        state = WorkerLearningState(worker_id="w1")
        state.add_outcome(0.8, 0.5)
        # surprise = |0.8 - 0.5| = 0.3
        assert abs(state.mean_surprise - 0.3) < 1e-10

    def test_recent_outcomes_trimming(self):
        state = WorkerLearningState(worker_id="w1")
        for i in range(150):
            state.add_outcome(float(i) / 150, 0.5)
        assert len(state.recent_outcomes) == 100  # max_recent = 100

    def test_outcome_trend_insufficient_data(self):
        state = WorkerLearningState(worker_id="w1")
        for i in range(3):
            state.add_outcome(0.5, 0.5)
        assert state.outcome_trend() == 0.0  # < 5 data points

    def test_outcome_trend_positive(self):
        state = WorkerLearningState(worker_id="w1")
        # Increasing outcomes
        for i in range(20):
            state.add_outcome(float(i) / 20, 0.5)
        trend = state.outcome_trend()
        assert trend > 0  # positive trend

    def test_outcome_trend_negative(self):
        state = WorkerLearningState(worker_id="w1")
        # Decreasing outcomes
        for i in range(20):
            state.add_outcome(1.0 - float(i) / 20, 0.5)
        trend = state.outcome_trend()
        assert trend < 0  # negative trend


# ═══════════════════════════════════════════════════════════════════
# AGGREGATED SIGNAL TESTS
# ═══════════════════════════════════════════════════════════════════


class TestAggregatedSignal:
    """Test the AggregatedSignal data class."""

    def test_to_fl_pattern(self):
        signal = AggregatedSignal(
            worker_id_hash="abc123",
            source=FeedbackSource.TRANSACTION_OUTCOME,
            outcome_value=0.8,
            expected_value=0.5,
            surprise=0.3,
        )
        pattern = signal.to_fl_pattern()

        assert "errorType" in pattern
        assert "errorHash" in pattern
        assert "correctionHash" in pattern
        assert "hourOfDay" in pattern
        assert "editDistance" in pattern
        assert pattern["editDistance"] == 0.3  # surprise clamped to [0,1]

    def test_to_fl_pattern_clamps_edit_distance(self):
        signal = AggregatedSignal(surprise=1.5)
        pattern = signal.to_fl_pattern()
        assert pattern["editDistance"] == 1.0  # clamped

    def test_signal_id_auto_generated(self):
        s1 = AggregatedSignal()
        s2 = AggregatedSignal()
        assert s1.signal_id != s2.signal_id


# ═══════════════════════════════════════════════════════════════════
# ADAPTIVE LEARNING SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestAdaptiveLearningService:
    """Test the AdaptiveLearningService."""

    @pytest.fixture
    def service(self):
        return AdaptiveLearningService()

    def test_init_defaults(self, service):
        assert service._fl_service is None
        assert service._session_sync is None
        assert service._worker_states == {}
        assert service._running is False
        assert service._total_signals_received == 0

    def test_get_or_create_state_new(self, service):
        state = service._get_or_create_state("worker_001", "sw")
        assert state.worker_id == "worker_001"
        assert state.language == "sw"
        assert "worker_001" in service._worker_states

    def test_get_or_create_state_existing(self, service):
        state1 = service._get_or_create_state("worker_001", "sw")
        state2 = service._get_or_create_state("worker_001", "en")
        assert state1 is state2
        assert state2.language == "en"  # language updated

    def test_extract_feedback_signal(self, service):
        state = service._get_or_create_state("w1")
        payload = {
            "feedback_type": "correction",
            "rating": 4,
            "success": True,
        }
        signal = service._extract_feedback_signal(payload, state)

        assert signal.source == FeedbackSource.WORKER_CORRECTION
        assert signal.outcome_value == 0.8  # 4/5
        assert signal.confidence == 0.8
        assert state.total_signals == 1

    def test_extract_feedback_signal_boolean_success(self, service):
        state = service._get_or_create_state("w1")
        payload = {"success": False}
        signal = service._extract_feedback_signal(payload, state)
        assert signal.outcome_value == 0.0

    def test_extract_transaction_signal_success(self, service):
        state = service._get_or_create_state("w1")
        payload = {
            "success": True,
            "quality_score": 0.9,
            "product_type": "food",
            "market": "nairobi",
        }
        signal = service._extract_transaction_signal(payload, state)

        assert signal.source == FeedbackSource.TRANSACTION_OUTCOME
        assert signal.outcome_value == 0.9  # max(True->1.0, 0.9)
        assert "product:food" in signal.context_tags

    def test_extract_performance_signal(self, service):
        state = service._get_or_create_state("w1")
        payload = {
            "performance_score": 0.85,
            "agent_name": "financial_agent",
        }
        signal = service._extract_performance_signal(payload, state)

        assert signal.source == FeedbackSource.AGENT_PERFORMANCE
        assert signal.outcome_value == 0.85
        assert "agent:financial_agent" in signal.context_tags

    @pytest.mark.asyncio
    async def test_on_feedback_event_increments_counter(self, service):
        service._running = True
        mock_event = MagicMock()
        mock_event.event_type.value = "feedback.received"
        mock_event.payload = {
            "worker_id": "w1",
            "language": "sw",
            "feedback_type": "correction",
            "rating": 3,
        }

        await service._on_feedback_event(mock_event)

        assert service._total_signals_received == 1
        assert "w1" in service._worker_states
        assert len(service._worker_states["w1"].signal_buffer) == 1

    @pytest.mark.asyncio
    async def test_flush_worker_insufficient_signals(self, service):
        """Workers with < MIN_SIGNALS_FOR_AGGREGATION signals should not flush."""
        state = service._get_or_create_state("w1")
        state.signal_buffer = [AggregatedSignal() for _ in range(3)]

        await service._flush_worker("w1")

        # Signals should be re-buffered
        assert len(state.signal_buffer) == 3
        assert service._total_aggregations == 0

    def test_get_metrics(self, service):
        service._get_or_create_state("w1")
        service._total_signals_received = 10
        service._total_aggregations = 2

        metrics = service.get_metrics()

        assert metrics["total_signals_received"] == 10
        assert metrics["total_aggregations"] == 2
        assert metrics["active_workers"] == 1

    def test_get_worker_state_exists(self, service):
        service._get_or_create_state("w1")
        state = service.get_worker_state("w1")
        assert state is not None
        assert state["worker_id"] == "w1"

    def test_get_worker_state_not_exists(self, service):
        assert service.get_worker_state("nonexistent") is None

    def test_dp_noise_produces_varied_values(self, service):
        """Differential privacy noise should produce different values each call."""
        values = [service._add_dp_noise(1.0, 0.1) for _ in range(100)]
        # All values should be close to 1.0 but not identical
        assert all(0.5 < v < 1.5 for v in values)
        assert len(set(values)) > 90  # most should be unique

    @pytest.mark.asyncio
    async def test_start_sets_running(self, service):
        mock_bus = AsyncMock()
        mock_bus.subscribe = AsyncMock()

        await service.start(mock_bus)

        assert service._running is True
        mock_bus.subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, service):
        service._running = True
        mock_bus = AsyncMock()
        await service.start(mock_bus)
        mock_bus.subscribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_flushes(self, service):
        service._running = True
        state = service._get_or_create_state("w1")
        state.signal_buffer = [AggregatedSignal() for _ in range(10)]

        await service.stop()

        assert service._running is False

    @pytest.mark.asyncio
    async def test_get_learning_context_empty(self, service):
        ctx = await service.get_learning_context("nonexistent")
        assert ctx == {}

    @pytest.mark.asyncio
    async def test_get_learning_context_with_data(self, service):
        state = service._get_or_create_state("w1")
        state.add_outcome(0.8, 0.5)

        ctx = await service.get_learning_context("w1")
        assert "adaptive_learning" in ctx
        assert ctx["adaptive_learning"]["total_signals"] == 1
