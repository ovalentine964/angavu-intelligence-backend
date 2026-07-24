"""
Agent Factory — Creates and wires agent infrastructure.

Delegates to the SuperagentEngine for actual intelligence,
while providing the AgentInfrastructure interface that main.py expects.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

from app.agents.base import BiasharaAgent
from app.agents.event_bus import EventBus
from app.agents.observability import AgentTracer
from app.agents.loops import EventStore

logger = structlog.get_logger(__name__)


@dataclass
class AgentInfrastructure:
    """Container for all agent infrastructure components."""
    event_bus: EventBus
    tracer: AgentTracer
    agents: list[BiasharaAgent] = field(default_factory=list)
    agent_map: dict[str, BiasharaAgent] = field(default_factory=dict)

    # Optional components
    meta_agent: Optional[Any] = None
    domain_agents: list[Any] = field(default_factory=list)
    utility_agents: list[Any] = field(default_factory=list)
    broadcast_protocol: Optional[Any] = None
    p2p_protocol: Optional[Any] = None
    delegation_protocol: Optional[Any] = None

    # DeerFlow
    deerflow_factory: Optional[Any] = None
    deerflow_lead_agent: Optional[Any] = None

    # Loop infrastructure
    loop_supervisor: Optional[Any] = None
    loop_event_store: Optional[EventStore] = None
    loop_agents: list[Any] = field(default_factory=list)

    # Long-horizon
    intelligence_flows: Optional[Any] = None
    research_orchestrator: Optional[Any] = None


class AgentFactory:
    """
    Creates and wires all agent infrastructure.

    In the new superagent architecture, this factory delegates to
    the SuperagentEngine while maintaining the interface that
    main.py and the API layer expect.
    """

    def __init__(self):
        self._infrastructure: Optional[AgentInfrastructure] = None
        self._superagent = None

    async def create_all(
        self,
        enable_loops: bool = True,
        enable_long_horizon: bool = True,
    ) -> AgentInfrastructure:
        """
        Create and wire all agent infrastructure.

        Returns an AgentInfrastructure with all components initialized.
        """
        # Core infrastructure
        event_bus = EventBus()
        tracer = AgentTracer()

        # Create the SuperagentEngine
        from app.superagent.core.reasoning_engine import SuperagentEngine

        superagent = SuperagentEngine(
            event_bus=event_bus,
            tracer=tracer,
        )
        await superagent.initialize()
        self._superagent = superagent

        # Create loop infrastructure
        loop_event_store = None
        loop_agents = []
        loop_supervisor = None

        if enable_loops:
            loop_event_store = EventStore()
            from app.agents.loops.ooda_loop import OODAAgent
            from app.agents.loops.feedback_loop import FeedbackAgent
            from app.agents.loops.human_in_the_loop import HumanInTheLoopAgent

            ooda = OODAAgent(name="SuperagentOODA", superagent=superagent)
            feedback = FeedbackAgent(name="SuperagentFeedback", superagent=superagent)
            hitl = HumanInTheLoopAgent(name="SuperagentHITL")
            loop_agents = [ooda, feedback, hitl]

            # Simple loop supervisor
            class _LoopSupervisor:
                def __init__(self, agents, event_store):
                    self.agents = agents
                    self.event_store = event_store
                    self._history = []

                async def supervise(self, task: str, context: dict = None):
                    result = {"task": task, "status": "completed", "agents": []}
                    for agent in self.agents:
                        try:
                            agent_result = await agent.execute({"task": task, **(context or {})})
                            result["agents"].append({"name": agent.name, "success": True})
                        except Exception as e:
                            result["agents"].append({"name": agent.name, "error": str(e)})
                    self._history.append(result)
                    return result

                def get_stats(self):
                    return {
                        "total_supervised": len(self._history),
                        "agents": [a.name for a in self.agents],
                    }

            loop_supervisor = _LoopSupervisor(loop_agents, loop_event_store)

        # Build infrastructure
        infra = AgentInfrastructure(
            event_bus=event_bus,
            tracer=tracer,
            agents=[superagent],
            agent_map={"SuperagentEngine": superagent},
            meta_agent=superagent,
            domain_agents=[],
            utility_agents=[],
            loop_supervisor=loop_supervisor,
            loop_event_store=loop_event_store,
            loop_agents=loop_agents,
        )

        self._infrastructure = infra
        logger.info(
            "agent_infrastructure_created",
            agents=len(infra.agents),
            loop_agents=len(loop_agents),
        )
        return infra

    async def shutdown(self):
        """Gracefully shutdown all agents."""
        if self._superagent:
            logger.info("superagent_shutdown")
        logger.info("agent_factory_shutdown_complete")
