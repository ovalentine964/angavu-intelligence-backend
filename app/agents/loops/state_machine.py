"""
State Machine — Explicit state transitions for agent lifecycle.

Makes agent lifecycle transitions explicit, auditable, and recoverable.
Instead of implicit state changes, every transition is a named event
with guards and actions.

States for Biashara agents:
    idle -> observing -> thinking -> acting -> reflecting -> idle
    With error recovery and timeout handling.

Features:
    - Named states with clear semantics
    - Guarded transitions (conditions that must hold)
    - Entry/exit actions (side effects on transitions)
    - Timeout handling (auto-transition on stuck states)
    - Full transition history (audit trail)
    - State persistence (crash recovery)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Union

import structlog

logger = structlog.get_logger(__name__)

# Type alias for sync or async callables
ActionFn = Union[
    Callable[[Dict[str, Any]], None],
    Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
]
GuardFn = Callable[[Dict[str, Any]], bool]


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


@dataclass
class StateTransition:
    """A transition between states."""
    from_state: str
    to_state: str
    trigger: str
    guard: Optional[GuardFn] = None
    action: Optional[ActionFn] = None
    priority: int = 0

    def can_fire(self, context: Dict[str, Any]) -> bool:
        """Check if this transition can fire."""
        if self.guard:
            try:
                return self.guard(context)
            except Exception:
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger": self.trigger,
            "priority": self.priority,
            "has_guard": self.guard is not None,
            "has_action": self.action is not None,
        }


@dataclass
class TransitionRecord:
    """A recorded transition in the history."""
    from_state: str
    to_state: str
    trigger: str
    timestamp: float
    transition_number: int
    context_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_state,
            "to": self.to_state,
            "trigger": self.trigger,
            "timestamp": self.timestamp,
            "transition_number": self.transition_number,
        }


@dataclass
class StateMachineConfig:
    """Configuration for an agent state machine."""
    states: Set[str]
    initial_state: str
    transitions: List[StateTransition]
    on_enter: Dict[str, List[ActionFn]] = field(default_factory=dict)
    on_exit: Dict[str, List[ActionFn]] = field(default_factory=dict)
    timeout_states: Dict[str, float] = field(default_factory=dict)
    # state -> max seconds before auto-transition


# ════════════════════════════════════════════════════════════════════
# State Machine
# ════════════════════════════════════════════════════════════════════


class AgentStateMachine:
    """
    Explicit state machine for agent lifecycle.

    Replaces implicit status tracking with auditable state transitions.

    Usage:
        sm = create_agent_state_machine("MyAgent")
        await sm.trigger("event_received", {"event": ...})
        # sm.current_state == "observing"
    """

    def __init__(self, config: StateMachineConfig, agent_name: str = "unknown"):
        self._config = config
        self._agent_name = agent_name
        self._current_state = config.initial_state
        self._history: List[TransitionRecord] = []
        self._state_entry_time: float = time.time()
        self._transition_count: int = 0
        self._logger = logger.bind(agent=agent_name, component="state_machine")
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate the state machine configuration."""
        if self._config.initial_state not in self._config.states:
            raise ValueError(
                f"Initial state '{self._config.initial_state}' not in states: "
                f"{self._config.states}"
            )
        for t in self._config.transitions:
            if t.from_state not in self._config.states:
                raise ValueError(f"Transition from unknown state '{t.from_state}'")
            if t.to_state not in self._config.states:
                raise ValueError(f"Transition to unknown state '{t.to_state}'")

    # ── Core operations ────────────────────────────────────────────

    @property
    def current_state(self) -> str:
        return self._current_state

    async def trigger(
        self,
        trigger: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Fire a trigger, transitioning to the next state.

        Returns the new state, or None if no valid transition found.
        """
        ctx = context or {}
        now = time.time()

        candidates = [
            t for t in self._config.transitions
            if t.from_state == self._current_state and t.trigger == trigger
        ]

        if not candidates:
            self._logger.debug(
                "no_matching_transition",
                trigger=trigger,
                current_state=self._current_state,
            )
            return None

        candidates.sort(key=lambda t: t.priority, reverse=True)

        for transition in candidates:
            if transition.can_fire(ctx):
                old_state = self._current_state

                # Execute exit actions
                await self._run_actions(
                    self._config.on_exit.get(old_state, []),
                    ctx, f"exit:{old_state}",
                )

                # Perform transition
                self._current_state = transition.to_state
                self._state_entry_time = now
                self._transition_count += 1

                # Record history
                record = TransitionRecord(
                    from_state=old_state,
                    to_state=transition.to_state,
                    trigger=trigger,
                    timestamp=now,
                    transition_number=self._transition_count,
                    context_keys=list(ctx.keys()),
                )
                self._history.append(record)

                # Execute transition action
                if transition.action:
                    await self._run_actions(
                        [transition.action], ctx, f"transition:{trigger}",
                    )

                # Execute enter actions
                await self._run_actions(
                    self._config.on_enter.get(transition.to_state, []),
                    ctx, f"enter:{transition.to_state}",
                )

                self._logger.info(
                    "state_transition",
                    from_state=old_state,
                    to_state=transition.to_state,
                    trigger=trigger,
                    transition_number=self._transition_count,
                )
                return transition.to_state

        self._logger.debug(
            "all_guards_failed",
            trigger=trigger,
            current_state=self._current_state,
            candidates=len(candidates),
        )
        return None

    def check_timeouts(self) -> Optional[str]:
        """
        Check if the current state has timed out.

        Returns the timed-out state name, or None.
        """
        timeout = self._config.timeout_states.get(self._current_state)
        if timeout and (time.time() - self._state_entry_time) > timeout:
            return self._current_state
        return None

    def get_state_duration(self) -> float:
        """How long the agent has been in the current state (seconds)."""
        return time.time() - self._state_entry_time

    # ── Query methods ──────────────────────────────────────────────

    def get_valid_triggers(self) -> List[str]:
        """Get all triggers valid from the current state."""
        return list(set(
            t.trigger for t in self._config.transitions
            if t.from_state == self._current_state
        ))

    def get_valid_transitions(self) -> List[Dict[str, Any]]:
        """Get details of all valid transitions from current state."""
        return [
            t.to_dict() for t in self._config.transitions
            if t.from_state == self._current_state
        ]

    def get_all_states(self) -> List[str]:
        """Get all states in the machine."""
        return sorted(self._config.states)

    def get_history(self, last_n: int = 20) -> List[Dict[str, Any]]:
        """Get transition history."""
        return [r.to_dict() for r in self._history[-last_n:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get state machine statistics."""
        return {
            "agent_name": self._agent_name,
            "current_state": self._current_state,
            "total_transitions": self._transition_count,
            "state_duration_seconds": round(self.get_state_duration(), 2),
            "valid_triggers": self.get_valid_triggers(),
            "history_length": len(self._history),
            "timeout_active": self._config.timeout_states.get(self._current_state) is not None,
        }

    # ── Persistence ────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state machine for persistence."""
        return {
            "agent_name": self._agent_name,
            "current_state": self._current_state,
            "state_entry_time": self._state_entry_time,
            "transition_count": self._transition_count,
            "history": [r.to_dict() for r in self._history],
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        config: StateMachineConfig,
    ) -> "AgentStateMachine":
        """Restore state machine from persisted data."""
        sm = cls(config, agent_name=data.get("agent_name", "unknown"))
        sm._current_state = data.get("current_state", config.initial_state)
        sm._state_entry_time = data.get("state_entry_time", time.time())
        sm._transition_count = data.get("transition_count", 0)
        return sm

    # ── Internal ───────────────────────────────────────────────────

    async def _run_actions(
        self,
        actions: List[ActionFn],
        context: Dict[str, Any],
        label: str,
    ) -> None:
        """Run a list of actions, catching exceptions."""
        for action in actions:
            try:
                if asyncio.iscoroutinefunction(action):
                    await action(context)
                else:
                    action(context)
            except Exception as exc:
                self._logger.warning("action_error", label=label, error=str(exc))


# ════════════════════════════════════════════════════════════════════
# Biashara Agent State Machine Factory
# ════════════════════════════════════════════════════════════════════


def create_agent_state_machine(agent_name: str) -> AgentStateMachine:
    """
    Create a state machine for a Biashara agent with standard lifecycle.

    States:
        idle -> observing -> thinking -> acting -> reflecting -> idle

    With error recovery:
        * -> error -> recovering -> idle

    And timeout handling:
        thinking: 30s, acting: 60s, observing: 10s
    """
    config = StateMachineConfig(
        states={
            "idle", "observing", "thinking", "acting",
            "reflecting", "error", "recovering",
        },
        initial_state="idle",
        transitions=[
            # Normal lifecycle
            StateTransition("idle", "observing", "event_received"),
            StateTransition("observing", "thinking", "observation_complete"),
            StateTransition("thinking", "acting", "decision_made"),
            StateTransition("acting", "reflecting", "action_complete"),
            StateTransition("reflecting", "idle", "reflection_complete"),

            # Error transitions
            StateTransition("observing", "error", "observation_failed"),
            StateTransition("thinking", "error", "thinking_failed"),
            StateTransition("acting", "error", "action_failed"),
            StateTransition("reflecting", "error", "reflection_failed"),

            # Recovery
            StateTransition("error", "recovering", "recovery_started"),
            StateTransition("recovering", "idle", "recovery_complete"),
            StateTransition("error", "idle", "error_acknowledged"),

            # Timeout recovery
            StateTransition("thinking", "idle", "timeout", guard=lambda ctx: True),
            StateTransition("acting", "idle", "timeout", guard=lambda ctx: True),
            StateTransition("observing", "idle", "timeout", guard=lambda ctx: True),
        ],
        timeout_states={
            "thinking": 30.0,
            "acting": 60.0,
            "observing": 10.0,
        },
    )

    return AgentStateMachine(config, agent_name=agent_name)
