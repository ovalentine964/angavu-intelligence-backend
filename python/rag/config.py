"""
RAG Service Configuration

Environment variables:
  DATABASE_URL          — PostgreSQL connection string (default: postgres://localhost:5432/angavu)
  EMBEDDING_MODEL       — Embedding model name (default: nvidia/nv-embedqa-e5-v5)
  EMBEDDING_ENDPOINT    — NIM embedding endpoint (default: http://localhost:8000/v1/embeddings)
  RERANKER_MODEL        — Reranker model name (default: nvidia/nv-rerankqa-mistral-4b-v3)
  RERANKER_ENDPOINT     — NIM reranker endpoint (default: http://localhost:8001/v1/reranking)
  LLM_ENDPOINT          — LLM endpoint for generation (default: http://localhost:8002/v1/chat/completions)
  RAG_TOP_K             — Default number of retrieved chunks (default: 10)
  RAG_RERANK_TOP_K      — Number of chunks after reranking (default: 5)
  CHUNK_SIZE            — Text chunk size in tokens (default: 512)
  CHUNK_OVERLAP         — Chunk overlap in tokens (default: 64)
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RAGConfig:
    """Configuration for the RAG pipeline."""

    # PostgreSQL / pgvector
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "postgres://angavu:angavu@localhost:5432/angavu"
        )
    )

    # Embedding model (NVIDIA NeMo Retriever)
    embedding_model: str = field(
        default_factory=lambda: os.environ.get(
            "EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5"
        )
    )
    embedding_endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "EMBEDDING_ENDPOINT", "http://localhost:8000/v1/embeddings"
        )
    )
    embedding_dimension: int = 1024  # nv-embedqa-e5-v5 output dimension

    # Reranker model (NVIDIA NeMo Retriever)
    reranker_model: str = field(
        default_factory=lambda: os.environ.get(
            "RERANKER_MODEL", "nvidia/nv-rerankqa-mistral-4b-v3"
        )
    )
    reranker_endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "RERANKER_ENDPOINT", "http://localhost:8001/v1/reranking"
        )
    )

    # LLM for generation
    llm_endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "LLM_ENDPOINT", "http://localhost:8002/v1/chat/completions"
        )
    )
    llm_model: str = field(
        default_factory=lambda: os.environ.get("LLM_MODEL", "deepseek-chat")
    )

    # Retrieval parameters
    top_k: int = field(
        default_factory=lambda: int(os.environ.get("RAG_TOP_K", "10"))
    )
    rerank_top_k: int = field(
        default_factory=lambda: int(os.environ.get("RAG_RERANK_TOP_K", "5"))
    )

    # Chunking parameters
    chunk_size: int = field(
        default_factory=lambda: int(os.environ.get("CHUNK_SIZE", "512"))
    )
    chunk_overlap: int = field(
        default_factory=lambda: int(os.environ.get("CHUNK_OVERLAP", "64"))
    )

    # Collection names for different RAG pipelines
    credit_collection: str = "angavu_credit_context"
    market_collection: str = "angavu_market_intelligence"
    health_collection: str = "angavu_health_insurance"

    # API
    host: str = "0.0.0.0"
    port: int = 8090

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Load configuration from environment variables."""
        return cls()
