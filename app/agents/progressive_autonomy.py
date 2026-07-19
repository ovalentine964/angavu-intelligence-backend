"""
Progressive Autonomy — 5-Level Trust System for Angavu Intelligence Agents.

Implements graduated autonomy where agents earn trust over time through
successful task completion. Higher trust levels unlock more autonomous
capabilities with less human oversight.

Trust Levels:
  Level 0 — Supervised:     All actions require explicit human approval
  Level 1 — Guided:         Agent proposes, human approves/rejects
  Level 2 — Semi-Autonomous: Agent acts within predefined guardrails
  Level 3 — Autonomous:     Agent acts freely, reports outcomes
  Level 4 — Self-Governing: Agent sets own goals within mission constraints

Trust is earned through:
  - Successful task completions (positive signal)
  - Error-free operation streaks (consistency signal)
  - Quality of decisions (outcome signal)
  - Time in service (stability signal)

Trust is lost through:
  - Failed tasks (negative signal)
  - Guardrail violations (safety signal)
  - Human overrides (correction signal)

References:
  - IEEE 7010-2020: Well-being metrics for autonomous systems
  - EU AI Act Article 14: Human oversight requirements
  - Anthropic's Core Views on AI Safety (2025)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TrustLevel(IntEnum):
    """
    5-level progressive autonomy trust system.

    Each level defines what actions an agent can take without
    human approval. Higher levels require higher trust scores.
    """
    SUPERVISED = 0        # All actions require human approval
    GUIDED = 1            # Agent proposes, human approves
    SEMI_AUTONOMOUS = 2   # Acts within predefined guardrails
    AUTONOMOUS = 3        # Acts freely, reports outcomes
    SELF_GOVERNING = 4    # Sets own goals within mission constraints


# Actions that unlock at each trust level
TRUST_LEVEL_CAPABILITIES = {
    TrustLevel.SUPERVISED: {
        "can_read_data": True,
        "can_propose_actions": True,
        "can_execute_actions": False,
        "can_modify_parameters": False,
        "can_delegate_tasks": False,
        "can_access_external_apis": False,
        "can_make_financial_decisions": False,
        "can_update_own_strategy": False,
        "requires_human_approval_for": "all_actions",
    },
    TrustLevel.GUIDED: {
        "can_read_data": True,
        "can_propose_actions": True,
        "can_execute_actions": False,  # Still needs approval
        "can_modify_parameters": False,
        "can_delegate_tasks": False,
        "can_access_external_apis": False,
        "can_make_financial_decisions": False,
        "can_update_own_strategy": False,
        "requires_human_approval_for": "all_executions",
    },
    TrustLevel.SEMI_AUTONOMOUS: {
        "can_read_data": True,
        "can_propose_actions": True,
        "can_execute_actions": True,  # Within guardrails
        "can_modify_parameters": True,  # Within bounds
        "can_delegate_tasks": False,
        "can_access_external_apis": False,
        "can_make_financial_decisions": False,  # Below threshold
        "can_update_own_strategy": False,
        "requires_human_approval_for": "high_risk_actions",
        "guardrails": {
            "max_financial_amount": 1000,  # KSh
            "max_delegation_depth": 0,
            "allowed_external_domains": [],
        },
    },
    TrustLevel.AUTONOMOUS: {
        "can_read_data": True,
        "can_propose_actions": True,
        "can_execute_actions": True,
        "can_modify_parameters": True,
        "can_delegate_tasks": True,
        "can_access_external_apis": True,
        "can_make_financial_decisions": True,  # Within limits
        "can_update_own_strategy": True,  # Within bounds
        "requires_human_approval_for": "critical_actions_only",
        "guardrails": {
            "max_financial_amount": 100000,  # KSh
            "max_delegation_depth": 2,
            "allowed_external_domains": ["api.safaricom.co.ke", "api.m-pesa.com"],
        },
    },
    TrustLevel.SELF_GOVERNING: {
        "can_read_data": True,
        "can_propose_actions": True,
        "can_execute_actions": True,
        "can_modify_parameters": True,
        "can_delegate_tasks": True,
        "can_access_external_apis": True,
        "can_make_financial_decisions": True,
        "can_update_own_strategy": True,
        "requires_human_approval_for": "safety_critical_only",
        "guardrails": {
            "max_financial_amount": 1000000,  # KSh
            "max_delegation_depth": 4,
            "allowed_external_domains": ["*"],  # All domains
        },
    },
}

# Trust score thresholds for each level
TRUST_THRESHOLDS = {
    TrustLevel.SUPERVISED: 0.0,
    TrustLevel.GUIDED: 0.2,
    TrustLevel.SEMI_AUTONOMOUS: 0.4,
    TrustLevel.AUTONOMOUS: 0.65,
    TrustLevel.SELF_GOVERNING: 0.85,
}


@dataclass
class TrustEvent:
    """An event that affects an agent's trust score."""
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = ""
    event_type: str = ""  # "task_success", "task_failure", "guardrail_violation", "human_override"
    impact: float = 0.0   # Positive = trust gain, negative = trust loss
    details: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentTrustState:
    """Trust state for a single agent."""
    agent_name: str = ""
    trust_score: float = 0.0         # 0.0 – 1.0
    trust_level: TrustLevel = TrustLevel.SUPERVISED
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    guardrail_violations: int = 0
    human_overrides: int = 0
    streak_successes: int = 0        # Current success streak
    best_streak: int = 0
    last_updated: float = field(default_factory=time.time)
    trust_history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate task success rate as a fraction."""
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks

    def to_dict(self) -> dict[str, Any]:
        """Serialize trust record to dictionary for API response."""
        return {
            "agent_name": self.agent_name,
            "trust_score": round(self.trust_score, 4),
            "trust_level": self.trust_level.name,
            "trust_level_value": int(self.trust_level),
            "capabilities": TRUST_LEVEL_CAPABILITIES[self.trust_level],
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "success_rate": round(self.success_rate, 4),
            "streak_successes": self.streak_successes,
            "best_streak": self.best_streak,
            "guardrail_violations": self.guardrail_violations,
            "human_overrides": self.human_overrides,
            "last_updated": self.last_updated,
        }


class ProgressiveAutonomyManager:
    """
    Manages progressive autonomy for all agents.

    Tracks trust scores and automatically promotes/demotes agents
    between trust levels based on their performance.

    Usage:
        manager = ProgressiveAutonomyManager()

        # Record a successful task
        manager.record_success("SokoPulse", task_complexity=0.5)

        # Check if agent can perform an action
        if manager.can_execute("SokoPulse", "make_financial_decision", amount=5000):
            # Proceed
            pass

        # Get agent's current trust state
        state = manager.get_trust_state("SokoPulse")
    """

    def __init__(self):
        self._states: dict[str, AgentTrustState] = {}
        self._events: list[TrustEvent] = []
        self._max_events = 10000
        self._logger = logger.bind(component="progressive_autonomy")

    def _get_or_create_state(self, agent_name: str) -> AgentTrustState:
        if agent_name not in self._states:
            self._states[agent_name] = AgentTrustState(agent_name=agent_name)
        return self._states[agent_name]

    # ── Trust Score Updates ────────────────────────────────────────

    def record_success(self, agent_name: str, task_complexity: float = 0.5) -> TrustEvent:
        """
        Record a successful task completion.

        Trust gain scales with task complexity: harder tasks earn more trust.
        Success streaks provide bonus trust (consistency signal).
        """
        state = self._get_or_create_state(agent_name)
        state.total_tasks += 1
        state.successful_tasks += 1
        state.streak_successes += 1
        state.best_streak = max(state.best_streak, state.streak_successes)

        # Base trust gain: 0.02 – 0.06 based on complexity
        base_gain = 0.02 + 0.04 * min(1.0, task_complexity)

        # Streak bonus: +0.005 per consecutive success (max +0.05)
        streak_bonus = min(0.05, state.streak_successes * 0.005)

        total_gain = base_gain + streak_bonus
        old_score = state.trust_score
        state.trust_score = min(1.0, state.trust_score + total_gain)

        event = TrustEvent(
            agent_name=agent_name,
            event_type="task_success",
            impact=total_gain,
            details=f"complexity={task_complexity:.2f}, streak={state.streak_successes}",
        )
        self._record_event(event)
        self._update_trust_level(state)

        self._logger.info(
            "trust_gain",
            agent=agent_name,
            gain=round(total_gain, 4),
            score=round(state.trust_score, 4),
            level=state.trust_level.name,
            streak=state.streak_successes,
        )
        return event

    def record_failure(self, agent_name: str, severity: float = 0.5) -> TrustEvent:
        """
        Record a task failure.

        Trust loss scales with severity. Breaks success streak.
        """
        state = self._get_or_create_state(agent_name)
        state.total_tasks += 1
        state.failed_tasks += 1
        state.streak_successes = 0

        # Trust loss: 0.03 – 0.10 based on severity
        loss = 0.03 + 0.07 * min(1.0, severity)
        old_score = state.trust_score
        state.trust_score = max(0.0, state.trust_score - loss)

        event = TrustEvent(
            agent_name=agent_name,
            event_type="task_failure",
            impact=-loss,
            details=f"severity={severity:.2f}",
        )
        self._record_event(event)
        self._update_trust_level(state)

        self._logger.warning(
            "trust_loss",
            agent=agent_name,
            loss=round(loss, 4),
            score=round(state.trust_score, 4),
            level=state.trust_level.name,
        )
        return event

    def record_guardrail_violation(self, agent_name: str, violation_type: str) -> TrustEvent:
        """
        Record a guardrail violation. Severe trust penalty.

        Guardrail violations are the strongest negative signal —
        they indicate the agent is not respecting its boundaries.
        """
        state = self._get_or_create_state(agent_name)
        state.guardrail_violations += 1
        state.streak_successes = 0

        # Heavy penalty: 0.10 – 0.20
        loss = 0.10 + 0.05 * min(2, state.guardrail_violations)
        state.trust_score = max(0.0, state.trust_score - loss)

        event = TrustEvent(
            agent_name=agent_name,
            event_type="guardrail_violation",
            impact=-loss,
            details=f"violation_type={violation_type}",
        )
        self._record_event(event)
        self._update_trust_level(state)

        self._logger.error(
            "guardrail_violation",
            agent=agent_name,
            violation=violation_type,
            loss=round(loss, 4),
            score=round(state.trust_score, 4),
            level=state.trust_level.name,
        )
        return event

    def record_human_override(self, agent_name: str, reason: str) -> TrustEvent:
        """
        Record a human override. Moderate trust penalty.

        Human overrides indicate the agent's judgment was wrong.
        Less severe than guardrail violations.
        """
        state = self._get_or_create_state(agent_name)
        state.human_overrides += 1

        loss = 0.05
        state.trust_score = max(0.0, state.trust_score - loss)

        event = TrustEvent(
            agent_name=agent_name,
            event_type="human_override",
            impact=-loss,
            details=f"reason={reason}",
        )
        self._record_event(event)
        self._update_trust_level(state)

        self._logger.warning(
            "human_override",
            agent=agent_name,
            reason=reason,
            loss=round(loss, 4),
            score=round(state.trust_score, 4),
        )
        return event

    # ── Capability Checks ──────────────────────────────────────────

    def can_execute(self, agent_name: str, action: str, **kwargs) -> bool:
        """
        Check if an agent is allowed to perform an action at its current trust level.

        Returns True if the action is within the agent's capabilities.
        """
        state = self._get_or_create_state(agent_name)
        caps = TRUST_LEVEL_CAPABILITIES[state.trust_level]

        # Check specific action types
        if action == "execute_action":
            return caps["can_execute_actions"]
        elif action == "modify_parameters":
            return caps["can_modify_parameters"]
        elif action == "delegate_task":
            return caps["can_delegate_tasks"]
        elif action == "access_external_api":
            if not caps["can_access_external_apis"]:
                return False
            domain = kwargs.get("domain", "")
            allowed = caps.get("guardrails", {}).get("allowed_external_domains", [])
            return "*" in allowed or domain in allowed
        elif action == "make_financial_decision":
            if not caps["can_make_financial_decisions"]:
                return False
            amount = kwargs.get("amount", 0)
            max_amount = caps.get("guardrails", {}).get("max_financial_amount", 0)
            return amount <= max_amount
        elif action == "update_own_strategy":
            return caps["can_update_own_strategy"]
        elif action == "propose_action":
            return caps["can_propose_actions"]
        elif action == "read_data":
            return caps["can_read_data"]

        # Default: check if execution is allowed
        return caps["can_execute_actions"]

    def get_required_approval_level(self, agent_name: str, action: str) -> str:
        """Get the approval level required for an action."""
        state = self._get_or_create_state(agent_name)
        caps = TRUST_LEVEL_CAPABILITIES[state.trust_level]

        if not self.can_execute(agent_name, action):
            return "full_approval"

        requires = caps.get("requires_human_approval_for", "all_actions")
        if requires == "all_actions":
            return "full_approval"
        elif requires == "all_executions":
            return "execution_approval"
        elif requires == "high_risk_actions":
            return "high_risk_approval"
        elif requires == "critical_actions_only":
            return "critical_approval"
        elif requires == "safety_critical_only":
            return "safety_approval"
        return "none"

    # ── Trust Level Management ─────────────────────────────────────

    def _update_trust_level(self, state: AgentTrustState) -> None:
        """Update trust level based on current trust score."""
        old_level = state.trust_level

        # Find the highest level whose threshold is met
        new_level = TrustLevel.SUPERVISED
        for level in sorted(TRUST_THRESHOLDS.keys(), reverse=True):
            if state.trust_score >= TRUST_THRESHOLDS[level]:
                new_level = level
                break

        if new_level != old_level:
            # Record the transition
            transition = {
                "from_level": old_level.name,
                "to_level": new_level.name,
                "score": round(state.trust_score, 4),
                "timestamp": time.time(),
            }
            state.trust_history.append(transition)
            if len(state.trust_history) > 50:
                state.trust_history = state.trust_history[-50:]

            state.trust_level = new_level

            if new_level > old_level:
                self._logger.info(
                    "trust_level_promoted",
                    agent=state.agent_name,
                    from_level=old_level.name,
                    to_level=new_level.name,
                    score=round(state.trust_score, 4),
                )
            else:
                self._logger.warning(
                    "trust_level_demoted",
                    agent=state.agent_name,
                    from_level=old_level.name,
                    to_level=new_level.name,
                    score=round(state.trust_score, 4),
                )

        state.last_updated = time.time()

    # ── Queries ────────────────────────────────────────────────────

    def get_trust_state(self, agent_name: str) -> dict[str, Any]:
        """Get the current trust state for an agent."""
        state = self._get_or_create_state(agent_name)
        return state.to_dict()

    def get_all_trust_states(self) -> dict[str, dict[str, Any]]:
        """Get trust states for all tracked agents."""
        return {name: state.to_dict() for name, state in self._states.items()}

    def get_trust_level(self, agent_name: str) -> TrustLevel:
        """Get the current trust level for an agent."""
        return self._get_or_create_state(agent_name).trust_level

    def get_capabilities(self, agent_name: str) -> dict[str, Any]:
        """Get the capabilities for an agent at its current trust level."""
        state = self._get_or_create_state(agent_name)
        return TRUST_LEVEL_CAPABILITIES[state.trust_level]

    def get_recent_events(self, agent_name: str | None = None, n: int = 20) -> list[dict[str, Any]]:
        """Get recent trust events, optionally filtered by agent."""
        events = self._events
        if agent_name:
            events = [e for e in events if e.agent_name == agent_name]
        return [
            {
                "event_id": e.event_id,
                "agent_name": e.agent_name,
                "event_type": e.event_type,
                "impact": round(e.impact, 4),
                "details": e.details,
                "timestamp": e.timestamp,
            }
            for e in events[-n:]
        ]

    def get_system_summary(self) -> dict[str, Any]:
        """Get a summary of all agents' trust levels."""
        levels = {level.name: 0 for level in TrustLevel}
        for state in self._states.values():
            levels[state.trust_level.name] += 1

        return {
            "total_agents": len(self._states),
            "agents_by_level": levels,
            "average_trust_score": (
                round(sum(s.trust_score for s in self._states.values()) / len(self._states), 4)
                if self._states else 0.0
            ),
            "total_events": len(self._events),
        }

    # ── Internal ───────────────────────────────────────────────────

    def _record_event(self, event: TrustEvent) -> None:
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
