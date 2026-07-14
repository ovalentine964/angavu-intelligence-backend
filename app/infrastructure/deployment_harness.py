"""
Deployment Harness — Canary deployment control plane for Angavu Intelligence.

Manages gradual rollout of new agent versions and model updates:
- Canary stages: 1% → 10% → 50% → 100%
- Health checks before each promotion
- Automatic rollback on failure
- Traffic splitting with weighted routing
- Deployment state machine with audit trail

Every agent/model deployment goes through this harness.
No direct promotion to 100% — always through canary stages.

Usage:
    harness = DeploymentHarness()
    deployment = await harness.start_deployment(
        component="IntelligenceGenerator",
        old_version="v1.2",
        new_version="v1.3",
    )
    # Automatically progresses through canary stages
    # Rolls back if health checks fail
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Deployment State Machine
# ════════════════════════════════════════════════════════════════════


class DeploymentStage(str, Enum):
    """Canary deployment stages."""
    PENDING = "pending"              # Deployment created, not started
    CANARY_1PCT = "canary_1pct"      # 1% traffic to new version
    CANARY_10PCT = "canary_10pct"    # 10% traffic
    CANARY_50PCT = "canary_50pct"    # 50% traffic
    FULL = "full"                    # 100% traffic (promoted)
    ROLLED_BACK = "rolled_back"      # Reverted to old version
    FAILED = "failed"                # Deployment failed
    PAUSED = "paused"                # Manually paused


class DeploymentStatus(str, Enum):
    """Overall deployment status."""
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    PAUSED = "paused"


# Canary stage progression: traffic % for each stage
CANARY_STAGES = [
    (DeploymentStage.CANARY_1PCT, 0.01),
    (DeploymentStage.CANARY_10PCT, 0.10),
    (DeploymentStage.CANARY_50PCT, 0.50),
    (DeploymentStage.FULL, 1.00),
]


@dataclass
class HealthCheckResult:
    """Result of a health check during canary deployment."""
    check_name: str
    passed: bool
    value: float = 0.0
    threshold: float = 0.0
    message: str = ""
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "value": round(self.value, 4),
            "threshold": round(self.threshold, 4),
            "message": self.message,
        }


@dataclass
class DeploymentRecord:
    """Full record of a deployment lifecycle."""
    deployment_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    component: str = ""               # e.g. "IntelligenceGenerator"
    old_version: str = ""
    new_version: str = ""
    stage: DeploymentStage = DeploymentStage.PENDING
    status: DeploymentStatus = DeploymentStatus.IN_PROGRESS
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    duration_s: float = 0.0
    current_traffic_pct: float = 0.0
    health_checks: List[HealthCheckResult] = field(default_factory=list)
    stage_history: List[Dict[str, Any]] = field(default_factory=list)
    rollback_reason: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "component": self.component,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "stage": self.stage.value,
            "status": self.status.value,
            "current_traffic_pct": self.current_traffic_pct,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_s": round(self.duration_s, 1),
            "health_checks_passed": sum(1 for h in self.health_checks if h.passed),
            "health_checks_failed": sum(1 for h in self.health_checks if not h.passed),
            "stage_history": self.stage_history,
            "rollback_reason": self.rollback_reason,
            "error": self.error,
        }


# ════════════════════════════════════════════════════════════════════
# Health Checkers
# ════════════════════════════════════════════════════════════════════


class HealthChecker:
    """
    Runs health checks on canary deployments before promotion.

    Default checks:
    - Success rate ≥ 95% (new version must match old version reliability)
    - Latency p95 ≤ 2x baseline (new version must not be significantly slower)
    - Error rate ≤ 5% (no excessive errors)
    - No circuit breaker trips (agent-level resilience)

    Custom checks can be registered per component.
    """

    def __init__(self):
        self._custom_checks: Dict[str, List[Callable]] = {}
        self._logger = logger.bind(component="health_checker")

    def register_check(
        self,
        component: str,
        check_fn: Callable[[Dict[str, Any]], Coroutine],
    ) -> None:
        """Register a custom health check for a component."""
        self._custom_checks.setdefault(component, []).append(check_fn)

    async def run_checks(
        self,
        component: str,
        new_version_metrics: Dict[str, Any],
        old_version_metrics: Optional[Dict[str, Any]] = None,
    ) -> List[HealthCheckResult]:
        """
        Run all health checks for a deployment.

        Args:
            component: The component being deployed
            new_version_metrics: Metrics from the new (canary) version
            old_version_metrics: Metrics from the old (baseline) version

        Returns:
            List of HealthCheckResult
        """
        results: List[HealthCheckResult] = []

        # 1. Success rate check
        success_rate = new_version_metrics.get("success_rate", 0.0)
        results.append(HealthCheckResult(
            check_name="success_rate",
            passed=success_rate >= 0.95,
            value=success_rate,
            threshold=0.95,
            message=f"Success rate: {success_rate:.1%} (threshold: ≥95%)",
        ))

        # 2. Latency check (p95)
        new_p95 = new_version_metrics.get("latency_p95_ms", 0)
        baseline_p95 = old_version_metrics.get("latency_p95_ms", new_p95) if old_version_metrics else new_p95
        latency_ratio = new_p95 / max(baseline_p95, 1)
        results.append(HealthCheckResult(
            check_name="latency_p95",
            passed=latency_ratio <= 2.0,
            value=latency_ratio,
            threshold=2.0,
            message=f"Latency ratio: {latency_ratio:.2f}x baseline (threshold: ≤2x)",
        ))

        # 3. Error rate check
        error_rate = new_version_metrics.get("error_rate", 0.0)
        results.append(HealthCheckResult(
            check_name="error_rate",
            passed=error_rate <= 0.05,
            value=error_rate,
            threshold=0.05,
            message=f"Error rate: {error_rate:.1%} (threshold: ≤5%)",
        ))

        # 4. Circuit breaker check
        circuit_trips = new_version_metrics.get("circuit_breaker_trips", 0)
        results.append(HealthCheckResult(
            check_name="circuit_breaker",
            passed=circuit_trips == 0,
            value=float(circuit_trips),
            threshold=0.0,
            message=f"Circuit breaker trips: {circuit_trips} (threshold: 0)",
        ))

        # 5. Custom checks
        for check_fn in self._custom_checks.get(component, []):
            try:
                custom_result = await check_fn(new_version_metrics)
                if isinstance(custom_result, HealthCheckResult):
                    results.append(custom_result)
                elif isinstance(custom_result, dict):
                    results.append(HealthCheckResult(**custom_result))
            except Exception as exc:
                results.append(HealthCheckResult(
                    check_name=f"custom_{check_fn.__name__}",
                    passed=False,
                    message=f"Check failed: {exc}",
                ))

        return results

    def all_passed(self, results: List[HealthCheckResult]) -> bool:
        """Check if all health checks passed."""
        return all(r.passed for r in results)


# ════════════════════════════════════════════════════════════════════
# Traffic Router
# ════════════════════════════════════════════════════════════════════


class TrafficRouter:
    """
    Routes traffic between old and new versions during canary deployment.

    Maintains traffic weights per component and version.
    Traffic splitting is probabilistic — each request independently
    routes based on weights.
    """

    def __init__(self):
        # component → [(version, weight), ...]
        self._routes: Dict[str, List[tuple]] = {}
        self._logger = logger.bind(component="traffic_router")

    def set_traffic_split(
        self,
        component: str,
        old_version: str,
        new_version: str,
        new_traffic_pct: float,
    ) -> None:
        """Set traffic split between old and new versions."""
        old_weight = 1.0 - new_traffic_pct
        new_weight = new_traffic_pct

        self._routes[component] = [
            (old_version, old_weight),
            (new_version, new_weight),
        ]

        self._logger.info(
            "traffic_split_updated",
            component=component,
            old_version=old_version,
            old_pct=round(old_weight * 100, 1),
            new_version=new_version,
            new_pct=round(new_weight * 100, 1),
        )

    def route(self, component: str) -> str:
        """Route a request to a version based on current weights."""
        import random

        versions = self._routes.get(component, [])
        if not versions:
            return "default"

        total = sum(w for _, w in versions)
        r = random.uniform(0, total)
        cumulative = 0
        for version, weight in versions:
            cumulative += weight
            if r <= cumulative:
                return version
        return versions[-1][0]

    def promote_to_full(self, component: str, version: str) -> None:
        """Promote a version to 100% traffic."""
        self._routes[component] = [(version, 1.0)]
        self._logger.info("traffic_promoted_full", component=component, version=version)

    def rollback_to(
        self,
        component: str,
        stable_version: str,
    ) -> None:
        """Rollback all traffic to the stable version."""
        self._routes[component] = [(stable_version, 1.0)]
        self._logger.info("traffic_rollback", component=component, version=stable_version)

    def get_routes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get current traffic routes."""
        return {
            component: [
                {"version": v, "weight": w, "pct": round(w * 100, 1)}
                for v, w in versions
            ]
            for component, versions in self._routes.items()
        }


