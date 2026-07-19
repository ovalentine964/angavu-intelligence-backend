"""
Goal Progress Loop — Track → Predict → Nudge.

Tracks savings goals for workers, predicts completion dates based on
current trajectory, and generates motivational nudges.

Uses DeerFlow's GoalState for progress tracking:
- Goal: "Track savings goal and predict completion"
- Evidence: progress_updated, prediction_generated, nudge_sent
- Continuation: keep predicting until nudge is sent
- No-progress: stop if contribution data is stale

Integrates with DeerFlow's goal evaluation to determine if a worker
is "on track" or needs intervention.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.agents.base import AgentDecision, AgentResult
from app.agents.loops.core import ReActAgent
from app.loops.config import get_loop_config

logger = structlog.get_logger(__name__)


@dataclass
class SavingsGoal:
    """A worker's savings goal."""
    goal_id: str
    worker_id: str
    target_amount: float
    current_amount: float = 0.0
    currency: str = "KES"
    goal_name: str = ""
    target_date: str = ""
    created_at: str = ""

    @property
    def progress_pct(self) -> float:
        return min(1.0, self.current_amount / self.target_amount) if self.target_amount > 0 else 0.0

    @property
    def remaining_amount(self) -> float:
        return max(0, self.target_amount - self.current_amount)


@dataclass
class GoalPrediction:
    """Prediction of goal completion."""
    goal_id: str
    predicted_completion_date: str
    confidence: float  # 0.0 – 1.0
    on_track: bool
    weekly_contribution_avg: float
    weeks_remaining: float
    adjustment_needed: float  # How much more per week to stay on track


@dataclass
class GoalNudge:
    """A motivational nudge for the worker."""
    goal_id: str
    worker_id: str
    nudge_type: str  # on_track | behind | ahead | milestone
    message_text: str
    language: str = "sw"


@dataclass
class GoalLoopState:
    """Loop state for goal progress tracking."""
    goal_id: str
    worker_id: str
    current_phase: str = "track"
    continuation_count: int = 0
    no_progress_count: int = 0
    max_continuations: int = 5
    max_no_progress: int = 2

    progress_updated: bool = False
    prediction_generated: bool = False
    nudge_sent: bool = False

    goal: SavingsGoal | None = None
    prediction: GoalPrediction | None = None
    nudge: GoalNudge | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def is_satisfied(self) -> bool:
        return self.progress_updated and self.prediction_generated and self.nudge_sent

    def get_blocker(self) -> str:
        if not self.progress_updated:
            return "missing_evidence"
        if not self.prediction_generated:
            return "goal_not_met_yet"
        if not self.nudge_sent:
            return "goal_not_met_yet"
        return "none"

    def record_progress(self, phase: str, result: dict[str, Any]) -> bool:
        changed = False
        if phase == "track" and not self.progress_updated:
            self.progress_updated = True
            self.evidence["progress_updated"] = result
            changed = True
        elif phase == "predict" and not self.prediction_generated:
            self.prediction_generated = True
            self.evidence["prediction_generated"] = result
            changed = True
        elif phase == "nudge" and not self.nudge_sent:
            self.nudge_sent = True
            self.evidence["nudge_sent"] = result
            changed = True
        return changed

    def to_goal_state(self) -> dict[str, Any]:
        return {
            "objective": f"Track goal {self.goal_id} for worker {self.worker_id}",
            "status": "active" if not self.is_satisfied() else "completed",
            "continuation_count": self.continuation_count,
            "max_continuations": self.max_continuations,
            "no_progress_count": self.no_progress_count,
            "max_no_progress_continuations": self.max_no_progress,
            "last_evaluation": {
                "satisfied": self.is_satisfied(),
                "blocker": self.get_blocker(),
                "evidence_summary": str(self.evidence),
            },
        }


