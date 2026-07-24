"""
Feedback Loop Agent — Learns from outcomes and adapts strategy.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class FeedbackAgent:
    """
    Feedback loop agent that tracks outcomes and adapts.

    Monitors signals, detects patterns, and adjusts strategy.
    """

    def __init__(self, name: str = "FeedbackAgent", superagent=None):
        self.name = name
        self._superagent = superagent
        self._signals: list[dict] = []
        self._patterns: list[dict] = []
        self._strategy_version = 1
        self._strategy_history: list[dict] = []

    async def execute(self, context: dict) -> dict:
        """Process feedback and adapt strategy."""
        signal = {
            "task": context.get("task"),
            "outcome": context.get("outcome", "unknown"),
            "timestamp": context.get("timestamp"),
        }
        self._signals.append(signal)

        # Detect patterns
        if len(self._signals) >= 5:
            pattern = {
                "signal_count": len(self._signals),
                "success_rate": sum(
                    1 for s in self._signals[-10:] if s.get("outcome") == "success"
                ) / min(len(self._signals), 10),
            }
            self._patterns.append(pattern)

        return {
            "signals_processed": len(self._signals),
            "patterns_detected": len(self._patterns),
            "strategy_version": self._strategy_version,
        }

    def get_signals(self) -> list[dict]:
        """Get learning signals summary."""
        return self._signals[-50:]

    def get_patterns(self) -> list[dict]:
        """Get detected patterns."""
        return self._patterns

    def get_strategy(self) -> dict:
        """Get current strategy."""
        return {
            "version": self._strategy_version,
            "signals_analyzed": len(self._signals),
            "patterns_found": len(self._patterns),
        }

    def get_history(self) -> list[dict]:
        """Get strategy version history."""
        return self._strategy_history
