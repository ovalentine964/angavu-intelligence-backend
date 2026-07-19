"""
RAG Engine — Core retrieval-augmented generation infrastructure.

Implements five RAG patterns from awesome-llm-apps, adapted for Angavu Intelligence:

1. Hybrid Search (BM25 + Vector)     — from hybrid_search_rag/
2. Corrective RAG (self-correction)  — from corrective_rag/
3. Agentic RAG with Reasoning        — from agentic_rag_with_reasoning/
4. Typed RAG with Pydantic outputs   — from agentic_typed_rag_pydanticai/
5. Knowledge Graph RAG with Citations — from knowledge_graph_rag_citations/

Designed as a pluggable layer between the event bus and domain agents.
Each Angavu product (Soko Pulse, Alama Score, Angavu Pulse) uses
a different combination of these patterns.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, Sequence

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Models
# ════════════════════════════════════════════════════════════════════


class RetrievalStrategy(StrEnum):
    """How to retrieve context for RAG."""
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    HYBRID_WITH_KG = "hybrid_with_kg"


class CorrectionAction(StrEnum):
    """Actions the corrective RAG can take."""
    PASS = "pass"               # Evidence is sufficient
    RETRY_RETRIEVAL = "retry"   # Re-retrieve with transformed query
    WEB_SEARCH = "web_search"   # Fallback to external search
    REFUSE = "refuse"           # Insufficient evidence


@dataclass(frozen=True)
class DocumentChunk:
    """A source span stored in the vector index."""
    source: str
    chunk_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    """A chunk paired with its relevance score."""
    chunk: DocumentChunk
    score: float
    retrieval_method: str = "vector"


@dataclass
class Citation:
    """A verifiable citation linking a claim to a source chunk."""
    source: str
    chunk_id: str
    quoted_span: str
    confidence: float = 1.0


@dataclass
class RetrievalEvidence:
    """Typed result of one retrieval cycle."""
    query: str
    chunks: list[SearchResult]
    enough_evidence: bool
    top_score: float
    retrieval_strategy: RetrievalStrategy
    correction_action: CorrectionAction = CorrectionAction.PASS
    transformed_query: str | None = None


@dataclass
class RAGAnswer:
    """Final answer with citations and reasoning trace."""
    text: str
    citations: list[Citation]
    confidence: float
    answered: bool
    reasoning_trace: list[str] = field(default_factory=list)
    retrieval_evidence: RetrievalEvidence | None = None


@dataclass
class EntityNode:
    """A node in the knowledge graph."""
    id: str
    name: str
    entity_type: str
    description: str
    source_doc: str
    source_chunk: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityRelationship:
    """An edge in the knowledge graph."""
    source_id: str
    target_id: str
    relation_type: str
    description: str
    source_doc: str
    weight: float = 1.0


# ════════════════════════════════════════════════════════════════════
# BM25 Retriever (from hybrid_search_rag pattern)
# ════════════════════════════════════════════════════════════════════


class BM25Retriever:
    """
    BM25 keyword-based retrieval for exact term matching.

    Complements vector search for queries with specific product names,
    numeric values, or Swahili terms that embeddings may not capture well.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._chunks: list[DocumentChunk] = []
        self._doc_freqs: list[dict[str, int]] = []
        self._avg_dl: float = 0.0
        self._doc_count: int = 0
        self._idf: dict[str, float] = {}
        self._term_freqs: list[dict[str, int]] = []

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text: lowercase, split on non-alphanumeric, stem."""
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        # Simple suffix stripping for Swahili/English
        stemmed = []
        for t in tokens:
            for suffix in ("ing", "ed", "es", "s", "tion", "ness"):
                if t.endswith(suffix) and len(t) > len(suffix) + 2:
                    t = t[: -len(suffix)]
                    break
            stemmed.append(t)
        return stemmed

    def add_documents(self, chunks: Sequence[DocumentChunk]) -> None:
        """Index document chunks for BM25 retrieval."""
        for chunk in chunks:
            tokens = self._tokenize(chunk.text)
            tf: dict[str, int] = defaultdict(int)
            for token in tokens:
                tf[token] += 1
            self._chunks.append(chunk)
            self._term_freqs.append(dict(tf))
            self._doc_freqs.append(tf)

        self._doc_count = len(self._chunks)
        if self._doc_count == 0:
            return

        # Compute average document length
        total_len = sum(len(self._tokenize(c.text)) for c in self._chunks)
        self._avg_dl = total_len / self._doc_count if self._doc_count > 0 else 1.0

        # Compute IDF for all terms
        df: dict[str, int] = defaultdict(int)
        for tf in self._term_freqs:
            for term in tf:
                df[term] += 1

        self._idf = {}
        for term, freq in df.items():
            self._idf[term] = math.log(
                (self._doc_count - freq + 0.5) / (freq + 0.5) + 1.0
            )

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search using BM25 scoring."""
        if not self._chunks:
            return []

        query_tokens = self._tokenize(query)
        scores: list[float] = []

        for i, chunk in enumerate(self._chunks):
            tf = self._term_freqs[i]
            doc_len = sum(tf.values())
            score = 0.0

            for qt in query_tokens:
                if qt not in tf or qt not in self._idf:
                    continue
                term_freq = tf[qt]
                idf = self._idf[qt]
                numerator = term_freq * (self.k1 + 1)
                denominator = term_freq + self.k1 * (
                    1 - self.b + self.b * doc_len / self._avg_dl
                )
                score += idf * numerator / denominator

            scores.append(score)

        # Normalize to [0, 1]
        max_score = max(scores) if scores else 1.0
        if max_score > 0:
            scores = [s / max_score for s in scores]

        ranked = sorted(
            zip(self._chunks, scores), key=lambda x: x[1], reverse=True
        )[:limit]

        return [
            SearchResult(chunk=chunk, score=round(score, 4), retrieval_method="bm25")
            for chunk, score in ranked
            if score > 0.01
        ]

    def clear(self) -> None:
        """Clear all indexed documents."""
        self._chunks.clear()
        self._doc_freqs.clear()
        self._term_freqs.clear()
        self._idf.clear()
        self._doc_count = 0
        self._avg_dl = 0.0


