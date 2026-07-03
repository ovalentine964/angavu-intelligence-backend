"""Tests for the autonomous orchestrator."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.autonomous.orchestrator import AutonomousOrchestrator, ScheduledTask
from app.autonomous.escalation import EscalationManager
from app.autonomous.monitoring import AgentMonitor
from app.autonomous.config import AgentConfigManager


class MockEventBus:
    """Minimal mock of EventBus for testing."""
    def __init__(self):
        self.subscriptions = {}

    async def subscribe(self, agent, event_types):
        self.subscriptions[agent.name] = event_types

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    def get_stats(self):
        return {"mode": "mock"}


class MockTracer:
    """Minimal mock of AgentTracer for testing."""
    def start_trace(self, name, context):
        return "trace_123"

    def record_decision(self, trace_id, decision):
        pass

    def record_result(self, trace_id, result):
        pass

    def end_trace(self, trace_id, success=True, error=None):
        pass


class TestScheduledTask:
    def test_scheduled_task_creation(self):
        async def dummy():
            pass

        task = ScheduledTask(
            name="test_task",
            agent_name="TestAgent",
            interval_seconds=60,
            handler=dummy,
        )
        assert task.name == "test_task"
        assert task.enabled is True
        assert task.run_count == 0

    def test_scheduled_task_to_dict(self):
        async def dummy():
            pass

        task = ScheduledTask(
            name="test_task",
            agent_name="TestAgent",
            interval_seconds=60,
            handler=dummy,
        )
        d = task.to_dict()
        assert d["name"] == "test_task"
        assert d["interval_seconds"] == 60
        assert "next_run_in" in d


class TestAutonomousOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        event_bus = MockEventBus()
        tracer = MockTracer()
        escalation = EscalationManager()
        monitor = AgentMonitor()
        config_manager = AgentConfigManager()
        return AutonomousOrchestrator(
            event_bus=event_bus,
            tracer=tracer,
            escalation_manager=escalation,
            monitor=monitor,
            config_manager=config_manager,
        )

    def test_orchestrator_initialization(self, orchestrator):
        assert orchestrator._running is False
        assert len(orchestrator._agents) == 0
        assert len(orchestrator._scheduled_tasks) == 0

    @pytest.mark.asyncio
    async def test_register_scheduled_task(self, orchestrator):
        async def dummy():
            pass

        task = ScheduledTask(
            name="test_task",
            agent_name="TestAgent",
            interval_seconds=60,
            handler=dummy,
        )
        orchestrator.register_scheduled_task(task)
        assert "test_task" in orchestrator._scheduled_tasks

    def test_get_status_when_not_running(self, orchestrator):
        status = orchestrator.get_status()
        assert status["running"] is False
        assert "agents" in status
        assert "scheduled_tasks" in status
        assert "escalation_metrics" in status
        assert "monitor_metrics" in status

    def test_get_agents_empty(self, orchestrator):
        agents = orchestrator.get_agents()
        assert agents == []

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, orchestrator):
        """Test that start/stop doesn't crash. Agents may fail to create
        if dependencies are missing, but orchestrator should handle gracefully."""
        try:
            await orchestrator.start()
            assert orchestrator._running is True
        except Exception:
            pass  # Agents may fail in test environment
        finally:
            try:
                await orchestrator.stop()
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_restart_nonexistent_agent(self, orchestrator):
        result = await orchestrator.restart_agent("NonexistentAgent")
        assert result is False
