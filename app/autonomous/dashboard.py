"""
Monitoring Dashboard — Agent performance metrics and operational visibility.

Provides a unified view of all autonomous operations:
    - Per-agent performance (success rate, error rate, cost)
    - Escalation metrics (rate, open tickets, breached SLAs)
    - Time-series data for trend analysis
    - System health overview
    - Cost tracking and budget alerts

Designed for API consumption (JSON) — the frontend renders the charts.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.autonomous.escalation import EscalationManager
from app.autonomous.monitoring import AgentMonitor

logger = structlog.get_logger(__name__)


class MonitoringDashboard:
    """
    Unified dashboard combining monitoring and escalation data.

    Usage:
        dashboard = MonitoringDashboard(monitor, escalation_manager)
        overview = dashboard.get_overview()
        agent_detail = dashboard.get_agent_detail("SalesAgent")
    """

    def __init__(
        self,
        monitor: AgentMonitor,
        escalation_manager: EscalationManager,
    ):
        self._monitor = monitor
        self._escalation = escalation_manager
        self._logger = logger.bind(component="dashboard")

    def get_overview(self) -> dict[str, Any]:
        """
        Get the full dashboard overview.

        Returns data suitable for rendering:
        - KPI cards (success rate, error rate, cost, escalation rate)
        - Agent comparison table
        - Recent activity
        - Open escalations
        - Alerts
        """
        metrics = self._monitor.get_metrics()
        escalation = self._escalation.get_metrics()

        return {
            "kpis": self._build_kpis(metrics, escalation),
            "agents": metrics.get("agents", {}),
            "escalation": {
                "rate": escalation["escalation_rate"],
                "target": escalation["escalation_target"],
                "on_target": escalation["on_target"],
                "open_tickets": escalation["open_tickets"],
                "breached": escalation["breached_count"],
            },
            "cost": {
                "total_usd": metrics["total_cost_usd"],
                "avg_per_task": metrics["avg_cost_per_task"],
            },
            "latency": metrics.get("latency", {}),
            "alerts": self._build_alerts(metrics, escalation),
        }

    def get_agent_detail(self, agent_name: str) -> dict[str, Any]:
        """Get detailed metrics for a specific agent."""
        agent_metrics = self._monitor.get_agent_metrics(agent_name)
        recent_tasks = [
            t for t in self._monitor.get_recent_tasks(100)
            if t.get("agent_name") == agent_name
        ]
        errors = [
            e for e in self._monitor.get_error_summary(50)
            if e.get("agent_name") == agent_name
        ]

        return {
            "metrics": agent_metrics,
            "recent_tasks": recent_tasks[:20],
            "recent_errors": errors[:10],
            "health_status": self._agent_health_status(agent_metrics),
        }

    def get_cost_report(self) -> dict[str, Any]:
        """Get detailed cost breakdown."""
        metrics = self._monitor.get_metrics()
        hourly = self._monitor.get_hourly_series(24)

        total_cost = metrics["total_cost_usd"]
        hourly_cost = sum(h["cost_usd"] for h in hourly)

        return {
            "total_cost_usd": total_cost,
            "last_24h_cost_usd": round(hourly_cost, 4),
            "avg_cost_per_task": metrics["avg_cost_per_task"],
            "by_agent": {
                name: data["total_cost_usd"]
                for name, data in metrics.get("agents", {}).items()
            },
            "hourly_series": hourly,
        }

    def get_escalation_report(self) -> dict[str, Any]:
        """Get detailed escalation report."""
        escalation = self._escalation.get_metrics()
        open_tickets = self._escalation.get_open_tickets()
        breached = self._escalation.get_breached_tickets()

        return {
            "summary": escalation,
            "open_tickets": open_tickets,
            "breached_tickets": breached,
        }

    # ── Internal Helpers ────────────────────────────────────────────

    def _build_kpis(
        self,
        metrics: dict[str, Any],
        escalation: dict[str, Any],
    ) -> dict[str, Any]:
        """Build KPI card data."""
        return {
            "success_rate": {
                "value": metrics["success_rate"],
                "unit": "%",
                "target": 95.0,
                "status": "good" if metrics["success_rate"] >= 95 else "warning" if metrics["success_rate"] >= 90 else "critical",
            },
            "error_rate": {
                "value": metrics["error_rate"],
                "unit": "%",
                "target": 5.0,
                "status": "good" if metrics["error_rate"] <= 5 else "warning" if metrics["error_rate"] <= 10 else "critical",
            },
            "escalation_rate": {
                "value": escalation["escalation_rate"],
                "unit": "%",
                "target": escalation["escalation_target"],
                "status": "good" if escalation["on_target"] else "warning",
            },
            "total_tasks": {
                "value": metrics["total_tasks"],
                "unit": "tasks",
                "status": "info",
            },
            "total_cost": {
                "value": metrics["total_cost_usd"],
                "unit": "USD",
                "status": "info",
            },
            "active_agents": {
                "value": metrics["active_agents"],
                "unit": "agents",
                "status": "info",
            },
        }

    def _build_alerts(
        self,
        metrics: dict[str, Any],
        escalation: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build alert list from current state."""
        alerts = []

        # Error rate alert
        if metrics["error_rate"] > 10:
            alerts.append({
                "level": "critical",
                "message": f"Error rate is {metrics['error_rate']}% (target: <5%)",
                "source": "monitoring",
            })
        elif metrics["error_rate"] > 5:
            alerts.append({
                "level": "warning",
                "message": f"Error rate is {metrics['error_rate']}% (target: <5%)",
                "source": "monitoring",
            })

        # Escalation rate alert
        if not escalation["on_target"]:
            alerts.append({
                "level": "warning",
                "message": f"Escalation rate is {escalation['escalation_rate']}% (target: <{escalation['escalation_target']}%)",
                "source": "escalation",
            })

        # Breached SLA alerts
        if escalation["breached_count"] > 0:
            alerts.append({
                "level": "critical",
                "message": f"{escalation['breached_count']} escalation ticket(s) have breached SLA",
                "source": "escalation",
            })

        # Per-agent alerts
        for name, agent_data in metrics.get("agents", {}).items():
            if agent_data.get("error_rate", 0) > 20:
                alerts.append({
                    "level": "critical",
                    "message": f"Agent '{name}' error rate is {agent_data['error_rate']}%",
                    "source": f"agent:{name}",
                })

        return alerts

    def _agent_health_status(self, metrics: dict[str, Any]) -> str:
        """Determine agent health status from metrics."""
        error_rate = metrics.get("error_rate", 0)
        escalation_rate = metrics.get("escalation_rate", 0)

        if error_rate > 20 or escalation_rate > 20:
            return "critical"
        if error_rate > 10 or escalation_rate > 10:
            return "degraded"
        if error_rate > 5 or escalation_rate > 5:
            return "warning"
        return "healthy"
