"""
Data Pipeline Harness — Unified control plane for intelligence data flows.

Wraps the intelligence pipeline with:
- Input/output validation (schema, range, completeness)
- Drift detection (CUSUM-based concept drift monitoring)
- Quality scoring (data completeness, freshness, accuracy)
- Auto-retrain triggers when drift is detected
- Alerting on quality degradation

Every data transformation in the intelligence pipeline flows through
this harness. No data should reach agents without validation.

Usage:
    harness = DataPipelineHarness()
    result = await harness.process_pipeline(
        pipeline_name="credit_scoring",
        input_data=raw_data,
        process_fn=my_pipeline_function,
        user_id="worker_123",
    )
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Quality Scoring
# ════════════════════════════════════════════════════════════════════


class QualityDimension(str, Enum):
    """Dimensions of data quality."""
    COMPLETENESS = "completeness"    # Are all required fields present?
    FRESHNESS = "freshness"          # How recent is the data?
    CONSISTENCY = "consistency"      # Are values internally consistent?
    ACCURACY = "accuracy"            # Do values fall within expected ranges?
    UNIQUENESS = "uniqueness"        # Are there duplicate records?


@dataclass
class QualityScore:
    """Quality score breakdown for a data item."""
    overall: float = 0.0            # 0.0–1.0 weighted average
    completeness: float = 1.0
    freshness: float = 1.0
    consistency: float = 1.0
    accuracy: float = 1.0
    uniqueness: float = 1.0
    issues: List[str] = field(default_factory=list)
    scored_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": round(self.overall, 4),
            "completeness": round(self.completeness, 4),
            "freshness": round(self.freshness, 4),
            "consistency": round(self.consistency, 4),
            "accuracy": round(self.accuracy, 4),
            "uniqueness": round(self.uniqueness, 4),
            "issues": self.issues,
        }


class DataQualityScorer:
    """
    Scores data quality across multiple dimensions.

    For each pipeline, registers expected schemas and validation rules.
    Produces a QualityScore for every data item processed.
    """

    def __init__(self):
        # pipeline_name → list of required fields
        self._schemas: Dict[str, List[str]] = {}
        # pipeline_name → list of (field, min_val, max_val) range checks
        self._range_checks: Dict[str, List[Tuple[str, float, float]]] = {}
        # pipeline_name → max age in seconds for freshness check
        self._max_age_s: Dict[str, float] = {}
        self._logger = logger.bind(component="data_quality_scorer")

    def register_schema(
        self,
        pipeline_name: str,
        required_fields: List[str],
        range_checks: Optional[List[Tuple[str, float, float]]] = None,
        max_age_s: float = 86400.0,  # 24h default
    ) -> None:
        """Register expected schema for a pipeline."""
        self._schemas[pipeline_name] = required_fields
        if range_checks:
            self._range_checks[pipeline_name] = range_checks
        self._max_age_s[pipeline_name] = max_age_s

    def score(
        self,
        pipeline_name: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> QualityScore:
        """Score data quality for a pipeline."""
        issues: List[str] = []
        scores: Dict[str, float] = {}

        # 1. Completeness
        required = self._schemas.get(pipeline_name, [])
        if required:
            present = sum(1 for f in required if f in data and data[f] is not None)
            scores["completeness"] = present / len(required)
            missing = [f for f in required if f not in data or data[f] is None]
            if missing:
                issues.append(f"missing_fields: {missing}")
        else:
            scores["completeness"] = 1.0

        # 2. Freshness
        max_age = self._max_age_s.get(pipeline_name, 86400.0)
        data_ts = timestamp or data.get("timestamp", time.time())
        age_s = time.time() - data_ts
        if age_s <= 0:
            scores["freshness"] = 1.0
        elif age_s <= max_age:
            scores["freshness"] = 1.0 - (age_s / max_age) * 0.5
        else:
            scores["freshness"] = max(0.0, 0.5 - (age_s - max_age) / max_age * 0.5)
            issues.append(f"data_stale: {age_s:.0f}s old (max {max_age:.0f}s)")

        # 3. Accuracy (range checks)
        ranges = self._range_checks.get(pipeline_name, [])
        if ranges:
            range_passes = 0
            for field_name, min_val, max_val in ranges:
                val = data.get(field_name)
                if val is not None:
                    try:
                        val_f = float(val)
                        if min_val <= val_f <= max_val:
                            range_passes += 1
                        else:
                            issues.append(f"out_of_range: {field_name}={val} not in [{min_val}, {max_val}]")
                    except (ValueError, TypeError):
                        issues.append(f"type_error: {field_name}={val} not numeric")
                else:
                    range_passes += 1  # Missing field handled by completeness
            scores["accuracy"] = range_passes / len(ranges) if ranges else 1.0
        else:
            scores["accuracy"] = 1.0

        # 4. Consistency (basic cross-field checks)
        scores["consistency"] = self._check_consistency(pipeline_name, data, issues)

        # 5. Uniqueness (check for duplicate-like values)
        scores["uniqueness"] = 1.0  # Per-item scoring; uniqueness is pipeline-level

        # Weighted average
        weights = {
            "completeness": 0.30,
            "freshness": 0.20,
            "accuracy": 0.25,
            "consistency": 0.15,
            "uniqueness": 0.10,
        }
        overall = sum(scores[k] * weights[k] for k in weights)

        return QualityScore(
            overall=overall,
            completeness=scores["completeness"],
            freshness=scores["freshness"],
            consistency=scores["consistency"],
            accuracy=scores["accuracy"],
            uniqueness=scores["uniqueness"],
            issues=issues,
        )

    def _check_consistency(
        self,
        pipeline_name: str,
        data: Dict[str, Any],
        issues: List[str],
    ) -> float:
        """Check cross-field consistency."""
        score = 1.0

        # Credit scoring consistency
        if pipeline_name == "credit_scoring":
            credit_score = data.get("credit_score") or data.get("alama_score")
            if credit_score is not None:
                try:
                    cs = float(credit_score)
                    if cs < 300 or cs > 850:
                        issues.append(f"credit_score_out_of_range: {cs}")
                        score -= 0.3
                except (ValueError, TypeError):
                    pass

            # Default probability should be 0-1
            dp = data.get("default_probability")
            if dp is not None:
                try:
                    dp_f = float(dp)
                    if dp_f < 0 or dp_f > 1:
                        issues.append(f"default_probability_out_of_range: {dp_f}")
                        score -= 0.2
                except (ValueError, TypeError):
                    pass

        # Market analysis consistency
        elif pipeline_name == "market_analysis":
            prices = data.get("prices", {})
            if isinstance(prices, dict):
                avg = prices.get("avg")
                min_p = prices.get("min")
                max_p = prices.get("max")
                if avg and min_p and max_p:
                    try:
                        if float(min_p) > float(avg) or float(avg) > float(max_p):
                            issues.append("price_inconsistency: min > avg or avg > max")
                            score -= 0.3
                    except (ValueError, TypeError):
                        pass

        return max(0.0, score)


# ════════════════════════════════════════════════════════════════════
# Drift Detection Integration
# ════════════════════════════════════════════════════════════════════


@dataclass
class DriftAlert:
    """Alert generated when data drift is detected."""
    alert_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    pipeline_name: str = ""
    metric_name: str = ""
    drift_type: str = ""               # "distribution_shift", "schema_change", "volume_anomaly"
    severity: str = "warning"          # "info", "warning", "critical"
    current_value: float = 0.0
    baseline_value: float = 0.0
    drift_magnitude: float = 0.0
    message: str = ""
    triggered_at: float = field(default_factory=time.time)
    auto_retrain_triggered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "pipeline_name": self.pipeline_name,
            "metric_name": self.metric_name,
            "drift_type": self.drift_type,
            "severity": self.severity,
            "current_value": round(self.current_value, 6),
            "baseline_value": round(self.baseline_value, 6),
            "drift_magnitude": round(self.drift_magnitude, 4),
            "message": self.message,
            "triggered_at": self.triggered_at,
            "auto_retrain_triggered": self.auto_retrain_triggered,
        }


class DataDriftDetector:
    """
    Detects data drift in pipeline inputs/outputs.

    Uses multiple detection methods:
    - Statistical: CUSUM on key metrics
    - Schema: field presence/type changes
    - Volume: sudden changes in data volume
    - Distribution: statistical distance from baseline

    When drift is detected:
    1. Generates an alert
    2. Optionally triggers automatic retraining
    3. Logs in Swahili for local operators
    """

    def __init__(self):
        # pipeline_name → metric_name → baseline stats
        self._baselines: Dict[str, Dict[str, Dict[str, float]]] = {}
        # pipeline_name → CUSUM state
        self._cusum_states: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        # CUSUM parameters
        self._cusum_delta: float = 1.0
        self._cusum_h: float = 4.0
        self._cusum_k: float = 0.5

        # Volume tracking (sliding window)
        self._volume_windows: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # Alerts
        self._alerts: List[DriftAlert] = []
        self._max_alerts = 500

        # Auto-retrain callback
        self._retrain_callback: Optional[Callable[[DriftAlert], Coroutine]] = None

        # Pipeline schemas for schema drift
        self._known_schemas: Dict[str, set] = {}

        self._logger = logger.bind(component="data_drift_detector")

    def set_retrain_callback(self, callback: Callable[[DriftAlert], Coroutine]) -> None:
        """Register callback to trigger when drift requires retraining."""
        self._retrain_callback = callback

    def register_baseline(
        self,
        pipeline_name: str,
        metric_name: str,
        mean: float,
        std: float,
    ) -> None:
        """Register baseline statistics for a pipeline metric."""
        if pipeline_name not in self._baselines:
            self._baselines[pipeline_name] = {}
        self._baselines[pipeline_name][metric_name] = {
            "mean": mean,
            "std": std,
        }

    def check_drift(
        self,
        pipeline_name: str,
        data: Dict[str, Any],
        metrics: Optional[Dict[str, float]] = None,
    ) -> List[DriftAlert]:
        """
        Check for drift in pipeline data.

        Args:
            pipeline_name: Which pipeline
            data: The data being processed (for schema checks)
            metrics: Optional pre-computed metrics to check

        Returns:
            List of drift alerts (empty if no drift)
        """
        alerts: List[DriftAlert] = []

        # 1. Schema drift
        schema_alert = self._check_schema_drift(pipeline_name, data)
        if schema_alert:
            alerts.append(schema_alert)

        # 2. Volume drift
        volume_alert = self._check_volume_drift(pipeline_name)
        if volume_alert:
            alerts.append(volume_alert)

        # 3. Metric drift (CUSUM)
        if metrics:
            for metric_name, value in metrics.items():
                metric_alert = self._check_metric_drift(
                    pipeline_name, metric_name, value
                )
                if metric_alert:
                    alerts.append(metric_alert)

        # Store alerts
        for alert in alerts:
            self._alerts.append(alert)
            if len(self._alerts) > self._max_alerts:
                self._alerts = self._alerts[-self._max_alerts:]

            self._logger.warning(
                "data_drift_detected",
                pipeline=pipeline_name,
                drift_type=alert.drift_type,
                severity=alert.severity,
                metric=alert.metric_name,
                magnitude=round(alert.drift_magnitude, 4),
            )

        return alerts

    def _check_schema_drift(
        self,
        pipeline_name: str,
        data: Dict[str, Any],
    ) -> Optional[DriftAlert]:
        """Check for schema changes (new/missing fields)."""
        current_fields = set(data.keys())
        known = self._known_schemas.get(pipeline_name)

        if known is None:
            # First time — record schema
            self._known_schemas[pipeline_name] = current_fields
            return None

        new_fields = current_fields - known
        removed_fields = known - current_fields

        if new_fields or removed_fields:
            # Update known schema
            self._known_schemas[pipeline_name] = current_fields

            issues = []
            if new_fields:
                issues.append(f"new_fields: {new_fields}")
            if removed_fields:
                issues.append(f"removed_fields: {removed_fields}")

            severity = "warning" if removed_fields else "info"

            return DriftAlert(
                pipeline_name=pipeline_name,
                metric_name="schema",
                drift_type="schema_change",
                severity=severity,
                message=f"Schema changed: {'; '.join(issues)}",
            )

        return None

    def _check_volume_drift(self, pipeline_name: str) -> Optional[DriftAlert]:
        """Check for sudden volume changes."""
        window = self._volume_windows[pipeline_name]
        window.append(time.time())

        if len(window) < 10:
            return None

        # Calculate recent vs historical rate
        now = time.time()
        recent = sum(1 for t in window if now - t < 60)
        historical = len(window) / max(1, (now - window[0]) / 60)

        if historical > 0:
            ratio = recent / historical
            if ratio > 3.0 or ratio < 0.3:
                return DriftAlert(
                    pipeline_name=pipeline_name,
                    metric_name="volume",
                    drift_type="volume_anomaly",
                    severity="warning",
                    current_value=recent,
                    baseline_value=historical,
                    drift_magnitude=abs(ratio - 1.0),
                    message=f"Volume anomaly: {recent}/min vs baseline {historical:.1f}/min (ratio {ratio:.2f})",
                )

        return None

    def _check_metric_drift(
        self,
        pipeline_name: str,
        metric_name: str,
        value: float,
    ) -> Optional[DriftAlert]:
        """Check for metric drift using CUSUM."""
        baseline = self._baselines.get(pipeline_name, {}).get(metric_name)
        if not baseline:
            return None

        mean = baseline["mean"]
        std = max(baseline["std"], 1e-6)

        # Standardize
        z = (value - mean) / std

        # Update CUSUM (upper = degradation)
        state_key = f"{pipeline_name}:{metric_name}"
        self._cusum_states[state_key]["s_upper"] = max(
            0, self._cusum_states[state_key].get("s_upper", 0) + (-z) - self._cusum_k
        )
        self._cusum_states[state_key]["s_lower"] = min(
            0, self._cusum_states[state_key].get("s_lower", 0) + (-z) + self._cusum_k
        )

        s_upper = self._cusum_states[state_key]["s_upper"]

        # Check threshold
        if s_upper > self._cusum_h:
            # Reset CUSUM
            self._cusum_states[state_key]["s_upper"] = 0.0

            severity = "critical" if s_upper > self._cusum_h * 2 else "warning"

            alert = DriftAlert(
                pipeline_name=pipeline_name,
                metric_name=metric_name,
                drift_type="distribution_shift",
                severity=severity,
                current_value=value,
                baseline_value=mean,
                drift_magnitude=s_upper / std,
                message=(
                    f"Metric '{metric_name}' drifted: "
                    f"current={value:.4f}, baseline={mean:.4f} ± {std:.4f}, "
                    f"CUSUM={s_upper:.4f} (threshold={self._cusum_h})"
                ),
            )

            # Auto-retrain for critical drift
            if severity == "critical" and self._retrain_callback:
                try:
                    asyncio.create_task(self._retrain_callback(alert))
                    alert.auto_retrain_triggered = True
                    self._logger.info(
                        "auto_retrain_triggered",
                        pipeline=pipeline_name,
                        metric=metric_name,
                    )
                except Exception as cb_err:
                    self._logger.error("retrain_callback_error", error=str(cb_err))

            return alert

        return None

    def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent drift alerts."""
        return [a.to_dict() for a in self._alerts[-limit:]]

    def get_status(self) -> Dict[str, Any]:
        """Get drift detection status."""
        recent_alerts = [a for a in self._alerts if time.time() - a.triggered_at < 3600]
        critical = sum(1 for a in recent_alerts if a.severity == "critical")
        warnings = sum(1 for a in recent_alerts if a.severity == "warning")

        return {
            "total_alerts": len(self._alerts),
            "recent_alerts_1h": len(recent_alerts),
            "critical_1h": critical,
            "warnings_1h": warnings,
            "pipelines_monitored": len(self._baselines),
            "schemas_tracked": len(self._known_schemas),
        }


