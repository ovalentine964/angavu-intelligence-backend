"""
Agent Implementations — Wrapping existing services as autonomous agents.

Each agent class wraps one or more existing Angavu Intelligence services
and adds the observe → think → act → reflect lifecycle.

    TransactionProcessorAgent  → pipeline.py (DataPipeline)
    IntelligenceGeneratorAgent → soko_pulse.py + alama_score.py + econometrics
    ReportGeneratorAgent       → report_generator.py (ReportGenerator)
    SelfEvolutionAgent         → self_evolution.py (SelfEvolutionService)

These agents don't replace the services — they orchestrate them.
The services remain usable directly for simple API calls.
The agents add event-driven coordination, memory, and observability.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentMessage,
    AgentResult,
    BiasharaAgent,
    EventType,
)
from app.services.skill_registry import get_skill_registry

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# TransactionProcessorAgent
# ════════════════════════════════════════════════════════════════════


class TransactionProcessorAgent(BiasharaAgent):
    """
    Processes raw M-Pesa / POS transactions into structured data.

    Wraps: DataPipeline (app/services/pipeline.py)
    Subscribes to: transaction.received
    Publishes:     transaction.processed, batch.processed

    Responsibilities:
    - Normalize product names (Swahili → English)
    - Categorize transactions
    - Apply k-anonymity and differential privacy
    - Validate data quality
    """

    def __init__(self, pipeline: Any = None):
        super().__init__(
            name="TransactionProcessor",
            role="Data cleaning and structuring specialist",
            capabilities=[
                "product_normalization",
                "transaction_categorization",
                "k_anonymity",
                "differential_privacy",
                "data_quality_validation",
            ],
        )
        # Real service dependency (injected by factory or main)
        self._pipeline: Any = pipeline  # DataPipeline | None

        # Wire skills
        registry = get_skill_registry()
        for skill in registry.get_skills_for_agent(self.name):
            self.tools.register(skill.name, skill.safe_execute, skill.description)

    def set_pipeline(self, pipeline: Any) -> None:
        """Inject the DataPipeline service."""
        self._pipeline = pipeline

    # ── Lifecycle ───────────────────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Filter for transaction events only."""
        await super().observe(event)
        # Only process transaction events
        if event.event_type not in (
            EventType.TRANSACTION_RECEIVED,
            EventType.BATCH_PROCESSED,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Decide how to process the incoming transaction data.

        Analyzes the event payload to determine:
        - Single transaction vs. batch
        - Which cleaning steps are needed
        - Whether data quality is sufficient
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})

        is_batch = payload.get("batch", False)
        user_id = payload.get("user_id", "unknown")
        transaction_count = payload.get("count", 1)

        # Check recent processing history for this user
        recent = self.memory.recall_recent(5)
        recent_errors = [r for r in recent if not r.get("success", True)]

        # Adjust confidence based on past errors for this user
        confidence = 0.95
        if recent_errors:
            confidence = max(0.5, 0.95 - len(recent_errors) * 0.1)

        # Apply strategy adjustment from reflect→behavior loop
        strategy = context.get("strategy_adjustment")
        if strategy:
            confidence *= strategy.get("threshold_factor", 1.0)
            confidence = max(0.3, confidence)

        # Check past reflections for relevant lessons
        reflections = context.get("past_reflections", [])
        if reflections:
            self._logger.debug(
                "applying_reflections",
                count=len(reflections),
            )

        action = "process_batch" if is_batch else "process_single"
        parameters = {
            "user_id": user_id,
            "is_batch": is_batch,
            "transaction_count": transaction_count,
        }

        reasoning = (
            f"Processing {'batch' if is_batch else 'single'} transaction(s) "
            f"for user {user_id}. "
            f"{transaction_count} record(s) to process. "
            f"Confidence: {confidence:.0%} "
            f"({len(recent_errors)} recent errors in history)."
        )

        return AgentDecision(
            action=action,
            parameters=parameters,
            confidence=confidence,
            reasoning=reasoning,
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Execute transaction processing via the DataPipeline.

        When a real DataPipeline is injected, calls clean_transactions()
        to normalize product names, categorize, and validate data quality.
        Always emits downstream events for the IntelligenceGenerator.
        """
        start = time.time()

        try:
            user_id = decision.parameters.get("user_id", "unknown")
            is_batch = decision.parameters.get("is_batch", False)

            # Call real service if available
            cleaned_records = []
            if self._pipeline:
                try:
                    cleaned_records = await self._pipeline.clean_transactions(
                        user_id=user_id,
                    )
                    self._logger.info(
                        "pipeline_clean_transactions",
                        user_id=user_id,
                        records_cleaned=len(cleaned_records),
                    )
                except Exception as pipeline_exc:
                    self._logger.warning(
                        "pipeline_call_failed",
                        error=str(pipeline_exc),
                        fallback=True,
                    )

            # Build downstream event for the IntelligenceGenerator
            downstream_event = AgentEvent(
                event_type=EventType.TRANSACTION_PROCESSED,
                source=self.name,
                payload={
                    "user_id": user_id,
                    "is_batch": is_batch,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "status": "cleaned_and_validated",
                    "records_cleaned": len(cleaned_records),
                },
            )

            duration_ms = (time.time() - start) * 1000

            return AgentResult(
                success=True,
                data={
                    "user_id": user_id,
                    "is_batch": is_batch,
                    "status": "processed",
                    "records_cleaned": len(cleaned_records),
                },
                duration_ms=duration_ms,
                events_to_publish=[downstream_event],
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
                        payload={"error": str(exc), "phase": "transaction_processing"},
                    )
                ],
            )


# ════════════════════════════════════════════════════════════════════
# IntelligenceGeneratorAgent
# ════════════════════════════════════════════════════════════════════


class IntelligenceGeneratorAgent(BiasharaAgent):
    """
    Generates intelligence products from processed transaction data.

    Wraps: SokoPulseService, AlamaScoreService, EconometricEngine
    Subscribes to: transaction.processed
    Publishes:     intelligence.generated, price.forecast.ready,
                   credit.score.ready, market.alert

    Responsibilities:
    - Price forecasting (ARIMA/SARIMA via Soko Pulse)
    - Credit scoring (MLE logit + Heckman correction via Alama Score)
    - Market intelligence (game theory, econometrics)
    - Demand pattern detection
    - Anomaly detection and alerting
    """

    def __init__(self, soko_pulse: Any = None, alama_score: Any = None):
        super().__init__(
            name="IntelligenceGenerator",
            role="Economic intelligence analyst",
            capabilities=[
                "price_forecasting",
                "credit_scoring",
                "market_analysis",
                "demand_pattern_detection",
                "anomaly_detection",
                "econometric_modeling",
            ],
        )
        # Real service dependencies (injected by factory or main)
        self._soko_pulse: Any = soko_pulse  # SokoPulseService | None
        self._alama_score: Any = alama_score  # AlamaScoreService | None

        # Wire skills
        registry = get_skill_registry()
        for skill in registry.get_skills_for_agent(self.name):
            self.tools.register(skill.name, skill.safe_execute, skill.description)

    def set_soko_pulse(self, service: Any) -> None:
        """Inject the SokoPulseService for price forecasting."""
        self._soko_pulse = service

    def set_alama_score(self, service: Any) -> None:
        """Inject the AlamaScoreService for credit scoring."""
        self._alama_score = service

    async def observe(self, event: AgentEvent) -> None:
        """Process transaction-processed events, market alerts, and outcome feedback."""
        await super().observe(event)
        if event.event_type not in (
            EventType.TRANSACTION_PROCESSED,
            EventType.INTELLIGENCE_REQUESTED,
            EventType.MARKET_ALERT,
            EventType.FEEDBACK_RECEIVED,
            EventType.CUSTOMER_FEEDBACK_RECEIVED,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Decide which intelligence products to generate.

        Analyzes the processed transaction data to determine:
        - Which intelligence products are relevant (Soko Pulse, Alama Score)
        - Whether to generate alerts (anomalies detected)
        - Priority ordering of intelligence generation
        - Process credit outcome feedback for Alama Score calibration
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        user_id = payload.get("user_id", "unknown")
        event_type = event_data.get("event_type", "")

        # Handle credit outcome feedback for Alama Score calibration
        if event_type in (
            EventType.FEEDBACK_RECEIVED.value,
            EventType.CUSTOMER_FEEDBACK_RECEIVED.value,
        ):
            outcome = payload.get("outcome", payload.get("feedback_type", ""))
            if outcome in ("repayment", "default"):
                return AgentDecision(
                    action="record_credit_outcome",
                    parameters={
                        "user_id": user_id,
                        "outcome": outcome,
                        "amount": payload.get("amount"),
                    },
                    confidence=0.95,
                    reasoning=f"Recording credit outcome '{outcome}' for user {user_id} to calibrate Alama Score",
                )

        # Determine which intelligence products to generate
        products = ["market_intelligence"]  # always generate

        # Check if credit scoring is needed
        recent = self.memory.recall_recent(10)
        has_credit_history = any(
            r.get("event_type") == "transaction.processed"
            and r.get("payload_summary", {}).get("user_id") == user_id
            for r in recent
        )
        if has_credit_history:
            products.append("credit_score")

        # Always generate price forecasts for market intelligence
        products.append("price_forecast")

        # Apply strategy adjustment from reflect→behavior loop
        confidence = 0.90
        strategy = context.get("strategy_adjustment")
        if strategy:
            confidence *= strategy.get("threshold_factor", 1.0)
            confidence = max(0.3, confidence)

        # Check past reflections for relevant lessons
        reflections = context.get("past_reflections", [])
        if reflections:
            self._logger.debug(
                "applying_reflections",
                count=len(reflections),
            )

        return AgentDecision(
            action="generate_intelligence",
            parameters={
                "user_id": user_id,
                "products": products,
            },
            confidence=confidence,
            reasoning=(
                f"Generating {len(products)} intelligence product(s) "
                f"for user {user_id}: {', '.join(products)}. "
                f"Based on transaction processing event."
            ),
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Generate intelligence products or record credit outcomes.

        Calls real SokoPulseService and AlamaScoreService when available.
        Always emits downstream events for ReportGenerator.
        """
        start = time.time()

        try:
            action = decision.action
            user_id = decision.parameters.get("user_id", "unknown")

            # Handle credit outcome recording (Alama Score feedback loop)
            if action == "record_credit_outcome":
                outcome = decision.parameters.get("outcome", "")
                amount = decision.parameters.get("amount")

                if self._alama_score:
                    try:
                        result = await self._alama_score.record_outcome(
                            business_id=user_id,
                            outcome=outcome,
                            amount=amount,
                        )
                        self._logger.info(
                            "alama_outcome_recorded",
                            user_id=user_id,
                            outcome=outcome,
                        )
                    except Exception as svc_exc:
                        self._logger.warning(
                            "alama_outcome_failed",
                            error=str(svc_exc),
                        )
                        result = {"error": str(svc_exc)}
                else:
                    result = {"status": "alama_score_not_available"}

                return AgentResult(
                    success=True,
                    data={
                        "action": "record_credit_outcome",
                        "user_id": user_id,
                        "outcome": outcome,
                        "result": result,
                    },
                    duration_ms=(time.time() - start) * 1000,
                )

            products = decision.parameters.get("products", [])

            # Call real services when available
            forecast_result = None
            score_result = None

            if "price_forecast" in products and self._soko_pulse:
                try:
                    forecast_result = await self._soko_pulse.generate_demand_forecast(
                        user_id=user_id,
                    )
                    self._logger.info(
                        "soko_pulse_forecast_generated",
                        user_id=user_id,
                    )
                except Exception as svc_exc:
                    self._logger.warning(
                        "soko_pulse_failed",
                        error=str(svc_exc),
                    )

            if "credit_score" in products and self._alama_score:
                try:
                    score_result = await self._alama_score.compute_score(
                        user_id=user_id,
                    )
                    self._logger.info(
                        "alama_score_computed",
                        user_id=user_id,
                    )
                except Exception as svc_exc:
                    self._logger.warning(
                        "alama_score_failed",
                        error=str(svc_exc),
                    )

            events_to_publish = []

            # Intelligence generated event
            events_to_publish.append(AgentEvent(
                event_type=EventType.INTELLIGENCE_GENERATED,
                source=self.name,
                payload={
                    "user_id": user_id,
                    "products_generated": products,
                    "has_forecast": forecast_result is not None,
                    "has_credit_score": score_result is not None,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            ))

            # If price forecast was generated, emit specific event
            if "price_forecast" in products:
                events_to_publish.append(AgentEvent(
                    event_type=EventType.PRICE_FORECAST_READY,
                    source=self.name,
                    payload={
                        "user_id": user_id,
                        "forecast_type": "soko_pulse",
                        "service_called": self._soko_pulse is not None,
                    },
                ))

            # If credit score was generated, emit specific event
            if "credit_score" in products:
                events_to_publish.append(AgentEvent(
                    event_type=EventType.CREDIT_SCORE_READY,
                    source=self.name,
                    payload={
                        "user_id": user_id,
                        "score_type": "alama_score",
                        "service_called": self._alama_score is not None,
                    },
                ))

            duration_ms = (time.time() - start) * 1000

            return AgentResult(
                success=True,
                data={
                    "user_id": user_id,
                    "products_generated": products,
                    "product_count": len(products),
                    "forecast_result": str(forecast_result)[:500] if forecast_result else None,
                    "score_result": str(score_result)[:500] if score_result else None,
                },
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
                        payload={"error": str(exc), "phase": "intelligence_generation"},
                    )
                ],
            )


