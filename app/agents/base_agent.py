"""
BiasharaAgent — Base class for all Angavu Intelligence agents.

Lifecycle:
    observe  → receive an event from the event bus
    think    → process context, make a decision
    act      → execute the decision using available tools
    reflect  → learn from the result, update memory

Each agent wraps one or more existing services and adds agent capabilities:
    - Identity   (name, role, capabilities)
    - Memory     (short-term context, long-term knowledge)
    - Tools      (what it can access)
    - Planning   (what it's working towards)
    - Communication (event bus integration)
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Any

import structlog

from app.agents.base_events import (
    AgentDecision,
    AgentEvent,
    AgentMessage,
    AgentResult,
    AgentStatus,
    EventType,
)
from app.agents.base_protocols import AgentMemory, AgentTools

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# BiasharaAgent — The Base Class
# ════════════════════════════════════════════════════════════════════


class BiasharaAgent:
    """Base class for all Angavu Intelligence agents."""

    def __init__(self, name: str, role: str, capabilities: Sequence[str]):
        self.name = name
        self.role = role
        self.capabilities = list(capabilities)
        self.memory = AgentMemory()
        self.tools = AgentTools()
        self.status = AgentStatus.IDLE

        # Injected after construction
        self._event_bus: Any = None  # EventBus | None
        self._tracer: Any = None  # AgentTracer | None
        self._harness: Any = None  # AgentExecutionHarness | None
        self._inference_harness: Any = None  # InferenceHarness | None

        # Agent loop improvements (injected via setters, feature-flagged)
        self._self_evaluation: Any = None  # SelfEvaluationMiddleware | None
        self._cost_tracker: Any = None  # AgentCostTracker | None

        # Background polling lifecycle
        self._poll_task: asyncio.Task | None = None
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

    def set_harness(self, harness: Any) -> None:
        """Inject the execution harness (called by orchestrator)."""
        self._harness = harness

    def set_inference_harness(self, harness: Any) -> None:
        """Inject the model inference harness (called by orchestrator)."""
        self._inference_harness = harness

    def set_self_evaluation(self, evaluator: Any) -> None:
        """Inject the self-evaluation middleware (called by orchestrator)."""
        self._self_evaluation = evaluator

    def set_cost_tracker(self, tracker: Any) -> None:
        """Inject the cost tracker (called by orchestrator)."""
        self._cost_tracker = tracker

    # ── Lifecycle start / stop ──────────────────────────────────────

    async def start(self) -> None:
        """Start the agent's background event polling loop."""
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
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
        self._poll_task = None
        self._logger.info("agent_stopped")

    async def _poll_loop(self) -> None:
        """Background loop: pull events from the bus and handle them."""
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
        """Receive an event from the event bus."""
        self.status = AgentStatus.OBSERVING
        self.memory.remember(
            {
                "event_type": event.event_type.value,
                "source": event.source,
                "payload_summary": {k: str(v)[:100] for k, v in event.payload.items()},
            }
        )
        self._logger.debug(
            "observed_event",
            event_type=event.event_type.value,
            source=event.source,
        )

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Full lifecycle: observe → think → act → reflect."""
        if self._harness:
            return await self._harness.execute(self, event)

        return await self._handle_event_inner(event)

    async def _handle_event_inner(self, event: AgentEvent) -> AgentResult:
        """Internal lifecycle: observe → think → act → reflect → publish."""
        cycle_start = time.time()
        trace_id = None

        try:
            await self.observe(event)
            self.status = AgentStatus.THINKING

            reflections = [
                v for k, v in self.memory._long_term.items() if k.startswith("reflection:")
            ]
            context: dict[str, Any] = {
                "event": event.to_dict(),
                "memory": self.memory.snapshot(),
                "tools": self.tools.list_tools(),
                "past_reflections": reflections[-5:],
                "strategy_adjustment": self.memory.retrieve("strategy_adjustment"),
            }

            if self._tracer:
                trace_id = self._tracer.start_trace(self.name, context)

            decision = await self.think(context)
            if self._tracer and trace_id:
                self._tracer.record_decision(trace_id, decision)

            self.status = AgentStatus.ACTING
            result = await self.act(decision)
            if self._tracer and trace_id:
                self._tracer.record_result(trace_id, result)

            # Self-evaluate (feature-flagged)
            if self._self_evaluation:
                try:
                    result = await self._self_evaluation.evaluate_and_refine(self, event, result)
                except Exception as eval_err:
                    self._logger.warning("self_evaluation_error", error=str(eval_err))

            await self.reflect(result)

            # Publish downstream events
            if self._event_bus and result.events_to_publish:
                for ev in result.events_to_publish:
                    try:
                        await self._event_bus.publish(ev)
                    except Exception as pub_err:
                        self._logger.warning(
                            "event_publish_failed",
                            event_type=ev.event_type.value,
                            error=str(pub_err),
                        )

            # Track cost (feature-flagged)
            if self._cost_tracker and isinstance(getattr(result, 'data', None), dict):
                try:
                    from app.agents.cost_tracker import CostRecord
                    self._cost_tracker.record(CostRecord(
                        agent_name=self.name,
                        input_tokens=result.data.get("input_tokens", 0),
                        output_tokens=result.data.get("output_tokens", 0),
                        cost_usd=result.data.get("cost_usd", 0),
                        model=result.data.get("model_used", ""),
                    ))
                except Exception:
                    pass

            if self._tracer and trace_id:
                self._tracer.end_trace(trace_id, success=result.success)

            self.status = AgentStatus.IDLE
            return result

        except asyncio.CancelledError:
            self.status = AgentStatus.IDLE
            raise
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
                success=False, error=str(exc),
                duration_ms=(time.time() - cycle_start) * 1000,
            )

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Process context and make a decision. Must be implemented by subclasses."""
        raise NotImplementedError(f"{self.name} must implement think()")

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the decision using available tools. Must be implemented by subclasses."""
        raise NotImplementedError(f"{self.name} must implement act()")

    async def reflect(self, result: AgentResult) -> None:
        """Learn from the result and update memory."""
        self.status = AgentStatus.REFLECTING
        self.memory.remember({
            "result_id": result.result_id,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "error": result.error,
        })

        if result.success:
            self._logger.info("act_success", result_id=result.result_id, duration_ms=result.duration_ms)
        else:
            self._logger.warning(
                "act_failed", result_id=result.result_id,
                error=result.error, duration_ms=result.duration_ms,
            )
            # Store reflection in long-term memory
            recent_context = self.memory.recall_recent(5)
            context_summary = [m.get("event_type", "unknown") for m in recent_context]
            reflection = (
                f"Action failed: {result.error}. "
                f"Recent event types: {context_summary}. "
                f"Lesson: adjust strategy for similar conditions."
            )
            self.memory.store(f"reflection:{result.result_id}", reflection)

            # Detect consecutive failures → adjust strategy
            recent = self.memory.recall_recent(10)
            recent_failures = [r for r in recent if not r.get("success", True)]
            if len(recent_failures) >= 3:
                factor = max(0.5, 1.0 - len(recent_failures) * 0.1)
                self.memory.store("strategy_adjustment", {
                    "action": "reduce_confidence_threshold",
                    "failures_in_window": len(recent_failures),
                    "threshold_factor": factor,
                    "updated_at": time.time(),
                })
                self._logger.warning(
                    "strategy_adjustment_triggered",
                    failures=len(recent_failures), threshold_factor=factor,
                )

    async def infer(
        self,
        prompt: str,
        task_type: str = "general",
        system_prompt: str = "",
        expect_json: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        complexity: str | None = None,
    ) -> Any:
        """Convenience method: run inference through the model harness."""
        if self._inference_harness:
            return await self._inference_harness.infer(
                prompt=prompt,
                user_id=self.name,
                task_type=task_type,
                system_prompt=system_prompt,
                expect_json=expect_json,
                max_tokens=max_tokens,
                temperature=temperature,
                complexity=complexity,
            )

        try:
            from app.services.llm_service import LLMConfig, LLMMessage, get_llm_service

            llm = get_llm_service()
            messages = []
            if system_prompt:
                messages.append(LLMMessage(role="system", content=system_prompt))
            messages.append(LLMMessage(role="user", content=prompt))
            config = LLMConfig(
                temperature=temperature or 0.7,
                max_tokens=max_tokens or 512,
            )
            result = await llm.complete(messages, config)
            from app.services.ml.inference_harness import InferenceResult, ModelTier

            return InferenceResult(
                success=result.success,
                output=result.content,
                model_used=result.model,
                tier_used=ModelTier.ON_DEVICE,
                input_tokens=result.usage.get("prompt_tokens", 0),
                output_tokens=result.usage.get("completion_tokens", 0),
                latency_ms=result.latency_ms,
                error=result.error,
            )
        except Exception as exc:
            self._logger.error("infer_fallback_failed", error=str(exc))
            from app.services.ml.inference_harness import InferenceResult

            return InferenceResult(success=False, error=str(exc))

    async def communicate(self, message: AgentMessage) -> None:
        """Send a message to another agent via the event bus."""
        if self._event_bus is None:
            self._logger.warning("no_event_bus", recipient=message.recipient)
            return

        event = AgentEvent(
            event_type=EventType.AGENT_HEALTH_CHECK,
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

    async def delegate_to(
        self,
        target_agent: BiasharaAgent,
        action: str,
        parameters: dict[str, Any] | None = None,
        timeout_seconds: float = 60.0,
    ) -> AgentResult:
        """Delegate a task to another agent and wait for the result."""
        if target_agent is None:
            raise ValueError("target_agent must not be None")

        event = AgentEvent(
            event_type=EventType.INTELLIGENCE_REQUESTED,
            source=self.name,
            payload={
                "action": action,
                "parameters": parameters or {},
                "delegated_by": self.name,
            },
        )

        try:
            result = await asyncio.wait_for(
                target_agent.handle_event(event),
                timeout=timeout_seconds,
            )
            return result
        except TimeoutError:
            self._logger.warning(
                "delegate_to_timeout",
                target=target_agent.name,
                action=action,
                timeout=timeout_seconds,
            )
            raise
        except Exception as exc:
            self._logger.error(
                "delegate_to_error",
                target=target_agent.name,
                action=action,
                error=str(exc),
            )
            return AgentResult(
                success=False,
                error=f"Delegation to {target_agent.name} failed: {exc}",
            )

    # ── Health ──────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Return agent health status for monitoring."""
        health = {
            "name": self.name, "role": self.role,
            "capabilities": self.capabilities, "status": self.status.value,
            "memory": self.memory.snapshot(), "tools": self.tools.list_tools(),
            "event_bus_connected": self._event_bus is not None,
            "tracer_connected": self._tracer is not None,
            "harness_connected": self._harness is not None,
            "inference_harness_connected": self._inference_harness is not None,
            "services": {},
        }

        # Check database
        try:
            from app.db.database import engine
            health["services"]["database"] = {
                "status": "connected" if engine else "disconnected",
                "url": engine.url.host if engine else None,
            }
        except Exception as exc:
            health["services"]["database"] = {"status": "error", "error": str(exc)}

        # Check Redis
        try:
            from app.config import get_settings as _gs
            _s = _gs()
            if _s.REDIS_URL:
                url = _s.REDIS_URL.split("@")[-1] if "@" in _s.REDIS_URL else _s.REDIS_URL
                health["services"]["redis"] = {"status": "configured", "url": url}
            else:
                health["services"]["redis"] = {"status": "not_configured"}
        except Exception as exc:
            health["services"]["redis"] = {"status": "error", "error": str(exc)}

        # Check ClickHouse
        try:
            from app.config import get_settings as _gs2
            _s2 = _gs2()
            health["services"]["clickhouse"] = {
                "status": "configured" if _s2.has_clickhouse else "not_configured"
            }
        except Exception as exc:
            health["services"]["clickhouse"] = {"status": "error", "error": str(exc)}

        return health

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} role={self.role!r}>"
