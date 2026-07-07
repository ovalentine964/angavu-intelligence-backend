"""
Loop Systems — Angavu Intelligence.

Agentic loop patterns for structured reasoning, self-correction,
and explicit state management.

Core loops (from loops/core.py):
    ReActAgent, ReflexionAgent, PlanExecuteAgent,
    EventSourcedAgent, SupervisorAgent, EventStore

OODA Loop (from loops/ooda_loop.py):
    OODAAgent — Fast, time-critical decisions with orientation state

Self-Improving Feedback (from loops/feedback_loop.py):
    FeedbackAgent — Learns from every transaction outcome

Human-in-the-Loop (from loops/human_in_the_loop.py):
    HumanInTheLoopAgent — Progressive autonomy and escalation

Additional:
    AgentStateMachine — Explicit state transitions with recovery
"""

# ── Core loops (re-export from core.py) ────────────────────────────
from app.agents.loops.core import (
    Critique,
    EventSourcedAgent,
    EventStore,
    ExecutionPlan,
    PlanExecuteAgent,
    PlanStep,
    ReActAgent,
    ReActTrace,
    ReasoningStep,
    ReflexionAgent,
    SupervisedExecution,
    SupervisionPolicy,
    SupervisorAgent,
)

# ── OODA Loop ──────────────────────────────────────────────────────
from app.agents.loops.ooda_loop import (
    OODAAgent,
    OODACycle,
    OODAMetrics,
    OrientationAxis,
    OrientationState,
)

# ── Self-Improving Feedback Loop ───────────────────────────────────
from app.agents.loops.feedback_loop import (
    ABTestResult,
    FeedbackAgent,
    FeedbackMetrics,
    LearningSignal,
    Pattern,
    SignalType,
    StrategyParameter,
)

# ── Human-in-the-Loop ─────────────────────────────────────────────
from app.agents.loops.human_in_the_loop import (
    AutonomyLevel,
    EscalationReason,
    EscalationRecord,
    HITLMetrics,
    HumanInTheLoopAgent,
    TrustScore,
)

# ── State Machine ──────────────────────────────────────────────────
from app.agents.loops.state_machine import (
    AgentStateMachine,
    StateMachineConfig,
    StateTransition,
    create_agent_state_machine,
)

__all__ = [
    # Core
    "Critique", "EventSourcedAgent", "EventStore", "ExecutionPlan",
    "PlanExecuteAgent", "PlanStep", "ReActAgent", "ReActTrace",
    "ReasoningStep", "ReflexionAgent", "SupervisedExecution",
    "SupervisionPolicy", "SupervisorAgent",
    # OODA Loop
    "OODAAgent", "OODACycle", "OODAMetrics",
    "OrientationAxis", "OrientationState",
    # Feedback Loop
    "ABTestResult", "FeedbackAgent", "FeedbackMetrics",
    "LearningSignal", "Pattern", "SignalType", "StrategyParameter",
    # Human-in-the-Loop
    "AutonomyLevel", "EscalationReason", "EscalationRecord",
    "HITLMetrics", "HumanInTheLoopAgent", "TrustScore",
    # State Machine
    "AgentStateMachine", "StateMachineConfig", "StateTransition",
    "create_agent_state_machine",
]