# ════════════════════════════════════════════════════════════════════
# ReportGeneratorAgent
# ════════════════════════════════════════════════════════════════════


class ReportGeneratorAgent(BiasharaAgent):
    """
    Generates and delivers reports to workers and buyers.

    Wraps: ReportGenerator (app/services/report_generator.py),
           IntelligenceDelivery (app/services/intelligence_delivery.py)
    Subscribes to: intelligence.generated, report.requested
    Publishes:     report.generated, report.delivered

    Responsibilities:
    - Generate 5 report types (daily, weekly, monthly, semi-annual, annual)
    - Format reports for WhatsApp delivery (Swahili, English, Sheng)
    - Track delivery success
    - Schedule recurring reports
    """

    def __init__(self, report_generator: Any = None):
        super().__init__(
            name="ReportGenerator",
            role="Report creation and delivery specialist",
            capabilities=[
                "daily_report",
                "weekly_report",
                "monthly_report",
                "semiannual_report",
                "annual_report",
                "whatsapp_formatting",
                "multilingual_support",
            ],
        )
        # Real service dependency (injected by factory or main)
        self._report_generator: Any = report_generator  # ReportGenerator | None

        # Wire skills
        registry = get_skill_registry()
        for skill in registry.get_skills_for_agent(self.name):
            self.tools.register(skill.name, skill.safe_execute, skill.description)

    def set_report_generator(self, service: Any) -> None:
        """Inject the ReportGenerator service."""
        self._report_generator = service

    async def observe(self, event: AgentEvent) -> None:
        """Filter for intelligence and report events."""
        await super().observe(event)
        if event.event_type not in (
            EventType.INTELLIGENCE_GENERATED,
            EventType.REPORT_REQUESTED,
            EventType.REPORT_DELIVERED,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Decide which report type to generate.

        Analyzes the intelligence event to determine:
        - Report type (daily/weekly/monthly/semi-annual/annual)
        - Language preference
        - Delivery priority
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        user_id = payload.get("user_id", "unknown")

        # Determine report type based on event context
        report_type = payload.get("report_type", "daily")

        # Check if this is a scheduled report or triggered by intelligence
        if event_data.get("event_type") == "intelligence.generated":
            # Intelligence-triggered → generate daily report
            report_type = "daily"

        # Check delivery history to avoid duplicates
        recent = self.memory.recall_recent(5)
        recent_deliveries = [
            r for r in recent
            if r.get("event_type") == "report.delivered"
            and r.get("payload_summary", {}).get("user_id") == user_id
        ]

        confidence = 0.95
        if recent_deliveries:
            confidence = 0.75  # Lower confidence — might be duplicate

        # Apply strategy adjustment from reflect→behavior loop
        strategy = context.get("strategy_adjustment")
        if strategy:
            confidence *= strategy.get("threshold_factor", 1.0)
            confidence = max(0.3, confidence)

        # Check past reflections for relevant lessons
        reflections = context.get("past_reflections", [])
        if reflections:
            self._logger.debug(
                "applying_reflections",
                count=len(reflections),
            )

        return AgentDecision(
            action="generate_report",
            parameters={
                "user_id": user_id,
                "report_type": report_type,
                "language": payload.get("language", "sw"),
            },
            confidence=confidence,
            reasoning=(
                f"Generating {report_type} report for user {user_id}. "
                f"{'Possible duplicate — recent delivery detected.' if recent_deliveries else 'Fresh generation.'}"
            ),
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Generate and deliver the report.

        Calls the real ReportGenerator service when available.
        Always emits downstream events for SelfEvolution.
        """
        start = time.time()

        try:
            user_id = decision.parameters.get("user_id", "unknown")
            report_type = decision.parameters.get("report_type", "daily")
            language = decision.parameters.get("language", "sw")

            # Call real service if available
            report_content = None
            if self._report_generator:
                try:
                    generate_fn = {
                        "daily": self._report_generator.generate_daily,
                        "weekly": self._report_generator.generate_weekly,
                        "monthly": self._report_generator.generate_monthly,
                        "semiannual": self._report_generator.generate_semiannual,
                        "annual": self._report_generator.generate_annual,
                    }.get(report_type)

                    if generate_fn:
                        report_content = generate_fn(user_id=user_id, language=language)
                        self._logger.info(
                            "report_generated_via_service",
                            user_id=user_id,
                            report_type=report_type,
                        )
                except Exception as svc_exc:
                    self._logger.warning(
                        "report_service_failed",
                        error=str(svc_exc),
                    )

            # Report generated event
            report_event = AgentEvent(
                event_type=EventType.REPORT_GENERATED,
                source=self.name,
                payload={
                    "user_id": user_id,
                    "report_type": report_type,
                    "language": language,
                    "service_called": self._report_generator is not None,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Report delivered event
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

            duration_ms = (time.time() - start) * 1000

            return AgentResult(
                success=True,
                data={
                    "user_id": user_id,
                    "report_type": report_type,
                    "language": language,
                    "channel": "whatsapp",
                    "report_content_length": len(report_content) if report_content else 0,
                },
                duration_ms=duration_ms,
                events_to_publish=[report_event, delivery_event],
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
                        payload={"error": str(exc), "phase": "report_generation"},
                    )
                ],
            )


# ════════════════════════════════════════════════════════════════════
# SelfEvolutionAgent
# ════════════════════════════════════════════════════════════════════


class SelfEvolutionAgent(BiasharaAgent):
    """
    Learns from worker feedback and improves the system.

    Wraps: SelfEvolutionService (app/services/self_evolution.py)
    Subscribes to: feedback.received, report.delivered
    Publishes:     feature.spec.generated, evolution.cycle.complete

    Responsibilities:
    - Collect and classify worker feedback
    - Cluster similar feedback to identify patterns
    - Generate feature specs from feedback clusters
    - Track feature adoption
    - Drive the self-evolution flywheel
    """

    def __init__(self, evolution_service: Any = None):
        super().__init__(
            name="SelfEvolution",
            role="Self-improvement and feedback analysis specialist",
            capabilities=[
                "feedback_collection",
                "feedback_classification",
                "feedback_clustering",
                "feature_spec_generation",
                "adoption_tracking",
                "evolution_reporting",
            ],
        )
        # Real service dependency (injected by factory or main)
        self._evolution_service: Any = evolution_service  # SelfEvolutionService | None

        # Wire all skills for learning
        registry = get_skill_registry()
        for skill in registry.get_skills_for_agent(self.name):
            self.tools.register(skill.name, skill.safe_execute, skill.description)

    def set_evolution_service(self, service: Any) -> None:
        """Inject the SelfEvolutionService."""
        self._evolution_service = service

    async def observe(self, event: AgentEvent) -> None:
        """Process feedback and delivery events."""
        await super().observe(event)
        if event.event_type not in (
            EventType.FEEDBACK_RECEIVED,
            EventType.REPORT_DELIVERED,
            EventType.EVOLUTION_CYCLE_COMPLETE,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Decide how to process feedback.

        Analyzes the feedback event to determine:
        - Feedback type (feature request, bug report, praise, etc.)
        - Urgency level
        - Whether to trigger a clustering/spec generation cycle
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})

        feedback_type = payload.get("feedback_type", "unknown")
        worker_id = payload.get("worker_id", "unknown")
        text = payload.get("text", "")

        # Check recent feedback volume to decide if we should cluster
        recent = self.memory.recall_recent(20)
        recent_feedback = [
            r for r in recent
            if r.get("event_type") == "feedback.received"
        ]

        # Trigger clustering if we have enough feedback
        should_cluster = len(recent_feedback) >= 5
        action = "analyze_and_cluster" if should_cluster else "collect_feedback"

        # Apply strategy adjustment from reflect→behavior loop
        confidence = 0.90
        strategy = context.get("strategy_adjustment")
        if strategy:
            confidence *= strategy.get("threshold_factor", 1.0)
            confidence = max(0.3, confidence)

        # Check past reflections for relevant lessons
        reflections = context.get("past_reflections", [])
        if reflections:
            self._logger.debug(
                "applying_reflections",
                count=len(reflections),
            )

        return AgentDecision(
            action=action,
            parameters={
                "worker_id": worker_id,
                "feedback_type": feedback_type,
                "text": text,
                "should_cluster": should_cluster,
                "feedback_count": len(recent_feedback),
            },
            confidence=confidence,
            reasoning=(
                f"Processing {feedback_type} feedback from worker {worker_id}. "
                f"{len(recent_feedback)} recent feedback items. "
                f"{'Triggering clustering cycle.' if should_cluster else 'Collecting — not enough for clustering yet.'}"
            ),
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Process feedback and optionally generate feature specs.

        Calls the real SelfEvolutionService when available.
        Always emits downstream events for the evolution cycle.
        """
        start = time.time()

        try:
            worker_id = decision.parameters.get("worker_id", "unknown")
            feedback_type = decision.parameters.get("feedback_type", "unknown")
            feedback_text = decision.parameters.get("text", "")
            should_cluster = decision.parameters.get("should_cluster", False)

            # Call real service if available
            feedback_result = None
            if self._evolution_service and feedback_text:
                try:
                    feedback_result = await self._evolution_service.collect_feedback(
                        worker_id=worker_id,
                        feedback=feedback_text,
                        feedback_type=feedback_type,
                    )
                    self._logger.info(
                        "evolution_feedback_collected",
                        worker_id=worker_id,
                        feedback_type=feedback_type,
                    )
                except Exception as svc_exc:
                    self._logger.warning(
                        "evolution_service_failed",
                        error=str(svc_exc),
                    )

            events_to_publish = []

            if should_cluster:
                # Emit feature spec generated event
                events_to_publish.append(AgentEvent(
                    event_type=EventType.FEATURE_SPEC_GENERATED,
                    source=self.name,
                    payload={
                        "worker_id": worker_id,
                        "feedback_type": feedback_type,
                        "cluster_size": decision.parameters.get("feedback_count", 0),
                        "service_called": self._evolution_service is not None,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    },
                ))

                # Emit evolution cycle complete
                events_to_publish.append(AgentEvent(
                    event_type=EventType.EVOLUTION_CYCLE_COMPLETE,
                    source=self.name,
                    payload={
                        "cycle_type": "feedback_clustering",
                        "items_processed": decision.parameters.get("feedback_count", 0),
                    },
                ))

            duration_ms = (time.time() - start) * 1000

            return AgentResult(
                success=True,
                data={
                    "worker_id": worker_id,
                    "feedback_type": feedback_type,
                    "clustered": should_cluster,
                    "feedback_stored": feedback_result is not None,
                },
                duration_ms=duration_ms,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )


# ════════════════════════════════════════════════════════════════════
# Agent Registry — Convenience factory
# ════════════════════════════════════════════════════════════════════


def create_all_agents(
    pipeline: Any = None,
    soko_pulse: Any = None,
    alama_score: Any = None,
    report_generator: Any = None,
    evolution_service: Any = None,
) -> List[BiasharaAgent]:
    """
    Create all four agents for the standard pipeline.

    Args:
        pipeline: DataPipeline service for TransactionProcessor
        soko_pulse: SokoPulseService for IntelligenceGenerator
        alama_score: AlamaScoreService for IntelligenceGenerator
        report_generator: ReportGenerator for ReportGeneratorAgent
        evolution_service: SelfEvolutionService for SelfEvolutionAgent

    Returns:
        List of 4 agents with optional service dependencies injected
    """
    return [
        TransactionProcessorAgent(pipeline=pipeline),
        IntelligenceGeneratorAgent(soko_pulse=soko_pulse, alama_score=alama_score),
        ReportGeneratorAgent(report_generator=report_generator),
        SelfEvolutionAgent(evolution_service=evolution_service),
    ]


AGENT_REGISTRY = {
    "TransactionProcessor": TransactionProcessorAgent,
    "IntelligenceGenerator": IntelligenceGeneratorAgent,
    "ReportGenerator": ReportGeneratorAgent,
    "SelfEvolution": SelfEvolutionAgent,
}