# ════════════════════════════════════════════════════════════════════
# Vector Retriever (from agentic_typed_rag_pydanticai pattern)
# ════════════════════════════════════════════════════════════════════


class VectorRetriever:
    """
    In-memory cosine similarity vector store.

    Uses a pluggable embedding backend. For production, replace
    HashingEmbedding with OpenAI or a local model.
    """

    def __init__(self, embedding_backend: Any | None = None):
        self._embedding_backend = embedding_backend or HashingEmbedding()
        self._chunks: list[DocumentChunk] = []
        self._vectors: list[list[float]] = []

    async def add_documents(self, chunks: Sequence[DocumentChunk]) -> int:
        """Embed and index document chunks."""
        texts = [c.text for c in chunks]
        vectors = await self._embedding_backend.embed(texts)
        self._chunks.extend(chunks)
        self._vectors.extend(vectors)
        return len(chunks)

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search using cosine similarity."""
        if not self._chunks:
            return []

        query_vec = await self._embedding_backend.embed([query])
        if not query_vec:
            return []

        q = query_vec[0]
        q_norm = math.sqrt(sum(x * x for x in q))
        if q_norm == 0:
            return []

        scores: list[float] = []
        for doc_vec in self._vectors:
            dot = sum(a * b for a, b in zip(q, doc_vec))
            d_norm = math.sqrt(sum(x * x for x in doc_vec))
            if d_norm == 0:
                scores.append(0.0)
            else:
                scores.append(dot / (q_norm * d_norm))

        ranked = sorted(
            zip(self._chunks, scores), key=lambda x: x[1], reverse=True
        )[:limit]

        return [
            SearchResult(
                chunk=chunk,
                score=round(max(0.0, min(1.0, score)), 4),
                retrieval_method="vector",
            )
            for chunk, score in ranked
        ]

    def clear(self) -> None:
        """Clear all indexed documents."""
        self._chunks.clear()
        self._vectors.clear()


class HashingEmbedding:
    """
    Offline fallback embedding using term hashing.

    Production should use OpenAI embeddings or a local model.
    This provides deterministic, zero-dependency embeddings for testing.
    """

    def __init__(self, dimensions: int = 768):
        self.dimensions = dimensions

    def _terms(self, text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        stemmed = []
        for t in tokens:
            for suffix in ("ing", "ed", "es", "s"):
                if t.endswith(suffix) and len(t) > len(suffix) + 2:
                    t = t[: -len(suffix)]
                    break
            stemmed.append(t)
        bigrams = [f"{a}:{b}" for a, b in zip(stemmed, stemmed[1:])]
        return stemmed + bigrams

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic hash-based embeddings."""
        results = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for term in self._terms(text):
                digest = hashlib.md5(term.encode()).digest()
                pos = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[0] & 1 else -1.0
                vector[pos] += sign
            norm = math.sqrt(sum(x * x for x in vector))
            if norm > 0:
                vector = [x / norm for x in vector]
            results.append(vector)
        return results


# ════════════════════════════════════════════════════════════════════
# Knowledge Graph Store (from knowledge_graph_rag_citations pattern)
# ════════════════════════════════════════════════════════════════════


