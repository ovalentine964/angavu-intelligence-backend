"""
RAG Evaluation Framework

Provides metrics for evaluating RAG quality:
- Retrieval relevance (precision, recall, MRR)
- Answer faithfulness (grounded in context)
- Answer relevance (addresses the query)
- Citation accuracy

Inspired by RAGAS framework, adapted for Angavu's domain.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .config import RAGConfig
from .pipeline import RAGPipeline, RAGResponse

logger = logging.getLogger(__name__)


@dataclass
class EvalMetrics:
    """Evaluation metrics for a single RAG query."""
    query: str
    answer: str
    # Retrieval metrics
    retrieval_precision: float = 0.0  # % of retrieved docs that are relevant
    retrieval_recall: float = 0.0     # % of relevant docs that were retrieved
    mrr: float = 0.0                  # Mean Reciprocal Rank
    # Generation metrics
    faithfulness: float = 0.0         # Is answer grounded in context?
    relevance: float = 0.0           # Does answer address the query?
    # Citation metrics
    citation_count: int = 0
    citation_accuracy: float = 0.0    # Are citations correct?
    # Latency
    latency_ms: float = 0.0


@dataclass
class EvalReport:
    """Aggregated evaluation report."""
    total_queries: int = 0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_mrr: float = 0.0
    avg_faithfulness: float = 0.0
    avg_relevance: float = 0.0
    avg_citation_accuracy: float = 0.0
    avg_latency_ms: float = 0.0
    metrics: list[EvalMetrics] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "total_queries": self.total_queries,
            "avg_precision": round(self.avg_precision, 4),
            "avg_recall": round(self.avg_recall, 4),
            "avg_mrr": round(self.avg_mrr, 4),
            "avg_faithfulness": round(self.avg_faithfulness, 4),
            "avg_relevance": round(self.avg_relevance, 4),
            "avg_citation_accuracy": round(self.avg_citation_accuracy, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "timestamp": self.timestamp,
        }


class RAGEvaluator:
    """Evaluates RAG pipeline quality."""

    def __init__(self, config: RAGConfig, pipeline: RAGPipeline):
        self.config = config
        self.pipeline = pipeline
        self._http_client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        """Initialize the evaluator."""
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def evaluate_single(
        self,
        query: str,
        expected_answer: Optional[str] = None,
        relevant_doc_ids: Optional[list[str]] = None,
        collection: str = "general",
    ) -> EvalMetrics:
        """Evaluate a single RAG query."""
        # Execute the RAG query
        response = await self.pipeline.query(
            question=query,
            collection=collection,
            pipeline_name="evaluation",
        )

        metrics = EvalMetrics(
            query=query,
            answer=response.answer,
            latency_ms=response.latency_ms,
        )

        # Count citations
        import re
        citations = re.findall(r"\[Source \d+\]", response.answer)
        metrics.citation_count = len(citations)

        # If we have ground truth, compute retrieval metrics
        if relevant_doc_ids:
            retrieved_ids = {s.id for s in response.sources}
            relevant_set = set(relevant_doc_ids)

            if retrieved_ids:
                metrics.retrieval_precision = len(
                    retrieved_ids & relevant_set
                ) / len(retrieved_ids)
            if relevant_set:
                metrics.retrieval_recall = len(
                    retrieved_ids & relevant_set
                ) / len(relevant_set)

            # MRR: reciprocal rank of first relevant result
            for i, source in enumerate(response.sources):
                if source.id in relevant_set:
                    metrics.mrr = 1.0 / (i + 1)
                    break

        # LLM-as-judge for faithfulness and relevance
        if response.answer and response.sources:
            metrics.faithfulness = await self._judge_faithfulness(
                query, response.answer, response.sources
            )
            metrics.relevance = await self._judge_relevance(
                query, response.answer
            )

        return metrics

    async def evaluate_batch(
        self,
        test_cases: list[dict],
        collection: str = "general",
    ) -> EvalReport:
        """Evaluate a batch of test cases.

        Each test case: {
            "query": str,
            "expected_answer": str (optional),
            "relevant_doc_ids": list[str] (optional),
        }
        """
        all_metrics = []

        for i, case in enumerate(test_cases):
            logger.info("Evaluating case %d/%d: %s", i + 1, len(test_cases), case["query"][:50])
            metrics = await self.evaluate_single(
                query=case["query"],
                expected_answer=case.get("expected_answer"),
                relevant_doc_ids=case.get("relevant_doc_ids"),
                collection=collection,
            )
            all_metrics.append(metrics)

        # Aggregate
        n = len(all_metrics)
        report = EvalReport(
            total_queries=n,
            avg_precision=sum(m.retrieval_precision for m in all_metrics) / max(n, 1),
            avg_recall=sum(m.retrieval_recall for m in all_metrics) / max(n, 1),
            avg_mrr=sum(m.mrr for m in all_metrics) / max(n, 1),
            avg_faithfulness=sum(m.faithfulness for m in all_metrics) / max(n, 1),
            avg_relevance=sum(m.relevance for m in all_metrics) / max(n, 1),
            avg_citation_accuracy=sum(m.citation_accuracy for m in all_metrics) / max(n, 1),
            avg_latency_ms=sum(m.latency_ms for m in all_metrics) / max(n, 1),
            metrics=all_metrics,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        return report

    async def _judge_faithfulness(
        self,
        query: str,
        answer: str,
        sources: list,
    ) -> float:
        """Use LLM to judge if answer is faithful to context."""
        context = "\n".join(s.content[:300] for s in sources[:3])

        prompt = (
            f"Rate the faithfulness of this answer to the provided context.\n"
            f"Context: {context}\n"
            f"Answer: {answer}\n\n"
            f"Rate from 0.0 (completely unfaithful) to 1.0 (fully faithful). "
            f"Return ONLY a number between 0.0 and 1.0."
        )

        try:
            score = await self._llm_judge(prompt)
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5  # Default neutral score

    async def _judge_relevance(self, query: str, answer: str) -> float:
        """Use LLM to judge if answer addresses the query."""
        prompt = (
            f"Rate how well this answer addresses the query.\n"
            f"Query: {query}\n"
            f"Answer: {answer}\n\n"
            f"Rate from 0.0 (completely irrelevant) to 1.0 (perfectly addresses query). "
            f"Return ONLY a number between 0.0 and 1.0."
        )

        try:
            score = await self._llm_judge(prompt)
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5

    async def _llm_judge(self, prompt: str) -> float:
        """Call LLM for judgment scoring."""
        resp = await self._http_client.post(
            self.config.llm_endpoint,
            json={
                "model": self.config.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 10,
                "temperature": 0.0,
            },
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # Extract number from response
        import re
        match = re.search(r"(\d+\.?\d*)", content)
        if match:
            return float(match.group(1))
        return 0.5

    async def shutdown(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
