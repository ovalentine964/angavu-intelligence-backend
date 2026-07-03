"""
Data Center Health Monitoring Service.

Tracks server metrics (CPU, RAM, disk, network), inference latency
per model, cost per inference, and provides dashboard API data.

Designed for Angavu Intelligence's phased infrastructure:
    Phase 1: Oracle Cloud Free Tier
    Phase 2: Home Server (ARM + Solar)
    Phase 3: Mini DC (3-5 servers)
    Phase 4: Data Center
    Phase 5: Pan-African DC Network

Usage:
    monitor = HealthMonitor()
    monitor.record_metric(server_id="oracle-1", cpu=45.2, ram=62.1, ...)
    health = monitor.get_cluster_health()
    costs = monitor.get_cost_summary()
"""

import statistics
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Alert Thresholds
# ════════════════════════════════════════════════════════════════════

THRESHOLDS = {
    "cpu_warning": 70.0,
    "cpu_critical": 90.0,
    "ram_warning": 75.0,
    "ram_critical": 90.0,
    "disk_warning": 80.0,
    "disk_critical": 95.0,
    "latency_warning_ms": 500.0,
    "latency_critical_ms": 2000.0,
    "uptime_minimum_pct": 99.0,
}


# ════════════════════════════════════════════════════════════════════
# In-Memory State (production would use time-series DB)
# ════════════════════════════════════════════════════════════════════


class _HealthState:
    """Mutable singleton holding monitoring state."""

    def __init__(self):
        self.reset()

    def reset(self):
        # Server configs: {server_id: config}
        self.servers: Dict[str, Dict[str, Any]] = {}
        # Latest metrics: {server_id: {metric: value, ...}}
        self.latest_metrics: Dict[str, Dict[str, Any]] = {}
        # Metric history (last 1000 per server): {server_id: [metrics_dict, ...]}
        self.metric_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        # Inference metrics: {model_name: {latencies: [], count: int}}
        self.inference_metrics: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"latencies": [], "count": 0, "errors": 0, "total_cost_usd": 0.0}
        )
        # Cost records
        self.cost_records: List[Dict[str, Any]] = []
        # Alerts
        self.alerts: List[Dict[str, Any]] = []


_state = _HealthState()


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════


