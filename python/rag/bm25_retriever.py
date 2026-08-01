"""
BM25 Retriever — Okapi BM25 for keyword-weighted retrieval.

Implements BM25 scoring for Swahili and English business text.
Combined with vector search via Reciprocal Rank Fusion (RRF)
for hybrid retrieval.
"""

import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BM25Document:
    """A document in the BM25 index."""
    id: str
    content: str
    metadata: dict
    token_count: int
    term_frequencies: Counter


class BM25Retriever:
    """
    Okapi BM25 retriever for keyword-weighted search.
    
    Parameters:
        k1: Term frequency saturation (1.2 typical, 1.5-2.0 for short docs)
        b: Document length normalization (0.75 typical)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._documents: dict[str, BM25Document] = {}
        self._idf: dict[str, float] = {}
        self._avg_doc_length: float = 0.0
        self._doc_count: int = 0
        self._term_doc_freq: Counter = Counter()

    def index_document(self, doc_id: str, content: str, metadata: dict = None):
        """Index a single document."""
        tokens = self._tokenize(content)
        term_freq = Counter(tokens)

        self._documents[doc_id] = BM25Document(
            id=doc_id,
            content=content,
            metadata=metadata or {},
            token_count=len(tokens),
            term_frequencies=term_freq
        )

        # Update document frequency counts
        for term in set(tokens):
            self._term_doc_freq[term] += 1

        self._doc_count = len(self._documents)
        self._avg_doc_length = sum(
            d.token_count for d in self._documents.values()
        ) / max(self._doc_count, 1)
        self._idf = {}  # Invalidate IDF cache

    def index_batch(self, documents: list[dict]):
        """Index multiple documents. Each dict should have: id, content, metadata (optional)."""
        for doc in documents:
            self.index_document(
                doc_id=doc["id"],
                content=doc["content"],
                metadata=doc.get("metadata")
            )
        logger.info(f"Indexed {len(documents)} documents (total: {self._doc_count})")

    def search(self, query: str, top_k: int = 10, metadata_filter: dict = None) -> list[dict]:
        """
        Search for documents matching the query using BM25 scoring.
        
        Returns list of {id, content, metadata, score} dicts.
        """
        if not self._documents:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Compute IDF if needed
        if not self._idf:
            self._compute_idf()

        # Score all documents
        scores = []
        for doc_id, doc in self._documents.items():
            # Apply metadata filter
            if metadata_filter and not self._matches_filter(doc.metadata, metadata_filter):
                continue

            score = self._score_document(query_tokens, doc)
            scores.append({
                "id": doc_id,
                "content": doc.content,
                "metadata": doc.metadata,
                "score": score
            })

        # Sort by score descending
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]

    def _score_document(self, query_tokens: list[str], doc: BM25Document) -> float:
        """Compute BM25 score for a document given query tokens."""
        score = 0.0
        doc_len = doc.token_count

        for term in query_tokens:
            if term not in doc.term_frequencies:
                continue

            tf = doc.term_frequencies[term]
            idf = self._idf.get(term, 0.0)

            # BM25 formula
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (
                1 - self.b + self.b * (doc_len / max(self._avg_doc_length, 1))
            )
            score += idf * (numerator / denominator)

        return score

    def _compute_idf(self):
        """Compute IDF scores for all terms."""
        n = self._doc_count
        self._idf = {}
        for term, df in self._term_doc_freq.items():
            # IDF with floor at 0 (ignore terms appearing in all docs)
            idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
            self._idf[term] = max(idf, 0.0)

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text for BM25 indexing/search.
        
        Handles:
        - Lowercase normalization
        - Swahili diacritics (preserve ng', ny, etc.)
        - Punctuation removal
        - Stop word filtering (minimal, language-agnostic)
        """
        text = text.lower()
        # Keep alphanumeric, spaces, and apostrophes (for Swahili ng')
        text = re.sub(r"[^a-z0-9\s']", " ", text)
        tokens = text.split()

        # Minimal stop words (language-agnostic)
        stop_words = {
            "na", "ya", "za", "wa", "la", "kwa", "ni", "si", "the", "a", "an",
            "is", "are", "was", "were", "in", "on", "at", "to", "for", "of"
        }

        return [t for t in tokens if len(t) > 1 and t not in stop_words]

    def _matches_filter(self, metadata: dict, filter_dict: dict) -> bool:
        """Check if document metadata matches the filter criteria."""
        for key, value in filter_dict.items():
            if key not in metadata:
                return False
            if str(metadata[key]) != str(value):
                return False
        return True

    def get_stats(self) -> dict:
        """Get index statistics."""
        return {
            "document_count": self._doc_count,
            "vocabulary_size": len(self._term_doc_freq),
            "avg_doc_length": round(self._avg_doc_length, 1),
            "unique_terms": len(self._idf) if self._idf else 0
        }


class HybridRetriever:
    """
    Combines BM25 and vector search using Reciprocal Rank Fusion (RRF).
    
    RRF score = sum(1 / (k + rank_i)) for each retrieval method.
    k=60 is the standard constant from the original RRF paper.
    """

    def __init__(self, bm25_retriever: BM25Retriever, vector_search_fn, k: int = 60):
        self.bm25 = bm25_retriever
        self.vector_search = vector_search_fn
        self.k = k

    async def search(
        self,
        query: str,
        collection: str,
        top_k: int = 10,
        metadata_filter: dict = None,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5
    ) -> list[dict]:
        """
        Hybrid search combining BM25 and vector retrieval.
        
        Args:
            query: Search query text
            collection: Vector store collection name
            top_k: Number of results to return
            metadata_filter: Optional metadata filter
            bm25_weight: Weight for BM25 scores (0-1)
            vector_weight: Weight for vector scores (0-1)
        """
        # Get BM25 results
        bm25_results = self.bm25.search(
            query=query,
            top_k=top_k * 2,
            metadata_filter=metadata_filter
        )

        # Get vector results
        vector_results = await self.vector_search(
            query=query,
            collection=collection,
            top_k=top_k * 2,
            metadata_filter=metadata_filter
        )

        # Compute RRF scores
        rrf_scores = defaultdict(float)

        # BM25 ranks
        for rank, result in enumerate(bm25_results):
            doc_id = result["id"]
            rrf_scores[doc_id] += bm25_weight / (self.k + rank + 1)

        # Vector ranks
        for rank, result in enumerate(vector_results):
            doc_id = result["id"]
            rrf_scores[doc_id] += vector_weight / (self.k + rank + 1)

        # Merge results
        all_results = {}
        for result in bm25_results + vector_results:
            if result["id"] not in all_results:
                all_results[result["id"]] = result

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        merged = []
        for doc_id in sorted_ids[:top_k]:
            result = all_results.get(doc_id, {"id": doc_id})
            result["rrf_score"] = rrf_scores[doc_id]
            merged.append(result)

        return merged
