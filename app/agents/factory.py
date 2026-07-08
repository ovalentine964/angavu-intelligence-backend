"""
Agent Factory — Creates, wires, and manages agent lifecycle.

Centralizes agent construction with proper service dependency injection,
correct startup ordering, and graceful shutdown. Replaces the inline
agent creation that was previously scattered across main.py lifespan.

V2: Now includes MetaAgent (Tier 1), Domain Agents (Tier 2),
and Utility Agents (Tier 3) in a 3-tier architecture.
V3: Adds MCP/A2A protocol integration and financial agent templates.

Usage:
    factory = AgentFactory()
    infrastructure = await factory.create_all()
    # ... application runs ...
    await factory.shutdown()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import BiasharaAgent, EventType
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

    V2: Added meta_agent, domain_agents, utility_agents, communication protocols.
    """

    event_bus: EventBus
    tracer: AgentTracer
    agents: List[BiasharaAgent]
    agent_map: Dict[str, BiasharaAgent] = field(default_factory=dict)

    # Tier 1: MetaAgent
    meta_agent: Any = None  # MetaAgent | None

    # Tier 2: Domain agents
    domain_agents: List[BiasharaAgent] = field(default_factory=list)

    # Tier 3: Utility agents
    utility_agents: List[BiasharaAgent] = field(default_factory=list)

    # Communication protocols
    broadcast_protocol: Any = None
    p2p_protocol: Any = None
    delegation_protocol: Any = None

    # Optional loop-enhanced infrastructure
    loop_supervisor: Any = None
    loop_event_store: Any = None
    loop_agents: List[BiasharaAgent] = field(default_factory=list)

    # Optional long-horizon orchestration
    intelligence_flows: Dict[str, Any] = field(default_factory=dict)
    research_orchestrator: Any = None

    # DeerFlow integration (deerflow-harness)
    deerflow_factory: Any = None
    deerflow_lead_agent: Any = None

    # V3: Protocol integration
    mcp_server: Any = None          # MCPServer
    mcp_client: Any = None          # MCPClient
    a2a_server: Any = None          # A2AServer
    a2a_client: Any = None          # A2AClient

    # V3: Financial agent templates
    financial_agents: List[BiasharaAgent] = field(default_factory=list)

    # V3: Sub-agent orchestration
    subagent_decomposer: Any = None  # TaskDecomposer
    skill_generator: Any = None      # SkillGenerator

    def __post_init__(self):
        if not self.agent_map:
            self.agent_map = {a.name: a for a in self.agents}


