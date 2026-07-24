"""
Superagent Reasoning Engine

The unified brain that replaces the multi-agent swarm.
Implements the OODA loop (Observe → Orient → Decide → Act)
with integrated domain modules for financial, credit, learning,
and evolution intelligence.

This engine wraps the existing sophisticated services (SokoPulse,
AlamaScore, FederatedLearning, SelfEvolution) and provides a
unified interface for all intelligence operations.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

import structlog

from app.agents.base import AgentEvent, AgentResult, AgentStatus, BiasharaAgent, EventType
from app.agents.event_bus import EventBus
from app.agents.observability import AgentTracer

logger = structlog.get_logger(__name__)


@dataclass
class OODACycle:
    """Record of one OODA reasoning cycle."""
    cycle_id: int
    observation: dict
    orientation: dict
    decision: dict
    action_result: dict
    learning: dict
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class SuperagentEngine(BiasharaAgent):
    """
    The unified reasoning engine for Angavu Intelligence.

    Replaces the previous 33+ agent classes and 6 swarm directories
    with a single, more capable agent architecture.

    Architecture:
    - Single OODA reasoning loop (Observe → Orient → Decide → Act → Learn)
    - Domain modules loaded as needed (financial, credit, learning, evolution)
    - Unified event bus for inter-component communication
    - Self-improvement through outcome tracking

    The engine delegates to specialized domain modules that wrap
    the existing sophisticated services:
    - FinancialModule → SokoPulse, FMCG Intelligence, Distribution Gap
    - CreditModule → AlamaScore credit scoring
    - LearningModule → Federated Learning with LoRA adapters
    - EvolutionModule → Self-evolution and feedback loops
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        tracer: Optional[AgentTracer] = None,
        config: Optional[dict] = None,
    ):
        super().__init__(name="SuperagentEngine", description="Unified intelligence engine")
        self._event_bus = event_bus
        self._tracer = tracer
        self._config = config or {}
        self._cycle_count = 0
        self._cycle_history: list[OODACycle] = []
        self._modules: dict[str, Any] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the engine and load domain modules.

        Imports and wires existing services into the superagent modules.
        """
        if self._initialized:
            return

        logger.info("superagent_initializing")

        # Load domain modules (lazy imports to avoid circular deps)
        try:
            from app.superagent.financial.module import FinancialModule
            self._modules["financial"] = FinancialModule()
            logger.info("financial_module_loaded")
        except (ImportError, Exception) as e:
            logger.warning("financial_module_load_failed", error=str(e))

        try:
            from app.superagent.credit.module import CreditModule
            self._modules["credit"] = CreditModule()
            logger.info("credit_module_loaded")
        except (ImportError, Exception) as e:
            logger.warning("credit_module_load_failed", error=str(e))

        try:
            from app.superagent.learning.module import LearningModule
            self._modules["learning"] = LearningModule()
            logger.info("learning_module_loaded")
        except (ImportError, Exception) as e:
            logger.warning("learning_module_load_failed", error=str(e))

        try:
            from app.superagent.evolution.module import EvolutionModule
            self._modules["evolution"] = EvolutionModule()
            logger.info("evolution_module_loaded")
        except (ImportError, Exception) as e:
            logger.warning("evolution_module_load_failed", error=str(e))

        self._initialized = True
        self.status = AgentStatus.IDLE
        logger.info(
            "superagent_initialized",
            modules=list(self._modules.keys()),
        )

    async def process_request(self, request: dict) -> dict:
        """
        Process a request through the OODA loop.

        This is the main entry point for all intelligence operations.
        Routes to the appropriate domain module based on request type.

        Args:
            request: Dict with keys like 'type', 'domain', 'data', etc.

        Returns:
            Dict with results from the appropriate domain module.
        """
        start_time = time.time()
        self._cycle_count += 1
        self.status = AgentStatus.RUNNING

        try:
            # OODA: Observe → Orient → Decide → Act
            observation = await self._observe(request)
            orientation = await self._orient(observation)
            decision = await self._decide(orientation)
            result = await self._act(decision)

            # Learn from the outcome
            learning = await self._learn(result)

            duration_ms = (time.time() - start_time) * 1000

            cycle = OODACycle(
                cycle_id=self._cycle_count,
                observation=observation,
                orientation=orientation,
                decision=decision,
                action_result=result,
                learning=learning,
                duration_ms=duration_ms,
            )
            self._cycle_history.append(cycle)

            # Trim history
            if len(self._cycle_history) > 500:
                self._cycle_history = self._cycle_history[-250:]

            # Publish event
            if self._event_bus:
                await self._event_bus.publish(AgentEvent(
                    event_type=EventType.TASK_COMPLETED,
                    source=self.name,
                    payload={
                        "cycle_id": self._cycle_count,
                        "domain": request.get("domain", "unknown"),
                        "duration_ms": duration_ms,
                    },
                ))

            self.status = AgentStatus.IDLE
            return {
                "success": True,
                "cycle_id": self._cycle_count,
                "result": result,
                "learning": learning,
                "duration_ms": duration_ms,
            }

        except Exception as exc:
            self.status = AgentStatus.ERROR
            duration_ms = (time.time() - start_time) * 1000

            logger.error(
                "superagent_request_failed",
                cycle=self._cycle_count,
                error=str(exc),
                request_type=request.get("type"),
            )

            if self._event_bus:
                await self._event_bus.publish(AgentEvent(
                    event_type=EventType.TASK_FAILED,
                    source=self.name,
                    payload={
                        "cycle_id": self._cycle_count,
                        "error": str(exc),
                    },
                ))

            return {
                "success": False,
                "cycle_id": self._cycle_count,
                "error": str(exc),
                "duration_ms": duration_ms,
            }

    async def _observe(self, request: dict) -> dict:
        """
        Observe: Gather and structure incoming data.

        Extracts relevant context from the request and enriches
        it with available domain knowledge.
        """
        observation = {
            "request_type": request.get("type", "unknown"),
            "domain": request.get("domain", "general"),
            "data": request.get("data", {}),
            "context": request.get("context", {}),
            "timestamp": datetime.now(UTC).isoformat(),
            "cycle_id": self._cycle_count,
        }

        # Enrich with domain-specific context
        domain = observation["domain"]
        if domain in self._modules:
            module = self._modules[domain]
            if hasattr(module, "observe"):
                enrichment = await module.observe(observation["data"])
                observation["enrichment"] = enrichment

        return observation

    async def _orient(self, observation: dict) -> dict:
        """
        Orient: Analyze the observation and determine the situation.

        Considers the current context, historical patterns, and
        domain knowledge to understand what's happening.
        """
        orientation = {
            "situation": "standard",
            "confidence": 0.8,
            "domain": observation.get("domain", "general"),
            "factors": [],
        }

        # Check if we have relevant historical patterns
        if self._cycle_history:
            recent_domains = [c.observation.get("domain") for c in self._cycle_history[-10:]]
            if recent_domains.count(observation.get("domain")) > 5:
                orientation["factors"].append("frequent_domain_activity")

        # Domain-specific orientation
        domain = orientation["domain"]
        if domain in self._modules:
            module = self._modules[domain]
            if hasattr(module, "orient"):
                domain_analysis = await module.orient(observation)
                orientation["domain_analysis"] = domain_analysis

        return orientation

    async def _decide(self, orientation: dict) -> dict:
        """
        Decide: Choose the best action based on orientation.

        Selects the appropriate domain module and action to execute.
        """
        domain = orientation.get("domain", "general")

        decision = {
            "action": "process",
            "domain": domain,
            "module": domain if domain in self._modules else None,
            "confidence": orientation.get("confidence", 0.5),
        }

        return decision

    async def _act(self, decision: dict) -> dict:
        """
        Act: Execute the decided action.

        Delegates to the appropriate domain module for execution.
        """
        domain = decision.get("domain")
        module = self._modules.get(domain)

        if module and hasattr(module, "execute"):
            return await module.execute(decision)

        return {
            "status": "no_handler",
            "domain": domain,
            "available_modules": list(self._modules.keys()),
        }

    async def _learn(self, result: dict) -> dict:
        """
        Learn: Extract learnings from the execution result.

        Updates internal state and publishes learning events.
        """
        learning = {
            "success": result.get("status") not in ("error", "no_handler"),
            "domain": result.get("domain"),
            "insights": [],
        }

        # Feed to evolution module if available
        evolution = self._modules.get("evolution")
        if evolution and hasattr(evolution, "record_outcome"):
            await evolution.record_outcome(result)

        return learning

    # ── BiasharaAgent interface ────────────────────────────────────

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Handle an incoming event from the event bus."""
        try:
            result = await self.process_request({
                "type": event.event_type.value,
                "domain": event.source,
                "data": event.payload,
            })
            return AgentResult(success=True, data=result)
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))

    def health_check(self) -> dict:
        """Return engine health status."""
        return {
            "name": self.name,
            "status": self.status.value,
            "initialized": self._initialized,
            "modules_loaded": list(self._modules.keys()),
            "total_cycles": self._cycle_count,
            "avg_cycle_ms": (
                sum(c.duration_ms for c in self._cycle_history) / max(len(self._cycle_history), 1)
                if self._cycle_history else 0
            ),
        }

    def get_module(self, name: str) -> Optional[Any]:
        """Get a domain module by name."""
        return self._modules.get(name)
