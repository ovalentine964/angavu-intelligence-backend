"""
Vector Store — pgvector Integration

Uses PostgreSQL with pgvector extension for vector storage and retrieval.
This leverages the existing PostgreSQL infrastructure in the Angavu stack.
"""

import logging
from typing import Optional
from dataclasses import dataclass

import numpy as np

from .config import RAGConfig

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved text chunk with metadata."""
    id: str
    content: str
    metadata: dict
    score: float
    collection: str


class PgVectorStore:
    """PostgreSQL pgvector-backed vector store for RAG."""

    def __init__(self, config: RAGConfig):
        self.config = config
        self._pool = None

    async def initialize(self):
        """Initialize the connection pool and ensure tables exist."""
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.config.database_url, min_size=2, max_size=10
            )

            # Enable pgvector extension
            async with self._pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

                # Create the RAG documents table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS rag_documents (
                        id BIGSERIAL PRIMARY KEY,
                        collection VARCHAR(128) NOT NULL,
                        content TEXT NOT NULL,
                        metadata JSONB DEFAULT '{}',
                        embedding vector(%d),
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """ % self.config.embedding_dimension)

                # Create indexes
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rag_documents_collection
                    ON rag_documents (collection)
                """)

                # HNSW index for fast approximate nearest neighbor search
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rag_documents_embedding
                    ON rag_documents USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                """)

                # GIN index on metadata for filtered queries
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rag_documents_metadata
                    ON rag_documents USING gin (metadata)
                """)

            logger.info("PgVector store initialized with dimension %d", self.config.embedding_dimension)

        except ImportError:
            logger.error("asyncpg not installed. Install: pip install asyncpg")
            raise
        except Exception as e:
            logger.error("Failed to initialize PgVector store: %s", e)
            raise

    async def insert(
        self,
        collection: str,
        content: str,
        embedding: list[float],
        metadata: Optional[dict] = None,
    ) -> int:
        """Insert a document with its embedding."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO rag_documents (collection, content, metadata, embedding)
                VALUES ($1, $2, $3, $4::vector)
                RETURNING id
                """,
                collection,
                content,
                metadata or {},
                str(embedding),
            )
            return row["id"]

    async def insert_batch(
        self,
        collection: str,
        documents: list[dict],
    ) -> list[int]:
        """Insert multiple documents with embeddings.

        Each document dict should have: content, embedding, metadata (optional)
        """
        ids = []
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for doc in documents:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO rag_documents (collection, content, metadata, embedding)
                        VALUES ($1, $2, $3, $4::vector)
                        RETURNING id
                        """,
                        collection,
                        doc["content"],
                        doc.get("metadata", {}),
                        str(doc["embedding"]),
                    )
                    ids.append(row["id"])
        return ids

    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        top_k: int = 10,
        metadata_filter: Optional[dict] = None,
    ) -> list[RetrievedChunk]:
        """Search for similar documents using cosine similarity."""
        async with self._pool.acquire() as conn:
            if metadata_filter:
                # Build metadata filter clause
                filter_conditions = []
                filter_values = []
                param_idx = 3  # $1=collection, $2=embedding, $3+=filters

                for key, value in metadata_filter.items():
                    filter_conditions.append(
                        f"metadata->>'{key}' = ${param_idx}"
                    )
                    filter_values.append(str(value))
                    param_idx += 1

                filter_clause = "AND " + " AND ".join(filter_conditions)
                query = f"""
                    SELECT id, content, metadata, 
                           1 - (embedding <=> $2::vector) as score
                    FROM rag_documents
                    WHERE collection = $1 {filter_clause}
                    ORDER BY embedding <=> $2::vector
                    LIMIT {top_k}
                """
                rows = await conn.fetch(
                    query, collection, str(query_embedding), *filter_values
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, content, metadata,
                           1 - (embedding <=> $2::vector) as score
                    FROM rag_documents
                    WHERE collection = $1
                    ORDER BY embedding <=> $2::vector
                    LIMIT $3
                    """,
                    collection,
                    str(query_embedding),
                    top_k,
                )

            return [
                RetrievedChunk(
                    id=str(row["id"]),
                    content=row["content"],
                    metadata=row["metadata"] if row["metadata"] else {},
                    score=float(row["score"]),
                    collection=collection,
                )
                for row in rows
            ]

    async def delete_collection(self, collection: str) -> int:
        """Delete all documents in a collection."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM rag_documents WHERE collection = $1", collection
            )
            count = int(result.split()[-1])
            return count

    async def collection_stats(self, collection: str) -> dict:
        """Get statistics for a collection."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) as doc_count,
                       pg_size_pretty(pg_total_relation_size('rag_documents')) as table_size
                FROM rag_documents
                WHERE collection = $1
                """,
                collection,
            )
            return {
                "collection": collection,
                "document_count": row["doc_count"],
                "table_size": row["table_size"],
            }

    async def list_collections(self) -> list[str]:
        """List all collections."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT collection FROM rag_documents ORDER BY collection"
            )
            return [row["collection"] for row in rows]

    async def shutdown(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
