"""
Tests for the Superagent Reasoning Engine — the full OODA loop.

Tests the reasoning_engine.py implementation with mocked dependencies.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime

from app.superagent.core.reasoning_engine import (
    SuperagentEngine,
    OODACycle,
)
from app.agents.base import AgentEvent, AgentResult, AgentStatus, EventType


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_tracer():
    return MagicMock()


@pytest.fixture
def engine(mock_event_bus, mock_tracer):
    return SuperagentEngine(
        event_bus=mock_event_bus,
        tracer=mock_tracer,
        config={"test": True},
    )


class TestOODACycleDataclass:
    """Test the OODACycle data structure."""

    def test_ooda_cycle_creation(self):
        cycle = OODACycle(
            cycle_id=1,
            observation={"domain": "financial"},
            orientation={"situation": "standard"},
            decision={"action": "process"},
            action_result={"status": "completed"},
            learning={"success": True},
            duration_ms=150.0,
        )
        assert cycle.cycle_id == 1
        assert cycle.observation["domain"] == "financial"
        assert cycle.duration_ms == 150.0
        assert isinstance(cycle.timestamp, datetime)

    def test_ooda_cycle_default_timestamp(self):
        cycle = OODACycle(
            cycle_id=1,
            observation={},
            orientation={},
            decision={},
            action_result={},
            learning={},
            duration_ms=0.0,
        )
        assert cycle.timestamp is not None
        # Should be very recent (within last minute)
        diff = datetime.now(UTC) - cycle.timestamp.replace(tzinfo=UTC)
        assert diff.total_seconds() < 60


class TestEngineInitialization:
    """Test the reasoning engine initialization."""

    def test_engine_default_state(self, engine):
        assert engine._cycle_count == 0
        assert engine._cycle_history == []
        assert engine._modules == {}
        assert engine._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_loads_modules(self, engine):
        """Test that initialize attempts to load domain modules."""
        with patch.dict("sys.modules", {
            "app.superagent.financial.module": MagicMock(),
            "app.superagent.credit.module": MagicMock(),
            "app.superagent.learning.module": MagicMock(),
            "app.superagent.evolution.module": MagicMock(),
        }):
            await engine.initialize()
            assert engine._initialized is True
            assert engine.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, engine):
        """Calling initialize twice should be a no-op."""
        engine._initialized = True
        await engine.initialize()
        assert engine._initialized is True


class TestProcessRequest:
    """Test the main process_request OODA loop."""

    @pytest.mark.asyncio
    async def test_successful_request(self, engine):
        """A request through a working OODA cycle returns success."""
        engine._initialized = True

        result = await engine.process_request({
            "type": "analysis",
            "domain": "financial",
            "data": {"transactions": [{"amount": 500}]},
        })

        assert result["success"] is True
        assert result["cycle_id"] == 1
        assert "duration_ms" in result
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_cycle_count_increments(self, engine):
        engine._initialized = True

        await engine.process_request({"type": "test", "domain": "general"})
        await engine.process_request({"type": "test", "domain": "general"})

        assert engine._cycle_count == 2
        assert len(engine._cycle_history) == 2

    @pytest.mark.asyncio
    async def test_request_with_unknown_domain(self, engine):
        """Request with unknown domain should still succeed (no_handler status)."""
        engine._initialized = True

        result = await engine.process_request({
            "type": "query",
            "domain": "nonexistent_domain",
        })

        assert result["success"] is True
        assert result["result"]["status"] == "no_handler"

    @pytest.mark.asyncio
    async def test_request_publishes_event(self, engine, mock_event_bus):
        engine._initialized = True

        await engine.process_request({"type": "test", "domain": "financial"})

        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert event.event_type == EventType.TASK_COMPLETED

    @pytest.mark.asyncio
    async def test_failed_request_publishes_fail_event(self, engine, mock_event_bus):
        """When _observe raises, a TASK_FAILED event should be published."""
        engine._initialized = True
        engine._observe = AsyncMock(side_effect=RuntimeError("boom"))

        result = await engine.process_request({"type": "test", "domain": "general"})

        assert result["success"] is False
        assert "boom" in result["error"]
        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert event.event_type == EventType.TASK_FAILED

    @pytest.mark.asyncio
    async def test_history_trimming_at_500(self, engine):
        """History should be trimmed when it exceeds 500 cycles."""
        engine._initialized = True
        engine._cycle_history = [
            OODACycle(
                cycle_id=i, observation={}, orientation={},
                decision={}, action_result={}, learning={},
                duration_ms=1.0,
            )
            for i in range(500)
        ]

        await engine.process_request({"type": "test", "domain": "general"})
        assert len(engine._cycle_history) == 251  # 250 old + 1 new


class TestOODAPhases:
    """Test individual OODA phases."""

    @pytest.mark.asyncio
    async def test_observe_extracts_fields(self, engine):
        engine._cycle_count = 1
        observation = await engine._observe({
            "type": "sale",
            "domain": "financial",
            "data": {"amount": 500},
            "context": {"worker": "test"},
        })

        assert observation["request_type"] == "sale"
        assert observation["domain"] == "financial"
        assert observation["data"]["amount"] == 500
        assert observation["cycle_id"] == 1
        assert "timestamp" in observation

    @pytest.mark.asyncio
    async def test_orient_default_analysis(self, engine):
        orientation = await engine._orient({
            "domain": "financial",
            "request_type": "sale",
        })

        assert orientation["situation"] == "standard"
        assert orientation["confidence"] == 0.8
        assert orientation["domain"] == "financial"

    @pytest.mark.asyncio
    async def test_orient_detects_frequent_domain(self, engine):
        """When same domain appears >5 times in last 10 cycles, flag it."""
        engine._cycle_history = [
            OODACycle(
                cycle_id=i,
                observation={"domain": "financial"},
                orientation={}, decision={},
                action_result={}, learning={}, duration_ms=1.0,
            )
            for i in range(10)
        ]

        orientation = await engine._orient({
            "domain": "financial",
            "request_type": "sale",
        })

        assert "frequent_domain_activity" in orientation["factors"]

    @pytest.mark.asyncio
    async def test_decide_selects_module(self, engine):
        engine._modules["financial"] = MagicMock()

        decision = await engine._decide({
            "domain": "financial",
            "confidence": 0.9,
        })

        assert decision["action"] == "process"
        assert decision["domain"] == "financial"
        assert decision["module"] == "financial"

    @pytest.mark.asyncio
    async def test_decide_no_module(self, engine):
        decision = await engine._decide({
            "domain": "unknown",
            "confidence": 0.5,
        })

        assert decision["module"] is None

    @pytest.mark.asyncio
    async def test_act_delegates_to_module(self, engine):
        mock_module = AsyncMock()
        mock_module.execute = AsyncMock(return_value={"status": "ok"})
        engine._modules["financial"] = mock_module

        result = await engine._act({
            "domain": "financial",
            "action": "process",
        })

        assert result["status"] == "ok"
        mock_module.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_act_no_handler(self, engine):
        result = await engine._act({
            "domain": "nonexistent",
            "action": "process",
        })

        assert result["status"] == "no_handler"
        assert "nonexistent" not in engine._modules

    @pytest.mark.asyncio
    async def test_learn_success(self, engine):
        learning = await engine._learn({"status": "completed", "domain": "financial"})
        assert learning["success"] is True

    @pytest.mark.asyncio
    async def test_learn_failure_status(self, engine):
        learning = await engine._learn({"status": "error", "domain": "financial"})
        assert learning["success"] is False

    @pytest.mark.asyncio
    async def test_learn_feeds_evolution_module(self, engine):
        mock_evolution = AsyncMock()
        mock_evolution.record_outcome = AsyncMock()
        engine._modules["evolution"] = mock_evolution

        await engine._learn({"status": "completed", "domain": "financial"})
        mock_evolution.record_outcome.assert_called_once()


class TestBiasharaAgentInterface:
    """Test the BiasharaAgent interface methods."""

    @pytest.mark.asyncio
    async def test_handle_event_success(self, engine):
        engine.process_request = AsyncMock(return_value={"success": True, "data": "ok"})

        event = AgentEvent(
            event_type=EventType.TASK_COMPLETED,
            source="test",
            payload={"key": "value"},
        )
        result = await engine.handle_event(event)

        assert result.success is True
        engine.process_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_event_failure(self, engine):
        engine.process_request = AsyncMock(side_effect=RuntimeError("fail"))

        event = AgentEvent(
            event_type=EventType.TASK_COMPLETED,
            source="test",
            payload={},
        )
        result = await engine.handle_event(event)

        assert result.success is False
        assert "fail" in result.error

    def test_health_check(self, engine):
        engine._initialized = True
        engine._modules["financial"] = MagicMock()

        health = engine.health_check()

        assert health["name"] == "SuperagentEngine"
        assert health["initialized"] is True
        assert "financial" in health["modules_loaded"]
        assert health["total_cycles"] == 0

    def test_get_module(self, engine):
        mock_mod = MagicMock()
        engine._modules["financial"] = mock_mod
        assert engine.get_module("financial") is mock_mod
        assert engine.get_module("nonexistent") is None