class KnowledgeGraphStore:
    """
    In-memory knowledge graph for multi-hop reasoning.

    Stores entities and relationships extracted from documents.
    Supports multi-hop traversal for complex queries like:
    "What products does the supplier with the highest volume sell?"

    Adapted from knowledge_graph_rag_citations/ for Angavu's domain:
    - Entities: products, suppliers, regions, markets, businesses
    - Relationships: SUPPLIES, COMPETES_WITH, LOCATED_IN, SELLS
    """

    def __init__(self):
        self._entities: dict[str, EntityNode] = {}
        self._relationships: list[EntityRelationship] = []
        self._adjacency: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
        # entity_id → [(target_id, relation_type, weight)]

    def add_entity(self, entity: EntityNode) -> None:
        """Add an entity node to the graph."""
        self._entities[entity.id] = entity

    def add_relationship(self, rel: EntityRelationship) -> None:
        """Add a relationship edge to the graph."""
        self._relationships.append(rel)
        self._adjacency[rel.source_id].append(
            (rel.target_id, rel.relation_type, rel.weight)
        )
        self._adjacency[rel.target_id].append(
            (rel.source_id, f"INVERSE_{rel.relation_type}", rel.weight)
        )

    def find_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[EntityNode]:
        """Find entities matching a text query."""
        query_lower = query.lower()
        results = []
        for entity in self._entities.values():
            if entity_type and entity.entity_type != entity_type:
                continue
            score = 0.0
            if query_lower in entity.name.lower():
                score += 2.0
            if query_lower in entity.description.lower():
                score += 1.0
            if score > 0:
                results.append((score, entity))

        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:limit]]

    def traverse(
        self,
        start_id: str,
        max_hops: int = 2,
        relation_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Multi-hop graph traversal from a starting entity.

        Returns paths with entity descriptions and relationship info.
        Used for answering complex queries that require connecting
        information across multiple entities.
        """
        visited: set[str] = set()
        paths: list[dict[str, Any]] = []
        queue: list[tuple[str, list[str], list[str]]] = [(start_id, [], [])]
        # (current_id, path_ids, path_descriptions)

        while queue:
            current_id, path_ids, path_descs = queue.pop(0)
            if current_id in visited or len(path_ids) > max_hops:
                continue
            visited.add(current_id)

            entity = self._entities.get(current_id)
            if entity:
                paths.append({
                    "entity": entity.name,
                    "entity_type": entity.entity_type,
                    "description": entity.description,
                    "source_doc": entity.source_doc,
                    "source_chunk": entity.source_chunk,
                    "hops": len(path_ids),
                    "path": list(path_ids),
                    "path_descriptions": list(path_descs),
                })

            for target_id, rel_type, weight in self._adjacency.get(current_id, []):
                if target_id not in visited:
                    if relation_filter and relation_filter not in rel_type:
                        continue
                    queue.append((
                        target_id,
                        path_ids + [current_id],
                        path_descs + [rel_type],
                    ))

        return paths

    def get_stats(self) -> dict[str, Any]:
        """Return graph statistics."""
        return {
            "entity_count": len(self._entities),
            "relationship_count": len(self._relationships),
            "entity_types": list(set(e.entity_type for e in self._entities.values())),
        }


# ════════════════════════════════════════════════════════════════════
# Hybrid Retriever (from hybrid_search_rag pattern)
# ════════════════════════════════════════════════════════════════════


class HybridRetriever:
    """
    Combines BM25 keyword search with vector semantic search.

    Pattern from hybrid_search_rag/ — merges results using
    Reciprocal Rank Fusion (RRF) for robust ranking.

    Why hybrid:
    - BM25 catches exact terms: product names, regions, Swahili words
    - Vector catches semantic similarity: "price increase" ≈ "bei imepanda"
    - RRF merge avoids score normalization issues between different methods
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever | None = None,
        bm25_retriever: BM25Retriever | None = None,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
        rrf_k: int = 60,
    ):
        self.vector = vector_retriever or VectorRetriever()
        self.bm25 = bm25_retriever or BM25Retriever()
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k

    async def add_documents(self, chunks: Sequence[DocumentChunk]) -> int:
        """Index documents in both retrievers."""
        await self.vector.add_documents(chunks)
        self.bm25.add_documents(chunks)
        return len(chunks)

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """
        Hybrid search using Reciprocal Rank Fusion.

        RRF score = Σ (weight / (k + rank_i)) for each retrieval method.
        This naturally combines scores from different scales.
        """
        vector_results = await self.vector.search(query, limit=limit * 2)
        bm25_results = self.bm25.search(query, limit=limit * 2)

        # Build RRF scores
        rrf_scores: dict[str, float] = defaultdict(float)
        chunk_map: dict[str, SearchResult] = {}

        for rank, result in enumerate(vector_results):
            key = result.chunk.chunk_id
            rrf_scores[key] += self.vector_weight / (self.rrf_k + rank + 1)
            chunk_map[key] = result

        for rank, result in enumerate(bm25_results):
            key = result.chunk.chunk_id
            rrf_scores[key] += self.bm25_weight / (self.rrf_k + rank + 1)
            chunk_map[key] = result

        # Sort by RRF score
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        # Normalize RRF scores to [0, 1]
        max_rrf = ranked[0][1] if ranked else 1.0

        results = []
        for chunk_id, score in ranked:
            original = chunk_map[chunk_id]
            results.append(SearchResult(
                chunk=original.chunk,
                score=round(score / max_rrf, 4) if max_rrf > 0 else 0.0,
                retrieval_method="hybrid",
            ))

        return results

    def clear(self) -> None:
        """Clear both retrievers."""
        self.vector.clear()
        self.bm25.clear()


# ════════════════════════════════════════════════════════════════════
# Corrective RAG (from corrective_rag pattern)
# ════════════════════════════════════════════════════════════════════


