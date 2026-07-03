"""
Customer Onboarding Agent — Auto-generates and tracks onboarding flows.

Lifecycle:
    observe → Qualified lead or invoice paid event
    think   → Generate onboarding steps based on product tier
    act     → Create flow, send welcome email, track progress
    reflect → Learn from completion rates and feedback

Onboarding flow:
    1. Welcome email (auto, day 0)
    2. Account setup (auto, day 1)
    3. Data integration (tech team, day 3)
    4. Initial training (success team, day 5)
    5. First report delivery (auto, day 7)
    6. 30-day check-in (success team, day 30)

Enterprise clients get additional steps:
    - Dedicated account manager assignment
    - Custom integration planning
    - Custom dashboard setup
    - Executive review
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)
from app.autonomous.models.onboarding import (
    OnboardingFlow,
    OnboardingStatus,
    OnboardingStep,
    StepStatus,
    create_default_onboarding_steps,
)

logger = structlog.get_logger(__name__)


class OnboardingAgent(BiasharaAgent):
    """
    Autonomous customer onboarding agent.

    Subscribes to: lead.qualified, invoice.paid
    Publishes:     onboarding.started, onboarding.completed, onboarding.feedback

    Auto-generates onboarding flows based on product tier,
    tracks progress, and collects feedback.
    """

    def __init__(self):
        super().__init__(
            name="OnboardingAgent",
            role="Customer onboarding and success specialist",
            capabilities=[
                "onboarding_flow_generation",
                "progress_tracking",
                "welcome_email",
                "feedback_collection",
                "stall_detection",
            ],
        )
        # Onboarding store (in-memory; wire to DB in production)
        self._flows: Dict[str, OnboardingFlow] = {}

    # ── Lifecycle ───────────────────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Filter for onboarding-related events."""
        await super().observe(event)
        if event.event_type not in (
            EventType.LEAD_QUALIFIED,
            EventType.INVOICE_PAID,
            EventType.ONBOARDING_STARTED,
            EventType.ONBOARDING_FEEDBACK,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Decide what onboarding action to take.

        Analysis:
        1. If qualified lead or paid invoice → create onboarding flow
        2. If onboarding in progress → check for stalled steps
        3. If feedback received → process and update flow
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        event_type = event_data.get("event_type", "")

        if event_type in (EventType.LEAD_QUALIFIED.value, EventType.INVOICE_PAID.value):
            # Create new onboarding flow
            client_id = payload.get("lead", {}).get("lead_id") or payload.get("client_id", "")
            client_name = payload.get("lead", {}).get("company_name") or payload.get("client_name", "")
            product_tier = payload.get("lead", {}).get("metadata", {}).get("product_tier", "standard") or payload.get("product_tier", "standard")

            return AgentDecision(
                action="create_onboarding",
                parameters={
                    "client_id": client_id,
                    "client_name": client_name,
                    "product_tier": product_tier,
                },
                confidence=0.95,
                reasoning=f"Creating onboarding flow for '{client_name}' — {product_tier} tier.",
            )

        elif event_type == EventType.ONBOARDING_FEEDBACK.value:
            # Process onboarding feedback
            flow_id = payload.get("flow_id", "")
            return AgentDecision(
                action="process_feedback",
                parameters={
                    "flow_id": flow_id,
                    "satisfaction_score": payload.get("satisfaction_score", 0),
                    "feedback": payload.get("feedback", ""),
                },
                confidence=0.90,
                reasoning=f"Processing onboarding feedback for flow {flow_id}.",
            )

        else:
            # Check for stalled onboarding flows
            return AgentDecision(
                action="check_progress",
                parameters={},
                confidence=0.80,
                reasoning="Checking all onboarding flows for stalled progress.",
            )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the onboarding action."""
        start = time.time()

        try:
            action = decision.action
            params = decision.parameters
            events_to_publish = []

            if action == "create_onboarding":
                result = await self._create_onboarding(params, events_to_publish)
            elif action == "process_feedback":
                result = await self._process_feedback(params, events_to_publish)
            elif action == "check_progress":
                result = await self._check_progress(events_to_publish)
            else:
                result = {"error": f"Unknown action: {action}"}

            duration_ms = (time.time() - start) * 1000

            return AgentResult(
                success="error" not in result,
                data=result,
                duration_ms=duration_ms,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=[
                    AgentEvent(
                        event_type=EventType.PIPELINE_ERROR,
                        source=self.name,
                        payload={"error": str(exc), "phase": "onboarding"},
                    )
                ],
            )

    async def reflect(self, result: AgentResult) -> None:
        """Learn from onboarding outcomes."""
        await super().reflect(result)

        if result.success:
            data = result.data or {}
            self.memory.remember({
                "event_type": "onboarding_action",
                "action": data.get("action"),
                "flow_id": data.get("flow_id"),
            })

    # ── Onboarding operations ───────────────────────────────────────

    async def _create_onboarding(
        self,
        params: Dict[str, Any],
        events: List[AgentEvent],
    ) -> Dict[str, Any]:
        """Create a new onboarding flow for a client."""
        client_id = params.get("client_id", "")
        client_name = params.get("client_name", "")
        product_tier = params.get("product_tier", "standard")

        # Generate steps based on product tier
        steps = create_default_onboarding_steps(product_tier)

        # Create flow
        flow = OnboardingFlow(
            client_id=client_id,
            client_name=client_name,
            product_tier=product_tier,
            status=OnboardingStatus.CREATED,
            steps=steps,
            started_at=datetime.now(timezone.utc),
            target_completion=datetime.now(timezone.utc) + timedelta(days=30),
        )

        # Auto-complete the welcome email step (day 0)
        if flow.steps:
            welcome_step = flow.steps[0]
            welcome_step.status = StepStatus.COMPLETED
            welcome_step.completed_at = datetime.now(timezone.utc)

        # Store
        self._flows[flow.flow_id] = flow

        # Emit onboarding started event
        events.append(AgentEvent(
            event_type=EventType.ONBOARDING_STARTED,
            source=self.name,
            payload={
                "flow": flow.to_dict(),
                "flow_id": flow.flow_id,
                "client_id": client_id,
                "client_name": client_name,
                "product_tier": product_tier,
                "total_steps": len(steps),
            },
        ))

        self._logger.info(
            "onboarding_created",
            flow_id=flow.flow_id,
            client=client_name,
            tier=product_tier,
            steps=len(steps),
        )

        return {
            "action": "create_onboarding",
            "flow_id": flow.flow_id,
            "client_name": client_name,
            "product_tier": product_tier,
            "total_steps": len(steps),
            "progress_pct": flow.progress_pct,
        }

    async def _process_feedback(
        self,
        params: Dict[str, Any],
        events: List[AgentEvent],
    ) -> Dict[str, Any]:
        """Process onboarding feedback from a client."""
        flow_id = params.get("flow_id", "")
        flow = self._flows.get(flow_id)

        if not flow:
            return {"error": f"Onboarding flow {flow_id} not found"}

        satisfaction = params.get("satisfaction_score", 0)
        feedback = params.get("feedback", "")

        flow.satisfaction_score = satisfaction
        flow.feedback = feedback

        # If satisfaction is high and all steps done, mark complete
        if satisfaction >= 4.0 and flow.progress_pct >= 100:
            flow.status = OnboardingStatus.COMPLETED
            flow.completed_at = datetime.now(timezone.utc)

            events.append(AgentEvent(
                event_type=EventType.ONBOARDING_COMPLETED,
                source=self.name,
                payload={
                    "flow_id": flow_id,
                    "client_id": flow.client_id,
                    "client_name": flow.client_name,
                    "product_tier": flow.product_tier,
                    "satisfaction_score": satisfaction,
                },
            ))

        self._logger.info(
            "onboarding_feedback_processed",
            flow_id=flow_id,
            satisfaction=satisfaction,
            status=flow.status.value,
        )

        return {
            "action": "process_feedback",
            "flow_id": flow_id,
            "satisfaction_score": satisfaction,
            "status": flow.status.value,
        }

    async def _check_progress(
        self,
        events: List[AgentEvent],
    ) -> Dict[str, Any]:
        """Check all onboarding flows for stalled progress."""
        stalled_count = 0
        active_count = 0
        completed_count = 0

        for flow in self._flows.values():
            if flow.status == OnboardingStatus.COMPLETED:
                completed_count += 1
                continue
            if flow.status == OnboardingStatus.CANCELLED:
                continue

            active_count += 1

            # Auto-advance steps that are due
            now = datetime.now(timezone.utc)
            for step in flow.steps:
                if step.status == StepStatus.PENDING:
                    due_date = flow.started_at + timedelta(days=step.due_days) if flow.started_at else None
                    if due_date and now >= due_date:
                        # Step is due — mark as in-progress
                        step.status = StepStatus.IN_PROGRESS
                        self._logger.info(
                            "onboarding_step_due",
                            flow_id=flow.flow_id,
                            step=step.name,
                        )

            # Check for stalled flows
            if flow.is_stalled:
                stalled_count += 1
                flow.status = OnboardingStatus.STALLED
                self._logger.warning(
                    "onboarding_stalled",
                    flow_id=flow.flow_id,
                    client=flow.client_name,
                    progress=flow.progress_pct,
                )

        self._logger.info(
            "onboarding_progress_check",
            active=active_count,
            stalled=stalled_count,
            completed=completed_count,
        )

        return {
            "action": "check_progress",
            "total_flows": len(self._flows),
            "active": active_count,
            "stalled": stalled_count,
            "completed": completed_count,
        }

    # ── Public helpers ──────────────────────────────────────────────

    def complete_step(self, flow_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """Mark a specific onboarding step as completed."""
        flow = self._flows.get(flow_id)
        if not flow:
            return None

        for step in flow.steps:
            if step.name == step_name:
                step.status = StepStatus.COMPLETED
                step.completed_at = datetime.now(timezone.utc)

                # Check if all steps are done
                all_done = all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in flow.steps)
                if all_done:
                    flow.status = OnboardingStatus.COMPLETED
                    flow.completed_at = datetime.now(timezone.utc)

                return {
                    "flow_id": flow_id,
                    "step": step_name,
                    "progress_pct": flow.progress_pct,
                    "status": flow.status.value,
                }

        return None

    def get_flow(self, flow_id: str) -> Optional[Dict[str, Any]]:
        """Get onboarding flow details."""
        flow = self._flows.get(flow_id)
        return flow.to_dict() if flow else None

    def get_all_flows(self) -> List[Dict[str, Any]]:
        """Get all onboarding flows."""
        return [f.to_dict() for f in self._flows.values()]
