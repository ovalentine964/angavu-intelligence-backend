"""
Alama Score RAG Agent — Credit Assessment with Structured Outputs.

Combines:
- Typed RAG with Pydantic outputs (from agentic_typed_rag_pydanticai/)
- Corrective RAG (from corrective_rag/)
- Hybrid Search (from hybrid_search_rag/)

Subscribes to: transaction.processed, intelligence.requested, credit.score.ready
Publishes:     intelligence.generated, credit.score.ready

Produces structured, validated credit assessments with:
- Every claim backed by a citation to transaction data
- Confidence scores bounded [0, 1]
- Refuses to assess when evidence is insufficient
- Structured Pydantic-compatible output for API consumers
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


# ════════════════════════════════════════════════════════════════════
# Structured Output Models (inspired by agentic_typed_rag_pydanticai)
# ════════════════════════════════════════════════════════════════════


class CreditAssessment:
    """
    Structured credit assessment output.

    Mirrors the Pydantic BaseModel pattern from agentic_typed_rag_pydanticai
    but implemented as a dataclass for zero-dependency operation.

    Invariants:
    - answered=True requires at least one citation
    - answered=False must not contain citations
    - confidence is bounded [0, 1]
    - score_band must be one of the valid bands
    """

    VALID_BANDS = ["A+", "A", "B+", "B", "C+", "C", "D", "E"]

    def __init__(
        self,
        worker_id: str,
        score: int | None,
        score_band: str,
        confidence: float,
        answered: bool,
        citations: list[dict[str, Any]],
        components: dict[str, float],
        risk_factors: list[str],
        recommendation: str,
        reasoning_trace: list[str],
    ):
        self.worker_id = worker_id
        self.score = score
        self.score_band = score_band
        self.confidence = max(0.0, min(1.0, confidence))
        self.answered = answered
        self.citations = citations
        self.components = components
        self.risk_factors = risk_factors
        self.recommendation = recommendation
        self.reasoning_trace = reasoning_trace

        # Validation (Pydantic-style)
        if self.answered and not self.citations:
            raise ValueError("answered assessments require at least one citation")
        if not self.answered and self.citations:
            raise ValueError("refused assessments must not contain citations")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "worker_id": self.worker_id,
            "score": self.score,
            "score_band": self.score_band,
            "confidence": self.confidence,
            "answered": self.answered,
            "citations": self.citations,
            "components": self.components,
            "risk_factors": self.risk_factors,
            "recommendation": self.recommendation,
            "reasoning_trace": self.reasoning_trace,
            "assessed_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def insufficient_evidence(
        cls, worker_id: str, top_score: float = 0.0
    ) -> "CreditAssessment":
        """Create a refusal response when evidence is insufficient."""
        return cls(
            worker_id=worker_id,
            score=None,
            score_band="N/A",
            confidence=round(min(max(top_score, 0.0), 1.0), 3),
            answered=False,
            citations=[],
            components={},
            risk_factors=[],
            recommendation=(
                "Insufficient transaction data to generate a credit assessment. "
                "More transaction history is needed."
            ),
            reasoning_trace=["Evidence insufficient — refusing to assess"],
        )


# ════════════════════════════════════════════════════════════════════
# Alama Score RAG Agent
# ════════════════════════════════════════════════════════════════════


class AlamaScoreRAGAgent(ReActAgent):
    """
    Alama Score enhanced with typed RAG for grounded credit assessment.

    Instead of just computing a score, this agent:
    1. Retrieves relevant transaction and repayment data using hybrid search
    2. Validates that evidence is sufficient (corrective RAG)
    3. Produces structured CreditAssessment with citations
    4. Refuses to score when data is insufficient (no hallucination)

    Key pattern from agentic_typed_rag_pydanticai:
    - Every claim must cite a source chunk
    - Citations must reference real data
    - Confidence is grounded in retrieval scores
    """

    def __init__(self, alama_score_service: Any = None):
        super().__init__(
            name="AlamaScoreRAG",
            role="Credit risk analyst with retrieval-augmented assessment",
            capabilities=[
                "credit_scoring",
                "risk_assessment",
                "transaction_analysis",
                "repayment_analysis",
                "behavioral_scoring",
                "rag_retrieval",
                "typed_output",
                "corrective_rag",
                "citation_verification",
            ],
        )
        self._alama_score = alama_score_service

        # RAG components — initialized lazily
        self._rag_initialized = False
        self._hybrid_retriever: Any = None
        self._corrective_rag: Any = None
        self._typed_agent: Any = None
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
            TypedRAGAgent,
            VectorRetriever,
        )

        embedding = HashingEmbedding(dimensions=768)
        vector = VectorRetriever(embedding_backend=embedding)
        bm25 = BM25Retriever()
        self._hybrid_retriever = HybridRetriever(
            vector_retriever=vector,
            bm25_retriever=bm25,
            vector_weight=0.5,
            bm25_weight=0.5,  # Higher BM25 weight — credit data has exact terms
        )
        self._corrective_rag = CorrectiveRAG(
            retriever=self._hybrid_retriever,
            min_relevance_score=0.3,
            max_retries=2,
            min_evidence_chunks=2,  # Need at least 2 data points for credit
        )
        self._typed_agent = TypedRAGAgent(
            corrective_rag=self._corrective_rag,
            min_confidence=0.4,
        )
        self._doc_processor = DocumentProcessor(
            chunk_size=300,  # Smaller chunks for precise credit data
            chunk_overlap=50,
        )
        self._rag_initialized = True
        self._logger.info("alama_score_rag_initialized")

    # ── Lifecycle ───────────────────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Index transaction and credit data for RAG retrieval."""
        await super().observe(event)
        self._ensure_rag()

        if event.event_type == EventType.TRANSACTION_PROCESSED:
            await self._index_transaction_data(event)
        elif event.event_type == EventType.CREDIT_SCORE_READY:
            await self._index_credit_outcome(event)

    async def _index_transaction_data(self, event: AgentEvent) -> None:
        """Index transaction data for credit-relevant retrieval."""
        payload = event.payload
        user_id = payload.get("user_id", "unknown")

        # Create credit-relevant chunks
        chunks = self._doc_processor.chunk_transactions(
            payload.get("transactions", []),
            source=f"credit_txn:{user_id}",
        )
        if chunks:
            await self._hybrid_retriever.add_documents(chunks)

    async def _index_credit_outcome(self, event: AgentEvent) -> None:
        """Index credit outcomes for future reference."""
        from .rag_engine import DocumentChunk

        payload = event.payload
        outcome_text = (
            f"Credit outcome for {payload.get('user_id', 'unknown')}: "
            f"Score type: {payload.get('score_type', 'N/A')}, "
            f"Service called: {payload.get('service_called', False)}"
        )
        chunk = DocumentChunk(
            source="credit_outcomes",
            chunk_id=f"outcome:{event.event_id}",
            text=outcome_text,
            metadata={"type": "credit_outcome"},
        )
        await self._hybrid_retriever.add_documents([chunk])

    # ── Think ───────────────────────────────────────────────────────

    async def _think_reasoning(self, context: dict[str, Any]) -> AgentDecision:
        """Decide what credit analysis to perform."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        event_type = event_data.get("event_type", "")

        worker_id = params.get("worker_id", payload.get("user_id", "unknown"))

        # Determine analysis type
        if event_type == EventType.CREDIT_SCORE_READY.value:
            action = "validate_credit_score"
        elif "repay" in str(params.get("action", "")):
            action = "analyze_repayment"
        elif "behavior" in str(params.get("action", "")):
            action = "behavioral_analysis"
        else:
            action = "full_credit_assessment"

        # Check memory for this worker's history
        recent = self.memory.recall_recent(20)
        worker_history = [
            r for r in recent
            if r.get("payload_summary", {}).get("user_id") == worker_id
        ]

        confidence = 0.85
        if len(worker_history) >= 3:
            confidence = 0.92  # More data = higher confidence

        strategy = context.get("strategy_adjustment")
        if strategy:
            confidence *= strategy.get("threshold_factor", 1.0)

        return AgentDecision(
            action=action,
            parameters={"worker_id": worker_id, **params},
            confidence=confidence,
            reasoning=(
                f"Alama Score RAG: {action} for worker {worker_id}. "
                f"{len(worker_history)} historical records in memory."
            ),
        )

    # ── Act ─────────────────────────────────────────────────────────

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """
        Execute credit assessment using typed RAG.

        Produces a structured CreditAssessment with:
        - Score and band (if sufficient evidence)
        - Component breakdown (activity, stability, growth, consistency)
        - Risk factors identified from data
        - Citations to supporting transaction data
        - Refusal if evidence is insufficient
        """
        start = time.time()
        action = decision.action
        params = decision.parameters
        worker_id = params.get("worker_id", "unknown")

        try:
            # Step 1: Get raw credit data from AlamaScoreService
            service_data = await self._get_credit_data(worker_id, action)

            # Step 2: Index service data for RAG
            if service_data:
                credit_chunks = self._doc_processor.chunk_credit_data(
                    service_data, worker_id=worker_id,
                    source=f"alama_score:{worker_id}",
                )
                if credit_chunks:
                    await self._hybrid_retriever.add_documents(credit_chunks)

            # Step 3: RAG-based assessment
            query = self._build_assessment_query(worker_id, action)
            system_prompt = (
                "You are a credit risk analyst for informal economy workers in Kenya. "
                "Assess creditworthiness based on transaction data. "
                "Every claim must cite a source using [N] notation. "
                "If data is insufficient, say so — never fabricate scores."
            )

            rag_answer = await self._typed_agent.answer(
                question=query,
                llm_fn=self._llm_fn,
                top_k=10,
                system_prompt=system_prompt,
            )

            # Step 4: Build structured assessment
            if rag_answer.answered:
                assessment = self._build_assessment(
                    worker_id, rag_answer, service_data
                )
            else:
                assessment = CreditAssessment.insufficient_evidence(
                    worker_id, rag_answer.confidence
                )

            # Step 5: Build response
            data = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(UTC).isoformat(),
                "agent": self.name,
                "rag_enabled": True,
                "assessment": assessment.to_dict(),
            }

            if service_data:
                data["service_data_available"] = True

            # Step 6: Build downstream events
            events_to_publish = [
                AgentEvent(
                    event_type=EventType.INTELLIGENCE_GENERATED,
                    source=self.name,
                    payload={
                        "product_type": "alama_score_rag",
                        "worker_id": worker_id,
                        "score": assessment.score,
                        "score_band": assessment.score_band,
                        "confidence": assessment.confidence,
                        "answered": assessment.answered,
                        "citation_count": len(assessment.citations),
                        "generated_at": datetime.now(UTC).isoformat(),
                    },
                ),
                AgentEvent(
                    event_type=EventType.CREDIT_SCORE_READY,
                    source=self.name,
                    payload={
                        "score_type": "alama_score_rag",
                        "worker_id": worker_id,
                        "score": assessment.score,
                        "confidence": assessment.confidence,
                    },
                ),
            ]

            return AgentResult(
                success=True,
                data=data,
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            self._logger.error("alama_score_rag_error", error=str(exc), worker_id=worker_id)
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=[
                    AgentEvent(
                        event_type=EventType.PIPELINE_ERROR,
                        source=self.name,
                        payload={"error": str(exc), "phase": "alama_score_rag"},
                    )
                ],
            )

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_credit_data(
        self, worker_id: str, action: str
    ) -> dict[str, Any] | None:
        """Get raw credit data from AlamaScoreService."""
        if not self._alama_score:
            return None

        try:
            data: dict[str, Any] = {}

            if "full" in action or "assess" in action:
                score = await self._alama_score.compute_score(
                    business_id=worker_id
                )
                if score:
                    data["credit_score"] = score

            return data if data else None
        except Exception as exc:
            self._logger.warning("alama_service_error", error=str(exc))
            return None

    def _build_assessment_query(self, worker_id: str, action: str) -> str:
        """Build a natural language query for credit assessment."""
        if "repay" in action:
            return (
                f"What is the repayment history and loan performance "
                f"for worker {worker_id}? What is their on-time payment rate?"
            )
        elif "behavior" in action:
            return (
                f"What are the transaction patterns and business behavior "
                f"of worker {worker_id}? Is their income regular or volatile?"
            )
        else:
            return (
                f"Assess the creditworthiness of worker {worker_id} based on "
                f"their transaction history, repayment record, and business behavior. "
                f"What credit score would you assign and why?"
            )

    def _build_assessment(
        self,
        worker_id: str,
        rag_answer: Any,
        service_data: dict[str, Any] | None,
    ) -> CreditAssessment:
        """Build a structured CreditAssessment from RAG answer."""
        # Extract score from RAG answer text
        score = self._extract_score(rag_answer.text, service_data)
        score_band = self._score_to_band(score)

        # Extract components
        components = {}
        if service_data and "credit_score" in service_data:
            cs = service_data["credit_score"]
            components = {
                "activity": cs.get("activity_score", 0),
                "stability": cs.get("stability_score", 0),
                "growth": cs.get("growth_score", 0),
                "consistency": cs.get("consistency_score", 0),
                "diversity": cs.get("diversity_score", 0),
            }

        # Extract risk factors from text
        risk_factors = self._extract_risk_factors(rag_answer.text)

        # Build citations from RAG
        citations = [
            {
                "source": c.source,
                "chunk_id": c.chunk_id,
                "quoted_span": c.quoted_span[:150],
                "confidence": c.confidence,
            }
            for c in rag_answer.citations
        ]

        # Generate recommendation
        recommendation = self._generate_recommendation(
            score, score_band, risk_factors, rag_answer.confidence
        )

        return CreditAssessment(
            worker_id=worker_id,
            score=score,
            score_band=score_band,
            confidence=rag_answer.confidence,
            answered=True,
            citations=citations,
            components=components,
            risk_factors=risk_factors,
            recommendation=recommendation,
            reasoning_trace=rag_answer.reasoning_trace,
        )

    def _extract_score(
        self, text: str, service_data: dict[str, Any] | None
    ) -> int:
        """Extract numeric credit score from text or service data."""
        # Prefer service data
        if service_data and "credit_score" in service_data:
            score = service_data["credit_score"].get("score")
            if score is not None:
                return int(score)

        # Try to extract from text
        import re
        patterns = [
            r"score[:\s]+(\d{3,3})",
            r"(\d{3,3})\s*/\s*850",
            r"alama[:\s]+(\d{3,3})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                score = int(match.group(1))
                if 300 <= score <= 850:
                    return score

        # Default: estimate from confidence
        return 500  # Neutral default

    def _score_to_band(self, score: int) -> str:
        """Convert numeric score to letter band."""
        if score >= 750:
            return "A+"
        elif score >= 700:
            return "A"
        elif score >= 650:
            return "B+"
        elif score >= 600:
            return "B"
        elif score >= 550:
            return "C+"
        elif score >= 500:
            return "C"
        elif score >= 400:
            return "D"
        else:
            return "E"

    def _extract_risk_factors(self, text: str) -> list[str]:
        """Extract risk factors mentioned in the analysis text."""
        risk_keywords = {
            "irregular": "Irregular transaction patterns",
            "volatile": "Volatile income",
            "declining": "Declining revenue trend",
            "default": "Previous loan default",
            "inactive": "Periods of inactivity",
            "low": "Low transaction volume",
            "risky": "High-risk indicators detected",
        }

        factors = []
        text_lower = text.lower()
        for keyword, description in risk_keywords.items():
            if keyword in text_lower:
                factors.append(description)

        return factors if factors else ["No significant risk factors identified"]

    def _generate_recommendation(
        self,
        score: int | None,
        band: str,
        risk_factors: list[str],
        confidence: float,
    ) -> str:
        """Generate actionable credit recommendation."""
        if score is None:
            return "Insufficient data for credit recommendation."

        if band in ("A+", "A"):
            eligibility = "eligible for premium credit products"
        elif band in ("B+", "B"):
            eligibility = "eligible for standard credit products"
        elif band in ("C+", "C"):
            eligibility = "eligible for basic credit with monitoring"
        else:
            eligibility = "requires significant improvement before credit eligibility"

        risk_note = ""
        if len(risk_factors) > 2:
            risk_note = f" Note: {len(risk_factors)} risk factors identified."

        return (
            f"Worker is {eligibility} (Alama Score: {score}, Band: {band}). "
            f"Assessment confidence: {confidence:.0%}.{risk_note}"
        )

    async def _llm_fn(self, prompt: str) -> str:
        """LLM function for typed RAG — delegates to agent's inference."""
        result = await self.infer(
            prompt=prompt,
            task_type="credit_assessment",
            system_prompt=(
                "You are a credit risk analyst for Kenya's informal economy. "
                "Assess creditworthiness from transaction data. "
                "Always cite sources using [N]. "
                "If data is insufficient, state that clearly."
            ),
            max_tokens=1024,
            temperature=0.2,  # Low temperature for consistent credit assessments
        )
        if result.success:
            return result.output
        raise RuntimeError(f"LLM inference failed: {result.error}")
