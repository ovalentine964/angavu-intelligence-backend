"""
Embedding Service — NVIDIA NeMo Retriever Embedding Integration

Uses NVIDIA NIM endpoints for high-quality embeddings.
Supports both single and batch embedding requests.
Falls back to local sentence-transformers if NIM is unavailable.
"""

import asyncio
import logging
from typing import Optional

import httpx
import numpy as np

from .config import RAGConfig

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Manages text embedding via NVIDIA NIM or local fallback."""

    def __init__(self, config: RAGConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._local_model = None

    async def initialize(self):
        """Initialize the embedding client."""
        self._client = httpx.AsyncClient(timeout=30.0)

        # Test NIM connectivity
        try:
            resp = await self._client.get(
                f"{self.config.embedding_endpoint.rstrip('/v1/embeddings')}/v1/models"
            )
            if resp.status_code == 200:
                logger.info(
                    "NIM embedding endpoint available: %s", self.config.embedding_endpoint
                )
                return
        except Exception:
            pass

        # Fall back to local model
        logger.warning(
            "NIM embedding endpoint unavailable, falling back to local model"
        )
        try:
            from sentence_transformers import SentenceTransformer

            self._local_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Local embedding model loaded: all-MiniLM-L6-v2")
        except ImportError:
            logger.error(
                "Neither NIM endpoint nor sentence-transformers available. "
                "Install sentence-transformers: pip install sentence-transformers"
            )
            raise

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings."""
        if self._local_model:
            return self._embed_local(texts)
        return await self._embed_nim(texts)

    async def _embed_nim(self, texts: list[str]) -> list[list[float]]:
        """Embed via NVIDIA NIM endpoint."""
        payload = {
            "input": texts,
            "model": self.config.embedding_model,
            "input_type": "passage",
            "encoding_format": "float",
        }

        try:
            resp = await self._client.post(
                self.config.embedding_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            # NIM returns embeddings in data[].embedding
            embeddings = [item["embedding"] for item in data["data"]]
            return embeddings

        except Exception as e:
            logger.error("NIM embedding failed: %s", e)
            if self._local_model:
                logger.info("Falling back to local model")
                return self._embed_local(texts)
            raise

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Embed using local sentence-transformers model."""
        embeddings = self._local_model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    async def shutdown(self):
        """Clean up resources."""
        if self._client:
            await self._client.aclose()
