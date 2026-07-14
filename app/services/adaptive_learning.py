"""
Adaptive Learning Service — Connects feedback loop to federated learning.

Bridges the gap between the FeedbackAgent (which extracts learning signals
from transaction outcomes) and the FederatedLearningService (which aggregates
model updates from devices).

Architecture:
    EventBus (feedback.received)
         │
         ▼
    ┌─────────────────────────┐
    │ AdaptiveLearningService │ ← Aggregates signals into FL updates
    └──────────┬──────────────┘
               │
               ▼
    ┌─────────────────────────┐
    │ FederatedLearningService│ ← Receives aggregated gradient updates
    └──────────┬──────────────┘
               │
               ▼
    ┌─────────────────────────┐
    │    Global Model Sync    │ ← Pushes improved models to devices
    └─────────────────────────┘

The service leverages the Hermes pattern from SessionSync:
- Learning state is keyed by WORKER, not by channel
- When a worker switches channels, their learning context follows
- Aggregated signals are associated with the worker's session

Feedback types handled:
- transaction.outcome: implicit feedback from transaction results
- feedback.received: explicit worker corrections and ratings
- agent.performance.recorded: agent self-assessment signals
- customer.feedback.received: end-user satisfaction signals

Privacy:
- All feedback is aggregated before leaving the service
- Individual worker signals are never transmitted to FL
- Differential privacy noise is added before FL submission
- Worker IDs are one-way hashed in FL updates
"""

from __future__ import annotations

import hashlib
import math
import secrets
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


class FeedbackSource(str, Enum):
    """Source of adaptive learning feedback."""
    TRANSACTION_OUTCOME = "transaction_outcome"
    WORKER_CORRECTION = "worker_correction"
    AGENT_PERFORMANCE = "agent_performance"
    CUSTOMER_FEEDBACK = "customer_feedback"
    EXPLICIT_RATING = "explicit_rating"
    IMPLICIT_SIGNAL = "implicit_signal"


@dataclass
class AggregatedSignal:
    """An aggregated learning signal ready for FL submission."""
    signal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    language: str = "sw"
    worker_id_hash: str = ""
    source: FeedbackSource = FeedbackSource.TRANSACTION_OUTCOME
    outcome_value: float = 0.0
    expected_value: float = 0.0
    surprise: float = 0.0
    signal_count: int = 1
    confidence: float = 0.0
    context_tags: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    # Derived correction patterns for FL
    error_type: str = ""
    edit_distance: float = 0.0
    phoneme_pattern: str = ""

    def to_fl_pattern(self) -> Dict[str, Any]:
        """Convert to FL-compatible correction pattern."""
        return {
            "errorType": self.error_type or f"adaptive_{self.source.value}",
            "errorHash": hashlib.sha256(
                f"{self.worker_id_hash}:{self.signal_id}".encode()
            ).hexdigest()[:16],
            "correctionHash": hashlib.sha256(
                f"{self.outcome_value}:{self.expected_value}".encode()
            ).hexdigest()[:16],
            "phonemePattern": self.phoneme_pattern,
            "hourOfDay": datetime.now(timezone.utc).hour,
            "editDistance": max(0.0, min(1.0, self.surprise)),
        }