class HealthMonitor:
    """
    Data center health monitoring service.

    Tracks server health, inference performance, and costs
    across Angavu Intelligence's infrastructure phases.
    """

    def register_server(
        self,
        server_id: str,
        phase: str = "cloud",
        cpu_cores: int = 1,
        ram_total_gb: float = 1.0,
        disk_total_gb: float = 50.0,
        cost_per_hour_usd: float = 0.0,
        description: str = "",
    ) -> Dict[str, Any]:
        """Register a server for monitoring."""
        _state.servers[server_id] = {
            "server_id": server_id,
            "phase": phase,
            "cpu_cores": cpu_cores,
            "ram_total_gb": ram_total_gb,
            "disk_total_gb": disk_total_gb,
            "cost_per_hour_usd": cost_per_hour_usd,
            "description": description,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("server_registered", server_id=server_id, phase=phase)
        return {"status": "registered", "server_id": server_id}

    def record_metric(
        self,
        server_id: str,
        cpu_usage_pct: float,
        ram_usage_pct: float,
        disk_usage_pct: float,
        network_in_mbps: float = 0.0,
        network_out_mbps: float = 0.0,
        inference_latency_ms: Optional[float] = None,
        inference_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Record a health metric snapshot for a server.

        Returns alerts if any thresholds are breached.
        """
        now = datetime.now(timezone.utc)

        # Auto-register if not known
        if server_id not in _state.servers:
            self.register_server(server_id)

        server = _state.servers[server_id]

        metric = {
            "server_id": server_id,
            "cpu_usage_pct": cpu_usage_pct,
            "ram_usage_pct": ram_usage_pct,
            "disk_usage_pct": disk_usage_pct,
            "ram_used_gb": round(server["ram_total_gb"] * ram_usage_pct / 100, 2),
            "ram_total_gb": server["ram_total_gb"],
            "disk_used_gb": round(server["disk_total_gb"] * disk_usage_pct / 100, 2),
            "disk_total_gb": server["disk_total_gb"],
            "network_in_mbps": network_in_mbps,
            "network_out_mbps": network_out_mbps,
            "inference_latency_ms": inference_latency_ms,
            "inference_count": inference_count,
            "recorded_at": now.isoformat(),
        }

        # Determine status
        status = "healthy"
        if (cpu_usage_pct >= THRESHOLDS["cpu_critical"] or
            ram_usage_pct >= THRESHOLDS["ram_critical"] or
            disk_usage_pct >= THRESHOLDS["disk_critical"]):
            status = "down"
        elif (cpu_usage_pct >= THRESHOLDS["cpu_warning"] or
              ram_usage_pct >= THRESHOLDS["ram_warning"] or
              disk_usage_pct >= THRESHOLDS["disk_warning"]):
            status = "degraded"

        metric["status"] = status

        # Store
        _state.latest_metrics[server_id] = metric
        history = _state.metric_history[server_id]
        history.append(metric)
        if len(history) > 1000:
            _state.metric_history[server_id] = history[-1000:]

        # Check alerts
        alerts = self._check_alerts(server_id, metric)
        _state.alerts.extend(alerts)

        return {
            "status": "recorded",
            "server_id": server_id,
            "server_status": metric["status"],
            "alerts": alerts,
        }

    def record_inference(
        self,
        model_name: str,
        latency_ms: float,
        cost_usd: float = 0.0,
        success: bool = True,
    ) -> Dict[str, Any]:
        """
        Record an inference event for latency and cost tracking.
        """
        m = _state.inference_metrics[model_name]
        m["latencies"].append(latency_ms)
        m["count"] += 1
        m["total_cost_usd"] += cost_usd
        if not success:
            m["errors"] += 1

        # Keep only last 10000 latencies
        if len(m["latencies"]) > 10000:
            m["latencies"] = m["latencies"][-10000:]

        return {"status": "recorded", "model": model_name}

    def record_cost(
        self,
        component: str,
        amount_usd: float,
        phase: str = "cloud",
        model_name: Optional[str] = None,
        inference_count: Optional[int] = None,
        workers_served: Optional[int] = None,
        period_hours: float = 1.0,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Record an infrastructure cost entry."""
        now = datetime.now(timezone.utc)
        record = {
            "id": str(uuid.uuid4()),
            "component": component,
            "phase": phase,
            "amount_usd": amount_usd,
            "model_name": model_name,
            "inference_count": inference_count,
            "cost_per_inference_usd": (
                round(amount_usd / inference_count, 8) if inference_count else None
            ),
            "workers_served": workers_served,
            "cost_per_worker_usd": (
                round(amount_usd / workers_served, 6) if workers_served else None
            ),
            "period_start": (now - timedelta(hours=period_hours)).isoformat(),
            "period_end": now.isoformat(),
            "notes": notes,
            "recorded_at": now.isoformat(),
        }
        _state.cost_records.append(record)

        return {"status": "recorded", "cost_id": record["id"]}

    def get_server_health(self, server_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get health status for a specific server or all servers.
        """
        if server_id:
            latest = _state.latest_metrics.get(server_id)
            server = _state.servers.get(server_id, {})
            return {
                "server_id": server_id,
                "server_config": server,
                "latest_metric": latest,
                "status": latest["status"] if latest else "unknown",
            }

        # All servers
        servers = []
        for sid, server in _state.servers.items():
            latest = _state.latest_metrics.get(sid)
            servers.append({
                "server_id": sid,
                "phase": server.get("phase", "unknown"),
                "status": latest["status"] if latest else "unknown",
                "cpu_usage_pct": latest["cpu_usage_pct"] if latest else None,
                "ram_usage_pct": latest["ram_usage_pct"] if latest else None,
                "disk_usage_pct": latest["disk_usage_pct"] if latest else None,
                "inference_latency_ms": latest.get("inference_latency_ms") if latest else None,
                "cost_per_hour_usd": server.get("cost_per_hour_usd", 0),
                "last_recorded_at": latest["recorded_at"] if latest else None,
            })

        return {
            "total_servers": len(servers),
            "healthy": sum(1 for s in servers if s["status"] == "healthy"),
            "degraded": sum(1 for s in servers if s["status"] == "degraded"),
            "down": sum(1 for s in servers if s["status"] == "down"),
            "servers": servers,
        }

    def get_inference_metrics(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get inference latency and cost metrics per model.
        """
        if model_name:
            m = _state.inference_metrics.get(model_name)
            if not m:
                return {"model": model_name, "status": "no_data"}

            latencies = m["latencies"]
            return {
                "model": model_name,
                "total_inferences": m["count"],
                "total_errors": m["errors"],
                "error_rate": round(m["errors"] / max(1, m["count"]) * 100, 2),
                "total_cost_usd": round(m["total_cost_usd"], 6),
                "cost_per_inference_usd": round(m["total_cost_usd"] / max(1, m["count"]), 8),
                "latency": self._compute_latency_stats(latencies),
            }

        # All models
        models = {}
        for name, m in _state.inference_metrics.items():
            latencies = m["latencies"]
            models[name] = {
                "total_inferences": m["count"],
                "total_errors": m["errors"],
                "error_rate": round(m["errors"] / max(1, m["count"]) * 100, 2),
                "total_cost_usd": round(m["total_cost_usd"], 6),
                "cost_per_inference_usd": round(m["total_cost_usd"] / max(1, m["count"]), 8),
                "latency": self._compute_latency_stats(latencies),
            }

        return {"models": models, "total_models": len(models)}

    def get_cost_summary(
        self,
        component: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get infrastructure cost summary.
        """
        records = _state.cost_records
        if component:
            records = [r for r in records if r["component"] == component]
        if phase:
            records = [r for r in records if r["phase"] == phase]

        total_usd = sum(r["amount_usd"] for r in records)

        # By component
        by_component: Dict[str, float] = defaultdict(float)
        for r in _state.cost_records:
            by_component[r["component"]] += r["amount_usd"]

        # By phase
        by_phase: Dict[str, float] = defaultdict(float)
        for r in _state.cost_records:
            by_phase[r["phase"]] += r["amount_usd"]

        # Inference costs
        total_inferences = sum(
            r.get("inference_count", 0) or 0 for r in records
        )
        total_workers = max(
            (r.get("workers_served", 0) or 0 for r in records),
            default=0,
        )

        return {
            "total_cost_usd": round(total_usd, 2),
            "total_records": len(records),
            "by_component": {k: round(v, 2) for k, v in by_component.items()},
            "by_phase": {k: round(v, 2) for k, v in by_phase.items()},
            "inference_costs": {
                "total_inferences": total_inferences,
                "total_inference_cost_usd": round(
                    sum(r["amount_usd"] for r in records if r.get("inference_count")), 2
                ),
                "avg_cost_per_inference_usd": round(
                    sum(r["amount_usd"] for r in records if r.get("inference_count"))
                    / max(1, total_inferences),
                    8,
                ),
            },
            "cost_per_worker_usd": round(
                total_usd / max(1, total_workers), 4
            ) if total_workers > 0 else None,
        }

    def get_alerts(self, unresolved_only: bool = True) -> List[Dict[str, Any]]:
        """Get recent alerts."""
        alerts = _state.alerts[-100:]  # Last 100
        if unresolved_only:
            alerts = [a for a in alerts if not a.get("resolved")]
        return alerts

    def get_cluster_health(self) -> Dict[str, Any]:
        """
        Get overall cluster health summary.
        """
        server_health = self.get_server_health()
        inference = self.get_inference_metrics()
        costs = self.get_cost_summary()
        alerts = self.get_alerts()

        # Overall status
        if server_health["down"] > 0:
            overall = "critical"
        elif server_health["degraded"] > 0:
            overall = "degraded"
        elif server_health["total_servers"] == 0:
            overall = "no_servers"
        else:
            overall = "healthy"

        return {
            "overall_status": overall,
            "servers": server_health,
            "inference": inference,
            "costs": costs,
            "active_alerts": len(alerts),
            "recent_alerts": alerts[:10],
            "thresholds": THRESHOLDS,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Internal helpers ──

    def _check_alerts(
        self, server_id: str, metric: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check metric against thresholds and generate alerts."""
        alerts = []

        for resource in ("cpu", "ram", "disk"):
            value = metric.get(f"{resource}_usage_pct", 0)
            warning_thresh = THRESHOLDS.get(f"{resource}_warning", 80)
            critical_thresh = THRESHOLDS.get(f"{resource}_critical", 95)

            if value >= critical_thresh:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "server_id": server_id,
                    "type": f"{resource}_critical",
                    "severity": "critical",
                    "message": f"{resource.upper()} usage at {value:.1f}% (critical threshold: {critical_thresh}%)",
                    "value": value,
                    "threshold": critical_thresh,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resolved": False,
                })
            elif value >= warning_thresh:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "server_id": server_id,
                    "type": f"{resource}_warning",
                    "severity": "warning",
                    "message": f"{resource.upper()} usage at {value:.1f}% (warning threshold: {warning_thresh}%)",
                    "value": value,
                    "threshold": warning_thresh,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resolved": False,
                })

        # Latency alert
        latency = metric.get("inference_latency_ms")
        if latency is not None:
            if latency >= THRESHOLDS["latency_critical_ms"]:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "server_id": server_id,
                    "type": "latency_critical",
                    "severity": "critical",
                    "message": f"Inference latency at {latency:.0f}ms (critical: {THRESHOLDS['latency_critical_ms']}ms)",
                    "value": latency,
                    "threshold": THRESHOLDS["latency_critical_ms"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resolved": False,
                })
            elif latency >= THRESHOLDS["latency_warning_ms"]:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "server_id": server_id,
                    "type": "latency_warning",
                    "severity": "warning",
                    "message": f"Inference latency at {latency:.0f}ms (warning: {THRESHOLDS['latency_warning_ms']}ms)",
                    "value": latency,
                    "threshold": THRESHOLDS["latency_warning_ms"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resolved": False,
                })

        return alerts

    @staticmethod
    def _compute_latency_stats(latencies: List[float]) -> Dict[str, float]:
        """Compute latency percentiles from a list of latency values."""
        if not latencies:
            return {"p50": 0, "p95": 0, "p99": 0, "mean": 0, "min": 0, "max": 0}

        sorted_lat = sorted(latencies)
        n = len(sorted_lat)

        return {
            "p50": round(sorted_lat[int(n * 0.5)], 1),
            "p95": round(sorted_lat[int(n * 0.95)], 1),
            "p99": round(sorted_lat[min(int(n * 0.99), n - 1)], 1),
            "mean": round(statistics.mean(sorted_lat), 1),
            "min": round(sorted_lat[0], 1),
            "max": round(sorted_lat[-1], 1),
            "samples": n,
        }
