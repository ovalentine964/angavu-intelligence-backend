"""
Intelligence Generation Loop — Collect → Analyze → Deliver.

Orchestrates the full intelligence pipeline:
1. Collect: Gather transaction data, market data, user context
2. Analyze: Run Soko Pulse, Alama Score, econometric analysis
3. Deliver: Format and send via WhatsApp

Uses DeerFlow's PlanExecute pattern for multi-step orchestration:
- Creates a plan with dependency tracking
- Executes steps in parallel where possible
- Re-plans on failure

Maps to DeerFlow's GoalState for tracking overall pipeline progress.
Each intelligence product (market intel, price forecast, credit score)
is a sub-goal within the larger intelligence generation goal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from app.agents.base import AgentEvent, EventType
from app.agents.loops.core import ExecutionPlan, PlanExecuteAgent, PlanStep
from app.loops.config import get_loop_config

logger = structlog.get_logger(__name__)


@dataclass
class IntelligenceRequest:
    """A request for intelligence generation."""
    request_id: str
    worker_id: str
    products: list[str]  # market_intelligence | price_forecast | credit_score
    language: str = "sw"
    delivery_channel: str = "whatsapp"
    priority: str = "normal"  # normal | high | urgent


@dataclass
class IntelligenceProduct:
    """A generated intelligence product."""
    product_type: str
    worker_id: str
    data: dict[str, Any]
    confidence: float
    generated_at: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(UTC).isoformat()


@dataclass
class IntelligenceDelivery:
    """Record of intelligence delivery."""
    request_id: str
    worker_id: str
    products_delivered: list[str]
    delivery_channel: str
    delivered_at: str = ""
    success: bool = True


@dataclass
class IntelligenceLoopState:
    """Loop state for intelligence generation."""
    request_id: str
    worker_id: str
    continuation_count: int = 0
    no_progress_count: int = 0
    max_continuations: int = 3
    max_no_progress: int = 1

    data_collected: bool = False
    analysis_complete: bool = False
    report_delivered: bool = False

    request: IntelligenceRequest | None = None
    products: dict[str, IntelligenceProduct] = field(default_factory=dict)
    delivery: IntelligenceDelivery | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def is_satisfied(self) -> bool:
        return self.data_collected and self.analysis_complete and self.report_delivered

    def get_blocker(self) -> str:
        if not self.data_collected:
            return "missing_evidence"
        if not self.analysis_complete:
            return "goal_not_met_yet"
        if not self.report_delivered:
            return "goal_not_met_yet"
        return "none"

    def record_progress(self, phase: str, result: dict[str, Any]) -> bool:
        changed = False
        if phase == "collect" and not self.data_collected:
            self.data_collected = True
            self.evidence["data_collected"] = result
            changed = True
        elif phase == "analyze" and not self.analysis_complete:
            self.analysis_complete = True
            self.evidence["analysis_complete"] = result
            changed = True
        elif phase == "deliver" and not self.report_delivered:
            self.report_delivered = True
            self.evidence["report_delivered"] = result
            changed = True
        return changed

    def to_goal_state(self) -> dict[str, Any]:
        return {
            "objective": f"Generate intelligence for worker {self.worker_id}",
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


class IntelligenceLoop(PlanExecuteAgent):
    """
    Intelligence generation loop: Collect → Analyze → Deliver.

    Uses PlanExecute pattern for multi-step orchestration:

    Plan:
      1. collect_data (no deps)
      2. generate_market_intelligence (depends on collect_data)
      3. generate_price_forecast (depends on collect_data)
      4. generate_credit_score (depends on collect_data)
      5. format_report (depends on 2, 3, 4)
      6. deliver_report (depends on 5)

    Steps 2, 3, 4 can run in parallel after step 1 completes.
    This maps naturally to DeerFlow's GoalState with sub-goals.

    Re-planning: If a product fails to generate, the plan is revised
    to deliver whatever products succeeded.
    """

    def __init__(self):
        super().__init__(
            name="IntelligenceLoop",
            role="Intelligence generation and delivery orchestrator",
            capabilities=[
                "data_collection",
                "market_intelligence",
                "price_forecasting",
                "credit_scoring",
                "report_formatting",
                "whatsapp_delivery",
                "multi_step_planning",
            ],
            max_replans=2,
        )
        self._config = get_loop_config("intelligence_generation")
        self._active_states: dict[str, IntelligenceLoopState] = {}

    def _get_or_create_state(self, request_id: str, worker_id: str) -> IntelligenceLoopState:
        if request_id not in self._active_states:
            self._active_states[request_id] = IntelligenceLoopState(
                request_id=request_id,
                worker_id=worker_id,
            )
        return self._active_states[request_id]

    async def _create_plan(
        self,
        goal: str,
        context: dict[str, Any],
        reflexion_feedback: dict | None = None,
    ) -> ExecutionPlan:
        """
        Create an intelligence generation plan.

        Steps with dependencies:
        1. collect_data
        2. market_intelligence (depends on 1)
        3. price_forecast (depends on 1)
        4. credit_score (depends on 1)
        5. format_report (depends on 2, 3, 4)
        6. deliver_report (depends on 5)
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        worker_id = payload.get("worker_id", "unknown")
        products = payload.get("products", ["market_intelligence", "price_forecast", "credit_score"])
        request_id = payload.get("request_id", f"intel_{worker_id}_{int(time.time())}")

        state = self._get_or_create_state(request_id, worker_id)
        state.request = IntelligenceRequest(
            request_id=request_id,
            worker_id=worker_id,
            products=products,
            language=payload.get("language", "sw"),
            delivery_channel=payload.get("delivery_channel", "whatsapp"),
        )

        steps = []

        # Step 1: Collect data
        steps.append(PlanStep(
            step_id="collect_data",
            description=f"Collect transaction and context data for worker {worker_id}",
            action="collect_data",
            parameters={"worker_id": worker_id, "request_id": request_id},
        ))

        # Steps 2-4: Generate products (parallel, depend on collect)
        product_steps = []
        for product in products:
            step_id = f"generate_{product}"
            steps.append(PlanStep(
                step_id=step_id,
                description=f"Generate {product} for worker {worker_id}",
                action=f"generate_{product}",
                parameters={"worker_id": worker_id, "product": product, "request_id": request_id},
                dependencies=["collect_data"],
            ))
            product_steps.append(step_id)

        # Step 5: Format report
        steps.append(PlanStep(
            step_id="format_report",
            description="Format intelligence products into WhatsApp-ready report",
            action="format_report",
            parameters={
                "worker_id": worker_id,
                "products": products,
                "language": payload.get("language", "sw"),
                "request_id": request_id,
            },
            dependencies=product_steps,
        ))

        # Step 6: Deliver report
        steps.append(PlanStep(
            step_id="deliver_report",
            description="Deliver formatted report via WhatsApp",
            action="deliver_report",
            parameters={
                "worker_id": worker_id,
                "channel": payload.get("delivery_channel", "whatsapp"),
                "request_id": request_id,
            },
            dependencies=["format_report"],
        ))

        plan = ExecutionPlan(
            goal=goal,
            steps=steps,
        )

        if reflexion_feedback:
            plan.replan_count = 1
            self._logger.info(
                "intelligence_plan_revised",
                feedback=reflexion_feedback,
                request_id=request_id,
            )

        return plan

    async def _execute_plan_step(
        self, action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a single intelligence pipeline step."""
        start = time.time()
        worker_id = parameters.get("worker_id", "unknown")
        request_id = parameters.get("request_id", "unknown")
        state = self._active_states.get(request_id)

        try:
            if action == "collect_data":
                return await self._step_collect(worker_id, request_id, state)

            elif action.startswith("generate_"):
                product = parameters.get("product", action.replace("generate_", ""))
                return await self._step_generate(product, worker_id, request_id, state)

            elif action == "format_report":
                return await self._step_format(worker_id, request_id, state)

            elif action == "deliver_report":
                return await self._step_deliver(worker_id, request_id, state)

            else:
                return {"success": False, "error": f"Unknown action: {action}"}

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": (time.time() - start) * 1000,
            }

    async def _step_collect(
        self, worker_id: str, request_id: str, state: IntelligenceLoopState | None
    ) -> dict[str, Any]:
        """Collect data for intelligence generation."""
        start = time.time()

        # In production: fetch from database, market APIs, etc.
        self.memory.remember({
            "event": "intelligence_data_collected",
            "worker_id": worker_id,
            "request_id": request_id,
        })

        if state:
            state.record_progress("collect", {"worker_id": worker_id})

        return {
            "success": True,
            "new_data": True,
            "data": {
                "worker_id": worker_id,
                "transaction_count": 42,
                "market_data_available": True,
                "context_loaded": True,
            },
            "duration_ms": (time.time() - start) * 1000,
        }

    async def _step_generate(
        self, product: str, worker_id: str, request_id: str, state: IntelligenceLoopState | None
    ) -> dict[str, Any]:
        """Generate a specific intelligence product."""
        start = time.time()

        # In production: call Soko Pulse, Alama Score, etc.
        product_data = {}

        if product == "market_intelligence":
            product_data = {
                "market_trend": "increasing",
                "volatility": "low",
                "top_commodities": ["maize", "beans", "rice"],
                "price_alerts": [],
            }
        elif product == "price_forecast":
            product_data = {
                "forecast_horizon_days": 30,
                "commodity": "maize",
                "current_price": 850.0,
                "predicted_price": 920.0,
                "confidence": 0.75,
                "trend": "upward",
            }
        elif product == "credit_score":
            product_data = {
                "score": 720,
                "rating": "good",
                "factors": ["consistent_payments", "growing_revenue"],
                "risk_level": "moderate",
            }

        intel_product = IntelligenceProduct(
            product_type=product,
            worker_id=worker_id,
            data=product_data,
            confidence=0.8,
        )

        if state:
            state.products[product] = intel_product

        self.memory.remember({
            "event": f"intelligence_{product}_generated",
            "worker_id": worker_id,
            "request_id": request_id,
        })

        return {
            "success": True,
            "new_data": True,
            "product": product,
            "data": product_data,
            "duration_ms": (time.time() - start) * 1000,
        }

    async def _step_format(
        self, worker_id: str, request_id: str, state: IntelligenceLoopState | None
    ) -> dict[str, Any]:
        """Format intelligence products into a report."""
        start = time.time()

        products_summary = {}
        if state:
            for name, product in state.products.items():
                products_summary[name] = {
                    "type": product.product_type,
                    "confidence": product.confidence,
                }

        # In production: format for WhatsApp using report templates
        formatted = {
            "worker_id": worker_id,
            "language": "sw",
            "sections": list(products_summary.keys()),
            "format": "whatsapp_markdown",
        }

        self.memory.remember({
            "event": "intelligence_report_formatted",
            "worker_id": worker_id,
            "request_id": request_id,
            "section_count": len(products_summary),
        })

        return {
            "success": True,
            "new_data": True,
            "formatted_report": formatted,
            "duration_ms": (time.time() - start) * 1000,
        }

    async def _step_deliver(
        self, worker_id: str, request_id: str, state: IntelligenceLoopState | None
    ) -> dict[str, Any]:
        """Deliver the formatted report."""
        start = time.time()

        channel = "whatsapp"
        products_delivered = list(state.products.keys()) if state else []

        if state:
            state.record_progress("deliver", {
                "channel": channel,
                "products": products_delivered,
            })

        self.memory.remember({
            "event": "intelligence_delivered",
            "worker_id": worker_id,
            "request_id": request_id,
            "channel": channel,
            "products": products_delivered,
        })

        # Publish delivery event
        if self._event_bus:
            await self._event_bus.publish(AgentEvent(
                event_type=EventType.REPORT_DELIVERED,
                source=self.name,
                payload={
                    "worker_id": worker_id,
                    "request_id": request_id,
                    "channel": channel,
                    "products": products_delivered,
                },
            ))

        return {
            "success": True,
            "new_data": True,
            "delivery": {
                "channel": channel,
                "products_delivered": products_delivered,
                "delivered_at": datetime.now(UTC).isoformat(),
            },
            "duration_ms": (time.time() - start) * 1000,
        }

    def get_state(self, request_id: str) -> dict[str, Any] | None:
        state = self._active_states.get(request_id)
        return state.to_goal_state() if state else None

    def reset_state(self, request_id: str) -> None:
        self._active_states.pop(request_id, None)