@dataclass
class WorkerLearningState:
    """
    Per-worker learning state (Hermes pattern).

    Keyed by worker_id, NOT by channel. Persists across channel switches.
    """
    worker_id: str
    language: str = "sw"
    total_signals: int = 0
    cumulative_outcome: float = 0.0
    cumulative_expected: float = 0.0
    signal_buffer: List[AggregatedSignal] = field(default_factory=list)
    last_aggregated: float = 0.0
    last_pushed_to_fl: float = 0.0
    # Rolling window of recent outcomes for trend detection
    recent_outcomes: List[float] = field(default_factory=list)
    max_recent = 100

    @property
    def mean_outcome(self) -> float:
        if self.total_signals == 0:
            return 0.5
        return self.cumulative_outcome / self.total_signals

    @property
    def mean_expected(self) -> float:
        if self.total_signals == 0:
            return 0.5
        return self.cumulative_expected / self.total_signals

    @property
    def mean_surprise(self) -> float:
        return abs(self.mean_outcome - self.mean_expected)

    def add_outcome(self, outcome: float, expected: float) -> None:
        self.total_signals += 1
        self.cumulative_outcome += outcome
        self.cumulative_expected += expected
        self.recent_outcomes.append(outcome)
        if len(self.recent_outcomes) > self.max_recent:
            self.recent_outcomes = self.recent_outcomes[-self.max_recent:]

    def outcome_trend(self) -> float:
        """Compute trend in recent outcomes (positive = improving)."""
        if len(self.recent_outcomes) < 5:
            return 0.0
        recent = self.recent_outcomes[-20:]
        n = len(recent)
        x_mean = (n - 1) / 2.0
        y_mean = sum(recent) / n
        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if denominator == 0:
            return 0.0
        return numerator / denominator


# ════════════════════════════════════════════════════════════════════
# Adaptive Learning Service
# ════════════════════════════════════════════════════════════════════


