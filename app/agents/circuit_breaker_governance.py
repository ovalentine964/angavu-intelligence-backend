"""
Circuit Breaker Governance — Connects circuit breaker state changes
to the Governance swarm for alerting and auto-remediation.

When a circuit breaker opens:
1. Emit a COMPLIANCE_VIOLATION event to the event bus
2. Pause the agent (set status to IDLE, stop polling)
3. Alert AuditAgent and EthicsAgent
4. After recovery_timeout, attempt auto-resume
5. If auto-resume fails, escalate to human

Integration:
    governance = CircuitBreakerGovernance(event_bus, agent_registry)
    # In CircuitBreaker._transition():
    governance.on_state_change(circuit_name, old_state, new_state)

Feature flag: Wire via set_governance() on CircuitBreaker — None means disabled.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CircuitEvent:
    """Record of a circuit breaker state change."""

    agent_name: str
    old_state: str
    new_state: str
    timestamp: float = field(default_factory=time.time)
    failure_count: int = 0
    recovery_timeout_s: float = 30.0
    auto_resumed: bool = False
    escalated: bool = False


class CircuitBreakerGovernance:
    """
    Connects circuit breaker events to governance and auto-remediation.

    Features:
    - Emits compliance events when circuits open
    - Auto-pauses failing agents
    - Attempts auto-recovery after timeout
    - Escalates to governance swarm if recovery fails
    - Tracks circuit breaker history for audit

    Auto-pause after N failures in T seconds:
    - Configurable via set_auto_pause_policy()
    - Default: 5 failures in 60 seconds triggers pause
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        agent_registry: dict[str, Any] | None = None,
    ):
        self._event_bus = event_bus
        self._agent_registry = agent_registry or {}
        self._circuit_events: list[CircuitEvent] = []
        self._max_events = 1000
        self._paused_agents: dict[str, float] = {}  # agent_name → paused_at
        self._auto_resume_tasks: dict[str, asyncio.Task] = {}
        self._logger = logger.bind(component="circuit_governance")

        # Configuration
        self._auto_resume_enabled: bool = True
        self._auto_resume_max_attempts: int = 3
        self._escalate_after_failures: int = 3  # Escalate after N auto-resume failures
        self._auto_resume_failures: dict[str, int] = {}

        # Auto-pause policy: pause agent after N failures in T seconds
        self._auto_pause_threshold: int = 5
        self._auto_pause_window_s: float = 60.0
        self._failure_timestamps: dict[str, list[float]] = {}

        # Half-open exponential backoff
        self._half_open_backoff_base: float = 30.0
        self._half_open_backoff_max: float = 300.0
        self._half_open_attempts: dict[str, int] = {}

    def register_agent(self, agent_name: str, agent: Any) -> None:
        """Register an agent for governance monitoring."""
        self._agent_registry[agent_name] = agent

    def set_auto_pause_policy(
        self,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
    ) -> None:
        """Configure the auto-pause policy."""
        self._auto_pause_threshold = failure_threshold
        self._auto_pause_window_s = window_seconds

    async def on_state_change(
        self,
        agent_name: str,
        old_state: str,
        new_state: str,
        failure_count: int = 0,
        recovery_timeout_s: float = 30.0,
    ) -> None:
        """
        Called when a circuit breaker changes state.

        This is the main hook — call from CircuitBreaker._transition().
        """
        event = CircuitEvent(
            agent_name=agent_name,
            old_state=old_state,
            new_state=new_state,
            failure_count=failure_count,
            recovery_timeout_s=recovery_timeout_s,
        )
        self._circuit_events.append(event)
        if len(self._circuit_events) > self._max_events:
            self._circuit_events = self._circuit_events[-self._max_events :]

        self._logger.warning(
            "circuit_state_change",
            agent=agent_name,
            old_state=old_state,
            new_state=new_state,
            failure_count=failure_count,
        )

        # Export Prometheus metrics
        self._export_metrics(agent_name, old_state, new_state)

        if new_state == "open":
            await self._handle_circuit_open(agent_name, event)
        elif new_state == "closed":
            await self._handle_circuit_closed(agent_name, event)
        elif new_state == "half_open":
            self._handle_half_open(agent_name)

    def record_failure(self, agent_name: str) -> None:
        """
        Record a failure for auto-pause tracking.

        Call this from the execution harness on each agent failure.
        If failures exceed threshold within the window, triggers auto-pause.
        """
        now = time.time()
        if agent_name not in self._failure_timestamps:
            self._failure_timestamps[agent_name] = []

        timestamps = self._failure_timestamps[agent_name]
        timestamps.append(now)

        # Trim old entries outside the window
        cutoff = now - self._auto_pause_window_s
        self._failure_timestamps[agent_name] = [t for t in timestamps if t > cutoff]

        # Check if auto-pause threshold is exceeded
        if len(self._failure_timestamps[agent_name]) >= self._auto_pause_threshold:
            self._logger.warning(
                "auto_pause_triggered",
                agent=agent_name,
                failures=len(self._failure_timestamps[agent_name]),
                window_s=self._auto_pause_window_s,
            )
            # Schedule auto-pause (don't await — fire and forget)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._auto_pause_agent(agent_name))
            except RuntimeError:
                pass

    async def _auto_pause_agent(self, agent_name: str) -> None:
        """Auto-pause an agent that has exceeded failure threshold."""
        await self._pause_agent(agent_name)

        # Emit compliance event
        if self._event_bus:
            try:
                from app.agents.base import AgentEvent, EventType

                violation = AgentEvent(
                    event_type=EventType.COMPLIANCE_VIOLATION,
                    source="CircuitBreakerGovernance",
                    payload={
                        "violation_type": "auto_pause_threshold",
                        "agent": agent_name,
                        "failure_count": len(self._failure_timestamps.get(agent_name, [])),
                        "window_seconds": self._auto_pause_window_s,
                        "severity": "high",
                        "message": (
                            f"Agent {agent_name} auto-paused after "
                            f"{len(self._failure_timestamps.get(agent_name, []))} failures "
                            f"in {self._auto_pause_window_s}s window."
                        ),
                    },
                )
                await self._event_bus.publish(violation)
            except Exception as exc:
                self._logger.debug("auto_pause_event_failed", error=str(exc))

    async def _handle_circuit_open(self, agent_name: str, event: CircuitEvent) -> None:
        """Handle circuit breaker opening."""
        # 1. Emit compliance event
        await self._emit_compliance_event(agent_name, event)

        # 2. Pause the agent
        await self._pause_agent(agent_name)

        # 3. Schedule auto-resume
        if self._auto_resume_enabled:
            self._schedule_auto_resume(agent_name, event.recovery_timeout_s)

    async def _handle_circuit_closed(self, agent_name: str, event: CircuitEvent) -> None:
        """Handle circuit breaker closing (recovery)."""
        # Cancel any pending auto-resume
        if agent_name in self._auto_resume_tasks:
            self._auto_resume_tasks[agent_name].cancel()
            del self._auto_resume_tasks[agent_name]

        # Resume the agent
        await self._resume_agent(agent_name)

        # Reset failure counter
        self._auto_resume_failures[agent_name] = 0
        self._half_open_attempts[agent_name] = 0

        # Clear failure timestamps
        self._failure_timestamps.pop(agent_name, None)

        # Emit recovery event
        if self._event_bus:
            try:
                from app.agents.base import AgentEvent, EventType

                recovery_event = AgentEvent(
                    event_type=EventType.AGENT_HEALTH_CHECK,
                    source="CircuitBreakerGovernance",
                    payload={
                        "status": "recovered",
                        "agent": agent_name,
                        "message": f"Agent {agent_name} circuit breaker closed — recovered",
                    },
                )
                await self._event_bus.publish(recovery_event)
            except Exception as exc:
                self._logger.debug("recovery_event_emit_failed", error=str(exc))

    def _handle_half_open(self, agent_name: str) -> None:
        """Handle half-open state with exponential backoff probing."""
        attempts = self._half_open_attempts.get(agent_name, 0)
        self._half_open_attempts[agent_name] = attempts + 1

        # Compute backoff delay for next probe
        delay = min(
            self._half_open_backoff_base * (2**attempts),
            self._half_open_backoff_max,
        )
        self._logger.info(
            "half_open_probe",
            agent=agent_name,
            attempt=attempts + 1,
            backoff_delay_s=delay,
        )

    async def _emit_compliance_event(self, agent_name: str, event: CircuitEvent) -> None:
        """Emit a compliance violation event for the governance swarm."""
        if not self._event_bus:
            return

        try:
            from app.agents.base import AgentEvent, EventType

            violation = AgentEvent(
                event_type=EventType.COMPLIANCE_VIOLATION,
                source="CircuitBreakerGovernance",
                payload={
                    "violation_type": "agent_failure_threshold",
                    "agent": agent_name,
                    "failure_count": event.failure_count,
                    "old_state": event.old_state,
                    "new_state": event.new_state,
                    "severity": "high" if event.failure_count >= 10 else "medium",
                    "message": (
                        f"Agent {agent_name} circuit breaker OPENED after "
                        f"{event.failure_count} consecutive failures. "
                        f"Agent has been paused. Auto-resume in {event.recovery_timeout_s}s."
                    ),
                    "recommended_action": "Investigate root cause before manual resume",
                },
            )
            await self._event_bus.publish(violation)
            self._logger.info(
                "compliance_event_emitted",
                agent=agent_name,
                failure_count=event.failure_count,
            )
        except Exception as exc:
            self._logger.error("compliance_event_failed", error=str(exc))

    async def _pause_agent(self, agent_name: str) -> None:
        """Pause an agent (stop its polling loop)."""
        agent = self._agent_registry.get(agent_name)
        if agent and hasattr(agent, "stop"):
            try:
                await agent.stop()
                self._paused_agents[agent_name] = time.time()
                self._logger.info("agent_paused", agent=agent_name)

                # Update Prometheus
                try:
                    from prometheus_client import Gauge

                    from app.infrastructure.metrics import _registry

                    if not hasattr(self, "_prom_agent_paused"):
                        self._prom_agent_paused = Gauge(
                            "angavu_agent_paused",
                            "Whether an agent is paused (1) or active (0)",
                            ["agent_name"],
                            registry=_registry,
                        )
                    self._prom_agent_paused.labels(agent_name=agent_name).set(1)
                except Exception:
                    pass

            except Exception as exc:
                self._logger.error("agent_pause_failed", agent=agent_name, error=str(exc))

    async def _resume_agent(self, agent_name: str) -> None:
        """Resume a paused agent."""
        if agent_name not in self._paused_agents:
            return

        agent = self._agent_registry.get(agent_name)
        if agent and hasattr(agent, "start"):
            try:
                await agent.start()
                del self._paused_agents[agent_name]
                self._logger.info("agent_resumed", agent=agent_name)

                # Update Prometheus
                try:
                    if hasattr(self, "_prom_agent_paused"):
                        self._prom_agent_paused.labels(agent_name=agent_name).set(0)
                except Exception:
                    pass

            except Exception as exc:
                self._logger.error("agent_resume_failed", agent=agent_name, error=str(exc))

    def _schedule_auto_resume(self, agent_name: str, delay_s: float) -> None:
        """Schedule an auto-resume attempt after delay."""
        if agent_name in self._auto_resume_tasks:
            self._auto_resume_tasks[agent_name].cancel()

        async def _auto_resume():
            await asyncio.sleep(delay_s)
            failures = self._auto_resume_failures.get(agent_name, 0)

            if failures >= self._escalate_after_failures:
                self._logger.error(
                    "auto_resume_escalating",
                    agent=agent_name,
                    failures=failures,
                )
                await self._escalate_to_governance(agent_name)
                return

            self._logger.info(
                "auto_resume_attempting",
                agent=agent_name,
                attempt=failures + 1,
            )

            # Try to resume — the circuit breaker will handle
            # re-evaluation on the next call
            await self._resume_agent(agent_name)
            self._auto_resume_failures[agent_name] = failures + 1

        try:
            loop = asyncio.get_running_loop()
            self._auto_resume_tasks[agent_name] = loop.create_task(_auto_resume())
        except RuntimeError:
            pass

    async def _escalate_to_governance(self, agent_name: str) -> None:
        """Escalate to governance swarm when auto-resume fails repeatedly."""
        if not self._event_bus:
            return

        try:
            from app.agents.base import AgentEvent, EventType

            escalation = AgentEvent(
                event_type=EventType.SECURITY_INCIDENT,
                source="CircuitBreakerGovernance",
                payload={
                    "incident_type": "agent_persistent_failure",
                    "agent": agent_name,
                    "auto_resume_failures": self._auto_resume_failures.get(agent_name, 0),
                    "severity": "critical",
                    "message": (
                        f"Agent {agent_name} has failed to recover after "
                        f"{self._auto_resume_failures.get(agent_name, 0)} auto-resume attempts. "
                        f"MANUAL INTERVENTION REQUIRED."
                    ),
                    "recommended_action": "Manual investigation and restart required",
                },
            )
            await self._event_bus.publish(escalation)
            self._logger.critical(
                "governance_escalation",
                agent=agent_name,
                failures=self._auto_resume_failures.get(agent_name, 0),
            )

            # Update Prometheus
            try:
                from prometheus_client import Counter

                if not hasattr(self, "_prom_escalations"):
                    self._prom_escalations = Counter(
                        "angavu_governance_escalations_total",
                        "Total governance escalations",
                        ["agent_name", "severity"],
                    )
                self._prom_escalations.labels(
                    agent_name=agent_name,
                    severity="critical",
                ).inc()
            except Exception:
                pass

        except Exception as exc:
            self._logger.error("escalation_emit_failed", error=str(exc))

    def _export_metrics(
        self,
        agent_name: str,
        old_state: str,
        new_state: str,
    ) -> None:
        """Export circuit breaker state change metrics to Prometheus."""
        try:
            from prometheus_client import Counter, Gauge

            if not hasattr(self, "_prom_state_changes"):
                self._prom_state_changes = Counter(
                    "angavu_circuit_state_changes_total",
                    "Total circuit breaker state changes",
                    ["agent_name", "from_state", "to_state"],
                )
                self._prom_open_duration = Gauge(
                    "angavu_circuit_open_duration_seconds",
                    "How long a circuit has been open",
                    ["agent_name"],
                )
            self._prom_state_changes.labels(
                agent_name=agent_name,
                from_state=old_state,
                to_state=new_state,
            ).inc()

            if new_state == "open":
                self._prom_open_duration.labels(agent_name=agent_name).set(0)
            elif old_state == "open":
                # Circuit was open, now closing — record duration would need tracking
                pass
        except Exception:
            pass

    # ── Manual Controls ─────────────────────────────────────────────

    async def manual_resume(self, agent_name: str) -> bool:
        """Manually resume a paused agent (bypasses circuit breaker)."""
        await self._resume_agent(agent_name)
        self._auto_resume_failures[agent_name] = 0
        return True

    def get_paused_agents(self) -> list[str]:
        """Get list of currently paused agents."""
        return list(self._paused_agents.keys())

    def get_circuit_history(
        self,
        agent_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get circuit breaker event history."""
        events = self._circuit_events
        if agent_name:
            events = [e for e in events if e.agent_name == agent_name]
        return [
            {
                "agent": e.agent_name,
                "old_state": e.old_state,
                "new_state": e.new_state,
                "failure_count": e.failure_count,
                "timestamp": e.timestamp,
                "auto_resumed": e.auto_resumed,
            }
            for e in events[-limit:]
        ]
