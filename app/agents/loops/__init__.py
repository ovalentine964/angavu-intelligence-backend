"""
Loop Systems — Angavu Intelligence.

Agentic loop patterns for structured reasoning, self-correction,
and explicit state management.

Core loops (from loops/core.py):
    ReActAgent, ReflexionAgent, PlanExecuteAgent,
    EventSourcedAgent, SupervisorAgent, EventStore

Additional:
    AgentStateMachine — Explicit state transitions with recovery

Removed (stub patterns with no users — re-add when needed):
    TreeOfThoughts, ConstitutionalAI, HITL
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
    # State Machine
    "AgentStateMachine", "StateMachineConfig", "StateTransition",
    "create_agent_state_machine",
]
