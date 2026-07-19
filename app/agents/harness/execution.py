"""
Agent Execution Harness — Unified control plane for all agent calls.

Wraps every agent execution with:
- Timeout enforcement (configurable per agent)
- Retry with exponential backoff
- Circuit breaker (prevents cascading failures)
- Metrics collection (latency, success rate, token usage)
- Cost attribution (per agent, per user)

Usage:
    harness = AgentExecutionHarness(timeout_s=30, max_retries=2)
    result = await harness.execute(agent, event)

Integration:
    In BiasharaAgent.handle_event(), route through harness:
        if self._harness:
            return await self._harness.execute(self, event)

This is the single most important harness component — it transforms
ad-hoc error handling into a systematic control plane.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.agents.base import AgentEvent, AgentResult, BiasharaAgent

logger = structlog.get_logger(__name__)

# Prompt guard integration (feature-flagged)
try:
    from app.security.prompt_guard import (
        PROMPT_GUARD_ENABLED,
        PROMPT_GUARD_STRICT,
        PromptGuard,
        SecureMessageHandler,
        get_prompt_guard,
    )
    _PROMPT_GUARD_AVAILABLE = True
except ImportError:
    _PROMPT_GUARD_AVAILABLE = False
    PROMPT_GUARD_ENABLED = False


# ════════════════════════════════════════════════════════════════════
# Circuit Breaker
# ════════════════════════════════════════════════════════════════════


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal operation — requests pass through
    OPEN = "open"            # Failing — requests are rejected immediately
    HALF_OPEN = "half_open"  # Testing — one request allowed through to probe


class CircuitBreaker:
    """
    Prevents cascading failures by stopping calls to failing agents.

    States:
        CLOSED → (failures >= threshold) → OPEN
        OPEN → (recovery timeout elapsed) → HALF_OPEN
        HALF_OPEN → (successes >= half_open_max) → CLOSED
        HALF_OPEN → (failure) → OPEN

    Each agent gets its own circuit breaker, so one agent's failure
    doesn't affect others.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_s: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout_s = recovery_timeout_s
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._last_state_change: float = time.time()
        self._half_open_calls = 0

        self._logger = logger.bind(circuit_breaker=name)

    @property
    def state(self) -> CircuitState:
        """Get current state, auto-transitioning from OPEN if recovery elapsed."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time > self._recovery_timeout_s:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (should reject calls)."""
        return self.state == CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._half_open_max_calls:
                self._transition(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)  # Decay failures

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._failure_threshold:
                self._transition(CircuitState.OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old = self._state
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0

        self._logger.info(
            "circuit_state_change",
            old_state=old.value,
            new_state=new_state.value,
            failure_count=self._failure_count,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for monitoring API."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "recovery_timeout_s": self._recovery_timeout_s,
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
        }


# ════════════════════════════════════════════════════════════════════
# Execution Metrics
# ════════════════════════════════════════════════════════════════════


@dataclass
class ExecutionRecord:
    """Record of a single agent execution through the harness."""
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = ""
    event_type: str = ""
    user_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    duration_ms: float = 0.0
    success: bool = False
    error: Optional[str] = None
    attempt: int = 1
    circuit_state: str = "closed"
    timeout_used_s: float = 30.0
    # Cost tracking
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_used: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "agent_name": self.agent_name,
            "event_type": self.event_type,
            "user_id": self.user_id,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "error": self.error,
            "attempt": self.attempt,
            "circuit_state": self.circuit_state,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "model_used": self.model_used,
        }


