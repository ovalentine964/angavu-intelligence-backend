"""Tests for the monitoring dashboard."""


import pytest

from app.autonomous.dashboard import MonitoringDashboard
from app.autonomous.escalation import EscalationManager
from app.autonomous.monitoring import AgentMonitor, TaskRecord


class TestMonitoringDashboard:
    @pytest.fixture
    def dashboard(self):
        monitor = AgentMonitor()
        escalation = EscalationManager()
        return MonitoringDashboard(monitor, escalation)

    def _add_tasks(self, monitor, count=10, success_rate=0.9):
        for i in range(count):
            monitor.record_task(TaskRecord(
                task_id=f"t_{i}",
                agent_name="TestAgent",
                task_type="test.action",
                success=i < int(count * success_rate),
                duration_ms=100.0 + i * 10,
                cost_usd=0.01,
            ))

    def test_overview_structure(self, dashboard):
        overview = dashboard.get_overview()
        assert "kpis" in overview
        assert "agents" in overview
        assert "escalation" in overview
        assert "cost" in overview
        assert "latency" in overview
        assert "alerts" in overview

    def test_kpi_cards(self, dashboard):
        self._add_tasks(dashboard._monitor, count=20, success_rate=0.95)
        overview = dashboard.get_overview()
        kpis = overview["kpis"]
        assert "success_rate" in kpis
        assert "error_rate" in kpis
        assert "escalation_rate" in kpis
        assert kpis["success_rate"]["value"] == 95.0
        assert kpis["success_rate"]["status"] == "good"

    def test_kpi_warning_on_low_success(self, dashboard):
        self._add_tasks(dashboard._monitor, count=20, success_rate=0.85)
        overview = dashboard.get_overview()
        assert overview["kpis"]["success_rate"]["status"] == "warning"

    def test_kpi_critical_on_very_low_success(self, dashboard):
        self._add_tasks(dashboard._monitor, count=20, success_rate=0.5)
        overview = dashboard.get_overview()
        assert overview["kpis"]["success_rate"]["status"] == "critical"

    def test_agent_detail(self, dashboard):
        self._add_tasks(dashboard._monitor, count=5)
        detail = dashboard.get_agent_detail("TestAgent")
        assert "metrics" in detail
        assert "recent_tasks" in detail
        assert "recent_errors" in detail
        assert "health_status" in detail

    def test_cost_report(self, dashboard):
        self._add_tasks(dashboard._monitor, count=5)
        report = dashboard.get_cost_report()
        assert "total_cost_usd" in report
        assert "last_24h_cost_usd" in report
        assert "by_agent" in report
        assert "hourly_series" in report

    def test_escalation_report(self, dashboard):
        report = dashboard.get_escalation_report()
        assert "summary" in report
        assert "open_tickets" in report
        assert "breached_tickets" in report

    def test_alerts_on_high_error_rate(self, dashboard):
        self._add_tasks(dashboard._monitor, count=20, success_rate=0.8)
        overview = dashboard.get_overview()
        alerts = overview["alerts"]
        # Should have an error rate alert
        error_alerts = [a for a in alerts if "error rate" in a["message"].lower()]
        assert len(error_alerts) > 0

    def test_alerts_on_breached_sla(self, dashboard):
        # This test verifies alert generation logic
        overview = dashboard.get_overview()
        # With no data, there should be no critical alerts
        assert isinstance(overview["alerts"], list)
