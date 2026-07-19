"""
Tithe Tracking Loop — Record → Analyze → Encourage.

Tracks tithe payments for workers, analyzes consistency patterns,
and generates encouragement or gentle reminders.

Uses DeerFlow's GoalState to track the loop lifecycle:
- Goal: "Track tithe payment and encourage consistency"
- Evidence: payment_recorded, analysis_complete, message_sent
- Continuation: keep analyzing until encouragement is generated
- No-progress: stop if no new data to analyze

Integrates with:
- GoalState (deerflow/agents/goal_state.py) — goal lifecycle
- GoalEvaluation — satisfied/blocker/reason
- Journal (deerflow/runtime/journal.py) — decision tracking
- LoopDetection — prevents infinite analysis loops
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from app.agents.base import AgentDecision, AgentResult
from app.agents.loops.core import ReActAgent
from app.loops.config import (
    get_loop_config,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Tithe Data Types
# ════════════════════════════════════════════════════════════════════


@dataclass
class TithePayment:
    """A single tithe payment record."""
    worker_id: str
    amount: float
    currency: str = "KES"
    payment_date: str = ""
    payment_method: str = "mpesa"
    is_missed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.payment_date:
            self.payment_date = datetime.now(UTC).isoformat()


@dataclass
class TitheAnalysis:
    """Analysis of tithe payment patterns."""
    worker_id: str
    total_payments: int = 0
    total_missed: int = 0
    current_streak_weeks: int = 0
    longest_streak_weeks: int = 0
    average_amount: float = 0.0
    consistency_score: float = 0.0  # 0.0 – 1.0
    last_payment_date: str | None = None
    trend: str = "stable"  # improving | stable | declining
    days_since_last_payment: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "total_payments": self.total_payments,
            "total_missed": self.total_missed,
            "current_streak_weeks": self.current_streak_weeks,
            "longest_streak_weeks": self.longest_streak_weeks,
            "average_amount": self.average_amount,
            "consistency_score": self.consistency_score,
            "last_payment_date": self.last_payment_date,
            "trend": self.trend,
            "days_since_last_payment": self.days_since_last_payment,
        }


@dataclass
class EncouragementMessage:
    """An encouragement message for the worker."""
    worker_id: str
    message_type: str  # streak_celebration | gentle_reminder | milestone | re_engage
    message_text: str
    language: str = "sw"
    metadata: dict[str, Any] = field(default_factory=dict)


# ════════════════════════════════════════════════════════════════════
# Tithe Loop State — Maps to DeerFlow GoalState
# ════════════════════════════════════════════════════════════════════


@dataclass
class TitheLoopState:
    """
    Internal state for the tithe tracking loop.

    Maps to DeerFlow's GoalState fields:
    - objective → "Track tithe payment and encourage consistency"
    - status → "active" while processing
    - continuation_count → number of analysis iterations
    - no_progress_count → iterations without new data
    - last_evaluation → latest analysis result
    """
    worker_id: str
    goal_objective: str = ""
    current_phase: str = "record"
    continuation_count: int = 0
    no_progress_count: int = 0
    max_continuations: int = 3
    max_no_progress: int = 1

    # Phase results
    payment_recorded: bool = False
    analysis_complete: bool = False
    message_sent: bool = False

    # Data
    latest_payment: TithePayment | None = None
    analysis: TitheAnalysis | None = None
    encouragement: EncouragementMessage | None = None

    # Evidence tracking (for DeerFlow GoalEvaluation)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_goal_state(self) -> dict[str, Any]:
        """Convert to DeerFlow GoalState format."""
        return {
            "objective": self.goal_objective,
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

    def is_satisfied(self) -> bool:
        """Check if all required phases are complete."""
        return self.payment_recorded and self.analysis_complete and self.message_sent

    def get_blocker(self) -> str:
        """Determine what's blocking goal completion."""
        if not self.payment_recorded:
            return "missing_evidence"
        if not self.analysis_complete:
            return "goal_not_met_yet"
        if not self.message_sent:
            return "goal_not_met_yet"
        return "none"

    def record_progress(self, phase: str, result: dict[str, Any]) -> bool:
        """Record phase completion. Returns True if new progress was made."""
        old_satisfied = self.is_satisfied()

        if phase == "record" and not self.payment_recorded:
            self.payment_recorded = True
            self.evidence["payment_recorded"] = result
        elif phase == "analyze" and not self.analysis_complete:
            self.analysis_complete = True
            self.evidence["analysis_complete"] = result
        elif phase == "encourage" and not self.message_sent:
            self.message_sent = True
            self.evidence["message_sent"] = result

        return self.is_satisfied() != old_satisfied or result.get("new_data", False)


# ════════════════════════════════════════════════════════════════════
# Tithe Loop — The Main Loop Implementation
# ════════════════════════════════════════════════════════════════════