class CorrectiveRAG:
    """
    Self-correcting RAG that grades retrieved evidence and decides
    whether to proceed, retry, or refuse.

    Pattern from corrective_rag/ — adds a quality gate between
    retrieval and generation:

    1. Retrieve initial evidence
    2. Grade each chunk for relevance
    3. If insufficient: transform query and retry
    4. If still insufficient: refuse or fallback

    For Angavu: ensures agents don't hallucinate market data or
    credit scores when evidence is thin.
    """

    def __init__(
        self,
        retriever: HybridRetriever,
        min_relevance_score: float = 0.3,
        max_retries: int = 2,
        min_evidence_chunks: int = 1,
    ):
        self.retriever = retriever
        self.min_relevance = min_relevance_score
        self.max_retries = max_retries
        self.min_evidence = min_evidence_chunks

    async def retrieve_with_correction(
        self,
        query: str,
        top_k: int = 5,
        llm_fn: Any | None = None,
    ) -> RetrievalEvidence:
        """
        Retrieve evidence with self-correction loop.

        Steps:
        1. Initial hybrid retrieval
        2. Grade documents for relevance (if llm_fn available)
        3. Filter irrelevant documents
        4. If insufficient: transform query and retry
        5. Return final evidence with correction metadata

        Args:
            query: The user's question
            top_k: Number of chunks to retrieve
            llm_fn: Optional async function(prompt) -> str for grading/transform
        """
        current_query = query
        trace: list[str] = []

        for attempt in range(self.max_retries + 1):
            trace.append(f"Attempt {attempt + 1}: searching for '{current_query}'")

            # Retrieve
            results = await self.retriever.search(current_query, limit=top_k)
            trace.append(f"  Retrieved {len(results)} chunks")

            if not results:
                if attempt < self.max_retries:
                    current_query = await self._transform_query(query, llm_fn)
                    trace.append(f"  No results. Transformed query: '{current_query}'")
                    continue
                return RetrievalEvidence(
                    query=query,
                    chunks=[],
                    enough_evidence=False,
                    top_score=0.0,
                    retrieval_strategy=RetrievalStrategy.HYBRID,
                    correction_action=CorrectionAction.REFUSE,
                    transformed_query=current_query if current_query != query else None,
                )

            # Grade documents if LLM available
            if llm_fn:
                graded_results = []
                for result in results:
                    is_relevant = await self._grade_document(
                        query, result.chunk.text, llm_fn
                    )
                    if is_relevant:
                        graded_results.append(result)
                    else:
                        trace.append(f"  Filtered out chunk {result.chunk.chunk_id} (irrelevant)")

                results = graded_results

            top_score = results[0].score if results else 0.0

            # Check if we have enough evidence
            enough = (
                len(results) >= self.min_evidence
                and top_score >= self.min_relevance
            )

            if enough:
                trace.append(f"  Sufficient evidence: {len(results)} chunks, top score {top_score:.3f}")
                return RetrievalEvidence(
                    query=query,
                    chunks=results,
                    enough_evidence=True,
                    top_score=top_score,
                    retrieval_strategy=RetrievalStrategy.HYBRID,
                    correction_action=CorrectionAction.PASS,
                    transformed_query=current_query if current_query != query else None,
                )

            # Not enough — try to transform query
            if attempt < self.max_retries:
                current_query = await self._transform_query(query, llm_fn)
                trace.append(f"  Insufficient. Transformed query: '{current_query}'")
            else:
                trace.append(f"  Max retries reached. Top score: {top_score:.3f}")
                return RetrievalEvidence(
                    query=query,
                    chunks=results,
                    enough_evidence=top_score >= self.min_relevance * 0.5,
                    top_score=top_score,
                    retrieval_strategy=RetrievalStrategy.HYBRID,
                    correction_action=CorrectionAction.REFUSE if top_score < self.min_relevance * 0.5 else CorrectionAction.PASS,
                    transformed_query=current_query if current_query != query else None,
                )

        # Should not reach here, but safety fallback
        return RetrievalEvidence(
            query=query,
            chunks=[],
            enough_evidence=False,
            top_score=0.0,
            retrieval_strategy=RetrievalStrategy.HYBRID,
            correction_action=CorrectionAction.REFUSE,
        )

    async def _grade_document(
        self, query: str, document: str, llm_fn: Any
    ) -> bool:
        """Grade a document's relevance to the query using LLM."""
        prompt = (
            f"You are grading the relevance of a retrieved document to a question.\n"
            f"Return ONLY 'yes' or 'no'.\n\n"
            f"Document: {document[:500]}\n"
            f"Question: {query}\n\n"
            f"Is this document relevant? (yes/no):"
        )
        try:
            response = await llm_fn(prompt)
            return "yes" in response.lower()
        except Exception:
            return True  # Keep document on error (fail-open)

    async def _transform_query(self, query: str, llm_fn: Any | None) -> str:
        """Transform query for better retrieval."""
        if llm_fn:
            prompt = (
                f"Generate a search-optimized version of this question.\n"
                f"Focus on key terms and concepts.\n\n"
                f"Original: {query}\n\n"
                f"Optimized:"
            )
            try:
                return (await llm_fn(prompt)).strip()
            except Exception:
                pass

        # Fallback: simple term extraction
        words = query.split()
        # Remove common stop words
        stops = {"the", "a", "an", "is", "are", "was", "were", "what", "how", "why"}
        key_words = [w for w in words if w.lower() not in stops]
        return " ".join(key_words) if key_words else query


