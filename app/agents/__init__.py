"""
Biashara Intelligence — Multi-Agent Runtime

Transforms the monolithic service layer into a true multi-agent system.

Agents:
    TransactionProcessor  — Cleans and structures raw M-Pesa / POS data
    IntelligenceGenerator — Runs Soko Pulse, Alama Score, econometrics
    ReportGenerator       — Produces WhatsApp-native reports for workers
    SelfEvolution         — Learns from worker feedback, drives product evolution

Infrastructure:
    EventBus    — Redis Streams for inter-agent communication
    AgentTracer — Observability for every agent decision
    BiasharaAgent — Base class with observe / think / act / reflect lifecycle

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
)

__all__ = [
    # Base
    "BiasharaAgent",
    "EventBus",
    "AgentTracer",
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
    # 12-Factor: Context, Errors, State
    "ContextManager",
    "AgentContextManager",
    "ErrorCompactor",
    "ErrorSeverity",
    "UnifiedStateManager",
]
