"""Tests for the agent monitoring system."""

import pytest
import time
from app.autonomous.monitoring import AgentMonitor, TaskRecord


class TestTaskRecord:
    def test_record_creation(self):
        record = TaskRecord(
            task_id="t1",
            agent_name="TestAgent",
            task_type="test.action",
            success=True,
            duration_ms=150.0,
            cost_usd=0.05,
        )
        assert record.success
        assert record.duration_ms == 150.0
        assert record.cost_usd == 0.05

    def test_record_to_dict(self):
        record = TaskRecord(
            task_id="t1",
            agent_name="TestAgent",
            task_type="test.action",
            success=False,
            duration_ms=200.0,
            error="Something went wrong",
        )
        d = record.to_dict()
        assert d["task_id"] == "t1"
        assert d["success"] is False
        assert d["error"] == "Something went wrong"


class TestAgentMonitor:
    @pytest.fixture
    def monitor(self):
        return AgentMonitor(max_records=100)

    def _make_record(self, agent="TestAgent", success=True, duration=100.0, cost=0.01, escalated=False):
        return TaskRecord(
            task_id=f"t_{int(time.time() * 1000)}",
            agent_name=agent,
            task_type="test.action",
            success=success,
            duration_ms=duration,
            cost_usd=cost,
            escalated=escalated,
        )

    def test_record_task(self, monitor):
        monitor.record_task(self._make_record())
        metrics = monitor.get_metrics()
        assert metrics["total_tasks"] == 1
        assert metrics["total_successes"] == 1

    def test_success_rate(self, monitor):
        for i in range(10):
            monitor.record_task(self._make_record(success=i < 8))
        metrics = monitor.get_metrics()
        assert metrics["success_rate"] == 80.0
        assert metrics["error_rate"] == 20.0

    def test_cost_tracking(self, monitor):
        monitor.record_task(self._make_record(cost=0.05))
        monitor.record_task(self._make_record(cost=0.10))
        metrics = monitor.get_metrics()
        assert metrics["total_cost_usd"] == pytest.approx(0.15, abs=0.001)
        assert metrics["avg_cost_per_task"] == pytest.approx(0.075, abs=0.001)

    def test_escalation_tracking(self, monitor):
        for i in range(10):
            monitor.record_task(self._make_record(escalated=i == 0))
        metrics = monitor.get_metrics()
        assert metrics["total_escalations"] == 1
        assert metrics["escalation_rate"] == 10.0

    def test_per_agent_metrics(self, monitor):
        monitor.record_task(self._make_record(agent="Agent1", success=True))
        monitor.record_task(self._make_record(agent="Agent1", success=False))
        monitor.record_task(self._make_record(agent="Agent2", success=True))

        metrics = monitor.get_metrics()
        assert metrics["agents"]["Agent1"]["total_tasks"] == 2
        assert metrics["agents"]["Agent1"]["success_rate"] == 50.0
        assert metrics["agents"]["Agent2"]["total_tasks"] == 1
        assert metrics["agents"]["Agent2"]["success_rate"] == 100.0

    def test_latency_percentiles(self, monitor):
        for i in range(100):
            monitor.record_task(self._make_record(duration=float(i * 10)))
        metrics = monitor.get_metrics()
        latency = metrics["latency"]
        assert latency["p50"] > 0
        assert latency["p95"] > latency["p50"]
        assert latency["max"] > latency["p95"]

    def test_ring_buffer(self):
        monitor = AgentMonitor(max_records=5)
        for i in range(10):
            monitor.record_task(self._make_record())
        assert len(monitor._records) == 5

    def test_get_recent_tasks(self, monitor):
        for i in range(5):
            monitor.record_task(self._make_record())
        recent = monitor.get_recent_tasks(limit=3)
        assert len(recent) == 3

    def test_get_error_summary(self, monitor):
        monitor.record_task(self._make_record(success=True))
        monitor.record_task(self._make_record(success=False))
        errors = monitor.get_error_summary()
        assert len(errors) == 1

    def test_hourly_series(self, monitor):
        monitor.record_task(self._make_record())
        series = monitor.get_hourly_series(hours=1)
        assert len(series) == 1
        assert series[0]["tasks"] >= 1

    def test_empty_monitor(self):
        monitor = AgentMonitor()
        metrics = monitor.get_metrics()
        assert metrics["total_tasks"] == 0
        assert metrics["success_rate"] == 0.0
        assert metrics["active_agents"] == 0