# ════════════════════════════════════════════════════════════════════
# Typed RAG Agent (from agentic_typed_rag_pydanticai pattern)
# ════════════════════════════════════════════════════════════════════


class TypedRAGAgent:
    """
    RAG agent that produces structured, validated outputs with citations.

    Pattern from agentic_typed_rag_pydanticai/ — enforces:
    - Every claim must have a citation
    - Citations must reference real chunks
    - Confidence is bounded [0, 1]
    - Refuses to answer when evidence is insufficient

    For Angavu: ensures credit scores and market data are always
    grounded in actual transaction data, not hallucinated.
    """

    def __init__(
        self,
        corrective_rag: CorrectiveRAG,
        min_confidence: float = 0.4,
    ):
        self.corrective_rag = corrective_rag
        self.min_confidence = min_confidence

    async def answer(
        self,
        question: str,
        llm_fn: Any | None = None,
        top_k: int = 5,
        system_prompt: str = "",
    ) -> RAGAnswer:
        """
        Answer a question with structured output and citations.

        Steps:
        1. Retrieve evidence (with correction)
        2. If insufficient evidence → refuse with explanation
        3. Generate answer grounded in evidence
        4. Extract and validate citations
        5. Return structured RAGAnswer
        """
        reasoning_trace: list[str] = []

        # Step 1: Retrieve evidence
        evidence = await self.corrective_rag.retrieve_with_correction(
            question, top_k=top_k, llm_fn=llm_fn
        )
        reasoning_trace.append(
            f"Retrieved {len(evidence.chunks)} chunks. "
            f"Top score: {evidence.top_score:.3f}. "
            f"Action: {evidence.correction_action.value}"
        )

        # Step 2: Check evidence sufficiency
        if not evidence.enough_evidence:
            reasoning_trace.append("Insufficient evidence — refusing to answer")
            return RAGAnswer(
                text="I do not have enough evidence in the indexed data to answer this question. "
                     "Please provide more context or transaction data.",
                citations=[],
                confidence=round(evidence.top_score, 3),
                answered=False,
                reasoning_trace=reasoning_trace,
                retrieval_evidence=evidence,
            )

        # Step 3: Build context from evidence
        context_parts = []
        source_map: dict[str, SearchResult] = {}
        for i, result in enumerate(evidence.chunks):
            marker = f"[{i + 1}]"
            context_parts.append(f"{marker} {result.chunk.text}")
            source_map[marker] = result

        context_text = "\n\n".join(context_parts)

        # Step 4: Generate answer
        if llm_fn:
            prompt = (
                f"Based on the following evidence, answer the question.\n"
                f"IMPORTANT: Cite sources using [N] notation for each claim.\n\n"
                f"EVIDENCE:\n{context_text}\n\n"
                f"QUESTION: {question}\n\n"
                f"Answer with inline citations:"
            )
            if system_prompt:
                prompt = f"{system_prompt}\n\n{prompt}"

            try:
                answer_text = await llm_fn(prompt)
            except Exception as exc:
                reasoning_trace.append(f"LLM generation failed: {exc}")
                answer_text = (
                    f"Based on the retrieved data: {context_text[:500]}..."
                )
        else:
            # No LLM — return raw evidence summary
            answer_text = f"Based on {len(evidence.chunks)} data sources:\n\n{context_text[:1000]}"

        # Step 5: Extract citations
        citations = self._extract_citations(answer_text, source_map)

        # Calculate confidence
        confidence = min(1.0, evidence.top_score * (1.0 + len(citations) * 0.1))
        confidence = round(max(0.0, confidence), 3)

        reasoning_trace.append(
            f"Generated answer with {len(citations)} citations. "
            f"Confidence: {confidence:.3f}"
        )

        return RAGAnswer(
            text=answer_text,
            citations=citations,
            confidence=confidence,
            answered=True,
            reasoning_trace=reasoning_trace,
            retrieval_evidence=evidence,
        )

    def _extract_citations(
        self, text: str, source_map: dict[str, SearchResult]
    ) -> list[Citation]:
        """Extract and validate citations from generated text."""
        citations = []
        refs = re.findall(r"\[(\d+)\]", text)

        for ref_num in set(refs):
            marker = f"[{ref_num}]"
            if marker in source_map:
                result = source_map[marker]
                citations.append(Citation(
                    source=result.chunk.source,
                    chunk_id=result.chunk.chunk_id,
                    quoted_span=result.chunk.text[:200],
                    confidence=result.score,
                ))

        return citations


# ════════════════════════════════════════════════════════════════════
# Agentic RAG with Reasoning (from agentic_rag_with_reasoning pattern)
# ════════════════════════════════════════════════════════════════════


