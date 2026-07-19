"""
Soko Pulse RAG Agent — Market Intelligence with Agentic Reasoning.

Combines:
- Agentic RAG with Reasoning (from agentic_rag_with_reasoning/)
- Hybrid Search (BM25 + Vector) (from hybrid_search_rag/)
- Corrective RAG (from corrective_rag/)

Subscribes to: transaction.processed, market.alert, intelligence.requested
Publishes:     intelligence.generated, price.forecast.ready, market.alert

Uses reasoning RAG to explain *why* market trends are happening,
not just *what* the trends are. Grounded in real transaction data.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    EventType,
)
from app.agents.loops.core import ReActAgent

logger = structlog.get_logger(__name__)


class SokoPulseRAGAgent(ReActAgent):
    """
    Soko Pulse enhanced with RAG-based reasoning.

    Instead of just running ARIMA/SARIMA forecasts, this agent:
    1. Retrieves relevant market data using hybrid search
    2. Reasons through the data step-by-step
    3. Produces explanations alongside predictions
    4. Self-corrects when evidence is insufficient

    Example output:
        "Tomato prices in Nairobi have increased 23% over the past 2 weeks.
         Based on 847 transactions from 12 sellers, the trend correlates with
         reduced supply from Kiambu (down 31%) and increased demand in
         Eastlands markets. Confidence: 0.87. Sources: [1][2][3]"
    """

    def __init__(self, soko_pulse_service: Any = None):
        super().__init__(
            name="SokoPulseRAG",
            role="Market intelligence analyst with retrieval-augmented reasoning",
            capabilities=[
                "market_price_analysis",
                "price_forecast_with_reasoning",
                "supply_demand_analysis",
                "competitor_intelligence",
                "market_trend_explanation",
                "rag_retrieval",
                "hybrid_search",
                "corrective_rag",
                "reasoning_chain",
            ],
        )
        self._soko_pulse = soko_pulse_service

        # RAG components — initialized lazily on first use
        self._rag_initialized = False
        self._hybrid_retriever: Any = None
        self._corrective_rag: Any = None
        self._reasoning_agent: Any = None
        self._doc_processor: Any = None

    def _ensure_rag(self) -> None:
        """Lazy initialization of RAG components."""
        if self._rag_initialized:
            return

        from .rag_engine import (
            BM25Retriever,
            CorrectiveRAG,
            DocumentProcessor,
            HashingEmbedding,
            HybridRetriever,
            ReasoningRAGAgent,
            VectorRetriever,
        )

        embedding = HashingEmbedding(dimensions=768)
        vector = VectorRetriever(embedding_backend=embedding)
        bm25 = BM25Retriever()
        self._hybrid_retriever = HybridRetriever(
            vector_retriever=vector,
            bm25_retriever=bm25,
            vector_weight=0.6,
            bm25_weight=0.4,
        )
        self._corrective_rag = CorrectiveRAG(
            retriever=self._hybrid_retriever,
            min_relevance_score=0.25,
            max_retries=2,
        )
        self._reasoning_agent = ReasoningRAGAgent(
            corrective_rag=self._corrective_rag,
            max_reasoning_steps=5,
        )
        self._doc_processor = DocumentProcessor(
            chunk_size=400,
            chunk_overlap=80,
        )
        self._rag_initialized = True
        self._logger.info("soko_pulse_rag_initialized")

    # ── Lifecycle ───────────────────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Filter for market-relevant events."""
        await super().observe(event)
        self._ensure_rag()

        # Index incoming transaction data into RAG store
        if event.event_type == EventType.TRANSACTION_PROCESSED:
            await self._index_transaction_event(event)
        elif event.event_type == EventType.MARKET_ALERT:
            await self._index_market_alert(event)

    async def _index_transaction_event(self, event: AgentEvent) -> None:
        """Index processed transactions into the RAG store."""
        payload = event.payload
        transactions = payload.get("transactions", [])
        if not transactions:
            # Create a synthetic transaction record from the event
            transactions = [{
                "user_id": payload.get("user_id", "unknown"),
                "item": payload.get("product", "unknown"),
                "amount": payload.get("amount", 0),
                "region": payload.get("region", "unknown"),
                "timestamp": payload.get("processed_at", datetime.now(UTC).isoformat()),
                "transaction_type": payload.get("transaction_type", "SALE"),
            }]

        chunks = self._doc_processor.chunk_transactions(
            transactions,
            source=f"txn:{payload.get('user_id', 'unknown')}",
        )
        if chunks:
            await self._hybrid_retriever.add_documents(chunks)
            self._logger.debug(
                "indexed_transactions",
                chunk_count=len(chunks),
                user_id=payload.get("user_id"),
            )

    async def _index_market_alert(self, event: AgentEvent) -> None:
        """Index market alerts into the RAG store."""
        from .rag_engine import DocumentChunk

        payload = event.payload
        alert_text = (
            f"Market alert: {payload.get('alert_type', 'unknown')} — "
            f"{payload.get('message', '')} "
            f"Region: {payload.get('region', 'N/A')} "
            f"Product: {payload.get('product', 'N/A')} "
            f"Severity: {payload.get('severity', 'N/A')}"
        )
        chunk = DocumentChunk(
            source="market_alerts",
            chunk_id=f"alert:{event.event_id}",
            text=alert_text,
            metadata={"type": "alert", "severity": payload.get("severity")},
        )
        await self._hybrid_retriever.add_documents([chunk])

    # ── Think ───────────────────────────────────────────────────────

    async def _think_reasoning(self, context: dict[str, Any]) -> AgentDecision:
        """
        Decide what market intelligence to generate.

        Uses event context + memory to determine:
        - What analysis to run (price, supply/demand, competitors)
        - What region/product to focus on
        - Whether this is a routine check or triggered by an alert
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        event_type = event_data.get("event_type", "")

        # Determine action based on event type
        if event_type == EventType.MARKET_ALERT.value:
            action = "analyze_market_alert"
            params = {
                "alert_type": payload.get("alert_type"),
                "region": payload.get("region", "Nairobi"),
                "product": payload.get("product"),
                "severity": payload.get("severity"),
            }
        elif event_type == EventType.INTELLIGENCE_REQUESTED.value:
            action = payload.get("parameters", {}).get("action", "market_overview")
            params = payload.get("parameters", {})
        else:
            action = "market_overview"
            params = {
                "region": payload.get("region", "Nairobi"),
                "product": payload.get("product"),
            }

        # Check memory for recent market context
        recent = self.memory.recall_recent(10)
        recent_alerts = [
            r for r in recent if r.get("event_type") == "market.alert"
        ]

        confidence = 0.90
        if recent_alerts:
            confidence = 0.95  # Higher confidence with more context

        # Apply strategy adjustment
        strategy = context.get("strategy_adjustment")
        if strategy:
            confidence *= strategy.get("threshold_factor", 1.0)

        return AgentDecision(
            action=action,
            parameters=params,
            confidence=confidence,
            reasoning=(
                f"Soko Pulse RAG: executing {action} for "
                f"{params.get('product', 'all products')} in "
                f"{params.get('region', 'Nairobi')}. "
                f"{len(recent_alerts)} recent alerts in memory."
            ),
        )

    # ── Act ─────────────────────────────────────────────────────────

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """
        Execute market intelligence generation using RAG.

        Combines:
        1. Real service calls (SokoPulseService) for raw data
        2. RAG retrieval for contextual market information
        3. Reasoning agent for step-by-step analysis
        """
        start = time.time()
        action = decision.action
        params = decision.parameters

        try:
            data: dict[str, Any] = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(UTC).isoformat(),
                "agent": self.name,
                "rag_enabled": True,
            }

            region = params.get("region", "Nairobi")
            product = params.get("product")

            # Step 1: Get raw data from SokoPulseService
            service_data = await self._get_service_data(action, params)
            if service_data:
                data["service_data"] = service_data

                # Index service data into RAG for future queries
                market_chunks = self._doc_processor.chunk_market_data(
                    service_data, source=f"soko_pulse:{action}"
                )
                if market_chunks:
                    await self._hybrid_retriever.add_documents(market_chunks)

            # Step 2: RAG-based reasoning
            query = self._build_rag_query(action, region, product)
            domain_context = (
                "You are analyzing market data for informal economy workers in Kenya. "
                "Products are traded in local markets (soko). "
                "Currency is KES (Kenya Shillings). "
                "Common products: tomatoes, onions, maize, sukuma wiki, potatoes."
            )

            rag_answer = await self._reasoning_agent.reason_and_answer(
                question=query,
                llm_fn=self._llm_fn,
                top_k=8,
                domain_context=domain_context,
            )

            # Step 3: Build response
            data["rag_analysis"] = {
                "answer": rag_answer.text,
                "confidence": rag_answer.confidence,
                "citations": [
                    {
                        "source": c.source,
                        "chunk_id": c.chunk_id,
                        "excerpt": c.quoted_span[:100],
                    }
                    for c in rag_answer.citations
                ],
                "reasoning_steps": len(rag_answer.reasoning_trace),
                "evidence_chunks": len(rag_answer.retrieval_evidence.chunks)
                if rag_answer.retrieval_evidence else 0,
            }

            # Step 4: Extract actionable insights
            if action == "analyze_market_alert":
                data["alert_analysis"] = {
                    "severity": params.get("severity"),
                    "region": region,
                    "product": product,
                    "recommendation": self._generate_recommendation(
                        rag_answer, params
                    ),
                }
            elif "price" in action:
                data["price_analysis"] = {
                    "region": region,
                    "product": product,
                    "trend": self._extract_trend(rag_answer),
                }

            # Step 5: Build downstream events
            events_to_publish = [
                AgentEvent(
                    event_type=EventType.INTELLIGENCE_GENERATED,
                    source=self.name,
                    payload={
                        "product_type": "soko_pulse_rag",
                        "action": action,
                        "region": region,
                        "product": product,
                        "confidence": rag_answer.confidence,
                        "has_citations": len(rag_answer.citations) > 0,
                        "generated_at": datetime.now(UTC).isoformat(),
                    },
                ),
                AgentEvent(
                    event_type=EventType.PRICE_FORECAST_READY,
                    source=self.name,
                    payload={
                        "forecast_type": "soko_pulse_rag",
                        "region": region,
                        "product": product,
                        "confidence": rag_answer.confidence,
                    },
                ),
            ]

            # Emit market alert if confidence is low
            if rag_answer.confidence < 0.4:
                events_to_publish.append(AgentEvent(
                    event_type=EventType.MARKET_ALERT,
                    source=self.name,
                    payload={
                        "alert_type": "low_confidence_analysis",
                        "region": region,
                        "product": product,
                        "confidence": rag_answer.confidence,
                        "message": (
                            f"Low confidence ({rag_answer.confidence:.0%}) in "
                            f"market analysis for {product or 'general'} in {region}. "
                            f"More data needed."
                        ),
                    },
                ))

            return AgentResult(
                success=True,
                data=data,
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            self._logger.error("soko_pulse_rag_error", error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=[
                    AgentEvent(
                        event_type=EventType.PIPELINE_ERROR,
                        source=self.name,
                        payload={"error": str(exc), "phase": "soko_pulse_rag"},
                    )
                ],
            )

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_service_data(
        self, action: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Get raw data from SokoPulseService if available."""
        if not self._soko_pulse:
            return None

        try:
            if "price" in action:
                return await self._soko_pulse.get_price_data(
                    region=params.get("region", "Nairobi"),
                    product=params.get("product"),
                )
            elif "supply" in action or "demand" in action:
                return await self._soko_pulse.get_supply_demand(
                    region=params.get("region", "Nairobi"),
                    product=params.get("product"),
                )
            elif "forecast" in action:
                return await self._soko_pulse.generate_demand_forecast(
                    user_id=params.get("user_id", "system"),
                )
            else:
                return await self._soko_pulse.get_market_overview(
                    region=params.get("region", "Nairobi"),
                )
        except Exception as exc:
            self._logger.warning("soko_pulse_service_error", error=str(exc))
            return None

    def _build_rag_query(
        self, action: str, region: str, product: str | None
    ) -> str:
        """Build a natural language query for RAG retrieval."""
        product_clause = f" for {product}" if product else ""

        if "price" in action:
            return f"What are the current market prices{product_clause} in {region}? What is the trend?"
        elif "supply" in action or "demand" in action:
            return f"What is the supply and demand situation{product_clause} in {region}?"
        elif "competitor" in action:
            return f"How many competitors are selling{product_clause} in {region}?"
        elif "alert" in action:
            return f"What market conditions{product_clause} in {region} could cause price changes?"
        else:
            return f"What is the overall market situation{product_clause} in {region}?"

    def _generate_recommendation(
        self, answer: Any, params: dict[str, Any]
    ) -> str:
        """Generate actionable recommendation from RAG analysis."""
        if answer.confidence >= 0.7:
            return (
                f"Based on analysis of {len(answer.citations)} data sources: "
                f"Market conditions for {params.get('product', 'products')} "
                f"in {params.get('region', 'the region')} require monitoring. "
                f"See detailed analysis above."
            )
        elif answer.confidence >= 0.4:
            return (
                f"Moderate confidence analysis. Consider gathering more "
                f"transaction data for {params.get('region', 'the region')} "
                f"before making decisions."
            )
        else:
            return (
                f"Insufficient data for reliable recommendation. "
                f"More transactions needed in {params.get('region', 'the region')}."
            )

    def _extract_trend(self, answer: Any) -> str:
        """Extract price trend from RAG answer text."""
        text = answer.text.lower()
        if any(w in text for w in ["increase", "rising", "up", "higher", "imepanda"]):
            return "rising"
        elif any(w in text for w in ["decrease", "falling", "down", "lower", "imepungua"]):
            return "falling"
        elif any(w in text for w in ["stable", "steady", "unchanged"]):
            return "stable"
        return "uncertain"

    async def _llm_fn(self, prompt: str) -> str:
        """LLM function for RAG reasoning — delegates to agent's inference."""
        result = await self.infer(
            prompt=prompt,
            task_type="market_analysis",
            system_prompt=(
                "You are a market intelligence analyst for Kenya's informal economy. "
                "Analyze transaction data and market trends. "
                "Always cite sources using [N] notation."
            ),
            max_tokens=1024,
            temperature=0.3,
        )
        if result.success:
            return result.output
        raise RuntimeError(f"LLM inference failed: {result.error}")