# ════════════════════════════════════════════════════════════════════
# Pipeline Execution Record
# ════════════════════════════════════════════════════════════════════


@dataclass
class PipelineExecutionRecord:
    """Record of a single pipeline execution through the harness."""
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    pipeline_name: str = ""
    user_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    duration_ms: float = 0.0
    success: bool = False
    input_quality: Optional[QualityScore] = None
    output_quality: Optional[QualityScore] = None
    drift_alerts: List[DriftAlert] = field(default_factory=list)
    error: Optional[str] = None
    input_size_bytes: int = 0
    output_size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "pipeline_name": self.pipeline_name,
            "user_id": self.user_id,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "input_quality": self.input_quality.to_dict() if self.input_quality else None,
            "output_quality": self.output_quality.to_dict() if self.output_quality else None,
            "drift_alerts": len(self.drift_alerts),
            "error": self.error,
        }


# ════════════════════════════════════════════════════════════════════
# Data Pipeline Harness
# ════════════════════════════════════════════════════════════════════


@dataclass
class DataHarnessConfig:
    """Configuration for the data pipeline harness."""
    min_input_quality: float = 0.3      # Minimum input quality to proceed
    min_output_quality: float = 0.5     # Minimum output quality to accept
    enable_drift_detection: bool = True
    enable_quality_scoring: bool = True
    auto_retrain_on_critical_drift: bool = True
    max_alerts: int = 500
    alert_quality_drop_threshold: float = 0.2  # Alert if quality drops by this much