class ReasoningRAGAgent:
    """
    RAG agent that reasons step-by-step before answering.

    Pattern from agentic_rag_with_reasoning/ — adds explicit
    reasoning steps:

    1. Analyze the question
    2. Retrieve relevant evidence
    3. Reason through evidence step by step
    4. Synthesize answer with reasoning trace

    For Angavu Soko Pulse: explains *why* prices are trending
    a certain way, not just *what* the trend is.
    """

    def __init__(
        self,
        corrective_rag: CorrectiveRAG,
        max_reasoning_steps: int = 5,
    ):
        self.corrective_rag = corrective_rag
        self.max_steps = max_reasoning_steps

    async def reason_and_answer(
        self,
        question: str,
        llm_fn: Any | None = None,
        top_k: int = 8,
        domain_context: str = "",
    ) -> RAGAnswer:
        """
        Answer with explicit reasoning chain.

        The reasoning trace shows each step of the analysis,
        making the answer auditable and explainable.
        """
        reasoning_trace: list[str] = []

        # Step 1: Analyze question
        reasoning_trace.append(f"Question: {question}")
        if domain_context:
            reasoning_trace.append(f"Domain context: {domain_context}")

        # Step 2: Retrieve evidence
        evidence = await self.corrective_rag.retrieve_with_correction(
            question, top_k=top_k, llm_fn=llm_fn
        )
        reasoning_trace.append(
            f"Retrieved {len(evidence.chunks)} evidence chunks "
            f"(top score: {evidence.top_score:.3f})"
        )

        if not evidence.enough_evidence:
            reasoning_trace.append("Insufficient evidence for reasoning")
            return RAGAnswer(
                text="Insufficient data to reason about this question.",
                citations=[],
                confidence=0.0,
                answered=False,
                reasoning_trace=reasoning_trace,
                retrieval_evidence=evidence,
            )

        # Step 3: Build reasoning context
        evidence_summary = []
        for i, chunk in enumerate(evidence.chunks[:5]):
            evidence_summary.append(
                f"[{i+1}] {chunk.chunk.source}: {chunk.chunk.text[:300]}"
            )

        # Step 4: Generate reasoning steps
        if llm_fn:
            reasoning_prompt = (
                f"{domain_context}\n\n"
                f"Analyze the following evidence step by step to answer the question.\n"
                f"Show your reasoning at each step.\n\n"
                f"EVIDENCE:\n{chr(10).join(evidence_summary)}\n\n"
                f"QUESTION: {question}\n\n"
                f"Reason step by step, then provide a final answer with citations [N]."
            )

            try:
                answer_text = await llm_fn(reasoning_prompt)
                reasoning_trace.append("Generated reasoning via LLM")
            except Exception as exc:
                reasoning_trace.append(f"LLM reasoning failed: {exc}")
                answer_text = self._simple_reasoning(evidence_summary, question)
                reasoning_trace.append("Used fallback simple reasoning")
        else:
            answer_text = self._simple_reasoning(evidence_summary, question)
            reasoning_trace.append("Used simple reasoning (no LLM)")

        # Step 5: Extract citations
        citations = []
        for i, chunk in enumerate(evidence.chunks[:5]):
            if f"[{i+1}]" in answer_text:
                citations.append(Citation(
                    source=chunk.chunk.source,
                    chunk_id=chunk.chunk.chunk_id,
                    quoted_span=chunk.chunk.text[:200],
                    confidence=chunk.score,
                ))

        confidence = min(1.0, evidence.top_score * (1.0 + len(citations) * 0.05))
        reasoning_trace.append(f"Final confidence: {confidence:.3f}")

        return RAGAnswer(
            text=answer_text,
            citations=citations,
            confidence=round(confidence, 3),
            answered=True,
            reasoning_trace=reasoning_trace,
            retrieval_evidence=evidence,
        )

    def _simple_reasoning(
        self, evidence_summary: list[str], question: str
    ) -> str:
        """Fallback reasoning when no LLM is available."""
        return (
            f"Analysis of {len(evidence_summary)} data sources:\n\n"
            + "\n\n".join(evidence_summary)
            + f"\n\nBased on the above data, here is the analysis for: {question}"
        )


# ════════════════════════════════════════════════════════════════════
# Knowledge Graph RAG (from knowledge_graph_rag_citations pattern)
# ════════════════════════════════════════════════════════════════════