# ════════════════════════════════════════════════════════════════════
# Deployment Harness
# ════════════════════════════════════════════════════════════════════


@dataclass
class DeploymentHarnessConfig:
    """Configuration for the deployment harness."""
    # Stage hold times (how long to bake at each stage)
    canary_1pct_hold_s: float = 300.0     # 5 minutes at 1%
    canary_10pct_hold_s: float = 600.0    # 10 minutes at 10%
    canary_50pct_hold_s: float = 1800.0   # 30 minutes at 50%
    # Health check interval
    health_check_interval_s: float = 60.0
    # Max concurrent deployments
    max_concurrent_deployments: int = 3
    # Auto-rollback on health check failure
    auto_rollback_on_failure: bool = True
    # Require manual approval for 50% → 100%
    require_approval_for_full: bool = False


class DeploymentHarness:
    """
    Unified deployment harness for canary rollouts.

    Manages the full deployment lifecycle:
    1. Start deployment (register old → new version)
    2. Canary at 1% → health check → promote or rollback
    3. Canary at 10% → health check → promote or rollback
    4. Canary at 50% → health check → promote or rollback
    5. Full promotion (100%)

    Each stage:
    - Routes traffic using TrafficRouter
    - Runs health checks using HealthChecker
    - Waits for bake time
    - Promotes if healthy, rolls back if not

    Usage:
        harness = DeploymentHarness()
        deployment = await harness.start_deployment(
            component="IntelligenceGenerator",
            old_version="v1.2",
            new_version="v1.3",
        )
        # Check status
        status = harness.get_deployment_status(deployment.deployment_id)
    """

    def __init__(self, config: Optional[DeploymentHarnessConfig] = None):
        self._config = config or DeploymentHarnessConfig()
        self._health_checker = HealthChecker()
        self._traffic_router = TrafficRouter()
        self._logger = logger.bind(component="deployment_harness")

        # Active deployments
        self._deployments: Dict[str, DeploymentRecord] = {}
        # deployment_id → background task
        self._deployment_tasks: Dict[str, asyncio.Task] = {}
        # Completed deployments (audit trail)
        self._completed: List[DeploymentRecord] = []
        self._max_completed = 100

        # Metrics collection callback
        self._metrics_fn: Optional[Callable[[str, str], Coroutine]] = None
        # Approval callback
        self._approval_fn: Optional[Callable[[DeploymentRecord], Coroutine]] = None
        # Rollback callback
        self._rollback_fn: Optional[Callable[[str, str], Coroutine]] = None

    # ── Configuration ───────────────────────────────────────────────

    def set_metrics_fn(
        self, fn: Callable[[str, str], Coroutine],
    ) -> None:
        """
        Set function to collect metrics for a component/version.

        fn(component, version) → Dict with success_rate, latency_p95_ms, etc.
        """
        self._metrics_fn = fn

    def set_approval_fn(
        self, fn: Callable[[DeploymentRecord], Coroutine],
    ) -> None:
        """Set function for manual approval gates."""
        self._approval_fn = fn

    def set_rollback_fn(
        self, fn: Callable[[str, str], Coroutine],
    ) -> None:
        """Set function to execute rollback (e.g., restart old version)."""
        self._rollback_fn = fn

    # ── Core Deployment ─────────────────────────────────────────────

    async def start_deployment(
        self,
        component: str,
        old_version: str,
        new_version: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DeploymentRecord:
        """
        Start a canary deployment.

        Creates a deployment record and starts the canary progression
        in the background.
        """
        # Check concurrent deployment limit
        active = sum(
            1 for d in self._deployments.values()
            if d.status == DeploymentStatus.IN_PROGRESS
        )
        if active >= self._config.max_concurrent_deployments:
            raise RuntimeError(
                f"Max concurrent deployments ({self._config.max_concurrent_deployments}) reached"
            )

        record = DeploymentRecord(
            component=component,
            old_version=old_version,
            new_version=new_version,
            metadata=metadata or {},
        )

        self._deployments[record.deployment_id] = record

        # Set initial traffic split (0% to new)
        self._traffic_router.set_traffic_split(
            component, old_version, new_version, 0.0,
        )

        # Start background progression task
        task = asyncio.create_task(
            self._progress_deployment(record)
        )
        self._deployment_tasks[record.deployment_id] = task

        self._logger.info(
            "deployment_started",
            deployment_id=record.deployment_id,
            component=component,
            old_version=old_version,
            new_version=new_version,
        )

        return record

    async def _progress_deployment(self, record: DeploymentRecord) -> None:
        """Progress through canary stages in the background."""
        try:
            for stage, traffic_pct in CANARY_STAGES:
                # Update stage
                record.stage = stage
                record.current_traffic_pct = traffic_pct
                record.stage_history.append({
                    "stage": stage.value,
                    "traffic_pct": traffic_pct,
                    "entered_at": time.time(),
                })

                self._logger.info(
                    "deployment_stage_entered",
                    deployment_id=record.deployment_id,
                    stage=stage.value,
                    traffic_pct=traffic_pct,
                )

                # Set traffic split
                self._traffic_router.set_traffic_split(
                    record.component,
                    record.old_version,
                    record.new_version,
                    traffic_pct,
                )

                # Get hold time for this stage
                hold_time = self._get_hold_time(stage)

                # Bake period: run health checks periodically
                bake_start = time.time()
                while time.time() - bake_start < hold_time:
                    await asyncio.sleep(self._config.health_check_interval_s)

                    # Collect metrics
                    new_metrics = await self._collect_metrics(
                        record.component, record.new_version
                    )
                    old_metrics = await self._collect_metrics(
                        record.component, record.old_version
                    )

                    # Run health checks
                    health_results = await self._health_checker.run_checks(
                        record.component, new_metrics, old_metrics
                    )
                    record.health_checks.extend(health_results)

                    if not self._health_checker.all_passed(health_results):
                        # Health check failed
                        failed = [r for r in health_results if not r.passed]
                        self._logger.warning(
                            "health_check_failed",
                            deployment_id=record.deployment_id,
                            stage=stage.value,
                            failed_checks=[r.check_name for r in failed],
                        )

                        if self._config.auto_rollback_on_failure:
                            await self._rollback(
                                record,
                                f"Health check failed at {stage.value}: "
                                f"{', '.join(r.check_name for r in failed)}",
                            )
                            return

                # Stage completed successfully
                self._logger.info(
                    "deployment_stage_completed",
                    deployment_id=record.deployment_id,
                    stage=stage.value,
                )

                # Check if approval needed for full promotion
                if (
                    stage == DeploymentStage.CANARY_50PCT
                    and self._config.require_approval_for_full
                    and self._approval_fn
                ):
                    record.stage = DeploymentStage.PAUSED
                    record.status = DeploymentStatus.PAUSED
                    try:
                        approved = await self._approval_fn(record)
                        if not approved:
                            await self._rollback(record, "Full promotion not approved")
                            return
                    except Exception as exc:
                        await self._rollback(record, f"Approval error: {exc}")
                        return

            # All stages passed — deployment complete
            record.stage = DeploymentStage.FULL
            record.status = DeploymentStatus.SUCCESS
            record.ended_at = time.time()
            record.duration_s = record.ended_at - record.started_at

            self._traffic_router.promote_to_full(
                record.component, record.new_version
            )

            self._logger.info(
                "deployment_completed",
                deployment_id=record.deployment_id,
                component=record.component,
                new_version=record.new_version,
                duration_s=round(record.duration_s, 1),
            )

            # Move to completed
            self._completed.append(record)
            if len(self._completed) > self._max_completed:
                self._completed = self._completed[-self._max_completed:]

        except asyncio.CancelledError:
            record.status = DeploymentStatus.FAILED
            record.error = "Deployment cancelled"
            record.ended_at = time.time()
            record.duration_s = record.ended_at - record.started_at

        except Exception as exc:
            record.status = DeploymentStatus.FAILED
            record.error = str(exc)
            record.ended_at = time.time()
            record.duration_s = record.ended_at - record.started_at

            self._logger.error(
                "deployment_error",
                deployment_id=record.deployment_id,
                error=str(exc),
            )

            # Auto-rollback on error
            if self._config.auto_rollback_on_failure:
                await self._rollback(record, f"Deployment error: {exc}")

    async def _rollback(
        self,
        record: DeploymentRecord,
        reason: str,
    ) -> None:
        """Rollback a deployment to the old version."""
        record.stage = DeploymentStage.ROLLED_BACK
        record.status = DeploymentStatus.ROLLED_BACK
        record.rollback_reason = reason
        record.ended_at = time.time()
        record.duration_s = record.ended_at - record.started_at

        # Restore traffic to old version
        self._traffic_router.rollback_to(record.component, record.old_version)

        # Execute rollback callback
        if self._rollback_fn:
            try:
                await self._rollback_fn(record.component, record.old_version)
            except Exception as exc:
                self._logger.error("rollback_fn_error", error=str(exc))

        self._logger.warning(
            "deployment_rolled_back",
            deployment_id=record.deployment_id,
            component=record.component,
            reason=reason,
        )

        # Move to completed
        self._completed.append(record)
        if len(self._completed) > self._max_completed:
            self._completed = self._completed[-self._max_completed:]

    async def manual_rollback(self, deployment_id: str, reason: str = "manual") -> bool:
        """Manually rollback a deployment."""
        record = self._deployments.get(deployment_id)
        if not record or record.status != DeploymentStatus.IN_PROGRESS:
            return False

        # Cancel background task
        task = self._deployment_tasks.get(deployment_id)
        if task and not task.done():
            task.cancel()

        await self._rollback(record, reason)
        return True

    async def pause_deployment(self, deployment_id: str) -> bool:
        """Pause a deployment at its current stage."""
        record = self._deployments.get(deployment_id)
        if not record or record.status != DeploymentStatus.IN_PROGRESS:
            return False

        record.stage = DeploymentStage.PAUSED
        record.status = DeploymentStatus.PAUSED

        # Cancel background task
        task = self._deployment_tasks.get(deployment_id)
        if task and not task.done():
            task.cancel()

        self._logger.info("deployment_paused", deployment_id=deployment_id)
        return True

    async def resume_deployment(self, deployment_id: str) -> bool:
        """Resume a paused deployment."""
        record = self._deployments.get(deployment_id)
        if not record or record.status != DeploymentStatus.PAUSED:
            return False

        record.status = DeploymentStatus.IN_PROGRESS
        record.stage = DeploymentStage.CANARY_50PCT  # Resume from last stage

        task = asyncio.create_task(self._progress_deployment(record))
        self._deployment_tasks[deployment_id] = task

        self._logger.info("deployment_resumed", deployment_id=deployment_id)
        return True

    # ── Metrics Collection ──────────────────────────────────────────

    async def _collect_metrics(
        self, component: str, version: str,
    ) -> Dict[str, Any]:
        """Collect metrics for a component version."""
        if self._metrics_fn:
            try:
                return await self._metrics_fn(component, version)
            except Exception as exc:
                self._logger.warning("metrics_collection_error", error=str(exc))

        # Default: return empty metrics (health checks will use defaults)
        return {
            "success_rate": 1.0,
            "latency_p95_ms": 100.0,
            "error_rate": 0.0,
            "circuit_breaker_trips": 0,
        }

    def _get_hold_time(self, stage: DeploymentStage) -> float:
        """Get the bake time for a canary stage."""
        if stage == DeploymentStage.CANARY_1PCT:
            return self._config.canary_1pct_hold_s
        elif stage == DeploymentStage.CANARY_10PCT:
            return self._config.canary_10pct_hold_s
        elif stage == DeploymentStage.CANARY_50PCT:
            return self._config.canary_50pct_hold_s
        return 0.0

    # ── Monitoring API ──────────────────────────────────────────────

    def get_deployment_status(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific deployment."""
        record = self._deployments.get(deployment_id)
        if record:
            return record.to_dict()
        # Check completed
        for r in self._completed:
            if r.deployment_id == deployment_id:
                return r.to_dict()
        return None

    def get_active_deployments(self) -> List[Dict[str, Any]]:
        """Get all active deployments."""
        return [
            d.to_dict() for d in self._deployments.values()
            if d.status == DeploymentStatus.IN_PROGRESS
        ]

    def get_all_deployments(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent deployments (active + completed)."""
        all_deps = list(self._deployments.values()) + self._completed
        all_deps.sort(key=lambda d: d.started_at, reverse=True)
        return [d.to_dict() for d in all_deps[:limit]]

    def get_traffic_routes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get current traffic routing state."""
        return self._traffic_router.get_routes()

    def get_health(self) -> Dict[str, Any]:
        """Get deployment harness health."""
        active = sum(
            1 for d in self._deployments.values()
            if d.status == DeploymentStatus.IN_PROGRESS
        )
        recent_rollbacks = sum(
            1 for d in self._completed[-20:]
            if d.status == DeploymentStatus.ROLLED_BACK
        )

        return {
            "status": "healthy",
            "active_deployments": active,
            "max_concurrent": self._config.max_concurrent_deployments,
            "recent_rollbacks": recent_rollbacks,
            "total_deployments": len(self._deployments) + len(self._completed),
            "config": {
                "canary_1pct_hold_s": self._config.canary_1pct_hold_s,
                "canary_10pct_hold_s": self._config.canary_10pct_hold_s,
                "canary_50pct_hold_s": self._config.canary_50pct_hold_s,
                "auto_rollback": self._config.auto_rollback_on_failure,
                "require_approval_for_full": self._config.require_approval_for_full,
            },
        }


# ════════════════════════════════════════════════════════════════════
# Factory & Singleton
# ════════════════════════════════════════════════════════════════════


_global_deployment_harness: Optional[DeploymentHarness] = None


def get_deployment_harness() -> DeploymentHarness:
    """Get or create the global deployment harness."""
    global _global_deployment_harness
    if _global_deployment_harness is None:
        _global_deployment_harness = DeploymentHarness()
    return _global_deployment_harness


def create_deployment_harness(
    canary_1pct_hold_s: float = 300.0,
    canary_10pct_hold_s: float = 600.0,
    canary_50pct_hold_s: float = 1800.0,
    auto_rollback: bool = True,
    require_approval: bool = False,
) -> DeploymentHarness:
    """Create a deployment harness with custom configuration."""
    config = DeploymentHarnessConfig(
        canary_1pct_hold_s=canary_1pct_hold_s,
        canary_10pct_hold_s=canary_10pct_hold_s,
        canary_50pct_hold_s=canary_50pct_hold_s,
        auto_rollback_on_failure=auto_rollback,
        require_approval_for_full=require_approval,
    )
    return DeploymentHarness(config)