class DataPipelineHarness:
    """
    Unified data pipeline harness for intelligence flows.

    Wraps every pipeline execution with:
    1. Input validation and quality scoring
    2. Drift detection on input data
    3. Output validation and quality scoring
    4. Alert generation on quality degradation
    5. Auto-retrain triggers on critical drift

    Usage:
        harness = DataPipelineHarness()
        harness.register_pipeline(
            "credit_scoring",
            required_fields=["worker_id", "transactions"],
            range_checks=[("credit_score", 300, 850)],
        )

        result = await harness.process_pipeline(
            pipeline_name="credit_scoring",
            input_data=raw_data,
            process_fn=my_credit_pipeline,
        )
    """

    def __init__(self, config: Optional[DataHarnessConfig] = None):
        self._config = config or DataHarnessConfig()
        self._quality_scorer = DataQualityScorer()
        self._drift_detector = DataDriftDetector()
        self._logger = logger.bind(component="data_pipeline_harness")

        # Execution history
        self._records: List[PipelineExecutionRecord] = []
        self._max_records = 1000

        # Per-pipeline quality trend (for detecting degradation)
        self._quality_trends: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # Alert hooks
        self._alert_hooks: List[Callable] = []

    # ── Pipeline Registration ───────────────────────────────────────

    def register_pipeline(
        self,
        pipeline_name: str,
        required_fields: List[str],
        range_checks: Optional[List[Tuple[str, float, float]]] = None,
        max_age_s: float = 86400.0,
        baseline_metrics: Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> None:
        """
        Register a pipeline with its expected schema and validation rules.

        Args:
            pipeline_name: Unique pipeline identifier
            required_fields: Fields that must be present in input
            range_checks: (field, min, max) tuples for range validation
            max_age_s: Maximum data age for freshness check
            baseline_metrics: {metric_name: (mean, std)} for drift detection
        """
        self._quality_scorer.register_schema(
            pipeline_name, required_fields, range_checks, max_age_s,
        )

        if baseline_metrics:
            for metric_name, (mean, std) in baseline_metrics.items():
                self._drift_detector.register_baseline(
                    pipeline_name, metric_name, mean, std,
                )

        self._logger.info(
            "pipeline_registered",
            pipeline=pipeline_name,
            required_fields=required_fields,
            has_range_checks=bool(range_checks),
            has_baselines=bool(baseline_metrics),
        )

    # ── Core Processing ─────────────────────────────────────────────

    async def process_pipeline(
        self,
        pipeline_name: str,
        input_data: Dict[str, Any],
        process_fn: Callable[[Dict[str, Any]], Coroutine],
        user_id: Optional[str] = None,
        input_timestamp: Optional[float] = None,
        input_metrics: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Process data through a pipeline with full harness protection.

        Steps:
        1. Score input quality
        2. Check input quality threshold
        3. Detect drift in input data
        4. Execute the pipeline function
        5. Score output quality
        6. Check output quality threshold
        7. Track quality trends
        8. Return wrapped result

        Args:
            pipeline_name: Which pipeline to run
            input_data: The raw input data
            process_fn: Async function that processes the data
            user_id: Optional user for tracking
            input_timestamp: When the data was generated
            input_metrics: Pre-computed metrics for drift detection

        Returns:
            Dict with 'success', 'data', 'quality', 'drift_alerts', etc.
        """
        record = PipelineExecutionRecord(
            pipeline_name=pipeline_name,
            user_id=user_id,
            input_size_bytes=len(str(input_data)),
        )

        try:
            # 1. Score input quality
            if self._config.enable_quality_scoring:
                input_quality = self._quality_scorer.score(
                    pipeline_name, input_data, input_timestamp,
                )
                record.input_quality = input_quality

                # 2. Check input quality threshold
                if input_quality.overall < self._config.min_input_quality:
                    self._logger.warning(
                        "input_quality_below_threshold",
                        pipeline=pipeline_name,
                        quality=input_quality.overall,
                        threshold=self._config.min_input_quality,
                        issues=input_quality.issues,
                    )
                    record.success = False
                    record.error = f"Input quality {input_quality.overall:.2f} below threshold"
                    record.ended_at = time.time()
                    record.duration_ms = (record.ended_at - record.started_at) * 1000
                    self._records.append(record)

                    return {
                        "success": False,
                        "error": record.error,
                        "input_quality": input_quality.to_dict(),
                        "execution_id": record.execution_id,
                    }

            # 3. Detect drift
            if self._config.enable_drift_detection:
                drift_alerts = self._drift_detector.check_drift(
                    pipeline_name, input_data, input_metrics,
                )
                record.drift_alerts = drift_alerts

                # Fire alert hooks
                for alert in drift_alerts:
                    for hook in self._alert_hooks:
                        try:
                            await hook(alert)
                        except Exception as hook_err:
                            self._logger.debug("alert_hook_error", error=str(hook_err))

            # 4. Execute pipeline
            result = await process_fn(input_data)

            # 5. Score output quality
            if self._config.enable_quality_scoring and isinstance(result, dict):
                output_quality = self._quality_scorer.score(
                    pipeline_name, result, time.time(),
                )
                record.output_quality = output_quality

                # 6. Check output quality threshold
                if output_quality.overall < self._config.min_output_quality:
                    self._logger.warning(
                        "output_quality_below_threshold",
                        pipeline=pipeline_name,
                        quality=output_quality.overall,
                        threshold=self._config.min_output_quality,
                    )

            # 7. Track quality trend
            if record.input_quality:
                trend = self._quality_trends[pipeline_name]
                trend.append(record.input_quality.overall)
                self._check_quality_degradation(pipeline_name, trend)

            record.success = True
            record.ended_at = time.time()
            record.duration_ms = (record.ended_at - record.started_at) * 1000
            record.output_size_bytes = len(str(result))
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

            return {
                "success": True,
                "data": result,
                "input_quality": record.input_quality.to_dict() if record.input_quality else None,
                "output_quality": record.output_quality.to_dict() if record.output_quality else None,
                "drift_alerts": [a.to_dict() for a in record.drift_alerts],
                "execution_id": record.execution_id,
                "duration_ms": record.duration_ms,
            }

        except Exception as exc:
            record.success = False
            record.error = str(exc)
            record.ended_at = time.time()
            record.duration_ms = (record.ended_at - record.started_at) * 1000
            self._records.append(record)

            self._logger.error(
                "pipeline_execution_error",
                pipeline=pipeline_name,
                error=str(exc),
                duration_ms=round(record.duration_ms, 2),
            )

            return {
                "success": False,
                "error": str(exc),
                "execution_id": record.execution_id,
                "duration_ms": record.duration_ms,
            }

    # ── Quality Degradation Detection ───────────────────────────────

    def _check_quality_degradation(
        self,
        pipeline_name: str,
        trend: deque,
    ) -> None:
        """Check if quality is degrading over time."""
        if len(trend) < 10:
            return

        recent = list(trend)[-5:]
        older = list(trend)[-10:-5]

        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)

        drop = older_avg - recent_avg
        if drop > self._config.alert_quality_drop_threshold:
            self._logger.warning(
                "quality_degradation_detected",
                pipeline=pipeline_name,
                recent_avg=round(recent_avg, 4),
                older_avg=round(older_avg, 4),
                drop=round(drop, 4),
            )

    # ── Alert Hooks ─────────────────────────────────────────────────

    def add_alert_hook(self, hook: Callable) -> None:
        """Add hook to be called when drift alerts are generated."""
        self._alert_hooks.append(hook)

    def set_retrain_callback(self, callback: Callable) -> None:
        """Set callback for automatic retraining on critical drift."""
        self._drift_detector.set_retrain_callback(callback)

    # ── Monitoring API ──────────────────────────────────────────────

    def get_pipeline_stats(self, pipeline_name: str) -> Dict[str, Any]:
        """Get stats for a specific pipeline."""
        records = [r for r in self._records if r.pipeline_name == pipeline_name]
        if not records:
            return {"pipeline_name": pipeline_name, "executions": 0}

        successes = sum(1 for r in records if r.success)
        durations = [r.duration_ms for r in records]
        qualities = [
            r.input_quality.overall for r in records
            if r.input_quality is not None
        ]

        return {
            "pipeline_name": pipeline_name,
            "total_executions": len(records),
            "successes": successes,
            "failures": len(records) - successes,
            "success_rate": round(successes / len(records), 4),
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "avg_input_quality": round(sum(qualities) / len(qualities), 4) if qualities else 0,
            "recent_drift_alerts": sum(
                len(r.drift_alerts) for r in records[-20:]
            ),
        }

    def get_all_stats(self) -> Dict[str, Any]:
        """Get stats for all pipelines."""
        pipeline_names = set(r.pipeline_name for r in self._records)
        return {
            "pipelines": {
                name: self.get_pipeline_stats(name)
                for name in pipeline_names
            },
            "total_executions": len(self._records),
            "drift_status": self._drift_detector.get_status(),
        }

    def get_health(self) -> Dict[str, Any]:
        """Get harness health status."""
        recent = [r for r in self._records if time.time() - r.started_at < 3600]
        recent_failures = sum(1 for r in recent if not r.success)
        recent_drift = sum(len(r.drift_alerts) for r in recent)

        status = "healthy"
        if recent_failures > len(recent) * 0.5 and len(recent) > 5:
            status = "degraded"
        if recent_drift > 10:
            status = "warning"

        return {
            "status": status,
            "recent_executions_1h": len(recent),
            "recent_failures_1h": recent_failures,
            "recent_drift_alerts_1h": recent_drift,
            "config": {
                "min_input_quality": self._config.min_input_quality,
                "min_output_quality": self._config.min_output_quality,
                "drift_detection_enabled": self._config.enable_drift_detection,
                "auto_retrain_enabled": self._config.auto_retrain_on_critical_drift,
            },
        }


# ════════════════════════════════════════════════════════════════════
# Factory & Singleton
# ════════════════════════════════════════════════════════════════════


_global_data_harness: Optional[DataPipelineHarness] = None


def get_data_pipeline_harness() -> DataPipelineHarness:
    """Get or create the global data pipeline harness."""
    global _global_data_harness
    if _global_data_harness is None:
        _global_data_harness = create_default_data_harness()
    return _global_data_harness


def create_default_data_harness() -> DataPipelineHarness:
    """Create a data pipeline harness with default Angavu pipeline schemas."""
    harness = DataPipelineHarness()

    # Register credit scoring pipeline
    harness.register_pipeline(
        "credit_scoring",
        required_fields=["worker_id"],
        range_checks=[
            ("credit_score", 300, 850),
            ("default_probability", 0, 1),
            ("confidence", 0, 1),
        ],
        baseline_metrics={
            "avg_credit_score": (620.0, 80.0),
            "default_rate": (0.10, 0.05),
        },
    )

    # Register market analysis pipeline
    harness.register_pipeline(
        "market_analysis",
        required_fields=["region"],
        range_checks=[
            ("supply_index", 0, 100),
            ("demand_index", 0, 100),
        ],
        baseline_metrics={
            "price_volatility": (0.15, 0.08),
            "trade_volume": (100000.0, 50000.0),
        },
    )

    # Register distribution analysis pipeline
    harness.register_pipeline(
        "distribution_analysis",
        required_fields=[],
        range_checks=[
            ("coverage_pct", 0, 100),
        ],
    )

    # Register competitor analysis pipeline
    harness.register_pipeline(
        "competitor_analysis",
        required_fields=[],
        range_checks=[
            ("distinct_sellers", 0, 10000),
        ],
    )

    logger.info("data_pipeline_harness_created", pipelines=4)
    return harness


def create_data_pipeline_harness(
    config: Optional[DataHarnessConfig] = None,
) -> DataPipelineHarness:
    """Create a data pipeline harness with custom configuration."""
    return DataPipelineHarness(config)