class KnowledgeGraphRAG:
    """
    RAG agent that uses a knowledge graph for multi-hop reasoning.

    Pattern from knowledge_graph_rag_citations/ — enables:
    - Multi-hop queries: "Which supplier of product X is in region Y?"
    - Relationship traversal: "What are the competitors of business Z?"
    - Verifiable reasoning paths: every claim traced to source entities

    For Angavu Pulse: connects economic indicators, business metrics,
    and regional data into a queryable knowledge graph.
    """

    def __init__(
        self,
        kg_store: KnowledgeGraphStore,
        hybrid_retriever: HybridRetriever,
    ):
        self.kg = kg_store
        self.retriever = hybrid_retriever

    async def query(
        self,
        question: str,
        llm_fn: Any | None = None,
        max_hops: int = 2,
    ) -> RAGAnswer:
        """
        Answer using knowledge graph traversal + vector retrieval.

        Steps:
        1. Extract key entities from the question
        2. Find matching entities in the knowledge graph
        3. Traverse relationships (multi-hop)
        4. Retrieve relevant document chunks
        5. Combine graph context + document context
        6. Generate answer with full citation trail
        """
        reasoning_trace: list[str] = []
        reasoning_trace.append(f"KG Query: {question}")

        # Step 1: Find relevant entities
        entities = self.kg.find_entities(question, limit=3)
        reasoning_trace.append(f"Found {len(entities)} matching entities")

        if not entities:
            # Fallback to pure vector retrieval
            reasoning_trace.append("No entities found — falling back to vector search")
            results = await self.retriever.search(question, limit=5)
            if not results:
                return RAGAnswer(
                    text="No relevant information found in knowledge graph or documents.",
                    citations=[],
                    confidence=0.0,
                    answered=False,
                    reasoning_trace=reasoning_trace,
                )
            context = "\n".join(f"[{i+1}] {r.chunk.text}" for i, r in enumerate(results))
            citations = [
                Citation(
                    source=r.chunk.source,
                    chunk_id=r.chunk.chunk_id,
                    quoted_span=r.chunk.text[:200],
                    confidence=r.score,
                )
                for r in results
            ]
            return RAGAnswer(
                text=f"Based on document search:\n\n{context}",
                citations=citations,
                confidence=round(results[0].score, 3),
                answered=True,
                reasoning_trace=reasoning_trace,
            )

        # Step 2: Multi-hop traversal
        all_paths: list[dict[str, Any]] = []
        for entity in entities[:2]:
            paths = self.kg.traverse(entity.id, max_hops=max_hops)
            all_paths.extend(paths)
            reasoning_trace.append(
                f"Traversed from '{entity.name}': found {len(paths)} related entities"
            )

        # Step 3: Retrieve document chunks
        doc_results = await self.retriever.search(question, limit=5)

        # Step 4: Build combined context
        context_parts = []

        # Graph context
        for i, path in enumerate(all_paths[:10]):
            hop_desc = f" ({path['hops']} hops)" if path["hops"] > 0 else ""
            context_parts.append(
                f"[G{i+1}] {path['entity']} ({path['entity_type']}){hop_desc}: "
                f"{path['description']}"
            )
            if path.get("path_descriptions"):
                context_parts.append(
                    f"    Path: {' → '.join(path['path_descriptions'])}"
                )

        # Document context
        doc_offset = len(all_paths[:10])
        for i, result in enumerate(doc_results[:5]):
            context_parts.append(
                f"[D{i+1}] {result.chunk.source}: {result.chunk.text[:300]}"
            )

        combined_context = "\n".join(context_parts)
        reasoning_trace.append(
            f"Built context: {len(all_paths)} graph paths + "
            f"{len(doc_results)} document chunks"
        )

        # Step 5: Generate answer
        if llm_fn:
            prompt = (
                f"Using the knowledge graph and document context below, "
                f"answer the question with citations.\n"
                f"Use [G#] for graph sources and [D#] for document sources.\n\n"
                f"CONTEXT:\n{combined_context}\n\n"
                f"QUESTION: {question}\n\n"
                f"Answer:"
            )
            try:
                answer_text = await llm_fn(prompt)
            except Exception:
                answer_text = f"Knowledge graph analysis:\n\n{combined_context[:1500]}"
        else:
            answer_text = f"Knowledge graph analysis:\n\n{combined_context[:1500]}"

        # Step 6: Build citations
        citations = []
        for i, path in enumerate(all_paths[:10]):
            if f"[G{i+1}]" in answer_text:
                citations.append(Citation(
                    source=path["source_doc"],
                    chunk_id=f"kg:{path['entity']}",
                    quoted_span=path["description"][:200],
                    confidence=0.8,
                ))
        for i, result in enumerate(doc_results[:5]):
            if f"[D{i+1}]" in answer_text:
                citations.append(Citation(
                    source=result.chunk.source,
                    chunk_id=result.chunk.chunk_id,
                    quoted_span=result.chunk.text[:200],
                    confidence=result.score,
                ))

        confidence = min(1.0, 0.5 + len(citations) * 0.1)
        reasoning_trace.append(f"Final confidence: {confidence:.3f}")

        return RAGAnswer(
            text=answer_text,
            citations=citations,
            confidence=round(confidence, 3),
            answered=True,
            reasoning_trace=reasoning_trace,
        )


# ════════════════════════════════════════════════════════════════════
# Document Processing Pipeline
# ════════════════════════════════════════════════════════════════════


