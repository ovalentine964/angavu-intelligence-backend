"""
BiasharaAgent — Base class for all Angavu Intelligence agents.

Lifecycle:
    observe  → receive an event from the event bus
    think    → process context, make a decision
    act      → execute the decision using available tools
    reflect  → learn from the result, update memory

Each agent wraps one or more existing services (Soko Pulse, Alama Score,
Report Generator, etc.) and adds agent capabilities:
    - Identity   (name, role, capabilities)
    - Memory     (short-term context, long-term knowledge)
    - Tools      (what it can access)
    - Planning   (what it's working towards)
    - Communication (event bus integration)

Inspired by: CrewAI role-based agents, LangGraph stateful nodes,
DeerFlow sub-agent orchestration.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Event & Message Types
# ════════════════════════════════════════════════════════════════════


class EventType(str, Enum):
    """All event types that flow through the event bus."""

    # Data pipeline
    TRANSACTION_RECEIVED = "transaction.received"
    TRANSACTION_PROCESSED = "transaction.processed"
    BATCH_PROCESSED = "batch.processed"

    # Intelligence
    INTELLIGENCE_REQUESTED = "intelligence.requested"
    INTELLIGENCE_GENERATED = "intelligence.generated"
    PRICE_FORECAST_READY = "price.forecast.ready"
    CREDIT_SCORE_READY = "credit.score.ready"
    MARKET_ALERT = "market.alert"

    # Reports
    REPORT_REQUESTED = "report.requested"
    REPORT_GENERATED = "report.generated"
    REPORT_DELIVERED = "report.delivered"

    # Self-evolution
    FEEDBACK_RECEIVED = "feedback.received"
    FEATURE_SPEC_GENERATED = "feature.spec.generated"
    EVOLUTION_CYCLE_COMPLETE = "evolution.cycle.complete"

    # System
    AGENT_HEALTH_CHECK = "agent.health.check"
    PIPELINE_ERROR = "pipeline.error"


class AgentStatus(str, Enum):
    """Agent lifecycle states."""
    IDLE = "idle"
    OBSERVING = "observing"
    THINKING = "thinking"
    ACTING = "acting"
    REFLECTING = "reflecting"
    ERROR = "error"


@dataclass
class AgentEvent:
    """
    An event flowing through the event bus.

    Every event has a type, a source agent, a payload, and metadata
    for tracing and observability.
    """
    event_type: EventType
    source: str                          # agent name that produced this
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None  # links related events
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentEvent:
        return cls(
            event_type=EventType(data["event_type"]),
            source=data["source"],
            payload=data["payload"],
            event_id=data.get("event_id", uuid.uuid4().hex[:16]),
            timestamp=data.get("timestamp", time.time()),
            correlation_id=data.get("correlation_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentDecision:
    """
    The output of an agent's think phase.

    Contains the action to take, confidence level, and reasoning
    for observability / explainability.
    """
    action: str                          # what to do (e.g. "process_batch", "generate_report")
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0              # 0.0 – 1.0
    reasoning: str = ""                  # human-readable explanation
    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class AgentResult:
    """
    The output of an agent's act phase.

    Wraps the raw result with success/failure status, timing,
    and any events to publish downstream.
    """
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    events_to_publish: List[AgentEvent] = field(default_factory=list)
    result_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class AgentMessage:
    """
    A message from one agent to another (via event bus).

    Unlike events (broadcast), messages are point-to-point.
    """
    sender: str
    recipient: str
    content: Dict[str, Any]
    message_type: str = "request"        # request | response | notification
    correlation_id: Optional[str] = None
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


# ════════════════════════════════════════════════════════════════════
# Memory & Tools
# ════════════════════════════════════════════════════════════════════


class AgentMemory:
    """
    Per-agent memory: short-term context + long-term knowledge.

    Short-term (context window):
        Recent events, current task state, last N results.
        Cleared between task cycles.

    Long-term (persistent):
        Learned patterns, performance metrics, feedback summaries.
        Persists across sessions.
    """

    def __init__(self, max_short_term: int = 50):
        self._short_term: List[Dict[str, Any]] = []
        self._long_term: Dict[str, Any] = {}
        self._max_short_term = max_short_term

    # ── Short-term ──────────────────────────────────────────────────

    def remember(self, item: Dict[str, Any]) -> None:
        """Add an item to short-term memory."""
        self._short_term.append({**item, "_ts": time.time()})
        if len(self._short_term) > self._max_short_term:
            self._short_term = self._short_term[-self._max_short_term:]

    def recall_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get the N most recent short-term memories."""
        return self._short_term[-n:]

    def clear_short_term(self) -> None:
        """Clear short-term memory (e.g. between task cycles)."""
        self._short_term.clear()

    # ── Long-term ───────────────────────────────────────────────────

    def store(self, key: str, value: Any) -> None:
        """Persist knowledge in long-term memory."""
        self._long_term[key] = value

    def retrieve(self, key: str, default: Any = None) -> Any:
        """Retrieve knowledge from long-term memory."""
        return self._long_term.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        """Full memory snapshot for debugging / observability."""
        return {
            "short_term_count": len(self._short_term),
            "short_term_recent": self._short_term[-5:],
            "long_term_keys": list(self._long_term.keys()),
        }


