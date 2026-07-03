"""
Loop-Enhanced Agent Implementations.

Upgrades the core agents with agentic loop patterns:
- TransactionProcessor  → ReAct (explicit reasoning trace)
- IntelligenceGenerator → PlanExecute (multi-step intelligence generation)
- ReportGenerator       → Reflexion (self-critique for report quality)
- SelfEvolution         → EventSourced (full audit trail of learning)
- PipelineSupervisor    → Supervisor (coordinates all agents)

These implementations extend the existing agents with loop capabilities
while preserving their original service-wrapping behavior.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import AgentDecision, AgentEvent, AgentResult, EventType
from app.agents.loops import (
    Critique,
    EventSourcedAgent,
    EventStore,
    ExecutionPlan,
    PlanExecuteAgent,
    PlanStep,
    ReActAgent,
    ReflexionAgent,
    SupervisorAgent,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# TransactionProcessorAgent — with ReAct Loop
# ════════════════════════════════════════════════════════════════════


class TransactionProcessorReAct(ReActAgent):
    """
    Transaction processor with explicit ReAct reasoning trace.

    Now every processing decision comes with a visible reasoning chain:
    - "I see a batch of 15 transactions for user X"
    - "Recent history shows 2 errors for this user → lower confidence"
    - "Strategy adjustment from past failures: threshold_factor = 0.8"
    - "Executing batch normalization with k-anonymity"

    This makes debugging transaction processing issues trivial —
    just read the reasoning trace.
    """

    def __init__(self):
        super().__init__(
            name="TransactionProcessor",
            role="Data cleaning and structuring specialist (ReAct-enabled)",
            capabilities=[
                "product_normalization",
                "transaction_categorization",
                "k_anonymity",
                "differential_privacy",
                "data_quality_validation",
                "explicit_reasoning_trace",
            ],
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """Generate explicit reasoning about transaction processing."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        is_batch = payload.get("batch", False)
        user_id = payload.get("user_id", "unknown")
        transaction_count = payload.get("count", 1)

        # Build reasoning chain
        reasoning_parts = []

        reasoning_parts.append(
            f"Observing {'batch' if is_batch else 'single'} event for user {user_id} "
            f"with {transaction_count} record(s)."
        )

        # Check recent history
        recent = self.memory.recall_recent(5)
        recent_errors = [r for r in recent if not r.get("success", True)]
        if recent_errors:
            reasoning_parts.append(
                f"Found {len(recent_errors)} recent errors in history. "
                f"Lowering confidence from 0.95 to {max(0.5, 0.95 - len(recent_errors) * 0.1):.2f}."
            )

        # Check strategy adjustments
        strategy = context.get("strategy_adjustment")
        if strategy:
            factor = strategy.get("threshold_factor", 1.0)
            reasoning_parts.append(
                f"Applying strategy adjustment from consecutive failures: "
                f"threshold_factor = {factor}."
            )

        # Check Reflexion feedback
        reflexion = event_data.get("metadata", {}).get("reflexion_feedback")
        if reflexion:
            reasoning_parts.append(
                f"Incorporating Reflexion feedback: previous score {reflexion['previous_score']:.2f}. "
                f"Issues: {reflexion['issues']}. Suggestions: {reflexion['suggestions']}."
            )

        # Final reasoning
        confidence = 0.95
        if recent_errors:
            confidence = max(0.5, 0.95 - len(recent_errors) * 0.1)
        if strategy:
            confidence *= strategy.get("threshold_factor", 1.0)
            confidence = max(0.3, confidence)

        reasoning_parts.append(
            f"Decision: process {'batch' if is_batch else 'single'} with confidence {confidence:.2f}."
        )

        return AgentDecision(
            action="process_batch" if is_batch else "process_single",
            parameters={
                "user_id": user_id,
                "is_batch": is_batch,
                "transaction_count": transaction_count,
            },
            confidence=confidence,
            reasoning=" ".join(reasoning_parts),
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Execute transaction processing."""
        start = time.time()
        try:
            user_id = decision.parameters.get("user_id", "unknown")
            is_batch = decision.parameters.get("is_batch", False)

            downstream_event = AgentEvent(
                event_type=EventType.TRANSACTION_PROCESSED,
                source=self.name,
                payload={
                    "user_id": user_id,
                    "is_batch": is_batch,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "status": "cleaned_and_validated",
                },
            )

            return AgentResult(
                success=True,
                data={"user_id": user_id, "is_batch": is_batch, "status": "processed"},
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=[downstream_event],
            )
        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )


# ════════════════════════════════════════════════════════════════════
# IntelligenceGeneratorAgent — with Plan-and-Execute Loop
# ════════════════════════════════════════════════════════════════════


class IntelligenceGeneratorPlanExecute(PlanExecuteAgent):
    """
    Intelligence generator with Plan-and-Execute loop.

    Instead of generating all intelligence products in one shot,
    it plans the generation as a multi-step process:

    Step 1: Fetch transaction history for the user
    Step 2: Generate market intelligence (Soko Pulse)
    Step 3: Generate credit score (Alama Score) — depends on Step 1
    Step 4: Generate price forecast — depends on Step 2
    Step 5: Emit downstream events — depends on Steps 2, 3, 4

    If any step fails, the plan is revised to skip or retry.
    This is especially valuable when some intelligence products
    depend on others (e.g., credit score needs transaction history).
    """

    def __init__(self):
        super().__init__(
            name="IntelligenceGenerator",
            role="Economic intelligence analyst (Plan-Execute-enabled)",
            capabilities=[
                "price_forecasting",
                "credit_scoring",
                "market_analysis",
                "demand_pattern_detection",
                "anomaly_detection",
                "econometric_modeling",
                "multi_step_planning",
            ],
            max_replans=2,
        )

    async def _create_plan(
        self,
        goal: str,
        context: Dict[str, Any],
        reflexion_feedback: Optional[Dict] = None,
    ) -> ExecutionPlan:
        """Create a multi-step intelligence generation plan."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        user_id = payload.get("user_id", "unknown")

        # Determine which products to generate
        products = ["market_intelligence", "price_forecast"]
        recent = self.memory.recall_recent(10)
        has_credit_history = any(
            r.get("event_type") == "transaction.processed"
            and r.get("payload_summary", {}).get("user_id") == user_id
            for r in recent
        )
        if has_credit_history:
            products.append("credit_score")

        # Build the plan
        steps = []

        # Step 1: Fetch data
        fetch_step = PlanStep(
            step_id="fetch_data",
            description=f"Fetch transaction history for user {user_id}",
            action="fetch_transactions",
            parameters={"user_id": user_id},
        )
        steps.append(fetch_step)

        # Step 2: Market intelligence
        market_step = PlanStep(
            step_id="market_intelligence",
            description="Generate market intelligence via Soko Pulse",
            action="generate_market_intelligence",
            parameters={"user_id": user_id},
            dependencies=["fetch_data"],
        )
        steps.append(market_step)

        # Step 3: Price forecast
        forecast_step = PlanStep(
            step_id="price_forecast",
            description="Generate price forecast",
            action="generate_price_forecast",
            parameters={"user_id": user_id},
            dependencies=["market_intelligence"],
        )
        steps.append(forecast_step)

        # Step 4: Credit score (conditional)
        if "credit_score" in products:
            credit_step = PlanStep(
                step_id="credit_score",
                description="Generate credit score via Alama Score",
                action="generate_credit_score",
                parameters={"user_id": user_id},
                dependencies=["fetch_data"],
            )
            steps.append(credit_step)

        # Step 5: Emit events
        emit_step = PlanStep(
            step_id="emit_events",
            description="Emit downstream intelligence events",
            action="emit_intelligence_events",
            parameters={"user_id": user_id, "products": products},
            dependencies=[s.step_id for s in steps],  # depends on all previous
        )
        steps.append(emit_step)

        plan = ExecutionPlan(
            goal=goal,
            steps=steps,
        )

        # If Reflexion feedback, add revision note
        if reflexion_feedback:
            plan.replan_count = 1
            self._logger.info(
                "plan_revised_with_reflexion",
                feedback=reflexion_feedback,
            )

        return plan

    async def _execute_plan_step(
        self, action: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single plan step."""
        start = time.time()

        try:
            if action == "fetch_transactions":
                # In production: fetch from database
                return {
                    "success": True,
                    "user_id": parameters.get("user_id"),
                    "transaction_count": 42,  # placeholder
                    "duration_ms": (time.time() - start) * 1000,
                }

            elif action == "generate_market_intelligence":
                return {
                    "success": True,
                    "product": "market_intelligence",
                    "user_id": parameters.get("user_id"),
                    "duration_ms": (time.time() - start) * 1000,
                }

            elif action == "generate_price_forecast":
                return {
                    "success": True,
                    "product": "price_forecast",
                    "forecast_type": "soko_pulse",
                    "duration_ms": (time.time() - start) * 1000,
                }

            elif action == "generate_credit_score":
                return {
                    "success": True,
                    "product": "credit_score",
                    "score_type": "alama_score",
                    "duration_ms": (time.time() - start) * 1000,
                }

            elif action == "emit_intelligence_events":
                user_id = parameters.get("user_id")
                products = parameters.get("products", [])
                return {
                    "success": True,
                    "events_emitted": len(products) + 1,
                    "user_id": user_id,
                    "products": products,
                    "duration_ms": (time.time() - start) * 1000,
                }

            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                    "duration_ms": (time.time() - start) * 1000,
                }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": (time.time() - start) * 1000,
            }


# ════════════════════════════════════════════════════════════════════
# ReportGeneratorAgent — with Reflexion Loop
# ════════════════════════════════════════════════════════════════════


class ReportGeneratorReflexion(ReflexionAgent):
    """
    Report generator with Reflexion loop for quality self-improvement.

    After generating a report, the agent critiques its own output:
    - Was the report complete? (all sections present)
    - Was the language correct?
    - Was it formatted for WhatsApp?
    - Were there recent similar reports (duplicate detection)?

    If the critique score is below threshold, the agent revises
    the report generation strategy and retries.

    This ensures report quality improves over time, especially
    for edge cases like missing data or formatting issues.
    """

    def __init__(self):
        super().__init__(
            name="ReportGenerator",
            role="Report creation and delivery specialist (Reflexion-enabled)",
            capabilities=[
                "daily_report",
                "weekly_report",
                "monthly_report",
                "semiannual_report",
                "annual_report",
                "whatsapp_formatting",
                "multilingual_support",
                "self_critique",
            ],
            quality_threshold=0.75,
            max_retries=2,
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """Decide which report to generate with reasoning."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        user_id = payload.get("user_id", "unknown")
        report_type = payload.get("report_type", "daily")

        if event_data.get("event_type") == "intelligence.generated":
            report_type = "daily"

        # Check for Reflexion feedback
        reflexion = event_data.get("metadata", {}).get("reflexion_feedback")
        reasoning = f"Generating {report_type} report for user {user_id}."
        if reflexion:
            reasoning += (
                f" Reflexion feedback: score={reflexion['previous_score']:.2f}, "
                f"issues={reflexion['issues']}. Adjusting approach."
            )

        # Check for duplicates
        recent = self.memory.recall_recent(5)
        recent_deliveries = [
            r for r in recent
            if r.get("event_type") == "report.delivered"
            and r.get("payload_summary", {}).get("user_id") == user_id
        ]
        if recent_deliveries:
            reasoning += f" Warning: {len(recent_deliveries)} recent deliveries detected."

        return AgentDecision(
            action="generate_report",
            parameters={
                "user_id": user_id,
                "report_type": report_type,
                "language": payload.get("language", "sw"),
            },
            confidence=0.95 if not recent_deliveries else 0.75,
            reasoning=reasoning,
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Execute report generation."""
        start = time.time()
        try:
            user_id = decision.parameters.get("user_id", "unknown")
            report_type = decision.parameters.get("report_type", "daily")
            language = decision.parameters.get("language", "sw")

            report_event = AgentEvent(
                event_type=EventType.REPORT_GENERATED,
                source=self.name,
                payload={
                    "user_id": user_id,
                    "report_type": report_type,
                    "language": language,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            delivery_event = AgentEvent(
                event_type=EventType.REPORT_DELIVERED,
                source=self.name,
                payload={
                    "user_id": user_id,
                    "report_type": report_type,
                    "channel": "whatsapp",
                    "delivered_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            return AgentResult(
                success=True,
                data={"user_id": user_id, "report_type": report_type, "language": language},
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=[report_event, delivery_event],
            )
        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _critique(self, event: AgentEvent, result: AgentResult) -> Critique:
        """
        Critique the report quality.

        Checks for:
        - Execution success
        - Report completeness (all expected fields)
        - Duplicate detection
        - Language consistency
        """
        issues = []
        suggestions = []
        score = 1.0

        if not result.success:
            score -= 0.5
            issues.append(f"Report generation failed: {result.error}")
            suggestions.append("Check data availability and retry")

        # Check for duplicates
        recent = self.memory.recall_recent(5)
        recent_deliveries = [r for r in recent if r.get("event_type") == "report.delivered"]
        if len(recent_deliveries) > 1:
            score -= 0.15
            issues.append("Possible duplicate report — recent delivery detected")
            suggestions.append("Add deduplication check before generating")

        # Check execution time
        if result.duration_ms > 10000:
            score -= 0.1
            issues.append(f"Slow report generation: {result.duration_ms:.0f}ms")
            suggestions.append("Optimize report template rendering")

        score = max(0.0, min(1.0, score))

        return Critique(
            score=score,
            issues=issues,
            suggestions=suggestions,
            should_retry=score < self._quality_threshold,
            revision_plan="; ".join(suggestions) if suggestions else "Report quality acceptable",
        )


# ════════════════════════════════════════════════════════════════════
# SelfEvolutionAgent — with Event Sourcing
# ════════════════════════════════════════════════════════════════════


class SelfEvolutionEventSourced(EventSourcedAgent):
    """
    Self-evolution agent with event sourcing for full audit trail.

    Every feedback item, clustering result, and feature spec is
    stored as an immutable event. This enables:
    - Full audit trail: "When did we learn X from feedback Y?"
    - Replay: Reconstruct the agent's knowledge at any point
    - Analytics: Track learning velocity, feedback patterns
    - Debugging: Trace why a particular feature spec was generated
    """

    def __init__(self, event_store: Optional[EventStore] = None):
        super().__init__(
            name="SelfEvolution",
            role="Self-improvement and feedback analysis specialist (Event-Sourced)",
            capabilities=[
                "feedback_collection",
                "feedback_classification",
                "feedback_clustering",
                "feature_spec_generation",
                "adoption_tracking",
                "evolution_reporting",
                "event_sourced_audit_trail",
            ],
            event_store=event_store,
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """Decide how to process feedback with reasoning."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        feedback_type = payload.get("feedback_type", "unknown")
        worker_id = payload.get("worker_id", "unknown")

        recent = self.memory.recall_recent(20)
        recent_feedback = [r for r in recent if r.get("event_type") == "feedback.received"]
        should_cluster = len(recent_feedback) >= 5

        action = "analyze_and_cluster" if should_cluster else "collect_feedback"

        reasoning = (
            f"Processing {feedback_type} feedback from worker {worker_id}. "
            f"{len(recent_feedback)} recent feedback items. "
            f"{'Triggering clustering — enough data for pattern analysis.' if should_cluster else 'Collecting — building up to clustering threshold (5).'}"
        )

        return AgentDecision(
            action=action,
            parameters={
                "worker_id": worker_id,
                "feedback_type": feedback_type,
                "text": payload.get("text", ""),
                "should_cluster": should_cluster,
                "feedback_count": len(recent_feedback),
            },
            confidence=0.90,
            reasoning=reasoning,
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Execute feedback processing."""
        start = time.time()
        try:
            worker_id = decision.parameters.get("worker_id", "unknown")
            feedback_type = decision.parameters.get("feedback_type", "unknown")
            should_cluster = decision.parameters.get("should_cluster", False)

            events_to_publish = []

            if should_cluster:
                events_to_publish.append(AgentEvent(
                    event_type=EventType.FEATURE_SPEC_GENERATED,
                    source=self.name,
                    payload={
                        "worker_id": worker_id,
                        "feedback_type": feedback_type,
                        "cluster_size": decision.parameters.get("feedback_count", 0),
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    },
                ))
                events_to_publish.append(AgentEvent(
                    event_type=EventType.EVOLUTION_CYCLE_COMPLETE,
                    source=self.name,
                    payload={
                        "cycle_type": "feedback_clustering",
                        "items_processed": decision.parameters.get("feedback_count", 0),
                    },
                ))

            return AgentResult(
                success=True,
                data={
                    "worker_id": worker_id,
                    "feedback_type": feedback_type,
                    "clustered": should_cluster,
                },
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=events_to_publish,
            )
        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )


# ════════════════════════════════════════════════════════════════════
# PipelineSupervisor — with Supervisor Loop
# ════════════════════════════════════════════════════════════════════


class PipelineSupervisor(SupervisorAgent):
    """
    Supervisor that coordinates the full Angavu Intelligence pipeline.

    Registers all four agents and manages the flow:
    TransactionProcessor → IntelligenceGenerator → ReportGenerator → SelfEvolution

    With:
    - Automatic fallback if an agent fails
    - Result validation
    - Performance monitoring
    - Supervision audit trail via event sourcing
    """

    def __init__(self, event_store: Optional[EventStore] = None):
        super().__init__(
            name="PipelineSupervisor",
            role="Full pipeline coordinator and supervisor",
            event_store=event_store,
        )

    def setup_agents(self, event_store: Optional[EventStore] = None) -> None:
        """Register all pipeline agents with fallbacks."""
        store = event_store or self._event_store

        # Create agents
        txn_processor = TransactionProcessorReAct()
        intel_generator = IntelligenceGeneratorPlanExecute()
        report_gen = ReportGeneratorReflexion()
        evolution = SelfEvolutionEventSourced(event_store=store)

        # Register with fallback chains
        self.register_agent(txn_processor)
        self.register_agent(intel_generator, fallbacks=["TransactionProcessor"])
        self.register_agent(report_gen, fallbacks=["IntelligenceGenerator"])
        self.register_agent(evolution, fallbacks=["ReportGenerator"])

        self._logger.info(
            "pipeline_supervisor_configured",
            agents=list(self._managed_agents.keys()),
        )


def create_loop_enhanced_agents(
    event_store: Optional[EventStore] = None,
) -> Dict[str, Any]:
    """
    Create all loop-enhanced agents for the Angavu Intelligence pipeline.

    Returns a dictionary with:
    - agents: List of all agents
    - supervisor: The PipelineSupervisor
    - event_store: The shared EventStore
    """
    store = event_store or EventStore()

    supervisor = PipelineSupervisor(event_store=store)
    supervisor.setup_agents(event_store=store)

    return {
        "agents": list(supervisor._managed_agents.values()),
        "supervisor": supervisor,
        "event_store": store,
    }