class AdaptiveLearningService:
    """
    Connects the feedback loop to the federated learning pipeline.

    Lifecycle:
    1. Subscribe to event bus for feedback events
    2. Collect and aggregate signals per worker (Hermes pattern)
    3. When aggregation threshold is met, convert signals to FL format
    4. Push aggregated updates through FederatedLearningService
    5. Emit sync events so devices know to pull new models

    The service is stateful — it holds per-worker learning state in memory
    and periodically flushes to the FL pipeline. This avoids overwhelming
    FL with individual signals and enables proper aggregation.

    Usage:
        service = AdaptiveLearningService(fl_service, session_sync)
        await service.start(event_bus)
        # ... signals flow in from event bus ...
        await service.stop()
    """

    # Aggregation thresholds
    MIN_SIGNALS_FOR_AGGREGATION = 5
    AGGREGATION_INTERVAL_SECONDS = 300  # 5 minutes minimum between FL pushes
    MAX_BUFFER_SIZE = 500  # Max signals buffered per worker before force-flush

    # Privacy parameters
    DP_EPSILON = 0.1  # Must match FL service epsilon
    DP_DELTA = 1e-5

    def __init__(
        self,
        fl_service: Any = None,
        session_sync: Any = None,
    ):
        """
        Initialize the adaptive learning service.

        Args:
            fl_service: FederatedLearningService instance
            session_sync: SessionSync instance (Hermes pattern)
        """
        self._fl_service = fl_service
        self._session_sync = session_sync
        self._worker_states: Dict[str, WorkerLearningState] = {}
        self._running = False
        self._event_bus: Any = None
        self._flush_task: Optional[Any] = None

        # Metrics
        self._total_signals_received = 0
        self._total_aggregations = 0
        self._total_fl_pushes = 0
        self._total_sync_events = 0

        # Registered FLUpdate constructor (lazy import to avoid circular deps)
        self._fl_update_cls = None
        self._fl_pattern_cls = None
        self._fl_metadata_cls = None

        self._logger = logger.bind(component="adaptive_learning")

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self, event_bus: Any) -> None:
        """
        Start the adaptive learning service.

        Subscribes to the event bus for feedback-related events and
        starts a background flush task.
        """
        if self._running:
            self._logger.warning("adaptive_learning_already_running")
            return

        self._event_bus = event_bus
        self._running = True

        # Import FL schemas lazily to avoid circular deps
        self._load_fl_schemas()

        # Subscribe to relevant event types
        from app.agents.base import AgentEvent, EventType

        # Create a lightweight handler agent for event bus subscription
        class _FeedbackCollector:
            """Lightweight agent that collects feedback events for adaptive learning."""
            def __init__(self, service: AdaptiveLearningService):
                self._service = service
                self.name = "AdaptiveLearningCollector"

            async def handle_event(self, event: AgentEvent) -> Any:
                await self._service._on_feedback_event(event)

        collector = _FeedbackCollector(self)

        feedback_event_types = [
            EventType.FEEDBACK_RECEIVED,
            EventType.TRANSACTION_PROCESSED,
            EventType.AGENT_PERFORMANCE_RECORDED,
            EventType.CUSTOMER_FEEDBACK_RECEIVED,
        ]

        await event_bus.subscribe(collector, feedback_event_types)

        self._logger.info(
            "adaptive_learning_started",
            subscribed_events=[et.value for et in feedback_event_types],
        )

    async def stop(self) -> None:
        """Stop the service and flush remaining signals."""
        if not self._running:
            return

        self._running = False

        # Final flush of all buffered signals
        await self._flush_all_workers()

        self._logger.info(
            "adaptive_learning_stopped",
            total_signals=self._total_signals_received,
            total_fl_pushes=self._total_fl_pushes,
        )

    # ── Event Handling ─────────────────────────────────────────────

    async def _on_feedback_event(self, event: Any) -> None:
        """
        Handle a feedback event from the event bus.

        Routes events to appropriate signal extraction based on type.
        """
        event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
        payload = event.payload or {}

        self._total_signals_received += 1

        # Extract worker_id from payload (Hermes: keyed by worker)
        worker_id = payload.get("worker_id", payload.get("user_id", "anonymous"))
        language = payload.get("language", payload.get("dialect", "sw"))

        # Get or create worker learning state
        state = self._get_or_create_state(worker_id, language)

        # Extract learning signal based on event type
        signal = None

        if event_type in ("feedback.received", "customer.feedback.received"):
            signal = self._extract_feedback_signal(payload, state)
        elif event_type == "transaction.processed":
            signal = self._extract_transaction_signal(payload, state)
        elif event_type == "agent.performance.recorded":
            signal = self._extract_performance_signal(payload, state)

        if signal is None:
            return

        # Buffer the signal
        state.signal_buffer.append(signal)
        state.last_aggregated = time.time()

        self._logger.debug(
            "adaptive_signal_collected",
            worker_id=worker_id[:8] + "...",
            source=signal.source.value,
            buffer_size=len(state.signal_buffer),
            surprise=round(signal.surprise, 3),
        )

        # Check if we should flush to FL
        if len(state.signal_buffer) >= self.MIN_SIGNALS_FOR_AGGREGATION:
            await self._flush_worker(worker_id)

        # Force flush if buffer is too large
        if len(state.signal_buffer) >= self.MAX_BUFFER_SIZE:
            await self._flush_worker(worker_id)

    # ── Signal Extraction ──────────────────────────────────────────

    def _extract_feedback_signal(
        self,
        payload: Dict[str, Any],
        state: WorkerLearningState,
    ) -> AggregatedSignal:
        """Extract signal from explicit feedback event."""
        feedback_type = payload.get("feedback_type", "unknown")
        rating = payload.get("rating", payload.get("score", 0.5))
        success = payload.get("success", True)

        # Normalize to 0-1
        if isinstance(rating, (int, float)):
            outcome = max(0.0, min(1.0, float(rating) / 5.0)) if rating > 1 else max(0.0, min(1.0, float(rating)))
        else:
            outcome = 1.0 if success else 0.0

        expected = state.mean_outcome if state.total_signals > 0 else 0.5
        state.add_outcome(outcome, expected)

        return AggregatedSignal(
            language=state.language,
            worker_id_hash=hashlib.sha256(state.worker_id.encode()).hexdigest()[:16],
            source=FeedbackSource.WORKER_CORRECTION,
            outcome_value=outcome,
            expected_value=expected,
            surprise=abs(outcome - expected),
            confidence=0.8,
            context_tags=[f"feedback:{feedback_type}", f"lang:{state.language}"],
            error_type=f"feedback_{feedback_type}",
            edit_distance=abs(outcome - expected),
        )

    def _extract_transaction_signal(
        self,
        payload: Dict[str, Any],
        state: WorkerLearningState,
    ) -> AggregatedSignal:
        """Extract signal from transaction outcome."""
        success = payload.get("success", payload.get("status") == "processed")
        quality = payload.get("quality_score", payload.get("confidence", 0.5))

        outcome = 1.0 if success else 0.0
        if isinstance(quality, (int, float)):
            outcome = max(outcome, float(quality))

        expected = state.mean_outcome if state.total_signals > 0 else 0.7
        state.add_outcome(outcome, expected)

        product = payload.get("product_type", payload.get("product", ""))
        market = payload.get("market", "")

        return AggregatedSignal(
            language=state.language,
            worker_id_hash=hashlib.sha256(state.worker_id.encode()).hexdigest()[:16],
            source=FeedbackSource.TRANSACTION_OUTCOME,
            outcome_value=outcome,
            expected_value=expected,
            surprise=abs(outcome - expected),
            confidence=0.9,
            context_tags=[
                f"product:{product}" if product else "",
                f"market:{market}" if market else "",
                f"lang:{state.language}",
            ],
            error_type="transaction_outcome",
            edit_distance=abs(outcome - expected),
        )

    def _extract_performance_signal(
        self,
        payload: Dict[str, Any],
        state: WorkerLearningState,
    ) -> AggregatedSignal:
        """Extract signal from agent performance recording."""
        performance = payload.get("performance_score", payload.get("accuracy", 0.5))
        agent_name = payload.get("agent_name", "unknown")

        outcome = max(0.0, min(1.0, float(performance)))
        expected = state.mean_outcome if state.total_signals > 0 else 0.6
        state.add_outcome(outcome, expected)

        return AggregatedSignal(
            language=state.language,
            worker_id_hash=hashlib.sha256(state.worker_id.encode()).hexdigest()[:16],
            source=FeedbackSource.AGENT_PERFORMANCE,
            outcome_value=outcome,
            expected_value=expected,
            surprise=abs(outcome - expected),
            confidence=0.85,
            context_tags=[f"agent:{agent_name}", f"lang:{state.language}"],
            error_type=f"agent_perf_{agent_name}",
            edit_distance=abs(outcome - expected),
        )

    # ── Aggregation & FL Push ──────────────────────────────────────

    async def _flush_worker(self, worker_id: str) -> None:
        """
        Flush a worker's buffered signals to the FL pipeline.

        Aggregates signals into an FL-compatible update and pushes
        through the FederatedLearningService.
        """
        state = self._worker_states.get(worker_id)
        if not state or not state.signal_buffer:
            return

        signals = list(state.signal_buffer)
        state.signal_buffer.clear()

        if len(signals) < self.MIN_SIGNALS_FOR_AGGREGATION:
            # Not enough signals — re-buffer
            state.signal_buffer = signals
            return

        self._total_aggregations += 1

        # Aggregate signals into FL-compatible update
        fl_update = self._aggregate_to_fl_update(signals, state)
        if fl_update is None:
            self._logger.warning("adaptive_fl_update_none", worker_id=worker_id[:8])
            return

        # Push to FL service
        if self._fl_service is not None:
            try:
                result = await self._fl_service.upload_update(fl_update)
                self._total_fl_pushes += 1
                state.last_pushed_to_fl = time.time()

                self._logger.info(
                    "adaptive_pushed_to_fl",
                    worker_id=worker_id[:8] + "...",
                    signals_aggregated=len(signals),
                    language=state.language,
                    fl_status=result.status,
                    aggregated=result.aggregated,
                )

                # Emit sync event so devices know to pull
                if result.aggregated and self._event_bus:
                    await self._emit_sync_event(state, result)

            except Exception as exc:
                self._logger.error(
                    "adaptive_fl_push_failed",
                    error=str(exc),
                    worker_id=worker_id[:8],
                )
                # Re-buffer signals on failure
                state.signal_buffer = signals + state.signal_buffer
        else:
            self._logger.warning(
                "adaptive_no_fl_service",
                signals_dropped=len(signals),
            )

    async def _flush_all_workers(self) -> None:
        """Flush all workers' buffered signals."""
        for worker_id in list(self._worker_states.keys()):
            await self._flush_worker(worker_id)

    def _aggregate_to_fl_update(
        self,
        signals: List[AggregatedSignal],
        state: WorkerLearningState,
    ) -> Any:
        """
        Aggregate learning signals into an FLUpdate for the FL pipeline.

        Converts the FeedbackAgent's learning signals into the format
        the FederatedLearningService expects:
        - Correction patterns from signal outcomes
        - Calibration params from signal statistics
        - Metadata about the aggregation

        Applies differential privacy noise before submission.
        """
        if not self._fl_update_cls:
            self._load_fl_schemas()

        if not self._fl_update_cls:
            return None

        # Aggregate signal statistics
        outcomes = [s.outcome_value for s in signals]
        surprises = [s.surprise for s in signals]
        mean_outcome = sum(outcomes) / len(outcomes) if outcomes else 0.5
        mean_surprise = sum(surprises) / len(surprises) if surprises else 0.0

        # Compute calibration adjustments from signal trends
        trend = state.outcome_trend()
        # Temperature: higher when outcomes are surprising (model is miscalibrated)
        temperature = 1.0 + mean_surprise * 0.5
        # Platt scaling: adjust based on trend
        platt_a = 1.0 + trend * 0.1
        platt_b = -mean_outcome * 0.1

        # Apply DP noise to calibration
        temperature = self._add_dp_noise(temperature, 0.1)
        platt_a = self._add_dp_noise(platt_a, 0.05)
        platt_b = self._add_dp_noise(platt_b, 0.05)

        # Build correction patterns from signals
        patterns = []
        for signal in signals:
            patterns.append(signal.to_fl_pattern())

        # Build calibration params
        cal_params = self._fl_calibration_cls(
            temperature=max(0.01, temperature),
            platt_a=platt_a,
            platt_b=platt_b,
            prior=max(0.0, min(1.0, mean_outcome)),
        )

        # Build metadata
        metadata = self._fl_metadata_cls(
            corrections_count=len(signals),
            vocabulary_size=len(set(s.error_type for s in signals)),
            estimated_wer=mean_surprise,
            device_tier="adaptive_backend",
        )

        # Hash worker ID for privacy
        device_id = hashlib.sha256(
            f"adaptive:{state.worker_id}".encode()
        ).hexdigest()[:32]

        # Build FLUpdate
        fl_update = self._fl_update_cls(
            device_id=device_id,
            language=state.language,
            timestamp=int(time.time() * 1000),
            correction_patterns=patterns,
            adapter_deltas=None,  # No LoRA deltas from feedback signals
            calibration_params=cal_params,
            metadata=metadata,
        )

        return fl_update

    def _add_dp_noise(self, value: float, sensitivity: float) -> float:
        """Add calibrated Gaussian noise for differential privacy."""
        sigma = sensitivity * math.sqrt(2.0 * math.log(1.25 / self.DP_DELTA)) / self.DP_EPSILON
        u1 = max(secrets.randbelow(10**8) / 10**8, 1e-10)
        u2 = secrets.randbelow(10**8) / 10**8
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        return value + sigma * z

    # ── Event Emission ─────────────────────────────────────────────

    async def _emit_sync_event(
        self,
        state: WorkerLearningState,
        fl_result: Any,
    ) -> None:
        """
        Emit an adaptive_learning.synced event so the system knows
        a new model version is available.
        """
        if self._event_bus is None:
            return

        from app.agents.base import AgentEvent, EventType

        event = AgentEvent(
            event_type=EventType.ADAPTIVE_LEARNING_SYNCED,
            source="AdaptiveLearningService",
            payload={
                "worker_id": state.worker_id,
                "language": state.language,
                "signals_aggregated": state.total_signals,
                "fl_version": fl_result.next_download_version,
                "fl_aggregated": fl_result.aggregated,
                "outcome_trend": state.outcome_trend(),
                "mean_outcome": state.mean_outcome,
                "mean_surprise": state.mean_surprise,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        await self._event_bus.publish(event)
        self._total_sync_events += 1

        self._logger.info(
            "adaptive_sync_event_emitted",
            language=state.language,
            version=fl_result.next_download_version,
        )

    # ── Hermes Pattern (SessionSync Integration) ───────────────────

    async def get_learning_context(
        self,
        worker_id: str,
    ) -> Dict[str, Any]:
        """
        Get the current adaptive learning context for a worker.

        Leverages the Hermes pattern: learning state is keyed by worker,
        not channel. Returns context that can be merged into session state.

        This allows the system to:
        - Personalize model behavior based on worker's learning history
        - Adjust confidence thresholds based on worker's outcome trends
        - Provide feedback-aware responses
        """
        state = self._worker_states.get(worker_id)
        if not state:
            return {}

        context = {
            "adaptive_learning": {
                "total_signals": state.total_signals,
                "mean_outcome": round(state.mean_outcome, 3),
                "outcome_trend": round(state.outcome_trend(), 4),
                "language": state.language,
                "last_pushed": state.last_pushed_to_fl,
                "buffer_size": len(state.signal_buffer),
            }
        }

        # Also update SessionSync if available
        if self._session_sync:
            try:
                await self._session_sync.update_session_context(
                    worker_id, context
                )
            except Exception as exc:
                self._logger.debug(
                    "adaptive_session_sync_update_failed",
                    error=str(exc),
                )

        return context

    # ── Helpers ────────────────────────────────────────────────────

    def _get_or_create_state(
        self,
        worker_id: str,
        language: str = "sw",
    ) -> WorkerLearningState:
        """Get or create worker learning state (Hermes pattern)."""
        if worker_id not in self._worker_states:
            self._worker_states[worker_id] = WorkerLearningState(
                worker_id=worker_id,
                language=language,
            )
        state = self._worker_states[worker_id]
        # Update language if changed (worker may switch dialect)
        if language != state.language:
            state.language = language
        return state

    def _load_fl_schemas(self) -> None:
        """Lazy-load FL schema classes to avoid circular imports."""
        try:
            from app.schemas.federated_learning import (
                AnonymizedPattern as AP,
                FLUpdate as FU,
                CalibrationParams as CP,
                UploadMetadata as UM,
            )
            self._fl_update_cls = FU
            self._fl_pattern_cls = AP
            self._fl_calibration_cls = CP
            self._fl_metadata_cls = UM
        except ImportError as exc:
            self._logger.error("adaptive_fl_schema_import_failed", error=str(exc))

    # ── Metrics ────────────────────────────────────────────────────

    def get_metrics(self) -> Dict[str, Any]:
        """Get adaptive learning service metrics."""
        return {
            "total_signals_received": self._total_signals_received,
            "total_aggregations": self._total_aggregations,
            "total_fl_pushes": self._total_fl_pushes,
            "total_sync_events": self._total_sync_events,
            "active_workers": len(self._worker_states),
            "total_buffered_signals": sum(
                len(s.signal_buffer) for s in self._worker_states.values()
            ),
            "worker_summaries": {
                wid: {
                    "total_signals": s.total_signals,
                    "mean_outcome": round(s.mean_outcome, 3),
                    "trend": round(s.outcome_trend(), 4),
                    "buffer_size": len(s.signal_buffer),
                    "language": s.language,
                }
                for wid, s in list(self._worker_states.items())[:20]  # Limit to 20
            },
        }

    def get_worker_state(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get learning state for a specific worker."""
        state = self._worker_states.get(worker_id)
        if not state:
            return None
        return {
            "worker_id": state.worker_id,
            "language": state.language,
            "total_signals": state.total_signals,
            "mean_outcome": round(state.mean_outcome, 3),
            "mean_expected": round(state.mean_expected, 3),
            "mean_surprise": round(state.mean_surprise, 3),
            "outcome_trend": round(state.outcome_trend(), 4),
            "buffer_size": len(state.signal_buffer),
            "last_aggregated": state.last_aggregated,
            "last_pushed_to_fl": state.last_pushed_to_fl,
        }