class AgentTools:
    """
    Registry of tools available to an agent.

    Tools are callables (sync or async) that an agent can invoke
    during its act phase. Each tool has a name and description
    for observability.
    """

    def __init__(self):
        self._tools: Dict[str, Any] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, name: str, fn: Any, description: str = "") -> None:
        """Register a tool for this agent."""
        self._tools[name] = fn
        self._descriptions[name] = description or name

    def get(self, name: str) -> Any:
        """Retrieve a registered tool."""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        """List all available tools with descriptions."""
        return [
            {"name": name, "description": self._descriptions.get(name, "")}
            for name in self._tools
        ]

    def has(self, name: str) -> bool:
        return name in self._tools


# ════════════════════════════════════════════════════════════════════
# BiasharaAgent — The Base Class
# ════════════════════════════════════════════════════════════════════


class BiasharaAgent:
    """
    Base class for all Angavu Intelligence agents.

    Subclasses must implement:
        - think()  — process context and return an AgentDecision
        - act()    — execute the decision and return an AgentResult

    Optionally override:
        - observe()  — custom event filtering / preprocessing
        - reflect()  — custom learning from results

    The event_bus is injected after construction via set_event_bus(),
    so agents can be created independently of infrastructure.
    """

    def __init__(self, name: str, role: str, capabilities: Sequence[str]):
        self.name = name
        self.role = role
        self.capabilities = list(capabilities)
        self.memory = AgentMemory()
        self.tools = AgentTools()
        self.status = AgentStatus.IDLE

        # Injected after construction
        self._event_bus: Any = None       # EventBus | None
        self._tracer: Any = None          # AgentTracer | None

        # Background polling lifecycle
        self._poll_task: Optional[asyncio.Task] = None
        self._poll_interval: float = 1.0  # seconds between polls
        self._running: bool = False

        self._logger = logger.bind(agent=name, role=role)

    # ── Infrastructure injection ────────────────────────────────────

    def set_event_bus(self, bus: Any) -> None:
        """Inject the event bus (called by orchestrator)."""
        self._event_bus = bus

    def set_tracer(self, tracer: Any) -> None:
        """Inject the tracer (called by orchestrator)."""
        self._tracer = tracer

    # ── Lifecycle start / stop ──────────────────────────────────────

    async def start(self) -> None:
        """
        Start the agent's background event polling loop.

        Call after set_event_bus() and subscribe() have been done.
        """
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._logger.info("agent_started", poll_interval=self._poll_interval)

    async def stop(self) -> None:
        """Stop the agent's background polling loop gracefully."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        self._logger.info("agent_stopped")

    async def _poll_loop(self) -> None:
        """
        Background loop: pull events from the bus and handle them.

        Each iteration calls get_events() then handle_event() for each.
        Errors are caught per-event so one bad event doesn't kill the loop.
        """
        self._logger.debug("poll_loop_started")
        while self._running:
            try:
                events = await self._event_bus.get_events(self, limit=10)
                for event in events:
                    try:
                        await self.handle_event(event)
                    except Exception as exc:
                        self._logger.error(
                            "poll_event_error",
                            event_type=event.event_type.value,
                            error=str(exc),
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.warning("poll_loop_error", error=str(exc))

            await asyncio.sleep(self._poll_interval)

        self._logger.debug("poll_loop_exited")

    # ── Lifecycle methods ───────────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """
        Receive an event from the event bus.

        Default implementation stores the event in short-term memory.
        Subclasses can override to filter or preprocess events.
        """
        self.status = AgentStatus.OBSERVING
        self.memory.remember({
            "event_type": event.event_type.value,
            "source": event.source,
            "payload_summary": {k: str(v)[:100] for k, v in event.payload.items()},
        })
        self._logger.debug(
            "observed_event",
            event_type=event.event_type.value,
            source=event.source,
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Process context and make a decision.

        Must be implemented by subclasses. The context typically includes:
        - The triggering event
        - Relevant memory
        - Available tools
        """
        raise NotImplementedError(f"{self.name} must implement think()")

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Execute the decision using available tools.

        Must be implemented by subclasses.
        """
        raise NotImplementedError(f"{self.name} must implement act()")

    async def reflect(self, result: AgentResult) -> None:
        """
        Learn from the result and update memory.

        Stores the result summary in memory. On failure, generates
        a reflection and stores it in long-term memory so that future
        think() calls can learn from past mistakes.

        On consecutive failures, adjusts strategy parameters.
        """
        self.status = AgentStatus.REFLECTING
        self.memory.remember({
            "result_id": result.result_id,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "error": result.error,
        })

        if result.success:
            self._logger.info(
                "act_success",
                result_id=result.result_id,
                duration_ms=result.duration_ms,
            )
        else:
            self._logger.warning(
                "act_failed",
                result_id=result.result_id,
                error=result.error,
                duration_ms=result.duration_ms,
            )

            # ── Store reflection in long-term memory (closes reflect→behavior loop) ──
            recent_context = self.memory.recall_recent(5)
            context_summary = [
                m.get("event_type", "unknown") for m in recent_context
            ]
            reflection = (
                f"Action failed: {result.error}. "
                f"Recent event types: {context_summary}. "
                f"Lesson: adjust strategy for similar conditions."
            )
            reflection_key = f"reflection:{result.result_id}"
            self.memory.store(reflection_key, reflection)
            self._logger.info(
                "reflection_stored",
                key=reflection_key,
                error=result.error,
            )

            # ── Detect consecutive failures → trigger strategy adjustment ──
            recent = self.memory.recall_recent(10)
            recent_failures = [r for r in recent if not r.get("success", True)]
            if len(recent_failures) >= 3:
                adjustment = {
                    "action": "reduce_confidence_threshold",
                    "failures_in_window": len(recent_failures),
                    "threshold_factor": max(0.5, 1.0 - len(recent_failures) * 0.1),
                    "updated_at": time.time(),
                }
                self.memory.store("strategy_adjustment", adjustment)
                self._logger.warning(
                    "strategy_adjustment_triggered",
                    failures=len(recent_failures),
                    threshold_factor=adjustment["threshold_factor"],
                )

    async def communicate(self, message: AgentMessage) -> None:
        """
        Send a message to another agent via the event bus.
        """
        if self._event_bus is None:
            self._logger.warning("no_event_bus", recipient=message.recipient)
            return

        event = AgentEvent(
            event_type=EventType.AGENT_HEALTH_CHECK,  # generic; subclasses refine
            source=self.name,
            payload={
                "message_type": message.message_type,
                "recipient": message.recipient,
                "content": message.content,
            },
            correlation_id=message.correlation_id,
        )
        await self._event_bus.publish(event)
        self._logger.debug(
            "message_sent",
            recipient=message.recipient,
            message_type=message.message_type,
        )

    # ── Full cycle (orchestrators call this) ────────────────────────

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """
        Full lifecycle: observe → think → act → reflect.

        Orchestrators and the event bus use this to trigger an agent.
        """
        cycle_start = time.time()
        trace_id = None

        try:
            # 1. Observe
            await self.observe(event)

            # 2. Think
            self.status = AgentStatus.THINKING

            # Gather past reflections from long-term memory
            reflections = [
                v for k, v in self.memory._long_term.items()
                if k.startswith("reflection:")
            ]

            # Check for strategy adjustments from consecutive failures
            strategy_adjustment = self.memory.retrieve("strategy_adjustment")

            context = {
                "event": event.to_dict(),
                "memory": self.memory.snapshot(),
                "tools": self.tools.list_tools(),
                "past_reflections": reflections[-5:],  # Last 5 reflections
                "strategy_adjustment": strategy_adjustment,
            }

            if self._tracer:
                trace_id = self._tracer.start_trace(self.name, context)

            decision = await self.think(context)

            if self._tracer and trace_id:
                self._tracer.record_decision(trace_id, decision)

            # 3. Act
            self.status = AgentStatus.ACTING
            result = await self.act(decision)

            if self._tracer and trace_id:
                self._tracer.record_result(trace_id, result)

            # 4. Reflect
            await self.reflect(result)

            # 5. Publish downstream events
            if self._event_bus and result.events_to_publish:
                for downstream_event in result.events_to_publish:
                    await self._event_bus.publish(downstream_event)

            # 6. Finalize trace
            if self._tracer and trace_id:
                self._tracer.end_trace(trace_id, success=result.success)

            self.status = AgentStatus.IDLE
            return result

        except Exception as exc:
            self.status = AgentStatus.ERROR
            self._logger.exception(
                "agent_cycle_error",
                event_type=event.event_type.value,
                error=str(exc),
            )
            if self._tracer and trace_id:
                self._tracer.end_trace(trace_id, success=False, error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - cycle_start) * 1000,
            )

    # ── Health ──────────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """Return agent health status for monitoring."""
        return {
            "name": self.name,
            "role": self.role,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "memory": self.memory.snapshot(),
            "tools": self.tools.list_tools(),
            "event_bus_connected": self._event_bus is not None,
            "tracer_connected": self._tracer is not None,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} role={self.role!r}>"
