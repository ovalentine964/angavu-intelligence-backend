"""
Angavu Intelligence — Multi-Agent Runtime V2

3-Tier Agent Architecture:
    Tier 1: Core agents + MetaAgent (system orchestrator)
    Tier 2: Domain agents (industry-specific intelligence)
    Tier 3: Utility agents (specialized computation)

Agents:
    TransactionProcessor  — Cleans and structures raw M-Pesa / POS data
    IntelligenceGenerator — Runs Soko Pulse, Alama Score, econometrics
    ReportGenerator       — Produces WhatsApp-native reports for workers
    SelfEvolution         — Learns from worker feedback, drives product evolution
    MetaAgent             — System-wide orchestrator and coordinator

Infrastructure:
    EventBus    — Redis Streams for inter-agent communication
    AgentTracer — Observability for every agent decision
    BiasharaAgent — Base class with observe / think / act / reflect lifecycle

Communication Protocols:
    BroadcastProtocol    — EventBus pub/sub
    PointToPointProtocol — Direct agent messaging
    DelegationProtocol   — Task delegation with timeout

Loop Patterns (from agentic AI research):
    ReActAgent       — Reasoning + Acting with explicit trace
    ReflexionAgent   — Self-improvement through self-critique
    PlanExecuteAgent — Multi-step task planning with re-planning
    EventSourcedAgent — Event sourcing for auditability and replay
    SupervisorAgent  — Multi-agent coordination and supervision
    EventStore       — Append-only event store for full audit trail
"""

from app.agents.base import BiasharaAgent
from app.agents.event_bus import EventBus
from app.agents.observability import AgentTracer
from app.agents.implementations import (
    TransactionProcessorAgent,
    IntelligenceGeneratorAgent,
    ReportGeneratorAgent,
    SelfEvolutionAgent,
)
from app.agents.factory import AgentFactory, AgentInfrastructure
from app.agents.context_manager import ContextManager, AgentContextManager
from app.agents.error_compactor import ErrorCompactor, ErrorSeverity
from app.agents.unified_state import UnifiedStateManager
from app.agents.loops import (
    ReActAgent,
    ReflexionAgent,
    PlanExecuteAgent,
    EventSourcedAgent,
    SupervisorAgent,
    EventStore,
    ReActTrace,
    ReasoningStep,
    Critique,
    ExecutionPlan,
    PlanStep,
    SupervisionPolicy,
    SupervisedExecution,
)

# Long-horizon orchestration (DeerFlow-inspired)
from app.agents.long_horizon import (
    LongHorizonOrchestrator,
    TaskPlanner,
    SubAgentDelegator,
    ProgressTracker,
    ResultAggregator,
    LongHorizonTask,
    SubTask,
    TaskCheckpoint,
    TaskStatus,
    SubTaskStatus,
)

# Research flow agents
from app.agents.research_flow import (
    ResearchPlanner,
    DataCollector,
    ResearchAnalyzer,
    ResearchReportGenerator,
    QualityValidator,
    ResearchResultAggregator,
    create_research_orchestrator,
)

# Intelligence pipeline flows
from app.agents.intelligence_pipeline import (
    MarketDataAgent,
    CreditAnalysisAgent,
    DistributionAgent,
    CompetitorAgent,
    create_market_analysis_flow,
    create_credit_scoring_flow,
    create_distribution_analysis_flow,
    create_competitor_analysis_flow,
    create_all_intelligence_flows,
    create_harnessed_flows,
    get_harnessed_intelligence_flows,
    IntelligenceDriftMonitor,
    get_intelligence_drift_monitor,
)

# V2: MetaAgent (Tier 1 system orchestrator)
from app.agents.meta_agent import (
    MetaAgent,
    CapabilityRouter,
    ConflictResolver,
    CrossAgentLearningManager,
    AgentMetrics,
    ConflictRecord,
    LearningShare,
)

# V2: Domain Agents (Tier 2)
from app.agents.domain import (
    AgricultureDomainAgent,
    RetailDomainAgent,
    TransportDomainAgent,
    DigitalDomainAgent,
    ManufacturingDomainAgent,
    ServiceDomainAgent,
)

# V2: Utility Agents (Tier 3)
from app.agents.utility import (
    DataQualityAgent,
    AnomalyDetectorAgent,
    PredictionAgent,
    CommunicationAgent,
    LearningAgent,
    SyncAgent,
)