class TitheLoop(ReActAgent):
    """
    Tithe tracking loop: Record → Analyze → Encourage.

    Implements the Angavu tithe tracking feature as a DeerFlow goal:
    1. Record: Capture tithe payment (or missed payment)
    2. Analyze: Calculate consistency, streaks, trends
    3. Encourage: Generate appropriate message

    Uses DeerFlow's GoalState for lifecycle management:
    - Goal evaluation checks if all 3 phases completed
    - Continuation limit prevents infinite analysis
    - No-progress detection stops when stuck
    - LoopDetection middleware prevents tool-call loops

    Example:
        loop = TitheLoop()
        result = await loop.handle_event(AgentEvent(
            event_type=EventType.TRANSACTION_RECEIVED,
            source="mpesa_webhook",
            payload={"worker_id": "w123", "amount": 500, "type": "tithe"},
        ))
    """

    def __init__(self):
        super().__init__(
            name="TitheLoop",
            role="Tithe tracking and encouragement specialist",
            capabilities=[
                "tithe_recording",
                "consistency_analysis",
                "streak_tracking",
                "encouragement_generation",
            ],
        )
        self._config = get_loop_config("tithe_tracking")
        self._active_states: dict[str, TitheLoopState] = {}

    def _get_or_create_state(self, worker_id: str) -> TitheLoopState:
        """Get or create loop state for a worker."""
        if worker_id not in self._active_states:
            self._active_states[worker_id] = TitheLoopState(
                worker_id=worker_id,
                goal_objective=self._config.to_goal_objective() if self._config else "",
            )
        return self._active_states[worker_id]

    async def _think_reasoning(self, context: dict[str, Any]) -> AgentDecision:
        """
        ReAct reasoning for tithe loop.

        Thought: What phase are we in? What data do we have?
        Action: Execute the current phase
        Observation: Record the result
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        worker_id = payload.get("worker_id", "unknown")

        state = self._get_or_create_state(worker_id)

        # Determine current phase based on state
        if not state.payment_recorded:
            phase = "record"
        elif not state.analysis_complete:
            phase = "analyze"
        elif not state.message_sent:
            phase = "encourage"
        else:
            phase = "complete"

        state.current_phase = phase
        state.continuation_count += 1

        # Check DeerFlow-style continuation limits
        if state.continuation_count > state.max_continuations:
            return AgentDecision(
                action="force_complete",
                parameters={
                    "worker_id": worker_id,
                    "reason": "max_continuations_exceeded",
                    "state": state.to_goal_state(),
                },
                confidence=0.5,
                reasoning=(
                    f"Max continuations ({state.max_continuations}) exceeded for worker {worker_id}. "
                    f"Forcing completion with partial results."
                ),
            )

        if state.no_progress_count >= state.max_no_progress:
            return AgentDecision(
                action="force_complete",
                parameters={
                    "worker_id": worker_id,
                    "reason": "no_progress",
                    "state": state.to_goal_state(),
                },
                confidence=0.5,
                reasoning=(
                    f"No progress for {state.no_progress_count} iterations. "
                    f"Stopping loop for worker {worker_id}."
                ),
            )

        # Normal phase execution
        reasoning = (
            f"Tithe loop for worker {worker_id}: "
            f"phase={phase}, "
            f"continuation={state.continuation_count}/{state.max_continuations}, "
            f"no_progress={state.no_progress_count}/{state.max_no_progress}. "
        )

        if phase == "record":
            reasoning += f"Recording payment: amount={payload.get('amount', 0)}."
        elif phase == "analyze":
            reasoning += "Analyzing tithe patterns and consistency."
        elif phase == "encourage":
            reasoning += "Generating encouragement message."

        return AgentDecision(
            action=f"execute_{phase}",
            parameters={
                "worker_id": worker_id,
                "phase": phase,
                "payment_data": payload,
                "state": state.to_goal_state(),
            },
            confidence=0.9,
            reasoning=reasoning,
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Execute the current phase of the tithe loop."""
        start = time.time()
        params = decision.parameters
        worker_id = params.get("worker_id", "unknown")
        phase = params.get("phase", "unknown")
        payment_data = params.get("payment_data", {})

        state = self._get_or_create_state(worker_id)

        try:
            if decision.action == "force_complete":
                return AgentResult(
                    success=True,
                    data={
                        "status": "force_completed",
                        "reason": params.get("reason"),
                        "state": state.to_goal_state(),
                        "evidence": state.evidence,
                    },
                    duration_ms=(time.time() - start) * 1000,
                )

            if phase == "record":
                result = await self._record_phase(worker_id, payment_data, state)
            elif phase == "analyze":
                result = await self._analyze_phase(worker_id, state)
            elif phase == "encourage":
                result = await self._encourage_phase(worker_id, state)
            else:
                result = {"success": False, "error": f"Unknown phase: {phase}"}

            # Record progress (DeerFlow-style)
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
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _record_phase(
        self, worker_id: str, payment_data: dict[str, Any], state: TitheLoopState
    ) -> dict[str, Any]:
        """Record a tithe payment."""
        payment = TithePayment(
            worker_id=worker_id,
            amount=payment_data.get("amount", 0),
            currency=payment_data.get("currency", "KES"),
            payment_method=payment_data.get("payment_method", "mpesa"),
            is_missed=payment_data.get("is_missed", False),
        )

        state.latest_payment = payment

        # Store in memory
        self.memory.remember({
            "event": "tithe_recorded",
            "worker_id": worker_id,
            "amount": payment.amount,
            "is_missed": payment.is_missed,
        })

        self._logger.info(
            "tithe_recorded",
            worker_id=worker_id,
            amount=payment.amount,
            is_missed=payment.is_missed,
        )

        return {
            "success": True,
            "new_data": True,
            "payment": {
                "worker_id": worker_id,
                "amount": payment.amount,
                "date": payment.payment_date,
                "is_missed": payment.is_missed,
            },
        }

    async def _analyze_phase(
        self, worker_id: str, state: TitheLoopState
    ) -> dict[str, Any]:
        """Analyze tithe patterns and consistency."""
        # In production, this would query the database
        # For now, use memory and the latest payment
        recent = self.memory.recall_recent(20)
        tithe_events = [
            r for r in recent
            if r.get("event") == "tithe_recorded"
            and r.get("worker_id") == worker_id
        ]

        total_payments = len([t for t in tithe_events if not t.get("is_missed")])
        total_missed = len([t for t in tithe_events if t.get("is_missed")])
        amounts = [t.get("amount", 0) for t in tithe_events if not t.get("is_missed")]

        analysis = TitheAnalysis(
            worker_id=worker_id,
            total_payments=total_payments,
            total_missed=total_missed,
            average_amount=sum(amounts) / len(amounts) if amounts else 0,
            consistency_score=min(1.0, total_payments / max(1, total_payments + total_missed)),
            current_streak_weeks=min(total_payments, 4),  # Simplified
            longest_streak_weeks=min(total_payments, 4),
            trend="improving" if total_payments > total_missed else "stable",
        )

        state.analysis = analysis

        self.memory.remember({
            "event": "tithe_analyzed",
            "worker_id": worker_id,
            "consistency_score": analysis.consistency_score,
            "trend": analysis.trend,
        })

        self._logger.info(
            "tithe_analyzed",
            worker_id=worker_id,
            consistency_score=analysis.consistency_score,
            trend=analysis.trend,
        )

        return {
            "success": True,
            "new_data": True,
            "analysis": analysis.to_dict(),
        }

    async def _encourage_phase(
        self, worker_id: str, state: TitheLoopState
    ) -> dict[str, Any]:
        """Generate encouragement message based on analysis."""
        analysis = state.analysis
        if not analysis:
            return {"success": False, "error": "No analysis available"}

        # Determine message type based on analysis
        if analysis.current_streak_weeks >= 4:
            msg_type = "streak_celebration"
            msg_text = (
                f"🎉 Hongera! Umefanikiwa kutoa zaka kwa wiki {analysis.current_streak_weeks} mfululizo! "
                f"Mungu akubariki. Uendelea hivi!"
            )
        elif analysis.consistency_score >= 0.7:
            msg_type = "gentle_reminder"
            msg_text = (
                f"Salamu! Zaka yako ya wiki hii bado haijapokelewa. "
                f"Umeonyesha uthabiti mzuri (score: {analysis.consistency_score:.0%}). "
                f"Tafadhali lipa ukiwa tayari."
            )
        elif analysis.days_since_last_payment > 14:
            msg_type = "re_engage"
            msg_text = (
                f"Habari! Tangu zaka yako ya mwisho imepita siku {analysis.days_since_last_payment}. "
                f"Tunakukumbuka na tunakuombea. Karibu urudi!"
            )
        else:
            msg_type = "gentle_reminder"
            msg_text = (
                f"Salamu! Zaka yako inakukumbusha. "
                f"Consistency yako ni {analysis.consistency_score:.0%}. "
                f"Hongera kwa juhudi zako!"
            )

        encouragement = EncouragementMessage(
            worker_id=worker_id,
            message_type=msg_type,
            message_text=msg_text,
            language="sw",
        )

        state.encouragement = encouragement

        self.memory.remember({
            "event": "tithe_encouragement_sent",
            "worker_id": worker_id,
            "message_type": msg_type,
        })

        self._logger.info(
            "tithe_encouragement_sent",
            worker_id=worker_id,
            message_type=msg_type,
        )

        return {
            "success": True,
            "new_data": True,
            "encouragement": {
                "worker_id": worker_id,
                "message_type": msg_type,
                "message_text": msg_text,
                "language": "sw",
            },
        }

    def get_state(self, worker_id: str) -> dict[str, Any] | None:
        """Get current loop state for a worker (for debugging/API)."""
        state = self._active_states.get(worker_id)
        return state.to_goal_state() if state else None

    def reset_state(self, worker_id: str) -> None:
        """Reset loop state for a worker."""
        self._active_states.pop(worker_id, None)
