"""
RAG Pipeline — End-to-End Retrieval-Augmented Generation

Orchestrates: query → embed → retrieve → rerank → generate
Provides domain-specific pipelines for credit, market, and health.
"""

import logging
import time
from typing import Optional

import httpx

from .config import RAGConfig
from .embeddings import EmbeddingService
from .vector_store import PgVectorStore, RetrievedChunk
from .reranker import RerankerService

logger = logging.getLogger(__name__)


class RAGResponse:
    """Response from a RAG pipeline query."""

    def __init__(
        self,
        answer: str,
        sources: list[RetrievedChunk],
        query: str,
        pipeline: str,
        latency_ms: float,
        metadata: Optional[dict] = None,
    ):
        self.answer = answer
        self.sources = sources
        self.query = query
        self.pipeline = pipeline
        self.latency_ms = latency_ms
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "sources": [
                {
                    "id": s.id,
                    "content": s.content[:200] + "..." if len(s.content) > 200 else s.content,
                    "score": round(s.score, 4),
                    "metadata": s.metadata,
                }
                for s in self.sources
            ],
            "query": self.query,
            "pipeline": self.pipeline,
            "latency_ms": round(self.latency_ms, 1),
            "metadata": self.metadata,
        }


class RAGPipeline:
    """Core RAG pipeline with domain-specific variants."""

    def __init__(
        self,
        config: RAGConfig,
        embedding_service: EmbeddingService,
        vector_store: PgVectorStore,
        reranker_service: RerankerService,
    ):
        self.config = config
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.reranker_service = reranker_service
        self._http_client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        """Initialize the pipeline."""
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def query(
        self,
        question: str,
        collection: str,
        top_k: Optional[int] = None,
        rerank_top_k: Optional[int] = None,
        metadata_filter: Optional[dict] = None,
        system_prompt: Optional[str] = None,
        pipeline_name: str = "general",
    ) -> RAGResponse:
        """Execute a RAG query: embed → retrieve → rerank → generate."""
        start_time = time.time()

        top_k = top_k or self.config.top_k
        rerank_top_k = rerank_top_k or self.config.rerank_top_k

        # Step 1: Embed the query
        query_embedding = await self.embedding_service.embed(question)

        # Step 2: Retrieve relevant chunks
        chunks = await self.vector_store.search(
            collection=collection,
            query_embedding=query_embedding,
            top_k=top_k,
            metadata_filter=metadata_filter,
        )

        if not chunks:
            return RAGResponse(
                answer="No relevant information found in the knowledge base.",
                sources=[],
                query=question,
                pipeline=pipeline_name,
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Step 3: Rerank
        reranked_chunks = await self.reranker_service.rerank(
            query=question,
            chunks=chunks,
            top_k=rerank_top_k,
        )

        # Step 4: Generate answer with LLM
        context = "\n\n---\n\n".join(
            f"[Source {i+1}] {chunk.content}"
            for i, chunk in enumerate(reranked_chunks)
        )

        default_system = (
            "You are Angavu Intelligence, an AI assistant for informal economy workers in Kenya. "
            "Answer questions based on the provided context. Be concise and actionable. "
            "If the context doesn't contain enough information, say so. "
            "Always cite your sources using [Source N] notation."
        )

        answer = await self._generate(
            question=question,
            context=context,
            system_prompt=system_prompt or default_system,
        )

        latency_ms = (time.time() - start_time) * 1000

        return RAGResponse(
            answer=answer,
            sources=reranked_chunks,
            query=question,
            pipeline=pipeline_name,
            latency_ms=latency_ms,
        )

    async def query_credit(
        self,
        question: str,
        worker_type: Optional[str] = None,
        region: Optional[str] = None,
    ) -> RAGResponse:
        """RAG query for credit scoring context."""
        metadata_filter = {}
        if worker_type:
            metadata_filter["worker_type"] = worker_type
        if region:
            metadata_filter["region"] = region

        system_prompt = (
            "You are Angavu Credit Intelligence, specialized in credit scoring for "
            "informal economy workers in Kenya. Use the provided context to answer "
            "questions about credit risk, repayment patterns, and financial behavior. "
            "Be specific about risk factors and provide actionable insights. "
            "Always cite your sources."
        )

        return await self.query(
            question=question,
            collection=self.config.credit_collection,
            metadata_filter=metadata_filter or None,
            system_prompt=system_prompt,
            pipeline_name="credit_scoring",
        )

    async def query_market(
        self,
        question: str,
        category: Optional[str] = None,
        region: Optional[str] = None,
    ) -> RAGResponse:
        """RAG query for market intelligence."""
        metadata_filter = {}
        if category:
            metadata_filter["category"] = category
        if region:
            metadata_filter["region"] = region

        system_prompt = (
            "You are Angavu Market Intelligence, specialized in analyzing market "
            "conditions for informal economy workers in Kenya. Use the provided "
            "context to answer questions about prices, demand, supply, and market "
            "opportunities. Provide specific, actionable market insights. "
            "Always cite your sources."
        )

        return await self.query(
            question=question,
            collection=self.config.market_collection,
            metadata_filter=metadata_filter or None,
            system_prompt=system_prompt,
            pipeline_name="market_intelligence",
        )

    async def query_health(
        self,
        question: str,
        worker_type: Optional[str] = None,
        region: Optional[str] = None,
    ) -> RAGResponse:
        """RAG query for health and insurance recommendations."""
        metadata_filter = {}
        if worker_type:
            metadata_filter["worker_type"] = worker_type
        if region:
            metadata_filter["region"] = region

        system_prompt = (
            "You are Angavu Health Intelligence, specialized in health risk assessment "
            "and insurance recommendations for informal economy workers in Kenya. "
            "Use the provided context to answer questions about occupation hazards, "
            "health risks, and insurance options. Be specific and actionable. "
            "Always cite your sources."
        )

        return await self.query(
            question=question,
            collection=self.config.health_collection,
            metadata_filter=metadata_filter or None,
            system_prompt=system_prompt,
            pipeline_name="health_insurance",
        )

    async def _generate(
        self,
        question: str,
        context: str,
        system_prompt: str,
    ) -> str:
        """Generate an answer using the LLM."""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Context:\n{context}\n\n"
                    f"Question: {question}\n\n"
                    "Answer based on the context above:"
                ),
            },
        ]

        try:
            resp = await self._http_client.post(
                self.config.llm_endpoint,
                json={
                    "model": self.config.llm_model,
                    "messages": messages,
                    "max_tokens": 1024,
                    "temperature": 0.3,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error("LLM generation failed: %s", e)
            # Return context summary as fallback
            return (
                f"[LLM unavailable] Based on retrieved context:\n\n"
                f"{context[:500]}..."
            )

    async def shutdown(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
