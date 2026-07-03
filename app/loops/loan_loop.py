"""
Loan Management Loop — Record → Verify → Alert.

Manages the loan lifecycle from disbursement through repayment tracking.
Records payments, verifies against schedule, and generates alerts
for overdue payments or milestones.

Uses DeerFlow's Reflexion pattern for verification quality:
- After verifying, critiques its own verification accuracy
- Retries verification if confidence is low
- Stores reflections for improving future verifications

Integrates with DeerFlow's GoalState for tracking loan repayment progress.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import AgentDecision, AgentEvent, AgentResult, EventType
from app.agents.loops.core import Critique, ReflexionAgent
from app.loops.config import get_loop_config

logger = structlog.get_logger(__name__)


@dataclass
class Loan:
    """A loan record."""
    loan_id: str
    worker_id: str
    principal: float
    outstanding_balance: float
    currency: str = "KES"
    interest_rate: float = 0.0  # Monthly rate
    disbursement_date: str = ""
    due_date: str = ""
    status: str = "active"  # active | completed | defaulted | overdue
    payments: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def total_paid(self) -> float:
        return sum(p.get("amount", 0) for p in self.payments)

    @property
    def payment_count(self) -> int:
        return len(self.payments)

    @property
    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        try:
            due = datetime.fromisoformat(self.due_date.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > due and self.outstanding_balance > 0
        except (ValueError, TypeError):
            return False

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        try:
            due = datetime.fromisoformat(self.due_date.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - due).days
        except (ValueError, TypeError):
            return 0


@dataclass
class VerificationResult:
    """Result of loan payment verification."""
    loan_id: str
    payment_amount: float
    verified: bool
    new_balance: float
    on_schedule: bool
    issues: List[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class LoanAlert:
    """Alert for loan status."""
    loan_id: str
    worker_id: str
    alert_type: str  # payment_received | overdue | milestone | default_warning
    message_text: str
    severity: str = "info"  # info | warning | critical
    language: str = "sw"


@dataclass
class LoanLoopState:
    """Loop state for loan management."""
    loan_id: str
    worker_id: str
    current_phase: str = "record"
    continuation_count: int = 0
    no_progress_count: int = 0
    max_continuations: int = 4
    max_no_progress: int = 2

    payment_recorded: bool = False
    verification_complete: bool = False
    alert_sent: bool = False

    loan: Optional[Loan] = None
    verification: Optional[VerificationResult] = None
    alert: Optional[LoanAlert] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def is_satisfied(self) -> bool:
        return self.payment_recorded and self.verification_complete and self.alert_sent

    def get_blocker(self) -> str:
        if not self.payment_recorded:
            return "missing_evidence"
        if not self.verification_complete:
            return "goal_not_met_yet"
        if not self.alert_sent:
            return "goal_not_met_yet"
        return "none"

    def record_progress(self, phase: str, result: Dict[str, Any]) -> bool:
        changed = False
        if phase == "record" and not self.payment_recorded:
            self.payment_recorded = True
            self.evidence["payment_recorded"] = result
            changed = True
        elif phase == "verify" and not self.verification_complete:
            self.verification_complete = True
            self.evidence["verification_complete"] = result
            changed = True
        elif phase == "alert" and not self.alert_sent:
            self.alert_sent = True
            self.evidence["alert_sent"] = result
            changed = True
        return changed

    def to_goal_state(self) -> Dict[str, Any]:
        return {
            "objective": f"Process loan payment for {self.loan_id}",
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


class LoanLoop(ReflexionAgent):
    """
    Loan management loop: Record → Verify → Alert.

    Uses Reflexion pattern for verification quality:
    - After verifying a payment, critiques its own accuracy
    - If verification confidence is low, retries with more context
    - Stores reflections for improving future verifications

    Phase 1 (Record): Capture loan payment or disbursement
    Phase 2 (Verify): Verify payment against schedule (with Reflexion)
    Phase 3 (Alert): Generate appropriate alert

    The Reflexion loop is especially important for the verify phase:
    catching calculation errors, schedule mismatches, or data inconsistencies.
    """

    def __init__(self):
        super().__init__(
            name="LoanLoop",
            role="Loan lifecycle management and payment verification specialist",
            capabilities=[
                "loan_recording",
                "payment_verification",
                "balance_calculation",
                "schedule_tracking",
                "alert_generation",
                "self_critique_verification",
            ],
            quality_threshold=0.85,
            max_retries=2,
        )
        self._config = get_loop_config("loan_management")
        self._active_states: Dict[str, LoanLoopState] = {}

    def _get_or_create_state(self, loan_id: str, worker_id: str) -> LoanLoopState:
        if loan_id not in self._active_states:
            self._active_states[loan_id] = LoanLoopState(
                loan_id=loan_id,
                worker_id=worker_id,
            )
        return self._active_states[loan_id]

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        loan_id = payload.get("loan_id", "unknown")
        worker_id = payload.get("worker_id", "unknown")

        state = self._get_or_create_state(loan_id, worker_id)

        if not state.payment_recorded:
            phase = "record"
        elif not state.verification_complete:
            phase = "verify"
        elif not state.alert_sent:
            phase = "alert"
        else:
            phase = "complete"

        state.current_phase = phase
        state.continuation_count += 1

        if state.continuation_count > state.max_continuations:
            return AgentDecision(
                action="force_complete",
                parameters={"loan_id": loan_id, "reason": "max_continuations_exceeded"},
                confidence=0.5,
                reasoning=f"Max continuations exceeded for loan {loan_id}",
            )

        # Incorporate reflexion feedback if retrying
        reflexion = context.get("event", {}).get("metadata", {}).get("reflexion_feedback")
        reasoning = f"Loan loop: phase={phase}, continuation={state.continuation_count}"
        if reflexion:
            reasoning += f" [Reflexion: score={reflexion['previous_score']:.2f}]"

        return AgentDecision(
            action=f"execute_{phase}",
            parameters={
                "loan_id": loan_id,
                "worker_id": worker_id,
                "phase": phase,
                "payment_data": payload,
                "state": state.to_goal_state(),
            },
            confidence=0.9,
            reasoning=reasoning,
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        params = decision.parameters
        loan_id = params.get("loan_id", "unknown")
        worker_id = params.get("worker_id", "unknown")
        phase = params.get("phase", "unknown")

        state = self._get_or_create_state(loan_id, worker_id)

        try:
            if decision.action == "force_complete":
                return AgentResult(
                    success=True,
                    data={"status": "force_completed", "reason": params.get("reason")},
                    duration_ms=(time.time() - start) * 1000,
                )

            if phase == "record":
                result = await self._record_phase(loan_id, worker_id, params.get("payment_data", {}), state)
            elif phase == "verify":
                result = await self._verify_phase(loan_id, worker_id, state)
            elif phase == "alert":
                result = await self._alert_phase(loan_id, worker_id, state)
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

    async def _record_phase(
        self, loan_id: str, worker_id: str, payment_data: Dict[str, Any], state: LoanLoopState
    ) -> Dict[str, Any]:
        """Record a loan payment or disbursement."""
        amount = payment_data.get("amount", 0)
        payment_type = payment_data.get("type", "repayment")  # repayment | disbursement

        # Get or create loan
        if not state.loan:
            state.loan = Loan(
                loan_id=loan_id,
                worker_id=worker_id,
                principal=payment_data.get("principal", amount),
                outstanding_balance=payment_data.get("outstanding_balance", amount),
                due_date=payment_data.get("due_date", ""),
            )

        if payment_type == "repayment":
            state.loan.payments.append({
                "amount": amount,
                "date": datetime.now(timezone.utc).isoformat(),
                "method": payment_data.get("method", "mpesa"),
            })
            state.loan.outstanding_balance = max(0, state.loan.outstanding_balance - amount)

        self.memory.remember({
            "event": "loan_payment_recorded",
            "loan_id": loan_id,
            "worker_id": worker_id,
            "amount": amount,
            "type": payment_type,
        })

        return {
            "success": True,
            "new_data": True,
            "payment": {
                "loan_id": loan_id,
                "amount": amount,
                "type": payment_type,
                "new_balance": state.loan.outstanding_balance,
            },
        }

    async def _verify_phase(
        self, loan_id: str, worker_id: str, state: LoanLoopState
    ) -> Dict[str, Any]:
        """Verify payment against schedule with self-critique."""
        loan = state.loan
        if not loan:
            return {"success": False, "error": "No loan data available"}

        issues = []
        confidence = 1.0
        on_schedule = True

        # Check if payment amount is reasonable
        if loan.payments:
            latest = loan.payments[-1]["amount"]
            if latest <= 0:
                issues.append("Payment amount is zero or negative")
                confidence -= 0.3
            if latest > loan.outstanding_balance + loan.principal:
                issues.append("Payment exceeds total possible balance")
                confidence -= 0.5

        # Check if loan is overdue
        if loan.is_overdue:
            on_schedule = False
            issues.append(f"Loan is {loan.days_overdue} days overdue")
            confidence -= 0.2

        # Check if balance is consistent
        expected_balance = loan.principal - loan.total_paid
        if abs(loan.outstanding_balance - expected_balance) > 0.01:
            issues.append(
                f"Balance inconsistency: recorded={loan.outstanding_balance}, "
                f"expected={expected_balance}"
            )
            confidence -= 0.3

        # Check for partial payment
        if loan.payments:
            latest_pct = loan.payments[-1]["amount"] / loan.principal if loan.principal > 0 else 0
            if latest_pct < 0.1:
                issues.append(f"Small partial payment: {latest_pct:.1%} of principal")

        verified = confidence >= 0.7 and len(issues) == 0
        confidence = max(0.0, min(1.0, confidence))

        verification = VerificationResult(
            loan_id=loan_id,
            payment_amount=loan.payments[-1]["amount"] if loan.payments else 0,
            verified=verified,
            new_balance=loan.outstanding_balance,
            on_schedule=on_schedule,
            issues=issues,
            confidence=confidence,
        )
        state.verification = verification

        self.memory.remember({
            "event": "loan_verified",
            "loan_id": loan_id,
            "verified": verified,
            "confidence": confidence,
            "issues": issues,
        })

        return {
            "success": True,
            "new_data": True,
            "verification": {
                "loan_id": loan_id,
                "verified": verified,
                "new_balance": loan.outstanding_balance,
                "on_schedule": on_schedule,
                "confidence": confidence,
                "issues": issues,
            },
        }

    async def _critique(
        self, event: AgentEvent, result: AgentResult
    ) -> Critique:
        """
        Critique verification quality (Reflexion pattern).

        Checks for:
        - Verification confidence
        - Issue severity
        - Balance consistency
        """
        issues = []
        suggestions = []
        score = 1.0

        if not result.success:
            score -= 0.5
            issues.append(f"Verification failed: {result.error}")
            suggestions.append("Check loan data availability")

        data = result.data or {}
        verification = data.get("result", {}).get("verification", {})

        if verification:
            conf = verification.get("confidence", 1.0)
            if conf < 0.8:
                score -= 0.2
                issues.append(f"Low verification confidence: {conf:.2f}")
                suggestions.append("Cross-check with additional data sources")

            if verification.get("issues"):
                score -= 0.1 * len(verification["issues"])
                issues.extend(verification["issues"])
                suggestions.append("Address verification issues before marking complete")

        score = max(0.0, min(1.0, score))

        return Critique(
            score=score,
            issues=issues,
            suggestions=suggestions,
            should_retry=score < self._quality_threshold,
            revision_plan="; ".join(suggestions) if suggestions else "Verification acceptable",
        )

    async def _alert_phase(
        self, loan_id: str, worker_id: str, state: LoanLoopState
    ) -> Dict[str, Any]:
        """Generate loan alert based on verification."""
        loan = state.loan
        verification = state.verification
        if not loan:
            return {"success": False, "error": "No loan data"}

        # Determine alert type
        if loan.status == "completed" or loan.outstanding_balance <= 0:
            alert_type = "milestone"
            severity = "info"
            msg = (
                f"🎉 Hongera! Umekamilisha kulipa loan yako ya {loan.loan_id}! "
                f"Mungu akubariki kwa uthabiti wako."
            )
        elif loan.is_overdue and loan.days_overdue > 30:
            alert_type = "default_warning"
            severity = "critical"
            msg = (
                f"⚠️ Loan yako ya {loan.loan_id} imechelewa siku {loan.days_overdue}. "
                f"Salio: KES {loan.outstanding_balance:.0f}. "
                f"Tafadhali lipa haraka ili kuepuka adhabu."
            )
        elif loan.is_overdue:
            alert_type = "overdue"
            severity = "warning"
            msg = (
                f"📢 Loan yako ya {loan.loan_id} imechelewa siku {loan.days_overdue}. "
                f"Salio: KES {loan.outstanding_balance:.0f}. "
                f"Tafadhali lipa wiki hii."
            )
        else:
            alert_type = "payment_received"
            severity = "info"
            last_amount = loan.payments[-1]["amount"] if loan.payments else 0
            msg = (
                f"✅ Malipo ya KES {last_amount:.0f} yamepokelewa kwa loan {loan.loan_id}. "
                f"Salio: KES {loan.outstanding_balance:.0f}. "
                f"Asante kwa kulipa kwa wakati!"
            )

        alert = LoanAlert(
            loan_id=loan_id,
            worker_id=worker_id,
            alert_type=alert_type,
            message_text=msg,
            severity=severity,
        )
        state.alert = alert

        return {
            "success": True,
            "new_data": True,
            "alert": {
                "loan_id": loan_id,
                "alert_type": alert_type,
                "severity": severity,
                "message": msg,
            },
        }

    def get_state(self, loan_id: str) -> Optional[Dict[str, Any]]:
        state = self._active_states.get(loan_id)
        return state.to_goal_state() if state else None

    def reset_state(self, loan_id: str) -> None:
        self._active_states.pop(loan_id, None)
