"""
Base Autonomous Agent — Extends BiasharaAgent with monitoring and escalation.

All autonomous agents inherit from this base class, which adds:
- Monitoring integration (task recording)
- Escalation integration (automatic escalation on failures)
- Configuration-driven behavior
- Cost tracking per task
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from typing import Any

import structlog

from app.agents.base import (
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)
from app.autonomous.config import AgentConfig
from app.autonomous.escalation import EscalationManager
from app.autonomous.monitoring import AgentMonitor, TaskRecord

logger = structlog.get_logger(__name__)


class AutonomousAgent(BiasharaAgent):
    """
    Base class for autonomous business agents.

    Extends BiasharaAgent with:
    - Monitoring (records every task)
    - Escalation (auto-escalates on failures/confidence issues)
    - Config-driven behavior
    - Cost tracking
    """

    # Subclasses must define these
    CONFIG_NAME: str = "base"
    SUBSCRIBED_EVENTS: list[EventType] = []

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        config: AgentConfig | None = None,
    ):
        super().__init__(name, role, capabilities)
        self._config = config
        self._monitor: AgentMonitor | None = None
        self._escalation: EscalationManager | None = None
        self._consecutive_errors: int = 0
        self._tasks_today: int = 0
        self._cost_today: float = 0.0
        self._last_reset: float = time.time()

        self._auto_logger = logger.bind(agent=name, component="autonomous_agent")

    def set_monitor(self, monitor: AgentMonitor) -> None:
        """Inject the performance monitor."""
        self._monitor = monitor

    def set_escalation(self, escalation: EscalationManager) -> None:
        """Inject the escalation manager."""
        self._escalation = escalation

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Override to add monitoring and escalation around the standard lifecycle."""
        task_id = uuid.uuid4().hex[:12]
        task_start = time.time()

        # Check rate limits
        if self._config and self._tasks_today >= self._config.max_tasks_per_hour:
            self._auto_logger.warning("rate_limit_hit", tasks_today=self._tasks_today)
            return AgentResult(
                success=False,
                error="Rate limit exceeded",
                duration_ms=0,
            )

        # Execute standard lifecycle
        result = await super().handle_event(event)

        # Record monitoring
        duration_ms = (time.time() - task_start) * 1000
        cost_usd = self._estimate_cost(duration_ms)

        if self._monitor:
            self._monitor.record_task(TaskRecord(
                task_id=task_id,
                agent_name=self.name,
                task_type=event.event_type.value,
                success=result.success,
                duration_ms=duration_ms,
                cost_usd=cost_usd,
                error=result.error,
            ))

        if self._escalation:
            self._escalation.record_task()

        # Track daily usage
        self._tasks_today += 1
        self._cost_today += cost_usd

        # Reset daily counters
        if time.time() - self._last_reset > 86400:
            self._tasks_today = 0
            self._cost_today = 0.0
            self._last_reset = time.time()

        # Handle failures
        if not result.success:
            self._consecutive_errors += 1
            await self._check_escalation_triggers(result, duration_ms)
        else:
            self._consecutive_errors = 0

        return result

    async def _check_escalation_triggers(
        self, result: AgentResult, duration_ms: float
    ) -> None:
        """Check if any escalation triggers fire."""
        if not self._escalation or not self._config:
            return

        esc_config = self._config.escalation

        # Consecutive errors
        if self._consecutive_errors >= esc_config.error_threshold:
            await self._escalation.escalate(
                trigger_name="consecutive_errors",
                agent_name=self.name,
                summary=f"{self.name} failed {self._consecutive_errors} consecutive tasks",
                details={
                    "last_error": result.error,
                    "consecutive_errors": self._consecutive_errors,
                },
            )

        # Task timeout
        if duration_ms / 1000 > esc_config.time_threshold_seconds:
            await self._escalation.escalate(
                trigger_name="task_timeout",
                agent_name=self.name,
                summary=f"{self.name} task took {duration_ms/1000:.0f}s (threshold: {esc_config.time_threshold_seconds}s)",
                details={"duration_ms": duration_ms},
            )

        # Cost overrun
        if self._cost_today > self._config.max_cost_per_day_usd:
            await self._escalation.escalate(
                trigger_name="cost_overrun",
                agent_name=self.name,
                summary=f"{self.name} daily cost ${self._cost_today:.2f} exceeds ${self._config.max_cost_per_day_usd}",
                details={"cost_today": self._cost_today},
            )

    def _estimate_cost(self, duration_ms: float) -> float:
        """Estimate the cost of a task based on duration and model."""
        # Rough estimate: ~$0.001 per second of LLM time
        # This would be replaced with actual token counting
        return round(duration_ms / 1000 * 0.001, 6)

    def health_check(self) -> dict[str, Any]:
        """Extended health check with autonomous-specific metrics."""
        base = super().health_check()
        base.update({
            "consecutive_errors": self._consecutive_errors,
            "tasks_today": self._tasks_today,
            "cost_today_usd": round(self._cost_today, 4),
            "config_loaded": self._config is not None,
            "monitor_connected": self._monitor is not None,
            "escalation_connected": self._escalation is not None,
        })
        return base