class AgentHealthTracker:
    """
    Tracks agent availability and error rates over time.

    Maintains rolling windows of success/failure counts per agent
    and exposes availability percentages and error rate trends.
    """

    def __init__(self, window_size: int = 100):
        self._window_size = window_size
        self._agent_windows: Dict[str, List[bool]] = {}  # agent_name → [success, ...]
        self._agent_error_counts: Dict[str, int] = defaultdict(int)
        self._agent_total_counts: Dict[str, int] = defaultdict(int)
        self._agent_consecutive_failures: Dict[str, int] = defaultdict(int)
        self._agent_last_error: Dict[str, Dict[str, Any]] = {}
        self._logger = logger.bind(component="agent_health")

    def record(self, agent_name: str, success: bool, error: Optional[str] = None) -> None:
        """Record an execution result for health tracking."""
        if agent_name not in self._agent_windows:
            self._agent_windows[agent_name] = []

        window = self._agent_windows[agent_name]
        window.append(success)
        if len(window) > self._window_size:
            window.pop(0)

        self._agent_total_counts[agent_name] += 1
        if not success:
            self._agent_error_counts[agent_name] += 1
            self._agent_consecutive_failures[agent_name] += 1
            self._agent_last_error[agent_name] = {
                "error": error or "unknown",
                "timestamp": time.time(),
            }
        else:
            self._agent_consecutive_failures[agent_name] = 0

    def get_availability(self, agent_name: str) -> float:
        """Get availability (success rate) over the rolling window. Returns 0.0–1.0."""
        window = self._agent_windows.get(agent_name, [])
        if not window:
            return 1.0  # assume healthy if no data
        return sum(1 for s in window if s) / len(window)

    def get_error_rate(self, agent_name: str) -> float:
        """Get error rate over the rolling window. Returns 0.0–1.0."""
        return 1.0 - self.get_availability(agent_name)

    def get_consecutive_failures(self, agent_name: str) -> int:
        """Get current consecutive failure streak."""
        return self._agent_consecutive_failures.get(agent_name, 0)

    def get_health_status(self, agent_name: str) -> Dict[str, Any]:
        """Get comprehensive health status for an agent."""
        availability = self.get_availability(agent_name)
        error_rate = self.get_error_rate(agent_name)
        consecutive = self.get_consecutive_failures(agent_name)
        total = self._agent_total_counts.get(agent_name, 0)
        errors = self._agent_error_counts.get(agent_name, 0)
        last_error = self._agent_last_error.get(agent_name)

        if availability >= 0.95:
            status = "healthy"
        elif availability >= 0.80:
            status = "degraded"
        else:
            status = "unhealthy"

        return {
            "agent_name": agent_name,
            "status": status,
            "availability": round(availability, 4),
            "error_rate": round(error_rate, 4),
            "consecutive_failures": consecutive,
            "total_executions": total,
            "total_errors": errors,
            "last_error": last_error,
        }

    def get_all_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all tracked agents."""
        return {
            name: self.get_health_status(name)
            for name in self._agent_total_counts
        }


class AgentMetricsCollector:
    """
    Collects and aggregates execution metrics per agent.

    Tracks:
    - Total calls, successes, failures
    - Latency (avg, p50, p95, p99)
    - Token usage (input, output)
    - Cost (per agent, per user, per swarm, per day)
    - Circuit breaker events
    """

    def __init__(self, max_records: int = 10_000):
        self._records: List[ExecutionRecord] = []
        self._max_records = max_records
        self._agent_latencies: Dict[str, List[float]] = defaultdict(list)
        self._agent_costs: Dict[str, float] = defaultdict(float)
        self._user_costs: Dict[str, float] = defaultdict(float)
        # Per-day cost tracking: key = "YYYY-MM-DD"
        self._daily_costs: Dict[str, float] = defaultdict(float)
        self._daily_agent_costs: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._daily_user_costs: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        # Per-swarm metrics (swarm = group of agents working together)
        self._swarm_costs: Dict[str, float] = defaultdict(float)
        self._swarm_calls: Dict[str, int] = defaultdict(int)
        self._swarm_successes: Dict[str, int] = defaultdict(int)
        self._swarm_latencies: Dict[str, List[float]] = defaultdict(list)
        # Agent → swarm mapping
        self._agent_swarm_map: Dict[str, str] = {}
        # Agent health tracker
        self._health = AgentHealthTracker()
        self._logger = logger.bind(component="agent_metrics")

    def register_agent_swarm(self, agent_name: str, swarm_name: str) -> None:
        """Register an agent as belonging to a swarm (group of cooperating agents)."""
        self._agent_swarm_map[agent_name] = swarm_name

    def get_swarm_stats(self, swarm_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get aggregated stats for a swarm of agents."""
        cutoff = time.time() - hours * 3600
        swarm_agents = [
            name for name, swarm in self._agent_swarm_map.items()
            if swarm == swarm_name
        ]
        records = [
            r for r in self._records
            if r.agent_name in swarm_agents and r.started_at > cutoff
        ]

        if not records:
            return {"swarm_name": swarm_name, "calls": 0}

        latencies = [r.duration_ms for r in records]
        successes = sum(1 for r in records if r.success)
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)

        return {
            "swarm_name": swarm_name,
            "period_hours": hours,
            "agents": swarm_agents,
            "total_calls": len(records),
            "successes": successes,
            "failures": len(records) - successes,
            "success_rate": round(successes / len(records), 4),
            "latency": {
                "avg_ms": round(sum(latencies) / n, 2),
                "p50_ms": round(sorted_lat[n // 2], 2),
                "p95_ms": round(sorted_lat[int(n * 0.95)], 2),
            },
            "cost_usd": round(self._swarm_costs.get(swarm_name, 0), 6),
            "total_tokens": sum(r.input_tokens + r.output_tokens for r in records),
        }

    def get_all_swarm_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get stats for all swarms."""
        swarms = set(self._agent_swarm_map.values())
        return {
            swarm: self.get_swarm_stats(swarm, hours)
            for swarm in swarms
        }

    def record(self, record: ExecutionRecord) -> None:
        """Record an execution."""
        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

        self._agent_latencies[record.agent_name].append(record.duration_ms)
        if len(self._agent_latencies[record.agent_name]) > 1000:
            self._agent_latencies[record.agent_name] = self._agent_latencies[record.agent_name][-1000:]

        if record.cost_usd > 0:
            self._agent_costs[record.agent_name] += record.cost_usd
            if record.user_id:
                self._user_costs[record.user_id] += record.cost_usd

            # Per-day cost tracking
            day_key = time.strftime("%Y-%m-%d", time.localtime(record.started_at))
            self._daily_costs[day_key] += record.cost_usd
            self._daily_agent_costs[day_key][record.agent_name] += record.cost_usd
            if record.user_id:
                self._daily_user_costs[day_key][record.user_id] += record.cost_usd

        # Per-swarm tracking
        swarm = self._agent_swarm_map.get(record.agent_name)
        if swarm:
            self._swarm_calls[swarm] += 1
            if record.success:
                self._swarm_successes[swarm] += 1
            self._swarm_latencies[swarm].append(record.duration_ms)
            if len(self._swarm_latencies[swarm]) > 1000:
                self._swarm_latencies[swarm] = self._swarm_latencies[swarm][-1000:]
            if record.cost_usd > 0:
                self._swarm_costs[swarm] += record.cost_usd

        # Health tracking
        self._health.record(record.agent_name, record.success, record.error)

    def get_agent_stats(self, agent_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get stats for a specific agent."""
        cutoff = time.time() - hours * 3600
        records = [r for r in self._records if r.agent_name == agent_name and r.started_at > cutoff]

        if not records:
            return {"agent_name": agent_name, "calls": 0}

        latencies = [r.duration_ms for r in records]
        successes = sum(1 for r in records if r.success)
        total_tokens_in = sum(r.input_tokens for r in records)
        total_tokens_out = sum(r.output_tokens for r in records)

        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        return {
            "agent_name": agent_name,
            "period_hours": hours,
            "total_calls": len(records),
            "successes": successes,
            "failures": len(records) - successes,
            "success_rate": round(successes / len(records), 4),
            "latency": {
                "avg_ms": round(sum(latencies) / n, 2),
                "p50_ms": round(sorted_latencies[n // 2], 2),
                "p95_ms": round(sorted_latencies[int(n * 0.95)], 2),
                "p99_ms": round(sorted_latencies[int(n * 0.99)], 2),
                "min_ms": round(min(latencies), 2),
                "max_ms": round(max(latencies), 2),
            },
            "tokens": {
                "input": total_tokens_in,
                "output": total_tokens_out,
                "total": total_tokens_in + total_tokens_out,
            },
            "cost_usd": round(self._agent_costs.get(agent_name, 0), 6),
        }

    def get_all_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get stats for all agents."""
        agent_names = set(r.agent_name for r in self._records)
        return {
            "agents": {name: self.get_agent_stats(name, hours) for name in agent_names},
            "swarms": self.get_all_swarm_stats(hours),
            "total_cost_usd": round(sum(self._agent_costs.values()), 6),
            "total_user_cost_usd": round(sum(self._user_costs.values()), 6),
            "total_swarm_cost_usd": round(sum(self._swarm_costs.values()), 6),
            "total_records": len(self._records),
            "health": self._health.get_all_health(),
        }

    def get_daily_costs(self, days: int = 7) -> Dict[str, Any]:
        """Get cost breakdown by day for the last N days."""
        import datetime
        today = datetime.date.today()
        result = {}
        for i in range(days):
            day = today - datetime.timedelta(days=i)
            day_key = day.isoformat()
            result[day_key] = {
                "total_usd": round(self._daily_costs.get(day_key, 0), 6),
                "by_agent": {
                    k: round(v, 6)
                    for k, v in self._daily_agent_costs.get(day_key, {}).items()
                },
                "by_user": {
                    k: round(v, 6)
                    for k, v in self._daily_user_costs.get(day_key, {}).items()
                },
            }
        return result

    def get_health_status(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all agents."""
        return self._health.get_all_health()

    def get_user_costs(self, user_id: str) -> Dict[str, Any]:
        """Get cost breakdown for a specific user."""
        records = [r for r in self._records if r.user_id == user_id]
        agent_costs: Dict[str, float] = defaultdict(float)
        for r in records:
            agent_costs[r.agent_name] += r.cost_usd

        return {
            "user_id": user_id,
            "total_cost_usd": round(self._user_costs.get(user_id, 0), 6),
            "total_calls": len(records),
            "cost_by_agent": {k: round(v, 6) for k, v in agent_costs.items()},
        }


# ════════════════════════════════════════════════════════════════════
# Agent Execution Harness
# ════════════════════════════════════════════════════════════════════


@dataclass
class HarnessConfig:
    """Configuration for the execution harness."""
    timeout_s: float = 30.0           # Default timeout per agent call
    max_retries: int = 3              # Default max retries (3 attempts total)
    retry_base_delay_s: float = 1.0   # Base delay for exponential backoff
    retry_multiplier: float = 3.0     # Multiplier for exponential backoff
    retry_max_delay_s: float = 30.0   # Max delay between retries
    circuit_failure_threshold: int = 5  # Failures before circuit opens
    circuit_recovery_timeout_s: float = 30.0  # Time before half-open probe
    circuit_half_open_max: int = 3    # Successes in half-open to close circuit
    enable_cost_tracking: bool = True
    per_agent_timeout: Dict[str, float] = field(default_factory=dict)
    per_agent_retries: Dict[str, int] = field(default_factory=dict)


class AgentExecutionHarness:
    """
    Unified execution harness for all Angavu agents.

    Wraps every agent call with:
    1. Timeout enforcement (prevents hung agents)
    2. Retry with exponential backoff (handles transient failures)
    3. Circuit breaker (prevents cascading failures)
    4. Metrics collection (latency, success rate, tokens)
    5. Cost attribution (per agent, per user)
    6. **NEW**: Prompt injection scanning (feature-flagged)

    Security (when ANGAVU_PROMPT_GUARD_ENABLED=true):
    - Inter-agent messages are scanned for prompt injection patterns
    - Messages with injection attempts are blocked before reaching the LLM
    - Chain: signature verification → capability check → prompt scan

    Usage:
        harness = AgentExecutionHarness()
        result = await harness.execute(agent, event)

    Integration with BiasharaAgent:
        # In base.py handle_event():
        async def handle_event(self, event):
            if self._harness:
                return await self._harness.execute(self, event)
            return await self._handle_event_inner(event)
    """

    def __init__(self, config: Optional[HarnessConfig] = None):
        self._config = config or HarnessConfig()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._metrics = AgentMetricsCollector()
        self._logger = logger.bind(component="execution_harness")

        # Pre/Post execution hooks
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []

        # Agent loop improvements (injected via setters, feature-flagged)
        self._cost_tracker: Any = None    # AgentCostTracker | None
        self._governance: Any = None      # CircuitBreakerGovernance | None

        # Prompt guard integration (feature-flagged)
        self._prompt_guard: Optional["PromptGuard"] = None
        self._secure_handlers: Dict[str, "SecureMessageHandler"] = {}
        self._injection_blocks: int = 0
        if PROMPT_GUARD_ENABLED and _PROMPT_GUARD_AVAILABLE:
            self._prompt_guard = get_prompt_guard()
            self._logger.info("prompt_guard_enabled", strict=PROMPT_GUARD_STRICT)

    # ── Circuit Breaker Management ──────────────────────────────────

    def _get_circuit_breaker(self, agent_name: str) -> CircuitBreaker:
        """Get or create a circuit breaker for an agent."""
        if agent_name not in self._circuit_breakers:
            self._circuit_breakers[agent_name] = CircuitBreaker(
                name=agent_name,
                failure_threshold=self._config.circuit_failure_threshold,
                recovery_timeout_s=self._config.circuit_recovery_timeout_s,
                half_open_max_calls=self._config.circuit_half_open_max,
            )
        return self._circuit_breakers[agent_name]

    # ── Core Execution ──────────────────────────────────────────────

    async def execute(
        self,
        agent: BiasharaAgent,
        event: AgentEvent,
        user_id: Optional[str] = None,
        timeout_override: Optional[float] = None,
    ) -> AgentResult:
        """
        Execute an agent call through the harness.

        Steps:
        1. Check circuit breaker — reject if open
        2. Run pre-execution hooks
        3. Execute with timeout and retry
        4. Record metrics and cost
        5. Run post-execution hooks
        6. Return result
        """
        from app.agents.base import AgentResult

        agent_name = agent.name
        cb = self._get_circuit_breaker(agent_name)

        # 0. Prompt injection scan (before circuit breaker check)
        if self._prompt_guard and PROMPT_GUARD_ENABLED:
            # Scan the event payload for injection attempts
            event_payload = event.payload if hasattr(event, 'payload') and isinstance(event.payload, dict) else {}
            if event_payload:
                detection = self._prompt_guard.scan_message(event_payload)
                if detection and detection.is_injection:
                    self._injection_blocks += 1
                    self._logger.warning(
                        "prompt_injection_blocked",
                        agent=agent_name,
                        severity=detection.severity.value,
                        pattern=detection.pattern_name,
                        field=detection.field,
                        confidence=detection.confidence,
                    )
                    return AgentResult(
                        success=False,
                        error=f"Message blocked: prompt injection detected ({detection.pattern_name})",
                        duration_ms=0,
                    )

        # 1. Circuit breaker check
        if cb.is_open:
            self._logger.warning(
                "circuit_breaker_open",
                agent=agent_name,
                state=cb.state.value,
            )
            record = ExecutionRecord(
                agent_name=agent_name,
                event_type=event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                user_id=user_id,
                success=False,
                error=f"Circuit breaker open for {agent_name}",
                circuit_state=cb.state.value,
            )
            self._metrics.record(record)
            return AgentResult(
                success=False,
                error=f"Circuit breaker open for {agent_name}. Agent is failing and temporarily disabled.",
                duration_ms=0,
            )

        # 2. Resolve per-agent config
        timeout_s = timeout_override or self._config.per_agent_timeout.get(agent_name, self._config.timeout_s)
        max_retries = self._config.per_agent_retries.get(agent_name, self._config.max_retries)

        # 3. Execute with retry
        last_error = None
        for attempt in range(max_retries + 1):
            record = ExecutionRecord(
                agent_name=agent_name,
                event_type=event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                user_id=user_id,
                attempt=attempt + 1,
                circuit_state=cb.state.value,
                timeout_used_s=timeout_s,
            )

            # Run pre-hooks
            for hook in self._pre_hooks:
                try:
                    await hook(agent, event, record)
                except Exception as hook_err:
                    self._logger.debug("pre_hook_error", error=str(hook_err))

            start_time = time.time()
            try:
                # Call _handle_event_inner directly to avoid re-entering the harness
                result = await asyncio.wait_for(
                    agent._handle_event_inner(event),
                    timeout=timeout_s,
                )

                record.ended_at = time.time()
                record.duration_ms = (record.ended_at - record.started_at) * 1000
                record.success = result.success
                record.error = result.error

                # Extract cost info from result if available
                if hasattr(result, 'data') and isinstance(result.data, dict):
                    record.input_tokens = result.data.get('input_tokens', 0)
                    record.output_tokens = result.data.get('output_tokens', 0)
                    record.cost_usd = result.data.get('cost_usd', 0)
                    record.model_used = result.data.get('model_used', '')

                # Record success with circuit breaker
                if result.success:
                    cb.record_success()
                else:
                    cb.record_failure()
                    # Notify governance of failure (for auto-pause tracking)
                    if self._governance:
                        try:
                            self._governance.record_failure(agent_name)
                        except Exception:
                            pass

                # Record metrics
                self._metrics.record(record)

                # Export to cost tracker if injected
                if self._cost_tracker and record.cost_usd > 0:
                    try:
                        from app.agents.cost_tracker import CostRecord
                        self._cost_tracker.record(CostRecord(
                            agent_name=record.agent_name,
                            input_tokens=record.input_tokens,
                            output_tokens=record.output_tokens,
                            cost_usd=record.cost_usd,
                            model=record.model_used,
                        ))
                    except Exception:
                        pass

                # Run post-hooks
                for hook in self._post_hooks:
                    try:
                        await hook(agent, event, result, record)
                    except Exception as hook_err:
                        self._logger.debug("post_hook_error", error=str(hook_err))

                self._logger.info(
                    "harness_execution_complete",
                    agent=agent_name,
                    attempt=attempt + 1,
                    success=result.success,
                    duration_ms=round(record.duration_ms, 2),
                )

                return result

            except asyncio.TimeoutError:
                elapsed = (time.time() - start_time) * 1000
                record.ended_at = time.time()
                record.duration_ms = elapsed
                record.success = False
                record.error = f"Timeout after {timeout_s}s"
                cb.record_failure()
                self._metrics.record(record)
                last_error = f"Timeout after {timeout_s}s"

                self._logger.warning(
                    "harness_timeout",
                    agent=agent_name,
                    attempt=attempt + 1,
                    timeout_s=timeout_s,
                    elapsed_ms=round(elapsed, 2),
                )

            except Exception as exc:
                elapsed = (time.time() - start_time) * 1000
                record.ended_at = time.time()
                record.duration_ms = elapsed
                record.success = False
                record.error = str(exc)
                cb.record_failure()
                self._metrics.record(record)
                last_error = str(exc)

                self._logger.warning(
                    "harness_error",
                    agent=agent_name,
                    attempt=attempt + 1,
                    error=str(exc),
                )

            # Exponential backoff before retry
            if attempt < max_retries:
                delay = min(
                    self._config.retry_base_delay_s * (self._config.retry_multiplier ** attempt),
                    self._config.retry_max_delay_s,
                )
                self._logger.info(
                    "harness_retry_backoff",
                    agent=agent_name,
                    attempt=attempt + 1,
                    delay_s=round(delay, 2),
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        self._logger.error(
            "harness_retries_exhausted",
            agent=agent_name,
            attempts=max_retries + 1,
            last_error=last_error,
        )

        return AgentResult(
            success=False,
            error=f"Failed after {max_retries + 1} attempts: {last_error}",
            duration_ms=0,
        )

    def set_cost_tracker(self, tracker: Any) -> None:
        """Inject the cost tracker for per-agent cost tracking."""
        self._cost_tracker = tracker

    def set_governance(self, governance: Any) -> None:
        """Inject the circuit breaker governance for alerting and auto-pause."""
        self._governance = governance

    # ── Hooks ───────────────────────────────────────────────────────

    def add_pre_hook(self, hook: Callable) -> None:
        """Add a pre-execution hook (called before each attempt)."""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable) -> None:
        """Add a post-execution hook (called after each attempt)."""
        self._post_hooks.append(hook)

    # ── Monitoring API ──────────────────────────────────────────────

    def register_agent_swarm(self, agent_name: str, swarm_name: str) -> None:
        """Register an agent as belonging to a swarm (group of cooperating agents)."""
        self._metrics.register_agent_swarm(agent_name, swarm_name)

    def get_swarm_metrics(self, swarm_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get metrics for a swarm of agents."""
        return self._metrics.get_swarm_stats(swarm_name, hours)

    def get_all_swarm_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Get metrics for all swarms."""
        return self._metrics.get_all_swarm_stats(hours)

    def get_circuit_breakers(self) -> Dict[str, Dict[str, Any]]:
        """Get state of all circuit breakers."""
        return {name: cb.to_dict() for name, cb in self._circuit_breakers.items()}

    def get_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Get aggregated execution metrics."""
        return self._metrics.get_all_stats(hours)

    def get_agent_metrics(self, agent_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get metrics for a specific agent."""
        return self._metrics.get_agent_stats(agent_name, hours)

    def get_user_costs(self, user_id: str) -> Dict[str, Any]:
        """Get cost breakdown for a specific user."""
        return self._metrics.get_user_costs(user_id)

    def get_daily_costs(self, days: int = 7) -> Dict[str, Any]:
        """Get cost breakdown by day."""
        return self._metrics.get_daily_costs(days)

    def get_agent_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all tracked agents (availability, error rates)."""
        return self._metrics.get_health_status()

    def get_health(self) -> Dict[str, Any]:
        """Get overall harness health status."""
        open_circuits = [
            name for name, cb in self._circuit_breakers.items()
            if cb.state == CircuitState.OPEN
        ]
        half_open = [
            name for name, cb in self._circuit_breakers.items()
            if cb.state == CircuitState.HALF_OPEN
        ]

        health = {
            "status": "degraded" if open_circuits else "healthy",
            "open_circuits": open_circuits,
            "half_open_circuits": half_open,
            "total_circuit_breakers": len(self._circuit_breakers),
            "total_executions": len(self._metrics._records),
            "agent_health": self._metrics.get_health_status(),
            "config": {
                "timeout_s": self._config.timeout_s,
                "max_retries": self._config.max_retries,
                "retry_multiplier": self._config.retry_multiplier,
                "circuit_failure_threshold": self._config.circuit_failure_threshold,
                "circuit_recovery_timeout_s": self._config.circuit_recovery_timeout_s,
                "circuit_half_open_max": self._config.circuit_half_open_max,
            },
        }

        # Include prompt guard stats if enabled
        if self._prompt_guard:
            guard_stats = self._prompt_guard.get_stats()
            guard_stats["injection_blocks"] = self._injection_blocks
            health["prompt_guard"] = guard_stats

        return health

    def reset_circuit_breaker(self, agent_name: str) -> bool:
        """Manually reset a circuit breaker to closed state."""
        cb = self._circuit_breakers.get(agent_name)
        if cb:
            cb._transition(CircuitState.CLOSED)
            self._logger.info("circuit_breaker_reset", agent=agent_name)
            return True
        return False


# ════════════════════════════════════════════════════════════════════
# Output Validators
# ════════════════════════════════════════════════════════════════════


@dataclass
class ValidationResult:
    """Result of output validation."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class OutputValidator:
    """
    Validates agent outputs against schemas and business rules.

    Use cases:
    - Credit scores must be 300-850
    - Confidence must be 0.0-1.0
    - Market forecasts must include time horizon
    - Reports must have non-empty content

    Usage:
        validator = OutputValidator()
        validator.register("credit_score", validate_credit_score)
        result = validator.validate("credit_score", output_data)
    """

    def __init__(self):
        self._validators: Dict[str, List[Callable[[Dict], tuple]]] = {}
        self._logger = logger.bind(component="output_validator")

    def register(self, output_type: str, validator_fn: Callable[[Dict], tuple]) -> None:
        """
        Register a validation function for an output type.

        validator_fn should return (is_valid: bool, error_message: str).
        """
        self._validators.setdefault(output_type, []).append(validator_fn)

    def validate(self, output_type: str, data: Dict[str, Any]) -> ValidationResult:
        """Run all validators for an output type."""
        errors = []
        warnings = []

        for validator_fn in self._validators.get(output_type, []):
            try:
                is_valid, message = validator_fn(data)
                if not is_valid:
                    errors.append(message)
            except Exception as exc:
                warnings.append(f"Validator error: {exc}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def get_registered_types(self) -> List[str]:
        """List all registered output types."""
        return list(self._validators.keys())


# ── Built-in Validators ────────────────────────────────────────────


def validate_credit_score(data: Dict[str, Any]) -> tuple:
    """Validate credit score is in range 300-850."""
    score = data.get("credit_score") or data.get("alama_score", 0)
    if not (300 <= score <= 850):
        return False, f"Credit score {score} outside valid range 300-850"
    return True, ""


def validate_confidence(data: Dict[str, Any]) -> tuple:
    """Validate confidence is in range 0.0-1.0."""
    confidence = data.get("confidence", None)
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        return False, f"Confidence {confidence} outside valid range 0.0-1.0"
    return True, ""


def validate_market_forecast(data: Dict[str, Any]) -> tuple:
    """Validate market forecast has required fields."""
    required = ["product_category", "region", "forecast_horizon"]
    missing = [f for f in required if f not in data]
    if missing:
        return False, f"Market forecast missing required fields: {missing}"
    return True, ""


def validate_report_content(data: Dict[str, Any]) -> tuple:
    """Validate report has non-empty content."""
    content = data.get("content") or data.get("report_content", "")
    if not content or len(str(content).strip()) < 10:
        return False, "Report content is empty or too short"
    return True, ""


def validate_transaction_amount(data: Dict[str, Any]) -> tuple:
    """Validate transaction amount is positive."""
    amount = data.get("amount", 0)
    if amount <= 0:
        return False, f"Transaction amount {amount} must be positive"
    if amount > 100_000_000:  # 100M KSh
        return False, f"Transaction amount {amount} exceeds maximum"
    return True, ""


def create_default_validator() -> OutputValidator:
    """Create a validator with all built-in validation rules."""
    validator = OutputValidator()
    validator.register("credit_score", validate_credit_score)
    validator.register("confidence", validate_confidence)
    validator.register("market_forecast", validate_market_forecast)
    validator.register("report", validate_report_content)
    validator.register("transaction", validate_transaction_amount)
    return validator


# ════════════════════════════════════════════════════════════════════
# Factory
# ════════════════════════════════════════════════════════════════════


_global_harness: Optional[AgentExecutionHarness] = None


def get_execution_harness() -> AgentExecutionHarness:
    """Get or create the global execution harness."""
    global _global_harness
    if _global_harness is None:
        _global_harness = AgentExecutionHarness()
    return _global_harness


def create_harness(
    timeout_s: float = 30.0,
    max_retries: int = 3,
    circuit_failure_threshold: int = 5,
    circuit_recovery_timeout_s: float = 30.0,
    circuit_half_open_max: int = 3,
    retry_multiplier: float = 3.0,
) -> AgentExecutionHarness:
    """Create a harness with custom configuration."""
    config = HarnessConfig(
        timeout_s=timeout_s,
        max_retries=max_retries,
        circuit_failure_threshold=circuit_failure_threshold,
        circuit_recovery_timeout_s=circuit_recovery_timeout_s,
        circuit_half_open_max=circuit_half_open_max,
        retry_multiplier=retry_multiplier,
    )
    return AgentExecutionHarness(config)


# ════════════════════════════════════════════════════════════════════
# Canary Router — Gradual Rollout
# ════════════════════════════════════════════════════════════════════


import random


class CanaryRouter:
    """
    Routes a percentage of traffic to different agent versions.

    Enables gradual rollout: 1% → 10% → 50% → 100%.
    Each version is a BiasharaAgent instance with a traffic weight.

    Usage:
        router = CanaryRouter()
        router.register("IntelligenceGenerator", old_agent, weight=0.9)
        router.register("IntelligenceGenerator", new_agent, weight=0.1)
        # 90% traffic → old, 10% → new

        agent = router.route("IntelligenceGenerator")
    """

    def __init__(self):
        self._versions: Dict[str, List[tuple]] = {}
        # agent_name → [(agent_instance, weight), ...]
        self._logger = logger.bind(component="canary_router")

    def register(
        self,
        agent_name: str,
        agent: Any,
        weight: float,
        version: str = "default",
    ) -> None:
        """Register an agent version with a traffic weight."""
        if agent_name not in self._versions:
            self._versions[agent_name] = []
        self._versions[agent_name].append((agent, weight, version))
        self._logger.info(
            "canary_version_registered",
            agent=agent_name,
            version=version,
            weight=weight,
        )

    def route(self, agent_name: str) -> Any:
        """Select an agent version based on traffic weights."""
        versions = self._versions.get(agent_name, [])
        if not versions:
            raise ValueError(f"No versions registered for {agent_name}")

        total = sum(w for _, w, _ in versions)
        r = random.uniform(0, total)
        cumulative = 0
        for agent, weight, version in versions:
            cumulative += weight
            if r <= cumulative:
                return agent
        return versions[-1][0]

    def get_weights(self, agent_name: str) -> List[Dict[str, Any]]:
        """Get current traffic weights for an agent."""
        versions = self._versions.get(agent_name, [])
        total = sum(w for _, w, _ in versions)
        return [
            {
                "version": v,
                "weight": w,
                "percentage": round(w / total * 100, 1) if total > 0 else 0,
            }
            for _, w, v in versions
        ]

    def update_weight(
        self, agent_name: str, version: str, new_weight: float
    ) -> bool:
        """Update the traffic weight for a specific version."""
        versions = self._versions.get(agent_name, [])
        for i, (agent, weight, ver) in enumerate(versions):
            if ver == version:
                versions[i] = (agent, new_weight, version)
                self._logger.info(
                    "canary_weight_updated",
                    agent=agent_name,
                    version=version,
                    new_weight=new_weight,
                )
                return True
        return False

    def remove_version(self, agent_name: str, version: str) -> bool:
        """Remove a version from canary routing."""
        versions = self._versions.get(agent_name, [])
        original_len = len(versions)
        self._versions[agent_name] = [
            (a, w, v) for a, w, v in versions if v != version
        ]
        return len(self._versions[agent_name]) < original_len
