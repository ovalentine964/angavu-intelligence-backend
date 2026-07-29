"""
Reranker Service — NVIDIA NeMo Retriever Reranking

Uses NVIDIA NIM reranker endpoint for high-quality reranking.
Falls back to a simple score-based reranker if NIM is unavailable.
"""

import logging
from typing import Optional

import httpx

from .config import RAGConfig
from .vector_store import RetrievedChunk

logger = logging.getLogger(__name__)


class RerankerService:
    """Reranks retrieved chunks using NVIDIA NIM reranker."""

    def __init__(self, config: RAGConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._use_nim = False

    async def initialize(self):
        """Initialize the reranker client."""
        self._client = httpx.AsyncClient(timeout=30.0)

        # Test NIM reranker connectivity
        try:
            base_url = self.config.reranker_endpoint.rstrip("/")
            if base_url.endswith("/v1/reranking"):
                base_url = base_url[: -len("/v1/reranking")]

            resp = await self._client.get(f"{base_url}/v1/models")
            if resp.status_code == 200:
                self._use_nim = True
                logger.info("NIM reranker endpoint available")
                return
        except Exception:
            pass

        logger.warning("NIM reranker unavailable, using score-based fallback")

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: Optional[int] = None,
    ) -> list[RetrievedChunk]:
        """Rerank chunks by relevance to the query."""
        if not chunks:
            return []

        top_k = top_k or self.config.rerank_top_k

        if self._use_nim:
            return await self._rerank_nim(query, chunks, top_k)

        return self._rerank_fallback(query, chunks, top_k)

    async def _rerank_nim(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Rerank via NVIDIA NIM endpoint."""
        passages = [chunk.content for chunk in chunks]

        payload = {
            "model": self.config.reranker_model,
            "query": {"text": query},
            "passages": [{"text": p} for p in passages],
            "top_n": top_k,
        }

        try:
            resp = await self._client.post(
                self.config.reranker_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            # Map reranker results back to chunks
            reranked = []
            for rank_result in data.get("rankings", data.get("results", [])):
                idx = rank_result.get("index", rank_result.get("passage_index", 0))
                score = rank_result.get("logit", rank_result.get("score", 0.0))
                if 0 <= idx < len(chunks):
                    chunk = chunks[idx]
                    chunk.score = float(score)
                    reranked.append(chunk)

            return reranked[:top_k]

        except Exception as e:
            logger.error("NIM reranker failed: %s, falling back", e)
            return self._rerank_fallback(query, chunks, top_k)

    def _rerank_fallback(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Simple keyword-overlap reranker as fallback."""
        query_words = set(query.lower().split())

        for chunk in chunks:
            chunk_words = set(chunk.content.lower().split())
            overlap = len(query_words & chunk_words)
            # Combine original score with keyword overlap
            keyword_score = overlap / max(len(query_words), 1)
            chunk.score = 0.7 * chunk.score + 0.3 * keyword_score

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:top_k]

    async def shutdown(self):
        """Clean up resources."""
        if self._client:
            await self._client.aclose()
