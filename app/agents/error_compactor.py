"""
Error Compactor — Factor 9: Compact Errors into Context.

Captures errors with full context, summarizes patterns, and injects
them into agent context for learning. Errors become training signal,
not just log noise.

Mathematical foundation:
- Error fingerprinting via content hashing for deduplication
- Frequency-weighted importance scoring
- Temporal clustering for pattern detection
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    LOW = "low"           # Recoverable, expected
    MEDIUM = "medium"     # Degraded functionality
    HIGH = "high"         # Significant failure
    CRITICAL = "critical" # System-threatening


@dataclass
class CompactedError:
    """A captured error with full context for agent learning."""
    error_type: str
    message: str
    severity: ErrorSeverity
    fingerprint: str  # Deduplication hash
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    agent_name: Optional[str] = None
    action: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    occurrence_count: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    resolution: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    @property
    def age_seconds(self) -> float:
        """Seconds since this error was first seen."""
        return time.time() - self.first_seen

    @property
    def frequency_score(self) -> float:
        """Higher frequency = higher score. Capped at 1.0."""
        return min(1.0, self.occurrence_count / 10.0)

    @property
    def recency_score(self) -> float:
        """Exponential decay based on last occurrence."""
        half_life = 600.0  # 10 minutes
        age = time.time() - self.last_seen
        return 2.0 ** (-age / half_life)

    @property
    def importance_score(self) -> float:
        """Combined severity + frequency + recency score."""
        severity_weight = {
            ErrorSeverity.LOW: 0.25,
            ErrorSeverity.MEDIUM: 0.5,
            ErrorSeverity.HIGH: 0.75,
            ErrorSeverity.CRITICAL: 1.0,
        }[self.severity]
        return (0.4 * severity_weight) + (0.35 * self.frequency_score) + (0.25 * self.recency_score)

    def to_context_dict(self) -> Dict[str, Any]:
        """Convert to a compact dict suitable for agent context."""
        return {
            "error_fingerprint": self.fingerprint[:8],
            "type": self.error_type,
            "message": self.message[:200],  # Truncate long messages
            "severity": self.severity.value,
            "occurrences": self.occurrence_count,
            "action": self.action,
            "resolution": self.resolution,
            "age_minutes": round(self.age_seconds / 60, 1),
        }


@dataclass
class ErrorPattern:
    """A detected pattern across multiple errors."""
    pattern_type: str  # e.g., "repeated_timeout", "cascade_failure"
    description: str
    error_fingerprints: List[str]
    frequency: int
    time_window_seconds: float
    suggested_action: Optional[str] = None
    detected_at: float = field(default_factory=time.time)


class ErrorCompactor:
    """
    Compacts errors into agent-consumable context.

    Features:
    - Error fingerprinting for deduplication
    - Pattern detection (repeated errors, cascades, bursts)
    - Frequency tracking with temporal decay
    - Context injection for agent learning
    - Resolution tracking for feedback loops

    Usage:
        compactor = ErrorCompactor(agent_name="soko_pulse")

        # Capture an error
        compactor.capture(
            error_type="ConnectionTimeout",
            message="Redis connection timed out after 5s",
            severity=ErrorSeverity.HIGH,
            context={"host": "redis://...", "attempt": 3},
            action="process_batch",
        )

        # Get compact errors for agent context
        context_errors = compactor.get_context_errors(max_items=5)

        # Mark resolution
        compactor.resolve(fingerprint, "Switched to in-memory fallback")
    """

    def __init__(
        self,
        agent_name: str,
        max_errors: int = 100,
        decay_interval: float = 3600.0,  # 1 hour
    ):
        self.agent_name = agent_name
        self.max_errors = max_errors
        self.decay_interval = decay_interval

        self._errors: Dict[str, CompactedError] = {}  # fingerprint → error
        self._patterns: List[ErrorPattern] = []
        self._total_captured: int = 0
        self._total_deduplicated: int = 0

        # Temporal window for burst detection
        self._recent_fingerprints: List[Tuple[str, float]] = []

        self._logger = logger.bind(agent=agent_name, component="error_compactor")

    # ── Capture ─────────────────────────────────────────────────────

    def capture(
        self,
        error_type: str,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        stack_trace: Optional[str] = None,
        action: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> CompactedError:
        """
        Capture an error with full context.

        If a matching fingerprint exists, increments the occurrence count
        instead of creating a duplicate.
        """
        fingerprint = self._compute_fingerprint(error_type, message, action)

        if fingerprint in self._errors:
            # Deduplicate: update existing error
            existing = self._errors[fingerprint]
            existing.occurrence_count += 1
            existing.last_seen = time.time()
            if context:
                existing.context.update(context)
            self._total_deduplicated += 1

            self._logger.debug(
                "error_deduplicated",
                fingerprint=fingerprint[:8],
                count=existing.occurrence_count,
            )
            error = existing
        else:
            # New error
            error = CompactedError(
                error_type=error_type,
                message=message,
                severity=severity,
                fingerprint=fingerprint,
                context=context or {},
                stack_trace=stack_trace,
                agent_name=self.agent_name,
                action=action,
                tags=tags or [],
            )
            self._errors[fingerprint] = error
            self._total_captured += 1

            self._logger.info(
                "error_captured",
                error_type=error_type,
                severity=severity.value,
                fingerprint=fingerprint[:8],
                action=action,
            )

        # Track for pattern detection
        self._recent_fingerprints.append((fingerprint, time.time()))
        self._trim_recent()

        # Detect patterns
        self._detect_patterns()

        # Evict old errors if over limit
        self._evict_if_needed()

        return error

    def capture_from_exception(
        self,
        exc: Exception,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        action: Optional[str] = None,
    ) -> CompactedError:
        """Capture an error from a Python exception."""
        import traceback
        return self.capture(
            error_type=type(exc).__name__,
            message=str(exc),
            severity=severity,
            context=context,
            stack_trace=traceback.format_exc(),
            action=action,
        )

    # ── Context Injection ───────────────────────────────────────────

    def get_context_errors(
        self,
        max_items: int = 5,
        min_importance: float = 0.1,
    ) -> List[Dict[str, Any]]:
        """
        Get compacted errors suitable for injection into agent context.

        Returns the most important errors, sorted by importance score.
        """
        # Filter and sort by importance
        errors = [
            e for e in self._errors.values()
            if e.importance_score >= min_importance
        ]
        errors.sort(key=lambda e: e.importance_score, reverse=True)

        return [e.to_context_dict() for e in errors[:max_items]]

    def get_context_patterns(self) -> List[Dict[str, Any]]:
        """Get detected error patterns for agent context."""
        return [
            {
                "pattern": p.pattern_type,
                "description": p.description,
                "frequency": p.frequency,
                "suggested_action": p.suggested_action,
            }
            for p in self._patterns[-5:]  # Last 5 patterns
        ]

    def get_full_context(self) -> Dict[str, Any]:
        """Get full error context for agent think phase."""
        return {
            "recent_errors": self.get_context_errors(max_items=5),
            "error_patterns": self.get_context_patterns(),
            "stats": self.get_stats(),
        }

    # ── Resolution Tracking ─────────────────────────────────────────

    def resolve(self, fingerprint: str, resolution: str) -> bool:
        """Mark an error as resolved with a resolution description."""
        error = self._errors.get(fingerprint)
        if error:
            error.resolution = resolution
            self._logger.info(
                "error_resolved",
                fingerprint=fingerprint[:8],
                resolution=resolution,
            )
            return True
        return False

    def get_resolutions(self) -> List[Dict[str, Any]]:
        """Get all resolved errors with their resolutions (for learning)."""
        return [
            {
                "error_type": e.error_type,
                "fingerprint": e.fingerprint[:8],
                "resolution": e.resolution,
                "occurrences": e.occurrence_count,
            }
            for e in self._errors.values()
            if e.resolution
        ]

    # ── Pattern Detection ───────────────────────────────────────────

    def _detect_patterns(self) -> None:
        """Detect error patterns from recent fingerprints."""
        now = time.time()
        window = 60.0  # 1 minute window for burst detection

        # Count fingerprints in the window
        recent = [
            fp for fp, ts in self._recent_fingerprints
            if now - ts < window
        ]

        if len(recent) < 3:
            return

        # Check for burst (many errors in short time)
        if len(recent) >= 5:
            pattern = ErrorPattern(
                pattern_type="error_burst",
                description=f"{len(recent)} errors in {window:.0f}s window",
                error_fingerprints=list(set(recent)),
                frequency=len(recent),
                time_window_seconds=window,
                suggested_action="Check for upstream service degradation",
            )
            self._add_pattern(pattern)

        # Check for repeated same error
        counts = Counter(recent)
        for fp, count in counts.items():
            if count >= 3:
                error = self._errors.get(fp)
                if error:
                    pattern = ErrorPattern(
                        pattern_type="repeated_error",
                        description=f"'{error.error_type}' repeated {count} times",
                        error_fingerprints=[fp],
                        frequency=count,
                        time_window_seconds=window,
                        suggested_action=f"Investigate root cause of {error.error_type}",
                    )
                    self._add_pattern(pattern)

    def _add_pattern(self, pattern: ErrorPattern) -> None:
        """Add a pattern if not already tracked."""
        # Deduplicate by type + first fingerprint
        key = f"{pattern.pattern_type}:{pattern.error_fingerprints[0]}"
        existing_keys = [
            f"{p.pattern_type}:{p.error_fingerprints[0]}"
            for p in self._patterns
        ]
        if key not in existing_keys:
            self._patterns.append(pattern)
            # Keep only last 20 patterns
            if len(self._patterns) > 20:
                self._patterns = self._patterns[-20:]

    # ── Helpers ─────────────────────────────────────────────────────

    def _compute_fingerprint(
        self,
        error_type: str,
        message: str,
        action: Optional[str],
    ) -> str:
        """Compute a deduplication fingerprint for an error."""
        # Normalize: strip numbers, timestamps, IDs from message
        import re
        normalized = re.sub(r'\d+', 'N', message)
        normalized = re.sub(r'[a-f0-9]{8,}', 'H', normalized)
        raw = f"{error_type}:{normalized}:{action or ''}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _trim_recent(self) -> None:
        """Trim recent fingerprints to last 100 entries."""
        if len(self._recent_fingerprints) > 100:
            self._recent_fingerprints = self._recent_fingerprints[-100:]

    def _evict_if_needed(self) -> None:
        """Evict oldest, lowest-importance errors if over limit."""
        if len(self._errors) <= self.max_errors:
            return

        # Sort by importance (lowest first), evict bottom
        sorted_errors = sorted(
            self._errors.values(),
            key=lambda e: e.importance_score,
        )
        to_evict = len(self._errors) - self.max_errors
        for error in sorted_errors[:to_evict]:
            del self._errors[error.fingerprint]

    # ── Stats ───────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get error compactor statistics."""
        severity_counts = Counter(e.severity.value for e in self._errors.values())
        return {
            "agent": self.agent_name,
            "active_errors": len(self._errors),
            "total_captured": self._total_captured,
            "total_deduplicated": self._total_deduplicated,
            "patterns_detected": len(self._patterns),
            "severity_distribution": dict(severity_counts),
            "resolved_count": sum(1 for e in self._errors.values() if e.resolution),
        }


# ── Type alias for Tuple (used in _recent_fingerprints) ────────────
from typing import Tuple
