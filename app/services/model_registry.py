"""
Model Registry — AI model version tracking, A/B testing, and rollback.

Tracks which model version each worker segment is using, enables
A/B testing for model comparison, and provides rollback capability.

Key features:
    - Model version lifecycle: training → staging → active → deprecated
    - A/B testing framework with traffic splitting
    - Performance metrics per worker segment
    - Instant rollback to previous version
    - Champion/challenger deployment pattern

Usage:
    registry = ModelRegistry()
    registry.register_model("qwen-0.5b-fl-sw", "v3.2.1", base="qwen-0.5b")
    registry.deploy("qwen-0.5b-fl-sw", "v3.2.1", traffic_pct=10)  # canary
    registry.promote("qwen-0.5b-fl-sw", "v3.2.1")  # full rollout
    registry.rollback("qwen-0.5b-fl-sw")  # revert to previous
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ModelStatus(str, Enum):
    TRAINING = "training"
    STAGING = "staging"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ROLLED_BACK = "rolled_back"


class ModelRegistry:
    """
    Registry for tracking AI model versions, A/B tests, and deployments.

    Supports:
    - Multiple models (e.g. different dialects, different base models)
    - A/B testing with traffic splitting
    - Champion/challenger pattern
    - Rollback to any previous active version
    - Performance tracking per model version
    """

    def __init__(self):
        # {model_name: {version: ModelEntry}}
        self._models: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        # {model_name: champion_version}
        self._champions: dict[str, str] = {}
        # {model_name: [version_history]}
        self._history: dict[str, list[str]] = defaultdict(list)
        # {ab_test_id: ABTestConfig}
        self._ab_tests: dict[str, dict[str, Any]] = {}
        # {model_name: {version: PerformanceMetrics}}
        self._metrics: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)

    def register_model(
        self,
        model_name: str,
        version: str,
        base_model: str,
        dialect: str = "sw",
        description: str = "",
        changelog: str = "",
        training_data_points: int = 0,
        federated_rounds: int = 0,
    ) -> dict[str, Any]:
        """
        Register a new model version.

        The model enters 'training' status by default.
        Move to 'staging' when ready for testing, then 'active' for production.
        """
        if version in self._models[model_name]:
            logger.warning("model_already_registered", model=model_name, version=version)
            return {"status": "already_exists", "model": model_name, "version": version}

        entry = {
            "model_name": model_name,
            "version": version,
            "base_model": base_model,
            "dialect": dialect,
            "status": ModelStatus.TRAINING.value,
            "is_champion": False,
            "traffic_pct": 0.0,
            "description": description,
            "changelog": changelog,
            "training_data_points": training_data_points,
            "federated_rounds": federated_rounds,
            "ab_test_id": None,
            "target_business_types": None,
            "target_regions": None,
            "created_at": datetime.now(UTC).isoformat(),
            "deployed_at": None,
            "deprecated_at": None,
        }

        self._models[model_name][version] = entry
        self._history[model_name].append(version)

        logger.info("model_registered", model=model_name, version=version, base=base_model)

        return {"status": "registered", "model": model_name, "version": version}

    def deploy(
        self,
        model_name: str,
        version: str,
        traffic_pct: float = 100.0,
        target_business_types: list[str] | None = None,
        target_regions: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Deploy a model version to receive traffic.

        traffic_pct: percentage of traffic to route to this model.
        If < 100%, it's a canary/A-B test deployment.
        """
        if model_name not in self._models or version not in self._models[model_name]:
            return {"status": "error", "message": f"Model {model_name}:{version} not found"}

        entry = self._models[model_name][version]

        # Validate status transition
        if entry["status"] not in (ModelStatus.TRAINING.value, ModelStatus.STAGING.value):
            return {
                "status": "error",
                "message": f"Cannot deploy model in '{entry['status']}' status. Must be training or staging.",
            }

        entry["status"] = ModelStatus.ACTIVE.value
        entry["traffic_pct"] = min(100.0, max(0.0, traffic_pct))
        entry["deployed_at"] = datetime.now(UTC).isoformat()
        entry["target_business_types"] = target_business_types
        entry["target_regions"] = target_regions

        # If 100% traffic and no champion exists, make it champion
        if traffic_pct >= 100.0:
            self._set_champion(model_name, version)

        logger.info(
            "model_deployed",
            model=model_name,
            version=version,
            traffic_pct=traffic_pct,
        )

        return {
            "status": "deployed",
            "model": model_name,
            "version": version,
            "traffic_pct": entry["traffic_pct"],
        }

    def promote(self, model_name: str, version: str) -> dict[str, Any]:
        """
        Promote a model to champion (100% traffic).

        Deprecates the current champion if one exists.
        """
        if model_name not in self._models or version not in self._models[model_name]:
            return {"status": "error", "message": f"Model {model_name}:{version} not found"}

        entry = self._models[model_name][version]
        if entry["status"] != ModelStatus.ACTIVE.value:
            return {
                "status": "error",
                "message": f"Can only promote active models. Current status: {entry['status']}",
            }

        self._set_champion(model_name, version)

        return {
            "status": "promoted",
            "model": model_name,
            "version": version,
            "message": f"{model_name}:{version} is now champion (100% traffic)",
        }

    def rollback(self, model_name: str) -> dict[str, Any]:
        """
        Rollback a model to the previous active version.

        Finds the most recent version that was active before the current
        champion and re-activates it.
        """
        if model_name not in self._champions:
            return {"status": "error", "message": f"No champion found for {model_name}"}

        current_version = self._champions[model_name]
        history = self._history.get(model_name, [])

        # Find previous version
        previous_version = None
        for v in reversed(history):
            if v != current_version:
                entry = self._models[model_name].get(v, {})
                if entry.get("status") in (
                    ModelStatus.ACTIVE.value,
                    ModelStatus.DEPRECATED.value,
                    ModelStatus.ROLLED_BACK.value,
                ):
                    previous_version = v
                    break

        if previous_version is None:
            return {
                "status": "error",
                "message": f"No previous version to rollback to for {model_name}",
            }

        # Deprecate current
        self._models[model_name][current_version]["status"] = ModelStatus.ROLLED_BACK.value
        self._models[model_name][current_version]["traffic_pct"] = 0.0
        self._models[model_name][current_version]["deprecated_at"] = (
            datetime.now(UTC).isoformat()
        )

        # Restore previous
        self._set_champion(model_name, previous_version)

        logger.warning(
            "model_rollback",
            model=model_name,
            from_version=current_version,
            to_version=previous_version,
        )

        return {
            "status": "rolled_back",
            "model": model_name,
            "from_version": current_version,
            "to_version": previous_version,
            "message": f"Rolled back {model_name} from {current_version} to {previous_version}",
        }

    def start_ab_test(
        self,
        model_name: str,
        champion_version: str,
        challenger_version: str,
        traffic_split: float = 50.0,
        description: str = "",
    ) -> dict[str, Any]:
        """
        Start an A/B test between two model versions.

        traffic_split: percentage of traffic going to the challenger.
        The champion gets (100 - traffic_split)%.
        """
        if model_name not in self._models:
            return {"status": "error", "message": f"Model {model_name} not found"}

        for v in (champion_version, challenger_version):
            if v not in self._models[model_name]:
                return {"status": "error", "message": f"Version {v} not found for {model_name}"}

        test_id = f"ab-{model_name}-{uuid.uuid4().hex[:8]}"

        # Set traffic splits
        self._models[model_name][champion_version]["traffic_pct"] = 100.0 - traffic_split
        self._models[model_name][champion_version]["is_champion"] = True
        self._models[model_name][champion_version]["ab_test_id"] = test_id

        self._models[model_name][challenger_version]["traffic_pct"] = traffic_split
        self._models[model_name][challenger_version]["is_champion"] = False
        self._models[model_name][challenger_version]["ab_test_id"] = test_id
        self._models[model_name][challenger_version]["status"] = ModelStatus.ACTIVE.value

        self._ab_tests[test_id] = {
            "test_id": test_id,
            "model_name": model_name,
            "champion": champion_version,
            "challenger": challenger_version,
            "traffic_split": traffic_split,
            "description": description,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "status": "running",
        }

        logger.info(
            "ab_test_started",
            test_id=test_id,
            model=model_name,
            champion=champion_version,
            challenger=challenger_version,
            split=traffic_split,
        )

        return {
            "status": "started",
            "test_id": test_id,
            "champion": champion_version,
            "challenger": challenger_version,
            "traffic_split": traffic_split,
        }

    def end_ab_test(
        self,
        test_id: str,
        winner: str | None = None,
    ) -> dict[str, Any]:
        """End an A/B test. If winner is specified, promote it."""
        if test_id not in self._ab_tests:
            return {"status": "error", "message": f"A/B test {test_id} not found"}

        test = self._ab_tests[test_id]
        test["ended_at"] = datetime.now(UTC).isoformat()
        test["status"] = "completed"

        if winner:
            self.promote(test["model_name"], winner)
            test["winner"] = winner

        return {"status": "completed", "test_id": test_id, "winner": winner}

    def record_metrics(
        self,
        model_name: str,
        version: str,
        metrics: dict[str, float],
    ) -> dict[str, Any]:
        """
        Record performance metrics for a model version.

        Common metrics:
        - accuracy_score: model accuracy on benchmarks
        - latency_p50_ms, latency_p95_ms, latency_p99_ms
        - worker_satisfaction: 0-5 scale
        - task_match_rate: percentage of correct task matches
        - error_rate: percentage of failed inferences
        """
        if model_name not in self._models or version not in self._models[model_name]:
            return {"status": "error", "message": f"Model {model_name}:{version} not found"}

        if model_name not in self._metrics:
            self._metrics[model_name] = {}
        if version not in self._metrics[model_name]:
            self._metrics[model_name][version] = {}

        self._metrics[model_name][version].update(metrics)
        self._metrics[model_name][version]["updated_at"] = (
            datetime.now(UTC).isoformat()
        )

        # Update entry with latest metrics
        entry = self._models[model_name][version]
        for key in ("accuracy_score", "latency_p50_ms", "latency_p95_ms",
                     "latency_p99_ms", "worker_satisfaction"):
            if key in metrics:
                entry[key] = metrics[key]

        return {"status": "recorded", "model": model_name, "version": version}

    def get_model(self, model_name: str, version: str) -> dict[str, Any] | None:
        """Get details of a specific model version."""
        if model_name in self._models and version in self._models[model_name]:
            entry = dict(self._models[model_name][version])
            entry["metrics"] = self._metrics.get(model_name, {}).get(version, {})
            return entry
        return None

    def get_champion(self, model_name: str) -> dict[str, Any] | None:
        """Get the current champion model for a given model name."""
        version = self._champions.get(model_name)
        if version:
            return self.get_model(model_name, version)
        return None

    def list_models(
        self,
        model_name: str | None = None,
        status: str | None = None,
        dialect: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all registered models with optional filters."""
        results = []
        names = [model_name] if model_name else list(self._models.keys())

        for name in names:
            for version, entry in self._models.get(name, {}).items():
                if status and entry["status"] != status:
                    continue
                if dialect and entry.get("dialect") != dialect:
                    continue
                item = dict(entry)
                item["metrics"] = self._metrics.get(name, {}).get(version, {})
                results.append(item)

        return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)

    def get_ab_tests(self, model_name: str | None = None) -> list[dict[str, Any]]:
        """List A/B tests, optionally filtered by model name."""
        tests = list(self._ab_tests.values())
        if model_name:
            tests = [t for t in tests if t["model_name"] == model_name]
        return sorted(tests, key=lambda x: x.get("started_at", ""), reverse=True)

    def get_model_performance(
        self,
        model_name: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        """
        Get performance metrics for a model, optionally comparing versions.
        """
        if model_name not in self._metrics:
            return {"model": model_name, "versions": {}}

        if version:
            return {
                "model": model_name,
                "version": version,
                "metrics": self._metrics[model_name].get(version, {}),
            }

        return {
            "model": model_name,
            "versions": {
                v: m for v, m in self._metrics[model_name].items()
            },
        }

    def get_registry_summary(self) -> dict[str, Any]:
        """Get a summary of the entire model registry."""
        total_models = sum(len(versions) for versions in self._models.values())
        active_models = sum(
            1
            for versions in self._models.values()
            for v in versions.values()
            if v["status"] == ModelStatus.ACTIVE.value
        )
        champions = {
            name: {
                "version": ver,
                "deployed_at": self._models[name][ver].get("deployed_at"),
            }
            for name, ver in self._champions.items()
            if name in self._models and ver in self._models[name]
        }

        return {
            "total_model_names": len(self._models),
            "total_versions": total_models,
            "active_versions": active_models,
            "champions": champions,
            "running_ab_tests": sum(
                1 for t in self._ab_tests.values() if t["status"] == "running"
            ),
            "total_ab_tests": len(self._ab_tests),
        }

    # ── Private helpers ──

    def _set_champion(self, model_name: str, version: str):
        """Set a version as champion, demoting the previous one."""
        # Demote old champion
        old_champion = self._champions.get(model_name)
        if old_champion and old_champion in self._models.get(model_name, {}):
            self._models[model_name][old_champion]["is_champion"] = False
            self._models[model_name][old_champion]["status"] = ModelStatus.DEPRECATED.value
            self._models[model_name][old_champion]["traffic_pct"] = 0.0
            self._models[model_name][old_champion]["deprecated_at"] = (
                datetime.now(UTC).isoformat()
            )

        # Promote new champion
        self._champions[model_name] = version
        entry = self._models[model_name][version]
        entry["is_champion"] = True
        entry["status"] = ModelStatus.ACTIVE.value
        entry["traffic_pct"] = 100.0
        entry["deployed_at"] = datetime.now(UTC).isoformat()