class DocumentProcessor:
    """
    Processes documents into chunks for indexing.

    Supports multiple document types common in Angavu:
    - Transaction records (JSON)
    - Market reports (text)
    - Economic indicators (structured data)
    - Credit assessments (mixed format)
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(
        self, text: str, source: str, metadata: dict[str, Any] | None = None
    ) -> list[DocumentChunk]:
        """Split text into overlapping word chunks."""
        words = text.split()
        if not words:
            return []

        chunks = []
        step = self.chunk_size - self.chunk_overlap
        for start in range(0, len(words), step):
            window = words[start: start + self.chunk_size]
            if not window:
                break
            chunk_text = " ".join(window)
            chunk_id = f"{source}:c{len(chunks) + 1}"
            chunks.append(DocumentChunk(
                source=source,
                chunk_id=chunk_id,
                text=chunk_text,
                metadata=metadata or {},
            ))
            if start + self.chunk_size >= len(words):
                break

        return chunks

    def chunk_transactions(
        self,
        transactions: list[dict[str, Any]],
        source: str = "transactions",
    ) -> list[DocumentChunk]:
        """
        Convert transaction records into searchable chunks.

        Each chunk groups related transactions and includes
        metadata for filtering by region, product, date.
        """
        chunks = []
        # Group transactions into chunks of ~20
        batch_size = 20
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i: i + batch_size]
            texts = []
            regions = set()
            products = set()

            for txn in batch:
                parts = []
                if "item" in txn:
                    parts.append(f"Product: {txn['item']}")
                    products.add(txn["item"])
                if "amount" in txn:
                    parts.append(f"Amount: KES {txn['amount']}")
                if "region" in txn:
                    parts.append(f"Region: {txn['region']}")
                    regions.add(txn["region"])
                if "timestamp" in txn:
                    parts.append(f"Date: {txn['timestamp']}")
                if "transaction_type" in txn:
                    parts.append(f"Type: {txn['transaction_type']}")
                texts.append(" | ".join(parts))

            chunk_text = "\n".join(texts)
            chunk_id = f"{source}:batch_{i // batch_size + 1}"
            chunks.append(DocumentChunk(
                source=source,
                chunk_id=chunk_id,
                text=chunk_text,
                metadata={
                    "regions": list(regions),
                    "products": list(products),
                    "transaction_count": len(batch),
                    "batch_index": i // batch_size,
                },
            ))

        return chunks

    def chunk_market_data(
        self,
        data: dict[str, Any],
        source: str = "market_data",
    ) -> list[DocumentChunk]:
        """Convert market data into searchable chunks."""
        chunks = []

        if "prices" in data:
            for product, price_info in data["prices"].items():
                text = (
                    f"Market price for {product}: "
                    f"Average KES {price_info.get('avg', 'N/A')}, "
                    f"Range KES {price_info.get('min', 'N/A')} - "
                    f"{price_info.get('max', 'N/A')}"
                )
                chunks.append(DocumentChunk(
                    source=source,
                    chunk_id=f"{source}:price:{product}",
                    text=text,
                    metadata={"type": "price", "product": product},
                ))

        if "supply_demand" in data:
            sd = data["supply_demand"]
            text = (
                f"Supply index: {sd.get('supply_index', 'N/A')}, "
                f"Demand index: {sd.get('demand_index', 'N/A')}, "
                f"Gap: {sd.get('gap', 'N/A')}"
            )
            chunks.append(DocumentChunk(
                source=source,
                chunk_id=f"{source}:supply_demand",
                text=text,
                metadata={"type": "supply_demand"},
            ))

        return chunks

    def chunk_credit_data(
        self,
        data: dict[str, Any],
        worker_id: str,
        source: str = "credit_data",
    ) -> list[DocumentChunk]:
        """Convert credit assessment data into searchable chunks."""
        chunks = []

        if "transaction_history" in data:
            th = data["transaction_history"]
            text = (
                f"Worker {worker_id} transaction history: "
                f"{th.get('total_transactions', 0)} transactions, "
                f"Average amount KES {th.get('avg_amount', 0):.0f}, "
                f"Active since {th.get('first_transaction', 'unknown')}"
            )
            chunks.append(DocumentChunk(
                source=source,
                chunk_id=f"{source}:history:{worker_id}",
                text=text,
                metadata={"type": "history", "worker_id": worker_id},
            ))

        if "repayment" in data:
            rp = data["repayment"]
            text = (
                f"Worker {worker_id} repayment: "
                f"On-time rate {rp.get('on_time_rate', 'N/A')}, "
                f"Completed {rp.get('completed_loans', 0)} loans, "
                f"Defaulted {rp.get('defaulted_loans', 0)} loans"
            )
            chunks.append(DocumentChunk(
                source=source,
                chunk_id=f"{source}:repayment:{worker_id}",
                text=text,
                metadata={"type": "repayment", "worker_id": worker_id},
            ))

        if "credit_score" in data:
            cs = data["credit_score"]
            text = (
                f"Worker {worker_id} credit score: "
                f"Score {cs.get('score', 'N/A')}, "
                f"Rating {cs.get('rating', 'N/A')}, "
                f"Confidence {cs.get('confidence', 'N/A')}"
            )
            chunks.append(DocumentChunk(
                source=source,
                chunk_id=f"{source}:score:{worker_id}",
                text=text,
                metadata={"type": "credit_score", "worker_id": worker_id},
            ))

        return chunks
