"""
Loop Systems — Biashara Intelligence.

Agentic loop patterns for structured reasoning, self-correction,
human feedback, and explicit state management.

Core loops (from loops/core.py):
    ReActAgent, ReflexionAgent, PlanExecuteAgent,
    EventSourcedAgent, SupervisorAgent, EventStore

Phase 1 additions:
    TreeOfThoughtsAgent  — Multi-path reasoning with branch evaluation
    HITLManager          — Human-in-the-loop feedback integration
    ConstitutionalAgent  — Principle-based self-correction
    AgentStateMachine    — Explicit state transitions with recovery
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

# ── Phase 1: Tree of Thoughts ──────────────────────────────────────
from app.agents.loops.tree_of_thoughts import (
    ThoughtNode,
    TreeOfThoughtsAgent,
)

# ── Phase 1: HITL ─────────────────────────────────────────────────
from app.agents.loops.hitl import (
    FeedbackType,
    HITLManager,
    HumanFeedback,
)

# ── Phase 1: Constitutional AI ─────────────────────────────────────
from app.agents.loops.constitutional import (
    ComplianceResult,
    ConstitutionalAgent,
    Principle,
)

# ── Phase 1: State Machine ─────────────────────────────────────────
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
    # Tree of Thoughts
    "ThoughtNode", "TreeOfThoughtsAgent",
    # HITL
    "FeedbackType", "HITLManager", "HumanFeedback",
    # Constitutional AI
    "ComplianceResult", "ConstitutionalAgent", "Principle",
    # State Machine
    "AgentStateMachine", "StateMachineConfig", "StateTransition",
    "create_agent_state_machine",
]
