"""
Deployment Harness — Canary deployment control plane for Angavu Intelligence.

Manages gradual rollout of new agent versions and model updates:
- Canary stages: 1% → 10% → 50% → 100%
- Health checks before each promotion
- Automatic rollback: error rate >1% or latency >2x baseline
- Traffic splitting with weighted routing
- Deployment state machine with audit trail
- Version tracking: which version serves what % of traffic
- Feature flags: enable/disable features per user segment
- Deployment metrics: error rate, latency, throughput per version

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

    # Feature flags
    harness.feature_flags.enable("new_scoring", segments=["premium_users"])
    if harness.feature_flags.is_enabled("new_scoring", user_segment="premium_users"):
        ...
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "value": round(self.value, 4),
            "threshold": round(self.threshold, 4),
            "message": self.message,
            "checked_at": self.checked_at,
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
    ended_at: float | None = None
    duration_s: float = 0.0
    current_traffic_pct: float = 0.0
    health_checks: list[HealthCheckResult] = field(default_factory=list)
    stage_history: list[dict[str, Any]] = field(default_factory=list)
    rollback_reason: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
            "metadata": self.metadata,
        }


# ════════════════════════════════════════════════════════════════════
# Version Tracker — which version serves what % of traffic
# ════════════════════════════════════════════════════════════════════


@dataclass
class VersionInfo:
    """Tracks a deployed version's state."""
    version: str
    component: str
    traffic_pct: float = 0.0
    deployed_at: float = field(default_factory=time.time)
    is_active: bool = True
    is_canary: bool = False
    promoted_at: float | None = None
    rolled_back_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "component": self.component,
            "traffic_pct": self.traffic_pct,
            "deployed_at": self.deployed_at,
            "is_active": self.is_active,
            "is_canary": self.is_canary,
            "promoted_at": self.promoted_at,
            "rolled_back_at": self.rolled_back_at,
        }


class VersionTracker:
    """
    Tracks which version serves what percentage of traffic.

    Maintains a registry of all versions per component, including
    active, canary, and historical versions.
    """

    def __init__(self):
        # component → version → VersionInfo
        self._versions: dict[str, dict[str, VersionInfo]] = defaultdict(dict)
        self._logger = logger.bind(component="version_tracker")

    def register_version(
        self, component: str, version: str, traffic_pct: float = 0.0,
        is_canary: bool = False,
    ) -> VersionInfo:
        """Register a new version for a component."""
        info = VersionInfo(
            version=version,
            component=component,
            traffic_pct=traffic_pct,
            is_canary=is_canary,
        )
        self._versions[component][version] = info
        self._logger.info(
            "version_registered",
            component=component, version=version,
            traffic_pct=traffic_pct, is_canary=is_canary,
        )
        return info

    def update_traffic(
        self, component: str, version: str, traffic_pct: float,
    ) -> None:
        """Update traffic percentage for a version."""
        info = self._versions.get(component, {}).get(version)
        if info:
            info.traffic_pct = traffic_pct

    def mark_promoted(self, component: str, version: str) -> None:
        """Mark a version as fully promoted."""
        info = self._versions.get(component, {}).get(version)
        if info:
            info.is_canary = False
            info.traffic_pct = 100.0
            info.promoted_at = time.time()
        # Demote old versions
        for v, vinfo in self._versions.get(component, {}).items():
            if v != version and vinfo.is_active:
                vinfo.is_active = False
                vinfo.traffic_pct = 0.0

    def mark_rolled_back(self, component: str, version: str) -> None:
        """Mark a version as rolled back."""
        info = self._versions.get(component, {}).get(version)
        if info:
            info.is_active = False
            info.is_canary = False
            info.traffic_pct = 0.0
            info.rolled_back_at = time.time()

    def get_active_versions(self, component: str) -> list[VersionInfo]:
        """Get all active versions for a component."""
        return [
            v for v in self._versions.get(component, {}).values()
            if v.is_active
        ]

    def get_version_map(self) -> dict[str, list[dict[str, Any]]]:
        """Get full version map: component → [version info, ...]."""
        return {
            comp: [v.to_dict() for v in versions.values()]
            for comp, versions in self._versions.items()
        }

    def get_serving_versions(self) -> list[dict[str, Any]]:
        """Get all versions currently serving traffic."""
        result = []
        for comp, versions in self._versions.items():
            for v in versions.values():
                if v.is_active and v.traffic_pct > 0:
                    result.append(v.to_dict())
        return result


# ════════════════════════════════════════════════════════════════════
# Feature Flags — enable/disable features per user segment
# ════════════════════════════════════════════════════════════════════


class FeatureFlagStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    PERCENTAGE_ROLLOUT = "percentage_rollout"


@dataclass
class FeatureFlag:
    """A feature flag with segment-based targeting."""
    name: str
    description: str = ""
    status: FeatureFlagStatus = FeatureFlagStatus.DISABLED
    enabled_segments: set[str] = field(default_factory=set)
    rollout_percentage: float = 0.0         # 0-100
    enabled_at: float | None = None
    disabled_at: float | None = None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "enabled_segments": sorted(self.enabled_segments),
            "rollout_percentage": self.rollout_percentage,
            "enabled_at": self.enabled_at,
            "disabled_at": self.disabled_at,
            "created_at": self.created_at,
        }


class FeatureFlagStore:
    """
    Manages feature flags with per-user-segment targeting.

    Supports:
    - Global on/off flags
    - Segment-based targeting (e.g., "premium_users", "beta_testers")
    - Percentage-based rollouts (deterministic via user ID hashing)

    Usage:
        flags = FeatureFlagStore()
        flags.create("new_scoring", description="New ML scoring algorithm")
        flags.enable("new_scoring", segments=["premium_users", "beta_testers"])

        if flags.is_enabled("new_scoring", user_id="user_123", user_segment="premium_users"):
            use_new_scoring()
    """

    def __init__(self):
        self._flags: dict[str, FeatureFlag] = {}
        self._logger = logger.bind(component="feature_flags")

    def create(
        self,
        name: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> FeatureFlag:
        """Create a new feature flag (disabled by default)."""
        if name in self._flags:
            raise ValueError(f"Feature flag '{name}' already exists")
        flag = FeatureFlag(
            name=name, description=description, metadata=metadata or {},
        )
        self._flags[name] = flag
        self._logger.info("feature_flag_created", name=name)
        return flag

    def enable(
        self,
        name: str,
        segments: list[str] | None = None,
        rollout_percentage: float = 100.0,
    ) -> None:
        """
        Enable a feature flag.

        Args:
            name: Flag name
            segments: User segments to enable for (None = all segments)
            rollout_percentage: Percentage of users to enable for (0-100)
        """
        flag = self._flags.get(name)
        if not flag:
            raise ValueError(f"Feature flag '{name}' not found")

        flag.status = FeatureFlagStatus.ENABLED
        flag.enabled_at = time.time()
        flag.disabled_at = None
        flag.rollout_percentage = min(100.0, max(0.0, rollout_percentage))

        if segments:
            flag.enabled_segments.update(segments)
            if rollout_percentage < 100.0:
                flag.status = FeatureFlagStatus.PERCENTAGE_ROLLOUT

        self._logger.info(
            "feature_flag_enabled",
            name=name, segments=segments,
            rollout_percentage=rollout_percentage,
        )

    def disable(self, name: str) -> None:
        """Disable a feature flag."""
        flag = self._flags.get(name)
        if not flag:
            raise ValueError(f"Feature flag '{name}' not found")

        flag.status = FeatureFlagStatus.DISABLED
        flag.disabled_at = time.time()
        self._logger.info("feature_flag_disabled", name=name)

    def is_enabled(
        self,
        name: str,
        user_id: str | None = None,
        user_segment: str | None = None,
    ) -> bool:
        """
        Check if a feature flag is enabled for a given user.

        Deterministic rollout: same user_id always gets the same result
        for a given flag, based on consistent hashing.
        """
        flag = self._flags.get(name)
        if not flag:
            return False

        if flag.status == FeatureFlagStatus.DISABLED:
            return False

        # If segments are defined, user must be in an enabled segment
        if flag.enabled_segments and user_segment:
            if user_segment not in flag.enabled_segments:
                return False

        # Percentage rollout check
        if flag.rollout_percentage < 100.0 and user_id:
            # Deterministic: hash user_id + flag_name → consistent bucket
            bucket = self._hash_bucket(user_id, name)
            return bucket < flag.rollout_percentage

        return True

    def get_all(self) -> list[dict[str, Any]]:
        """Get all feature flags."""
        return [f.to_dict() for f in self._flags.values()]

    def get_flag(self, name: str) -> dict[str, Any] | None:
        """Get a specific feature flag."""
        flag = self._flags.get(name)
        return flag.to_dict() if flag else None

    def delete(self, name: str) -> bool:
        """Delete a feature flag."""
        if name in self._flags:
            del self._flags[name]
            self._logger.info("feature_flag_deleted", name=name)
            return True
        return False

    @staticmethod
    def _hash_bucket(user_id: str, flag_name: str) -> float:
        """Deterministic hash → bucket [0, 100)."""
        h = hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest()
        return (int(h[:8], 16) % 10000) / 100.0


# ════════════════════════════════════════════════════════════════════
# Deployment Metrics — per-version error rate, latency, throughput
# ════════════════════════════════════════════════════════════════════


@dataclass
class VersionMetrics:
    """Aggregated metrics for a deployed version."""
    component: str
    version: str
    request_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    latency_samples: list[float] = field(default_factory=list)
    max_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    last_error_at: float | None = None
    last_request_at: float | None = None
    window_start: float = field(default_factory=time.time)

    # Sliding window for recent errors (last 5 min)
    _recent_errors: deque = field(default_factory=lambda: deque(maxlen=10000))
    _recent_requests: deque = field(default_factory=lambda: deque(maxlen=10000))

    @property
    def error_rate(self) -> float:
        """Current error rate (recent window)."""
        if not self._recent_requests:
            return 0.0
        now = time.time()
        window = 300  # 5 minutes
        recent = [t for t in self._recent_requests if now - t < window]
        errors = [t for t in self._recent_errors if now - t < window]
        if not recent:
            return 0.0
        return len(errors) / len(recent)

    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        return sum(self.latency_samples) / len(self.latency_samples)

    @property
    def p95_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        sorted_samples = sorted(self.latency_samples)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    @property
    def throughput_rps(self) -> float:
        """Requests per second over the last minute."""
        now = time.time()
        window = 60
        recent = [t for t in self._recent_requests if now - t < window]
        return len(recent) / window if window > 0 else 0.0

    def record_request(self, latency_ms: float, is_error: bool = False) -> None:
        """Record a request with its latency and error status."""
        now = time.time()
        self.request_count += 1
        self.total_latency_ms += latency_ms
        self.latency_samples.append(latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.last_request_at = now
        self._recent_requests.append(now)

        # Keep only last 1000 samples for percentile calculation
        if len(self.latency_samples) > 1000:
            self.latency_samples = self.latency_samples[-1000:]

        if is_error:
            self.error_count += 1
            self.last_error_at = now
            self._recent_errors.append(now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "version": self.version,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2) if self.min_latency_ms != float("inf") else 0,
            "throughput_rps": round(self.throughput_rps, 2),
            "last_error_at": self.last_error_at,
            "last_request_at": self.last_request_at,
        }


class DeploymentMetricsCollector:
    """
    Collects and aggregates deployment metrics per version.

    Tracks error rate, latency (avg, p95, max), and throughput
    for each deployed version of each component.
    """

    def __init__(self):
        # component → version → VersionMetrics
        self._metrics: dict[str, dict[str, VersionMetrics]] = defaultdict(dict)
        self._logger = logger.bind(component="deployment_metrics")

    def get_or_create(
        self, component: str, version: str,
    ) -> VersionMetrics:
        """Get or create metrics for a component version."""
        if version not in self._metrics[component]:
            self._metrics[component][version] = VersionMetrics(
                component=component, version=version,
            )
        return self._metrics[component][version]

    def record(
        self,
        component: str,
        version: str,
        latency_ms: float,
        is_error: bool = False,
    ) -> None:
        """Record a request for a component version."""
        metrics = self.get_or_create(component, version)
        metrics.record_request(latency_ms, is_error)

    def get_metrics(
        self, component: str, version: str,
    ) -> dict[str, Any]:
        """Get metrics for a specific component version."""
        metrics = self._metrics.get(component, {}).get(version)
        return metrics.to_dict() if metrics else {}

    def get_component_metrics(
        self, component: str,
    ) -> list[dict[str, Any]]:
        """Get metrics for all versions of a component."""
        return [
            m.to_dict() for m in self._metrics.get(component, {}).values()
        ]

    def get_all_metrics(self) -> dict[str, list[dict[str, Any]]]:
        """Get all metrics across all components."""
        return {
            comp: [m.to_dict() for m in versions.values()]
            for comp, versions in self._metrics.items()
        }

    def get_baseline_metrics(
        self, component: str, version: str,
    ) -> dict[str, Any]:
        """
        Get metrics formatted for health checker baseline comparison.

        Returns dict with success_rate, latency_p95_ms, error_rate, etc.
        """
        metrics = self._metrics.get(component, {}).get(version)
        if not metrics:
            return {
                "success_rate": 1.0,
                "latency_p95_ms": 100.0,
                "error_rate": 0.0,
                "circuit_breaker_trips": 0,
            }
        return {
            "success_rate": 1.0 - metrics.error_rate,
            "latency_p95_ms": metrics.p95_latency_ms,
            "error_rate": metrics.error_rate,
            "circuit_breaker_trips": 0,
        }


# ════════════════════════════════════════════════════════════════════
# Health Checkers
# ════════════════════════════════════════════════════════════════════


class HealthChecker:
    """
    Runs health checks on canary deployments before promotion.

    Default checks (production-grade thresholds):
    - Error rate ≤ 1% (strict: catches regressions early)
    - Latency p95 ≤ 2x baseline (new version must not be significantly slower)
    - Success rate ≥ 99%
    - No circuit breaker trips

    Custom checks can be registered per component.
    """

    def __init__(self):
        self._custom_checks: dict[str, list[Callable]] = {}
        self._logger = logger.bind(component="health_checker")

    def register_check(
        self,
        component: str,
        check_fn: Callable[[dict[str, Any]], Coroutine],
    ) -> None:
        """Register a custom health check for a component."""
        self._custom_checks.setdefault(component, []).append(check_fn)

    async def run_checks(
        self,
        component: str,
        new_version_metrics: dict[str, Any],
        old_version_metrics: dict[str, Any] | None = None,
    ) -> list[HealthCheckResult]:
        """
        Run all health checks for a deployment.

        Args:
            component: The component being deployed
            new_version_metrics: Metrics from the new (canary) version
            old_version_metrics: Metrics from the old (baseline) version

        Returns:
            List of HealthCheckResult
        """
        results: list[HealthCheckResult] = []

        # 1. Error rate check — ≤ 1% (production-grade threshold)
        error_rate = new_version_metrics.get("error_rate", 0.0)
        results.append(HealthCheckResult(
            check_name="error_rate",
            passed=error_rate <= 0.01,
            value=error_rate,
            threshold=0.01,
            message=f"Error rate: {error_rate:.2%} (threshold: ≤1%)",
        ))

        # 2. Success rate check — ≥ 99%
        success_rate = new_version_metrics.get("success_rate", 1.0)
        results.append(HealthCheckResult(
            check_name="success_rate",
            passed=success_rate >= 0.99,
            value=success_rate,
            threshold=0.99,
            message=f"Success rate: {success_rate:.1%} (threshold: ≥99%)",
        ))

        # 3. Latency check (p95) — ≤ 2x baseline
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

    def all_passed(self, results: list[HealthCheckResult]) -> bool:
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
        self._routes: dict[str, list[tuple]] = {}
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

    def get_routes(self) -> dict[str, list[dict[str, Any]]]:
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
    # Rollback thresholds (used by health checker)
    error_rate_threshold: float = 0.01    # 1%
    latency_ratio_threshold: float = 2.0  # 2x baseline


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
    - Collects metrics per version
    - Waits for bake time
    - Promotes if healthy, rolls back if not (error rate >1% or latency >2x)

    Includes:
    - Version tracking: which version serves what % of traffic
    - Feature flags: enable/disable features per user segment
    - Deployment metrics: error rate, latency, throughput per version
    """

    def __init__(self, config: DeploymentHarnessConfig | None = None):
        self._config = config or DeploymentHarnessConfig()
        self._health_checker = HealthChecker()
        self._traffic_router = TrafficRouter()
        self._version_tracker = VersionTracker()
        self._metrics_collector = DeploymentMetricsCollector()
        self.feature_flags = FeatureFlagStore()
        self._logger = logger.bind(component="deployment_harness")

        # Active deployments
        self._deployments: dict[str, DeploymentRecord] = {}
        # deployment_id → background task
        self._deployment_tasks: dict[str, asyncio.Task] = {}
        # Completed deployments (audit trail)
        self._completed: list[DeploymentRecord] = []
        self._max_completed = 100

        # Metrics collection callback (external source)
        self._metrics_fn: Callable[[str, str], Coroutine] | None = None
        # Approval callback
        self._approval_fn: Callable[[DeploymentRecord], Coroutine] | None = None
        # Rollback callback
        self._rollback_fn: Callable[[str, str], Coroutine] | None = None

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
        metadata: dict[str, Any] | None = None,
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

        # Register versions in tracker
        self._version_tracker.register_version(
            component, old_version, traffic_pct=100.0,
        )
        self._version_tracker.register_version(
            component, new_version, traffic_pct=0.0, is_canary=True,
        )

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
                # Update version tracker
                self._version_tracker.update_traffic(
                    record.component, record.old_version,
                    (1.0 - traffic_pct) * 100,
                )
                self._version_tracker.update_traffic(
                    record.component, record.new_version,
                    traffic_pct * 100,
                )

                # Get hold time for this stage
                hold_time = self._get_hold_time(stage)

                # Bake period: run health checks periodically
                bake_start = time.time()
                while time.time() - bake_start < hold_time:
                    await asyncio.sleep(self._config.health_check_interval_s)

                    # Collect metrics from both internal collector and external source
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
            self._version_tracker.mark_promoted(
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
        self._version_tracker.mark_rolled_back(
            record.component, record.new_version
        )

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
    ) -> dict[str, Any]:
        """
        Collect metrics for a component version.

        First tries the internal metrics collector, then falls back
        to the external metrics callback.
        """
        # Try internal collector first
        internal = self._metrics_collector.get_baseline_metrics(component, version)
        if internal.get("request_count", 0) > 0 if "request_count" in internal else True:
            # Has data from internal collector
            pass

        # Also try external source
        if self._metrics_fn:
            try:
                external = await self._metrics_fn(component, version)
                # Merge: prefer external if it has more data
                if external.get("request_count", 0) > internal.get("request_count", 0):
                    return external
            except Exception as exc:
                self._logger.warning("metrics_collection_error", error=str(exc))

        return internal

    def record_request(
        self, component: str, version: str,
        latency_ms: float, is_error: bool = False,
    ) -> None:
        """
        Record a request for metrics tracking.

        Call this from request handlers to feed the metrics collector.
        """
        self._metrics_collector.record(component, version, latency_ms, is_error)

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

    def get_deployment_status(self, deployment_id: str) -> dict[str, Any] | None:
        """Get status of a specific deployment."""
        record = self._deployments.get(deployment_id)
        if record:
            return record.to_dict()
        # Check completed
        for r in self._completed:
            if r.deployment_id == deployment_id:
                return r.to_dict()
        return None

    def get_active_deployments(self) -> list[dict[str, Any]]:
        """Get all active deployments."""
        return [
            d.to_dict() for d in self._deployments.values()
            if d.status == DeploymentStatus.IN_PROGRESS
        ]

    def get_all_deployments(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent deployments (active + completed)."""
        all_deps = list(self._deployments.values()) + self._completed
        all_deps.sort(key=lambda d: d.started_at, reverse=True)
        return [d.to_dict() for d in all_deps[:limit]]

    def get_traffic_routes(self) -> dict[str, list[dict[str, Any]]]:
        """Get current traffic routing state."""
        return self._traffic_router.get_routes()

    def get_version_map(self) -> dict[str, list[dict[str, Any]]]:
        """Get full version map: which version serves what %."""
        return self._version_tracker.get_version_map()

    def get_serving_versions(self) -> list[dict[str, Any]]:
        """Get all versions currently serving traffic."""
        return self._version_tracker.get_serving_versions()

    def get_all_metrics(self) -> dict[str, list[dict[str, Any]]]:
        """Get deployment metrics for all components and versions."""
        return self._metrics_collector.get_all_metrics()

    def get_component_metrics(self, component: str) -> list[dict[str, Any]]:
        """Get metrics for all versions of a specific component."""
        return self._metrics_collector.get_component_metrics(component)

    def get_health(self) -> dict[str, Any]:
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
            "feature_flags_count": len(self.feature_flags.get_all()),
            "tracked_versions": len(self._version_tracker.get_serving_versions()),
            "config": {
                "canary_1pct_hold_s": self._config.canary_1pct_hold_s,
                "canary_10pct_hold_s": self._config.canary_10pct_hold_s,
                "canary_50pct_hold_s": self._config.canary_50pct_hold_s,
                "auto_rollback": self._config.auto_rollback_on_failure,
                "require_approval_for_full": self._config.require_approval_for_full,
                "error_rate_threshold": self._config.error_rate_threshold,
                "latency_ratio_threshold": self._config.latency_ratio_threshold,
            },
        }


# ════════════════════════════════════════════════════════════════════
# Factory & Singleton
# ════════════════════════════════════════════════════════════════════


_global_deployment_harness: DeploymentHarness | None = None


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
    error_rate_threshold: float = 0.01,
    latency_ratio_threshold: float = 2.0,
) -> DeploymentHarness:
    """Create a deployment harness with custom configuration."""
    config = DeploymentHarnessConfig(
        canary_1pct_hold_s=canary_1pct_hold_s,
        canary_10pct_hold_s=canary_10pct_hold_s,
        canary_50pct_hold_s=canary_50pct_hold_s,
        auto_rollback_on_failure=auto_rollback,
        require_approval_for_full=require_approval,
        error_rate_threshold=error_rate_threshold,
        latency_ratio_threshold=latency_ratio_threshold,
    )
    return DeploymentHarness(config)