# V4: Newly Added Agents (Voice, Compliance, Security, Onboarding)
from app.agents.implementations_extra import (
    VoicePipelineAgent,
    ComplianceAgent,
    SecurityAgent,
    OnboardingAgent,
    SocialHandler,
)

# V2: Communication Protocols
from app.agents.communication import (
    BroadcastProtocol,
    PointToPointProtocol,
    DelegationProtocol,
)

# V3: Sub-Agent Orchestration
from app.agents.subagent import (
    SubAgentOrchestrator,
    SubAgentTask,
    SubAgentResult,
    SubAgentCapableMixin,
)

# V3: Task Decomposition
from app.agents.task_decomposition import (
    TaskDecomposer,
    DecompositionPlan,
    DecompositionResult,
    SubTaskDefinition,
)

# V3: Skill Generator
from app.agents.skill_generator import (
    SkillGenerator,
    GeneratedSkill,
)

__all__ = [
    # Base
    "BiasharaAgent",
    "EventBus",
    "AgentTracer",
    # Factory
    "AgentFactory",
    "AgentInfrastructure",
    # Implementations
    "TransactionProcessorAgent",
    "IntelligenceGeneratorAgent",
    "ReportGeneratorAgent",
    "SelfEvolutionAgent",
    # Loop Patterns
    "ReActAgent",
    "ReflexionAgent",
    "PlanExecuteAgent",
    "EventSourcedAgent",
    "SupervisorAgent",
    "EventStore",
    # Data classes
    "ReActTrace",
    "ReasoningStep",
    "Critique",
    "ExecutionPlan",
    "PlanStep",
    "SupervisionPolicy",
    "SupervisedExecution",
    # Long-horizon orchestration
    "LongHorizonOrchestrator",
    "TaskPlanner",
    "SubAgentDelegator",
    "ProgressTracker",
    "ResultAggregator",
    "LongHorizonTask",
    "SubTask",
    "TaskCheckpoint",
    "TaskStatus",
    "SubTaskStatus",
    # Research flow
    "ResearchPlanner",
    "DataCollector",
    "ResearchAnalyzer",
    "ResearchReportGenerator",
    "QualityValidator",
    "ResearchResultAggregator",
    "create_research_orchestrator",
    # Intelligence pipeline agents
    "MarketDataAgent",
    "CreditAnalysisAgent",
    "DistributionAgent",
    "CompetitorAgent",
    "create_market_analysis_flow",
    "create_credit_scoring_flow",
    "create_distribution_analysis_flow",
    "create_competitor_analysis_flow",
    "create_all_intelligence_flows",
    "create_harnessed_flows",
    "get_harnessed_intelligence_flows",
    "IntelligenceDriftMonitor",
    "get_intelligence_drift_monitor",
    # 12-Factor: Context, Errors, State
    "ContextManager",
    "AgentContextManager",
    "ErrorCompactor",
    "ErrorSeverity",
    "UnifiedStateManager",
    # V2: MetaAgent (Tier 1)
    "MetaAgent",
    "CapabilityRouter",
    "ConflictResolver",
    "CrossAgentLearningManager",
    "AgentMetrics",
    "ConflictRecord",
    "LearningShare",
    # V2: Domain Agents (Tier 2)
    "AgricultureDomainAgent",
    "RetailDomainAgent",
    "TransportDomainAgent",
    "DigitalDomainAgent",
    "ManufacturingDomainAgent",
    "ServiceDomainAgent",
    # V2: Utility Agents (Tier 3)
    "DataQualityAgent",
    "AnomalyDetectorAgent",
    "PredictionAgent",
    "CommunicationAgent",
    "LearningAgent",
    "SyncAgent",
    # V2: Communication Protocols
    "BroadcastProtocol",
    "PointToPointProtocol",
    "DelegationProtocol",
    # V3: Sub-Agent Orchestration
    "SubAgentOrchestrator",
    "SubAgentTask",
    "SubAgentResult",
    "SubAgentCapableMixin",
    # V3: Task Decomposition
    "TaskDecomposer",
    "DecompositionPlan",
    "DecompositionResult",
    "SubTaskDefinition",
    # V3: Skill Generator
    "SkillGenerator",
    "GeneratedSkill",
    # V4: Newly Added Agents
    "VoicePipelineAgent",
    "ComplianceAgent",
    "SecurityAgent",
    "OnboardingAgent",
    # V5: Social Handler
    "SocialHandler",
]
