"""
Document Ingestion Pipeline

Handles document chunking, embedding, and storage for the RAG system.
Supports text, PDF, and structured data ingestion.
"""

import hashlib
import logging
import re
from typing import Optional

from .config import RAGConfig
from .embeddings import EmbeddingService
from .vector_store import PgVectorStore

logger = logging.getLogger(__name__)


class DocumentChunk:
    """A chunk of text with metadata."""

    def __init__(
        self,
        content: str,
        metadata: Optional[dict] = None,
        source: str = "",
        chunk_index: int = 0,
    ):
        self.content = content
        self.metadata = metadata or {}
        self.source = source
        self.chunk_index = chunk_index
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]


class IngestionPipeline:
    """Ingests documents into the RAG vector store."""

    def __init__(
        self,
        config: RAGConfig,
        embedding_service: EmbeddingService,
        vector_store: PgVectorStore,
    ):
        self.config = config
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def chunk_text(
        self,
        text: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> list[DocumentChunk]:
        """Split text into overlapping chunks."""
        chunk_size = chunk_size or self.config.chunk_size
        chunk_overlap = chunk_overlap or self.config.chunk_overlap

        # Clean text
        text = re.sub(r"\n{3,}", "\n\n", text.strip())

        if len(text) <= chunk_size:
            return [DocumentChunk(content=text)]

        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence end within last 20% of chunk
                search_start = start + int(chunk_size * 0.8)
                for sep in [". ", ".\n", "!\n", "?\n", "\n\n"]:
                    last_sep = text.rfind(sep, search_start, end)
                    if last_sep > start:
                        end = last_sep + len(sep)
                        break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    DocumentChunk(
                        content=chunk_text,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1

            start = end - chunk_overlap
            if start >= len(text):
                break

        return chunks

    async def ingest_text(
        self,
        collection: str,
        text: str,
        metadata: Optional[dict] = None,
        source: str = "",
    ) -> dict:
        """Ingest a text document into a collection."""
        # Chunk the text
        chunks = self.chunk_text(text)
        logger.info("Chunked text into %d chunks for collection '%s'", len(chunks), collection)

        # Embed all chunks
        contents = [c.content for c in chunks]
        embeddings = await self.embedding_service.embed_batch(contents)

        # Prepare documents for insertion
        documents = []
        for chunk, embedding in zip(chunks, embeddings):
            doc_metadata = {
                **(metadata or {}),
                "source": source,
                "chunk_index": chunk.chunk_index,
                "content_hash": chunk.content_hash,
            }
            documents.append(
                {
                    "content": chunk.content,
                    "embedding": embedding,
                    "metadata": doc_metadata,
                }
            )

        # Insert into vector store
        ids = await self.vector_store.insert_batch(collection, documents)

        return {
            "collection": collection,
            "chunks_ingested": len(ids),
            "document_ids": ids,
            "source": source,
        }

    async def ingest_structured(
        self,
        collection: str,
        records: list[dict],
        content_field: str = "text",
        metadata_fields: Optional[list[str]] = None,
    ) -> dict:
        """Ingest structured records (e.g., market data, credit histories).

        Each record should have a `content_field` with the text to embed.
        Additional fields listed in `metadata_fields` are stored as metadata.
        """
        documents = []
        for record in records:
            content = record.get(content_field, "")
            if not content:
                continue

            metadata = {}
            if metadata_fields:
                for field in metadata_fields:
                    if field in record:
                        metadata[field] = record[field]

            embedding = await self.embedding_service.embed(content)
            documents.append(
                {
                    "content": content,
                    "embedding": embedding,
                    "metadata": metadata,
                }
            )

        ids = await self.vector_store.insert_batch(collection, documents)

        return {
            "collection": collection,
            "records_ingested": len(ids),
            "document_ids": ids,
        }

    async def ingest_market_data(
        self,
        region: str,
        category: str,
        data_points: list[dict],
    ) -> dict:
        """Ingest market intelligence data.

        Each data_point should have: price, volume, date, source, etc.
        """
        records = []
        for dp in data_points:
            text = (
                f"Market data for {category} in {region}: "
                f"Price KES {dp.get('price', 'N/A')}, "
                f"Volume {dp.get('volume', 'N/A')}, "
                f"Trend: {dp.get('trend', 'stable')}. "
                f"Date: {dp.get('date', 'unknown')}. "
                f"Source: {dp.get('source', 'internal')}."
            )
            records.append(
                {
                    "text": text,
                    "region": region,
                    "category": category,
                    "date": dp.get("date"),
                    "price": dp.get("price"),
                    "volume": dp.get("volume"),
                }
            )

        return await self.ingest_structured(
            collection=self.config.market_collection,
            records=records,
            content_field="text",
            metadata_fields=["region", "category", "date", "price", "volume"],
        )

    async def ingest_credit_context(
        self,
        worker_type: str,
        region: str,
        context_records: list[dict],
    ) -> dict:
        """Ingest credit scoring context data.

        Each record should describe credit-relevant factors.
        """
        records = []
        for cr in context_records:
            text = cr.get("description", cr.get("text", ""))
            if not text:
                continue

            records.append(
                {
                    "text": text,
                    "worker_type": worker_type,
                    "region": region,
                    "context_type": cr.get("type", "general"),
                }
            )

        return await self.ingest_structured(
            collection=self.config.credit_collection,
            records=records,
            content_field="text",
            metadata_fields=["worker_type", "region", "context_type"],
        )
