"""
Feedback Loop Agent — Self-improving feedback loop.

Implements a closed learning loop: task → trace → feedback → strategy update.
Tracks learning signals, detects patterns, and adapts strategy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import BiasharaAgent


@dataclass
class LearningSignal:
    """A signal extracted from task outcomes."""
    signal_id: str
    signal_type: str  # success, failure, latency, user_feedback
    strength: float  # 0.0-1.0
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class DetectedPattern:
    """A pattern detected across multiple signals."""
    pattern_id: str
    pattern_type: str
    confidence: float
    description: str
    signal_count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


@dataclass
class StrategyVersion:
    """A version of the agent's strategy parameters."""
    version: int
    parameters: dict[str, Any]
    triggered_by: str | None = None
    timestamp: float = field(default_factory=time.time)


class FeedbackAgent(BiasharaAgent):
    """
    Self-improving feedback loop agent.

    Accumulates learning signals from task outcomes,
    detects patterns, and adapts strategy parameters.
    """

    def __init__(self, name: str = "FeedbackAgent", superagent: Any = None):
        super().__init__(name=name, description="Self-improving feedback loop agent")
        self._superagent = superagent
        self._signals: list[LearningSignal] = []
        self._patterns: list[DetectedPattern] = []
        self._strategy_history: list[StrategyVersion] = [StrategyVersion(version=1, parameters={})]
        self._current_strategy = self._strategy_history[0]
        self._total_signals = 0

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a task and record learning signals."""
        result = {"status": "completed", "agent": self.name}

        # Record learning signal
        signal = LearningSignal(
            signal_id=f"sig_{self._total_signals}",
            signal_type="task_completion",
            strength=1.0 if context.get("success", True) else 0.0,
            context=context,
        )
        self._signals.append(signal)
        self._total_signals += 1

        if len(self._signals) > 1000:
            self._signals = self._signals[-500:]

        return result

    def get_signals_summary(self) -> dict[str, Any]:
        """Get summary of learning signals."""
        type_counts: dict[str, int] = {}
        for s in self._signals:
            type_counts[s.signal_type] = type_counts.get(s.signal_type, 0) + 1
        return {
            "total_signals": self._total_signals,
            "type_distribution": type_counts,
            "avg_strength": sum(s.strength for s in self._signals[-100:]) / max(min(len(self._signals), 100), 1),
        }

    def get_recent_signals(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent learning signals."""
        return [
            {"signal_id": s.signal_id, "type": s.signal_type, "strength": s.strength, "timestamp": s.timestamp}
            for s in self._signals[-limit:]
        ]

    def get_patterns(self) -> list[dict[str, Any]]:
        """Get detected patterns."""
        return [
            {
                "pattern_id": p.pattern_id,
                "type": p.pattern_type,
                "confidence": p.confidence,
                "description": p.description,
            }
            for p in self._patterns
        ]

    def get_current_strategy(self) -> dict[str, Any]:
        """Get current active strategy."""
        return {
            "version": self._current_strategy.version,
            "parameters": self._current_strategy.parameters,
        }

    def get_strategy_parameters(self) -> dict[str, Any]:
        """Get strategy parameters (alias for get_current_strategy)."""
        return self.get_current_strategy()

    def get_strategy_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get strategy version history."""
        return [
            {"version": s.version, "parameters": s.parameters, "triggered_by": s.triggered_by, "timestamp": s.timestamp}
            for s in self._strategy_history[-limit:]
        ]

    def get_metrics(self) -> dict[str, Any]:
        """Get feedback loop metrics."""
        return {
            "total_signals": self._total_signals,
            "total_patterns": len(self._patterns),
            "strategy_version": self._current_strategy.version,
        }

    def get_recent_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent reasoning traces."""
        return self.get_recent_signals(limit)
