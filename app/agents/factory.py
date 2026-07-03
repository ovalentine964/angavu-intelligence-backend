"""
Agent Factory — Creates, wires, and manages agent lifecycle.

Centralizes agent construction with proper service dependency injection,
correct startup ordering, and graceful shutdown. Replaces the inline
agent creation that was previously scattered across main.py lifespan.

Usage:
    factory = AgentFactory()
    infrastructure = await factory.create_all()
    # ... application runs ...
    await factory.shutdown()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import AgentEvent, BiasharaAgent, EventType
from app.agents.event_bus import EventBus
from app.agents.observability import AgentTracer
from app.agents.implementations import (
    IntelligenceGeneratorAgent,
    ReportGeneratorAgent,
    SelfEvolutionAgent,
    TransactionProcessorAgent,
)

logger = structlog.get_logger(__name__)


@dataclass
class AgentInfrastructure:
    """
    Container for all agent runtime artifacts.

    Returned by AgentFactory.create_all() and stored on app.state
    for API access and health checks.
    """

    event_bus: EventBus
    tracer: AgentTracer
    agents: List[BiasharaAgent]
    agent_map: Dict[str, BiasharaAgent] = field(default_factory=dict)

    # Optional loop-enhanced infrastructure
    loop_supervisor: Any = None
    loop_event_store: Any = None
    loop_agents: List[BiasharaAgent] = field(default_factory=list)

    # Optional long-horizon orchestration
    intelligence_flows: Dict[str, Any] = field(default_factory=dict)
    research_orchestrator: Any = None

    def __post_init__(self):
        if not self.agent_map:
            self.agent_map = {a.name: a for a in self.agents}


class AgentFactory:
    """
    Creates and wires all Biashara Intelligence agents.

    Responsibilities:
    - Construct EventBus with Redis Streams (or in-memory fallback)
    - Create agents with proper service dependencies
    - Subscribe agents to their event types
    - Wire reflect→behavior feedback loops
    - Start agents in correct dependency order
    - Handle graceful shutdown in reverse order

    Startup order:
        1. EventBus (must exist before agents can subscribe)
        2. AgentTracer (observability from the start)
        3. TransactionProcessor (first in pipeline)
        4. IntelligenceGenerator (depends on processed transactions)
        5. ReportGenerator (depends on intelligence)
        6. SelfEvolution (depends on report delivery + feedback)

    Shutdown order: reverse of startup.
    """

    def __init__(self):
        self._infrastructure: Optional[AgentInfrastructure] = None
        self._logger = logger.bind(component="agent_factory")

    async def create_all(
        self,
        *,
        enable_loops: bool = True,
        enable_long_horizon: bool = True,
    ) -> AgentInfrastructure:
        """
        Create, wire, and start all agents.

        Args:
            enable_loops: Also create loop-enhanced agents (ReAct, Reflexion, etc.)
            enable_long_horizon: Also create long-horizon orchestration flows

        Returns:
            AgentInfrastructure with all runtime references
        """
        self._logger.info("creating_agent_infrastructure")

        # 1. EventBus
        event_bus = EventBus()
        await event_bus.connect()
        self._logger.info("event_bus_ready", mode=event_bus.get_stats()["mode"])

        # 2. Tracer
        tracer = AgentTracer()

        # 3. Create core agents
        transaction_processor = TransactionProcessorAgent()
        intelligence_generator = IntelligenceGeneratorAgent()
        report_generator = ReportGeneratorAgent()
        self_evolution = SelfEvolutionAgent()

        agents = [
            transaction_processor,
            intelligence_generator,
            report_generator,
            self_evolution,
        ]

        # 4. Inject infrastructure
        for agent in agents:
            agent.set_event_bus(event_bus)
            agent.set_tracer(tracer)

        # 5. Subscribe agents to event types
        await self._subscribe_agents(event_bus, agents)

        # 6. Wire reflect→behavior feedback loops
        self._wire_reflect_loops(agents)

        # 7. Start agents in dependency order
        for agent in agents:
            await agent.start()

        self._logger.info("core_agents_started", count=len(agents))

        # Build infrastructure container
        infrastructure = AgentInfrastructure(
            event_bus=event_bus,
            tracer=tracer,
            agents=agents,
        )

        # 8. Optional: loop-enhanced agents
        if enable_loops:
            infrastructure = await self._attach_loop_agents(
                infrastructure, event_bus, tracer,
            )

        # 9. Optional: long-horizon orchestration
        if enable_long_horizon:
            infrastructure = await self._attach_long_horizon(
                infrastructure, event_bus, tracer,
            )

        self._infrastructure = infrastructure
        self._logger.info(
            "agent_infrastructure_ready",
            core_agents=len(agents),
            loop_agents=len(infrastructure.loop_agents),
            flows=list(infrastructure.intelligence_flows.keys()),
        )

        return infrastructure

    async def shutdown(self) -> None:
        """
        Gracefully stop all agents and disconnect infrastructure.

        Stops agents in reverse order so downstream agents can
        process any in-flight events before the upstream agents stop.
        """
        if not self._infrastructure:
            return

        infra = self._infrastructure
        self._logger.info("shutting_down_agent_infrastructure")

        # Stop long-horizon agents first (they depend on core agents)
        if infra.research_orchestrator:
            try:
                for agent in infra.research_orchestrator.delegator._agents.values():
                    await agent.stop()
            except Exception as exc:
                self._logger.warning("research_orchestrator_stop_error", error=str(exc))

        for flow_name, orch in infra.intelligence_flows.items():
            try:
                for agent in orch.delegator._agents.values():
                    await agent.stop()
            except Exception as exc:
                self._logger.warning("intelligence_flow_stop_error", flow=flow_name, error=str(exc))

        # Stop loop-enhanced agents
        for agent in reversed(infra.loop_agents):
            try:
                await agent.stop()
            except Exception as exc:
                self._logger.warning("loop_agent_stop_error", agent=agent.name, error=str(exc))

        # Stop core agents in reverse order
        for agent in reversed(infra.agents):
            try:
                await agent.stop()
            except Exception as exc:
                self._logger.warning("core_agent_stop_error", agent=agent.name, error=str(exc))

        # Disconnect event bus
        await infra.event_bus.disconnect()

        self._logger.info("agent_infrastructure_shutdown_complete")
        self._infrastructure = None

    # ── Internal wiring ────────────────────────────────────────────

    async def _subscribe_agents(
        self,
        event_bus: EventBus,
        agents: List[BiasharaAgent],
    ) -> None:
        """Subscribe each agent to its relevant event types."""
        subscription_map = {
            "TransactionProcessor": [
                EventType.TRANSACTION_RECEIVED,
                EventType.BATCH_PROCESSED,
            ],
            "IntelligenceGenerator": [
                EventType.TRANSACTION_PROCESSED,
                EventType.INTELLIGENCE_REQUESTED,
                EventType.MARKET_ALERT,
            ],
            "ReportGenerator": [
                EventType.INTELLIGENCE_GENERATED,
                EventType.REPORT_REQUESTED,
                EventType.REPORT_DELIVERED,
            ],
            "SelfEvolution": [
                EventType.FEEDBACK_RECEIVED,
                EventType.REPORT_DELIVERED,
                EventType.EVOLUTION_CYCLE_COMPLETE,
            ],
        }

        for agent in agents:
            event_types = subscription_map.get(agent.name, [])
            if event_types:
                await event_bus.subscribe(agent, event_types)

    def _wire_reflect_loops(self, agents: List[BiasharaAgent]) -> None:
        """
        Wire reflect→behavior feedback loops on agents.

        After reflect(), agents adjust their future behavior:
        - IntelligenceGenerator: adjusts confidence thresholds
        - TransactionProcessor: tracks error patterns for retries
        """
        agent_map = {a.name: a for a in agents}

        # IntelligenceGenerator: adaptive confidence
        intel = agent_map.get("IntelligenceGenerator")
        if intel:
            orig_reflect = intel.reflect

            async def _adaptive_intel_reflect(result):
                await orig_reflect(result)
                recent = intel.memory.recall_recent(20)
                successes = [r for r in recent if r.get("success", True)]
                if len(recent) >= 5:
                    success_rate = len(successes) / len(recent)
                    new_confidence = max(0.5, min(0.99, success_rate))
                    intel.memory.store("adaptive_base_confidence", new_confidence)
                    if success_rate < 0.7:
                        intel._logger.warning(
                            "low_success_rate_adjusting",
                            success_rate=round(success_rate, 2),
                            new_base_confidence=round(new_confidence, 2),
                        )

            intel.reflect = _adaptive_intel_reflect

        # TransactionProcessor: error pattern tracking
        txn = agent_map.get("TransactionProcessor")
        if txn:
            orig_reflect = txn.reflect

            async def _adaptive_tp_reflect(result):
                await orig_reflect(result)
                if not result.success:
                    txn.memory.store(
                        "last_error",
                        {"error": result.error, "timestamp": __import__("time").time()},
                    )

            txn.reflect = _adaptive_tp_reflect

        self._logger.info("reflect_behavior_loops_wired")

    async def _attach_loop_agents(
        self,
        infrastructure: AgentInfrastructure,
        event_bus: EventBus,
        tracer: AgentTracer,
    ) -> AgentInfrastructure:
        """Create and attach loop-enhanced agents."""
        try:
            from app.agents.loops import EventStore
            from app.agents.loop_implementations import create_loop_enhanced_agents

            loop_event_store = EventStore()
            loop_infra = create_loop_enhanced_agents(event_store=loop_event_store)

            for agent in loop_infra["agents"]:
                agent.set_event_bus(event_bus)
                agent.set_tracer(tracer)

            # Subscribe loop agents to same event types
            loop_subscriptions = {
                "TransactionProcessor": [
                    EventType.TRANSACTION_RECEIVED,
                    EventType.BATCH_PROCESSED,
                ],
                "IntelligenceGenerator": [
                    EventType.TRANSACTION_PROCESSED,
                    EventType.INTELLIGENCE_REQUESTED,
                    EventType.MARKET_ALERT,
                ],
                "ReportGenerator": [
                    EventType.INTELLIGENCE_GENERATED,
                    EventType.REPORT_REQUESTED,
                    EventType.REPORT_DELIVERED,
                ],
                "SelfEvolution": [
                    EventType.FEEDBACK_RECEIVED,
                    EventType.REPORT_DELIVERED,
                    EventType.EVOLUTION_CYCLE_COMPLETE,
                ],
            }

            for agent in loop_infra["agents"]:
                event_types = loop_subscriptions.get(agent.name, [])
                if event_types:
                    await event_bus.subscribe(agent, event_types)

            for agent in loop_infra["agents"]:
                await agent.start()

            infrastructure.loop_supervisor = loop_infra["supervisor"]
            infrastructure.loop_event_store = loop_event_store
            infrastructure.loop_agents = loop_infra["agents"]

            self._logger.info("loop_agents_attached", count=len(loop_infra["agents"]))
        except Exception as exc:
            self._logger.warning("loop_agents_setup_failed", error=str(exc))

        return infrastructure

    async def _attach_long_horizon(
        self,
        infrastructure: AgentInfrastructure,
        event_bus: EventBus,
        tracer: AgentTracer,
    ) -> AgentInfrastructure:
        """Create and attach long-horizon orchestration flows."""
        try:
            from app.agents.intelligence_pipeline import create_all_intelligence_flows
            from app.agents.research_flow import create_research_orchestrator

            event_store = infrastructure.loop_event_store
            intelligence_flows = create_all_intelligence_flows(event_store=event_store)
            research_orchestrator = create_research_orchestrator(event_store=event_store)

            # Wire intelligence flow agents
            for flow_name, orch in intelligence_flows.items():
                for agent in orch.delegator._agents.values():
                    agent.set_event_bus(event_bus)
                    agent.set_tracer(tracer)
                    await event_bus.subscribe(agent, [
                        EventType.INTELLIGENCE_REQUESTED,
                        EventType.MARKET_ALERT,
                    ])

            # Wire research flow agents
            for agent in research_orchestrator.delegator._agents.values():
                agent.set_event_bus(event_bus)
                agent.set_tracer(tracer)
                await event_bus.subscribe(agent, [
                    EventType.INTELLIGENCE_REQUESTED,
                    EventType.MARKET_ALERT,
                ])

            infrastructure.intelligence_flows = intelligence_flows
            infrastructure.research_orchestrator = research_orchestrator

            self._logger.info(
                "long_horizon_attached",
                flows=list(intelligence_flows.keys()),
            )
        except Exception as exc:
            self._logger.warning("long_horizon_setup_failed", error=str(exc))

        return infrastructure