class GoalProgressLoop(ReActAgent):
    """
    Goal progress loop: Track → Predict → Nudge.

    Implements savings goal tracking as a DeerFlow goal:

    Phase 1 (Track): Record contribution, update goal progress
    Phase 2 (Predict): Estimate completion date based on trajectory
    Phase 3 (Nudge): Generate motivational message

    Uses DeerFlow's GoalState for lifecycle:
    - Evaluates satisfaction after each phase
    - Continuation limits prevent infinite prediction loops
    - No-progress detection stops when data is stale
    """

    def __init__(self):
        super().__init__(
            name="GoalProgressLoop",
            role="Savings goal tracking and motivation specialist",
            capabilities=[
                "goal_tracking",
                "contribution_recording",
                "completion_prediction",
                "nudge_generation",
            ],
        )
        self._config = get_loop_config("goal_progress")
        self._active_states: dict[str, GoalLoopState] = {}

    def _get_or_create_state(self, goal_id: str, worker_id: str) -> GoalLoopState:
        if goal_id not in self._active_states:
            self._active_states[goal_id] = GoalLoopState(
                goal_id=goal_id,
                worker_id=worker_id,
            )
        return self._active_states[goal_id]

    async def _think_reasoning(self, context: dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        goal_id = payload.get("goal_id", "unknown")
        worker_id = payload.get("worker_id", "unknown")

        state = self._get_or_create_state(goal_id, worker_id)

        # Determine phase
        if not state.progress_updated:
            phase = "track"
        elif not state.prediction_generated:
            phase = "predict"
        elif not state.nudge_sent:
            phase = "nudge"
        else:
            phase = "complete"

        state.current_phase = phase
        state.continuation_count += 1

        # DeerFlow-style continuation checks
        if state.continuation_count > state.max_continuations:
            return AgentDecision(
                action="force_complete",
                parameters={"goal_id": goal_id, "reason": "max_continuations_exceeded"},
                confidence=0.5,
                reasoning=f"Max continuations exceeded for goal {goal_id}",
            )

        if state.no_progress_count >= state.max_no_progress:
            return AgentDecision(
                action="force_complete",
                parameters={"goal_id": goal_id, "reason": "no_progress"},
                confidence=0.5,
                reasoning=f"No progress for goal {goal_id}",
            )

        return AgentDecision(
            action=f"execute_{phase}",
            parameters={
                "goal_id": goal_id,
                "worker_id": worker_id,
                "phase": phase,
                "contribution_data": payload,
            },
            confidence=0.9,
            reasoning=f"Goal loop: phase={phase}, continuation={state.continuation_count}",
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        params = decision.parameters
        goal_id = params.get("goal_id", "unknown")
        worker_id = params.get("worker_id", "unknown")
        phase = params.get("phase", "unknown")

        state = self._get_or_create_state(goal_id, worker_id)

        try:
            if decision.action == "force_complete":
                return AgentResult(
                    success=True,
                    data={"status": "force_completed", "reason": params.get("reason")},
                    duration_ms=(time.time() - start) * 1000,
                )

            if phase == "track":
                result = await self._track_phase(goal_id, worker_id, params.get("contribution_data", {}), state)
            elif phase == "predict":
                result = await self._predict_phase(goal_id, worker_id, state)
            elif phase == "nudge":
                result = await self._nudge_phase(goal_id, worker_id, state)
            else:
                result = {"success": False, "error": f"Unknown phase: {phase}"}

            made_progress = state.record_progress(phase, result)
            if not made_progress:
                state.no_progress_count += 1
            else:
                state.no_progress_count = 0

            return AgentResult(
                success=result.get("success", False),
                data={
                    "phase": phase,
                    "result": result,
                    "state": state.to_goal_state(),
                    "loop_complete": state.is_satisfied(),
                },
                error=result.get("error"),
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            state.no_progress_count += 1
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)

    async def _track_phase(
        self, goal_id: str, worker_id: str, contribution_data: dict[str, Any], state: GoalLoopState
    ) -> dict[str, Any]:
        """Record contribution and update goal progress."""
        amount = contribution_data.get("amount", 0)
        target = contribution_data.get("target_amount", 10000)

        goal = SavingsGoal(
            goal_id=goal_id,
            worker_id=worker_id,
            target_amount=target,
            current_amount=amount,
            goal_name=contribution_data.get("goal_name", "Savings"),
        )
        state.goal = goal

        self.memory.remember({
            "event": "goal_contribution",
            "goal_id": goal_id,
            "worker_id": worker_id,
            "amount": amount,
            "progress_pct": goal.progress_pct,
        })

        return {
            "success": True,
            "new_data": True,
            "goal": {
                "goal_id": goal_id,
                "progress_pct": goal.progress_pct,
                "remaining": goal.remaining_amount,
            },
        }

    async def _predict_phase(
        self, goal_id: str, worker_id: str, state: GoalLoopState
    ) -> dict[str, Any]:
        """Predict goal completion date."""
        goal = state.goal
        if not goal:
            return {"success": False, "error": "No goal data available"}

        # Calculate average weekly contribution from memory
        recent = self.memory.recall_recent(20)
        contributions = [
            r for r in recent
            if r.get("event") == "goal_contribution" and r.get("goal_id") == goal_id
        ]

        if contributions:
            total_contributed = sum(c.get("amount", 0) for c in contributions)
            weeks = max(1, len(contributions))
            weekly_avg = total_contributed / weeks
        else:
            weekly_avg = goal.current_amount  # Assume single contribution

        remaining = goal.remaining_amount
        weeks_remaining = remaining / weekly_avg if weekly_avg > 0 else float("inf")

        on_track = weeks_remaining <= 52  # Within a year
        predicted_date = (datetime.now(UTC) + timedelta(weeks=weeks_remaining)).isoformat()

        # Calculate adjustment needed to meet target in 26 weeks (6 months)
        target_weeks = 26
        needed_per_week = remaining / target_weeks
        adjustment = max(0, needed_per_week - weekly_avg)

        prediction = GoalPrediction(
            goal_id=goal_id,
            predicted_completion_date=predicted_date,
            confidence=0.75 if len(contributions) >= 3 else 0.5,
            on_track=on_track,
            weekly_contribution_avg=weekly_avg,
            weeks_remaining=weeks_remaining,
            adjustment_needed=adjustment,
        )
        state.prediction = prediction

        return {
            "success": True,
            "new_data": True,
            "prediction": {
                "predicted_date": predicted_date,
                "on_track": on_track,
                "weekly_avg": weekly_avg,
                "weeks_remaining": weeks_remaining,
                "adjustment_needed": adjustment,
            },
        }

    async def _nudge_phase(
        self, goal_id: str, worker_id: str, state: GoalLoopState
    ) -> dict[str, Any]:
        """Generate motivational nudge."""
        prediction = state.prediction
        goal = state.goal
        if not prediction or not goal:
            return {"success": False, "error": "No prediction or goal data"}

        if prediction.on_track and goal.progress_pct >= 0.8:
            nudge_type = "milestone"
            msg = (
                f"🎉 Hongera! Umefikia {goal.progress_pct:.0%} ya lengo lako la {goal.goal_name}! "
                f"Karibu sana kufikia lengo. Endelea hivi!"
            )
        elif prediction.on_track:
            nudge_type = "on_track"
            msg = (
                f"👍 Vizuri! Uko kwenye njia sahihi kufikia lengo lako la {goal.goal_name}. "
                f"Unahitaji KES {prediction.weekly_contribution_avg:.0f}/wiki kufikia lengo."
            )
        elif prediction.adjustment_needed > 0:
            nudge_type = "behind"
            msg = (
                f"📢 Lengo lako la {goal.goal_name} linahitaji juhudi zaidi. "
                f"Ongeza KES {prediction.adjustment_needed:.0f}/wiki ili kufikia lengo kwa wakati. "
                f"Una {prediction.weeks_remaining:.0f} wiki zilizobaki."
            )
        else:
            nudge_type = "ahead"
            msg = (
                f"🌟 Umepita lengo! Umefikia {goal.progress_pct:.0%} ya {goal.goal_name}. "
                f"Endelea hivi na utafikia lengo mapema!"
            )

        nudge = GoalNudge(
            goal_id=goal_id,
            worker_id=worker_id,
            nudge_type=nudge_type,
            message_text=msg,
        )
        state.nudge = nudge

        return {
            "success": True,
            "new_data": True,
            "nudge": {
                "goal_id": goal_id,
                "nudge_type": nudge_type,
                "message": msg,
            },
        }

    def get_state(self, goal_id: str) -> dict[str, Any] | None:
        state = self._active_states.get(goal_id)
        return state.to_goal_state() if state else None

    def reset_state(self, goal_id: str) -> None:
        self._active_states.pop(goal_id, None)