class AgentFactory:
    """
    Creates and wires all Angavu Intelligence agents.

    V2 Architecture — 3 Tiers:
        Tier 1: Core agents (TransactionProcessor, IntelligenceGenerator,
                ReportGenerator, SelfEvolution) + MetaAgent
        Tier 2: Domain agents (Agriculture, Retail, Transport, Digital,
                Manufacturing, Service)
        Tier 3: Utility agents (DataQuality, AnomalyDetector, Prediction,
                Communication, Learning, Sync)

    Startup order:
        1. EventBus (must exist before agents can subscribe)
        2. AgentTracer (observability from the start)
        3. Communication protocols (broadcast, p2p, delegation)
        4. Utility agents (Tier 3 — stateless, no dependencies)
        5. Core agents (Tier 1 — pipeline backbone)
        6. Domain agents (Tier 2 — activated per request)
        7. MetaAgent (Tier 1 — monitors and routes everything)

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
        enable_deerflow: bool = True,
    ) -> AgentInfrastructure:
        """
        Create, wire, and start all agents.

        Args:
            enable_loops: Also create loop-enhanced agents (ReAct, Reflexion, etc.)
            enable_long_horizon: Also create long-horizon orchestration flows

        Returns:
            AgentInfrastructure with all runtime references
        """
        self._logger.info("creating_agent_infrastructure_v2")

        # Load scaling config from settings
        from app.config import get_settings
        settings = get_settings()

        # 1. EventBus with scaling config
        event_bus = EventBus(
            max_consumers_per_group=settings.AGENT_MAX_CONCURRENT // 5,
        )
        await event_bus.connect()
        self._logger.info("event_bus_ready", mode=event_bus.get_stats()["mode"])

        # 2. Tracer
        tracer = AgentTracer()

        # 3. Communication protocols
        from app.agents.communication.broadcast import BroadcastProtocol
        from app.agents.communication.point_to_point import PointToPointProtocol
        from app.agents.communication.delegation import DelegationProtocol

        broadcast_protocol = BroadcastProtocol(event_bus)
        p2p_protocol = PointToPointProtocol(event_bus)
        delegation_protocol = DelegationProtocol(event_bus)

        self._logger.info("communication_protocols_ready")

        # 4. Create Tier 3: Utility agents (stateless, no dependencies)
        utility_agents = self._create_utility_agents()
        self._logger.info("utility_agents_created", count=len(utility_agents))

        # 5. Create Tier 1: Core agents
        transaction_processor = TransactionProcessorAgent()
        intelligence_generator = IntelligenceGeneratorAgent()
        report_generator = ReportGeneratorAgent()
        self_evolution = SelfEvolutionAgent()

        # Wire real services into agents (when available)
        try:
            from app.services.intelligence.soko_pulse import SokoPulseService
            soko_pulse = SokoPulseService()
            intelligence_generator.set_soko_pulse(soko_pulse)
            self._logger.info("soko_pulse_wired_to_agent")
        except (ImportError, Exception) as exc:
            self._logger.info("soko_pulse_not_available", error=str(exc))

        try:
            from app.services.intelligence.alama_score import AlamaScoreService
            alama_score = AlamaScoreService()
            intelligence_generator.set_alama_score(alama_score)
            self._logger.info("alama_score_wired_to_agent")
        except (ImportError, Exception) as exc:
            self._logger.info("alama_score_not_available", error=str(exc))

        core_agents = [
            transaction_processor,
            intelligence_generator,
            report_generator,
            self_evolution,
        ]

        # 6. Create Tier 2: Domain agents
        domain_agents = self._create_domain_agents()
        self._logger.info("domain_agents_created", count=len(domain_agents))

        # 7. Create Tier 1: MetaAgent + New Agents
        meta_agent = self._create_meta_agent()
        new_agents = self._create_new_agents()
        self._logger.info("new_agents_created", count=len(new_agents))

        # 8. Wire all agents together
        all_agents = core_agents + domain_agents + utility_agents + new_agents + [meta_agent]

        # Inject infrastructure into all agents
        for agent in all_agents:
            agent.set_event_bus(event_bus)
            agent.set_tracer(tracer)

        # 9. Register all agents with MetaAgent
        for agent in all_agents:
            if agent.name != "MetaAgent":
                meta_agent.register_agent(agent)

        # 9b. Wire SubAgentCapableMixin agents to SubAgentOrchestrator
        for agent in all_agents:
            if hasattr(agent, 'get_or_create_orchestrator'):
                agent.get_or_create_orchestrator()

        # 10. Subscribe agents to event types
        await self._subscribe_agents(event_bus, core_agents, domain_agents + new_agents, meta_agent)

        # 11. Wire reflect→behavior feedback loops
        self._wire_reflect_loops(core_agents)

        # 12. Start agents in dependency order
        # Tier 3 first (stateless)
        for agent in utility_agents:
            await agent.start()

        # Tier 1 core
        for agent in core_agents:
            await agent.start()

        # Tier 2 domain
        for agent in domain_agents:
            await agent.start()

        # MetaAgent last (needs all others registered)
        await meta_agent.start()

        self._logger.info(
            "all_agents_started",
            core=len(core_agents),
            domain=len(domain_agents),
            utility=len(utility_agents),
            meta=1,
        )

        # Build infrastructure container
        infrastructure = AgentInfrastructure(
            event_bus=event_bus,
            tracer=tracer,
            agents=core_agents,
            meta_agent=meta_agent,
            domain_agents=domain_agents + new_agents,
            utility_agents=utility_agents,
            broadcast_protocol=broadcast_protocol,
            p2p_protocol=p2p_protocol,
            delegation_protocol=delegation_protocol,
        )

        # 13. Optional: loop-enhanced agents
        if enable_loops:
            infrastructure = await self._attach_loop_agents(
                infrastructure, event_bus, tracer,
            )

        # 14. Optional: long-horizon orchestration
        if enable_long_horizon:
            infrastructure = await self._attach_long_horizon(
                infrastructure, event_bus, tracer,
            )

        # 15. Optional: DeerFlow integration (deerflow-harness)
        if enable_deerflow:
            infrastructure = await self._attach_deerflow(
                infrastructure, event_bus, tracer,
            )

        # 16. Attach MCP/A2A protocols
        infrastructure = await self._attach_protocols(infrastructure, event_bus, tracer)

        # 17. Create financial agent templates
        infrastructure = await self._attach_financial_agents(infrastructure, event_bus, tracer)

        # 18. Attach sub-agent orchestration and skill generation
        infrastructure = await self._attach_subagent_infrastructure(infrastructure, event_bus, tracer)

        self._infrastructure = infrastructure
        total_agents = (
            len(core_agents) + len(domain_agents) + len(new_agents) + len(utility_agents) + 1
            + len(infrastructure.financial_agents)
        )
        self._logger.info(
            "agent_infrastructure_v3_ready",
            total_agents=total_agents,
            core_agents=len(core_agents),
            domain_agents=len(domain_agents),
            utility_agents=len(utility_agents),
            meta_agent=1,
            financial_agents=len(infrastructure.financial_agents),
            loop_agents=len(infrastructure.loop_agents),
            flows=list(infrastructure.intelligence_flows.keys()),
            has_deerflow=infrastructure.deerflow_factory is not None,
            has_mcp=infrastructure.mcp_server is not None,
            has_a2a=infrastructure.a2a_server is not None,
            has_subagent_decomposer=infrastructure.subagent_decomposer is not None,
            has_skill_generator=infrastructure.skill_generator is not None,
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
        self._logger.info("shutting_down_agent_infrastructure_v3")

        # Stop MetaAgent first (it orchestrates everything)
        if infra.meta_agent:
            try:
                await infra.meta_agent.stop()
            except (RuntimeError, OSError) as exc:
                self._logger.warning("meta_agent_stop_error", error=str(exc))

        # Stop long-horizon agents
        if infra.research_orchestrator:
            try:
                for agent in infra.research_orchestrator.delegator._agents.values():
                    await agent.stop()
            except (RuntimeError, OSError, AttributeError) as exc:
                self._logger.warning("research_orchestrator_stop_error", error=str(exc))

        for flow_name, orch in infra.intelligence_flows.items():
            try:
                for agent in orch.delegator._agents.values():
                    await agent.stop()
            except (RuntimeError, OSError, AttributeError) as exc:
                self._logger.warning("intelligence_flow_stop_error", flow=flow_name, error=str(exc))

        # Stop loop-enhanced agents
        for agent in reversed(infra.loop_agents):
            try:
                await agent.stop()
            except (RuntimeError, OSError) as exc:
                self._logger.warning("loop_agent_stop_error", agent=agent.name, error=str(exc))

        # Stop domain agents (Tier 2)
        for agent in reversed(infra.domain_agents):
            try:
                await agent.stop()
            except (RuntimeError, OSError) as exc:
                self._logger.warning("domain_agent_stop_error", agent=agent.name, error=str(exc))

        # Stop utility agents (Tier 3)
        for agent in reversed(infra.utility_agents):
            try:
                await agent.stop()
            except (RuntimeError, OSError) as exc:
                self._logger.warning("utility_agent_stop_error", agent=agent.name, error=str(exc))

        # Stop core agents in reverse order
        for agent in reversed(infra.agents):
            try:
                await agent.stop()
            except (RuntimeError, OSError) as exc:
                self._logger.warning("core_agent_stop_error", agent=agent.name, error=str(exc))

        # Stop financial agents
        for agent in reversed(infra.financial_agents):
            try:
                await agent.stop()
            except (RuntimeError, OSError) as exc:
                self._logger.warning("financial_agent_stop_error", agent=agent.name, error=str(exc))

        # Disconnect event bus
        await infra.event_bus.disconnect()

        self._logger.info("agent_infrastructure_v3_shutdown_complete")
        self._infrastructure = None

    # ── Agent Creation ──────────────────────────────────────────────

    def _create_meta_agent(self):
        """Create the MetaAgent (Tier 1 system orchestrator)."""
        from app.agents.meta_agent import MetaAgent
        return MetaAgent()

    def _create_domain_agents(self) -> List[BiasharaAgent]:
        """Create Tier 2 domain agents."""
        from app.agents.domain import (
            AgricultureDomainAgent,
            RetailDomainAgent,
            TransportDomainAgent,
            DigitalDomainAgent,
            ManufacturingDomainAgent,
            ServiceDomainAgent,
        )

        return [
            AgricultureDomainAgent(),
            RetailDomainAgent(),
            TransportDomainAgent(),
            DigitalDomainAgent(),
            ManufacturingDomainAgent(),
            ServiceDomainAgent(),
        ]

    def _create_utility_agents(self) -> List[BiasharaAgent]:
        """Create Tier 3 utility agents."""
        from app.agents.utility import (
            DataQualityAgent,
            AnomalyDetectorAgent,
            PredictionAgent,
            CommunicationAgent,
            LearningAgent,
            SyncAgent,
        )

        return [
            DataQualityAgent(),
            AnomalyDetectorAgent(),
            PredictionAgent(),
            CommunicationAgent(),
            LearningAgent(),
            SyncAgent(),
        ]

    def _create_new_agents(self) -> List[BiasharaAgent]:
        """Create newly identified agents: Voice, Compliance, Security, Onboarding."""
        from app.agents.implementations_extra import (
            VoicePipelineAgent,
            ComplianceAgent,
            SecurityAgent,
            OnboardingAgent,
        )

        return [
            VoicePipelineAgent(),
            ComplianceAgent(),
            SecurityAgent(),
            OnboardingAgent(),
        ]

    # ── Internal wiring ────────────────────────────────────────────

    async def _subscribe_agents(
        self,
        event_bus: EventBus,
        core_agents: List[BiasharaAgent],
        domain_agents: List[BiasharaAgent],
        meta_agent: BiasharaAgent,
    ) -> None:
        """Subscribe each agent to its relevant event types."""
        # Core agent subscriptions
        core_subscription_map = {
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

        for agent in core_agents:
            event_types = core_subscription_map.get(agent.name, [])
            if event_types:
                await event_bus.subscribe(agent, event_types)

        # New agent subscriptions (Voice, Compliance, Security, Onboarding)
        new_subscription_map = {
            "VoicePipeline": [
                EventType.VOICE_INPUT_RECEIVED,
                EventType.REPORT_GENERATED,
            ],
            "ComplianceAgent": [
                EventType.COMPLIANCE_CHECK,
                EventType.TRANSACTION_PROCESSED,
                EventType.INTELLIGENCE_GENERATED,
                EventType.REPORT_GENERATED,
                EventType.DOMAIN_ANALYSIS_COMPLETED,
            ],
            "SecurityAgent": [
                EventType.SECURITY_SCAN,
                EventType.TRANSACTION_PROCESSED,
                EventType.PIPELINE_ERROR,
                EventType.VOICE_INPUT_RECEIVED,
            ],
            "OnboardingAgent": [
                EventType.ONBOARDING_STARTED,
                EventType.ONBOARDING_STEP_COMPLETED,
                EventType.ONBOARDING_VERIFICATION,
                EventType.ONBOARDING_FEEDBACK,
            ],
        }

        for agent in domain_agents:
            if agent.name in new_subscription_map:
                await event_bus.subscribe(agent, new_subscription_map[agent.name])
            else:
                # Standard domain agent subscriptions
                domain_event_types = [
                    EventType.DOMAIN_ANALYSIS_REQUESTED,
                    EventType.INTELLIGENCE_REQUESTED,
                    EventType.TRANSACTION_PROCESSED,
                    EventType.COMPLIANCE_CHECK,
                    EventType.SECURITY_SCAN,
                ]
                await event_bus.subscribe(agent, domain_event_types)

        # MetaAgent subscribes to system-wide events
        meta_event_types = [
            EventType.TRANSACTION_PROCESSED,
            EventType.INTELLIGENCE_REQUESTED,
            EventType.CONFLICT_DETECTED,
            EventType.AGENT_HEALTH_CHECK,
            EventType.PIPELINE_ERROR,
            EventType.DOMAIN_ANALYSIS_COMPLETED,
            EventType.MARKET_ALERT,
            # New event types for MetaAgent oversight
            EventType.COMPLIANCE_VIOLATION,
            EventType.SECURITY_ALERT,
            EventType.SECURITY_INCIDENT,
            EventType.ONBOARDING_COMPLETED,
            EventType.VOICE_TRANSCRIBED,
        ]
        await event_bus.subscribe(meta_agent, meta_event_types)

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
        except (ImportError, AttributeError, RuntimeError) as exc:
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
        except (ImportError, AttributeError, RuntimeError) as exc:
            self._logger.warning("long_horizon_setup_failed", error=str(exc))

        return infrastructure

    async def _attach_protocols(
        self,
        infrastructure: AgentInfrastructure,
        event_bus: EventBus,
        tracer: AgentTracer,
    ) -> AgentInfrastructure:
        """Create and attach MCP and A2A protocol servers/clients."""
        try:
            from app.agents.protocols.mcp import (
                MCPServer,
                MCPClient,
                create_angavu_mcp_tools,
            )
            from app.agents.protocols.a2a import (
                A2AServer,
                A2AClient,
                create_angavu_agent_card,
            )

            # MCP Server — expose Angavu tools
            mcp_server = MCPServer()
            mcp_tools = create_angavu_mcp_tools()
            mcp_server.register_tools(mcp_tools)

            # MCP Client — consume external servers
            mcp_client = MCPClient()
            MCPClient.register_local_server(mcp_server)

            # A2A Server — accept tasks from external agents
            agent_card = create_angavu_agent_card()
            a2a_server = A2AServer(agent_card=agent_card)

            # A2A Client — delegate to external agents
            a2a_client = A2AClient()

            infrastructure.mcp_server = mcp_server
            infrastructure.mcp_client = mcp_client
            infrastructure.a2a_server = a2a_server
            infrastructure.a2a_client = a2a_client

            self._logger.info(
                "protocols_attached",
                mcp_tools=len(mcp_tools),
                a2a_capabilities=len(agent_card.capabilities),
            )
        except (ImportError, AttributeError, RuntimeError) as exc:
            self._logger.warning("protocols_setup_failed", error=str(exc))

        return infrastructure

    async def _attach_financial_agents(
        self,
        infrastructure: AgentInfrastructure,
        event_bus: EventBus,
        tracer: AgentTracer,
    ) -> AgentInfrastructure:
        """Create and attach financial agent templates."""
        try:
            from app.agents.templates.financial import (
                create_all_financial_agents,
                get_financial_agent_mcp_tools,
            )

            financial_agents = create_all_financial_agents()

            # Wire into infrastructure
            for agent in financial_agents:
                agent.set_event_bus(event_bus)
                agent.set_tracer(tracer)
                await event_bus.subscribe(agent, [
                    EventType.TRANSACTION_PROCESSED,
                    EventType.INTELLIGENCE_REQUESTED,
                    EventType.DOMAIN_ANALYSIS_REQUESTED,
                ])
                await agent.start()

            # Register financial MCP tools
            if infrastructure.mcp_server:
                fin_tools = get_financial_agent_mcp_tools()
                infrastructure.mcp_server.register_tools(fin_tools)

            infrastructure.financial_agents = financial_agents

            self._logger.info(
                "financial_agents_attached",
                count=len(financial_agents),
                names=[a.name for a in financial_agents],
            )
        except (ImportError, AttributeError, RuntimeError) as exc:
            self._logger.warning("financial_agents_setup_failed", error=str(exc))

        return infrastructure

    async def _attach_subagent_infrastructure(
        self,
        infrastructure: AgentInfrastructure,
        event_bus: EventBus,
        tracer: AgentTracer,
    ) -> AgentInfrastructure:
        """Create and attach sub-agent orchestration and skill generation."""
        try:
            from app.agents.subagent import SubAgentOrchestrator
            from app.agents.task_decomposition import create_financial_task_decomposer
            from app.agents.skill_generator import SkillGenerator

            # Create task decomposer with financial handlers
            task_decomposer = create_financial_task_decomposer()

            # Create skill generator
            skill_generator = SkillGenerator()

            # Store on infrastructure for API access
            infrastructure.subagent_decomposer = task_decomposer  # type: ignore
            infrastructure.skill_generator = skill_generator  # type: ignore

            self._logger.info(
                "subagent_infrastructure_attached",
                decomposer_handlers=len(task_decomposer.get_registered_handlers()),
            )
        except (ImportError, AttributeError, RuntimeError) as exc:
            self._logger.warning("subagent_infrastructure_setup_failed", error=str(exc))

        return infrastructure

    async def _attach_deerflow(
        self,
        infrastructure: AgentInfrastructure,
        event_bus: EventBus,
        tracer: AgentTracer,
    ) -> AgentInfrastructure:
        """
        Create and attach DeerFlow-powered agents via deerflow-harness.

        Uses DeerFlow's create_deerflow_agent factory to create LangGraph
        agents with Angavu tools. Falls back gracefully if deerflow-harness
        is not installed.
        """
        try:
            from app.deerflow.integration import BiasharaAgentFactory

            df_factory = BiasharaAgentFactory()

            # Create domain agents using DeerFlow's factory
            domain_agent_names = ["research", "credit", "distribution", "fmcg", "health", "development"]
            for agent_name in domain_agent_names:
                try:
                    df_factory.create_domain_agent(agent_name)
                except (ImportError, RuntimeError, ValueError) as e:
                    self._logger.warning("deerflow_domain_agent_failed", agent=agent_name, error=str(e))

            # Create lead agent
            try:
                df_factory.create_lead_agent()
            except (ImportError, RuntimeError, ValueError) as e:
                self._logger.warning("deerflow_lead_agent_failed", error=str(e))

            infrastructure.deerflow_factory = df_factory
            infrastructure.deerflow_lead_agent = df_factory.get_lead_agent()

            created = df_factory.list_agents()
            self._logger.info(
                "deerflow_agents_attached",
                domain_agents=created,
                has_lead=df_factory.get_lead_agent() is not None,
            )

        except ImportError:
            self._logger.info("deerflow_harness_not_installed_skipping")
        except (RuntimeError, AttributeError) as exc:
            self._logger.warning("deerflow_setup_failed", error=str(exc))

        return infrastructure
