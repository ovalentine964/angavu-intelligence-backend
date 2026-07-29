"""
RAG Service — FastAPI Server

Exposes the RAG pipeline as HTTP API for the Rust backend to call.
Provides endpoints for querying, ingestion, and evaluation.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import RAGConfig
from .embeddings import EmbeddingService
from .vector_store import PgVectorStore
from .reranker import RerankerService
from .pipeline import RAGPipeline
from .ingestion import IngestionPipeline
from .evaluation import RAGEvaluator

logger = logging.getLogger(__name__)

# Global instances
config: Optional[RAGConfig] = None
embedding_service: Optional[EmbeddingService] = None
vector_store: Optional[PgVectorStore] = None
reranker_service: Optional[RerankerService] = None
rag_pipeline: Optional[RAGPipeline] = None
ingestion_pipeline: Optional[IngestionPipeline] = None
evaluator: Optional[RAGEvaluator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up RAG services."""
    global config, embedding_service, vector_store, reranker_service
    global rag_pipeline, ingestion_pipeline, evaluator

    config = RAGConfig.from_env()

    # Initialize services
    embedding_service = EmbeddingService(config)
    await embedding_service.initialize()

    vector_store = PgVectorStore(config)
    await vector_store.initialize()

    reranker_service = RerankerService(config)
    await reranker_service.initialize()

    rag_pipeline = RAGPipeline(config, embedding_service, vector_store, reranker_service)
    await rag_pipeline.initialize()

    ingestion_pipeline = IngestionPipeline(config, embedding_service, vector_store)

    evaluator = RAGEvaluator(config, rag_pipeline)
    await evaluator.initialize()

    logger.info("RAG service initialized on %s:%d", config.host, config.port)
    yield

    # Cleanup
    await embedding_service.shutdown()
    await vector_store.shutdown()
    await reranker_service.shutdown()
    await rag_pipeline.shutdown()
    await evaluator.shutdown()
    logger.info("RAG service shut down")


app = FastAPI(
    title="Angavu RAG Service",
    description="Retrieval-Augmented Generation for Angavu Intelligence",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Request/Response Models ──────────────────────────────────────────────────


class QueryRequest(BaseModel):
    question: str
    collection: str = "general"
    top_k: int = 10
    rerank_top_k: int = 5
    metadata_filter: Optional[dict] = None
    system_prompt: Optional[str] = None


class CreditQueryRequest(BaseModel):
    question: str
    worker_type: Optional[str] = None
    region: Optional[str] = None


class MarketQueryRequest(BaseModel):
    question: str
    category: Optional[str] = None
    region: Optional[str] = None


class HealthQueryRequest(BaseModel):
    question: str
    worker_type: Optional[str] = None
    region: Optional[str] = None


class IngestTextRequest(BaseModel):
    collection: str
    text: str
    metadata: Optional[dict] = None
    source: str = ""


class IngestMarketRequest(BaseModel):
    region: str
    category: str
    data_points: list[dict]


class IngestCreditRequest(BaseModel):
    worker_type: str
    region: str
    context_records: list[dict]


class EvalRequest(BaseModel):
    test_cases: list[dict]
    collection: str = "general"


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check endpoint."""
    collections = await vector_store.list_collections() if vector_store else []
    return {
        "status": "healthy",
        "service": "angavu-rag",
        "version": "0.1.0",
        "collections": collections,
    }


# ── RAG Query Endpoints ─────────────────────────────────────────────────────


@app.post("/v1/rag/query")
async def rag_query(request: QueryRequest):
    """Generic RAG query."""
    if not rag_pipeline:
        raise HTTPException(503, "RAG service not initialized")

    response = await rag_pipeline.query(
        question=request.question,
        collection=request.collection,
        top_k=request.top_k,
        rerank_top_k=request.rerank_top_k,
        metadata_filter=request.metadata_filter,
        system_prompt=request.system_prompt,
    )
    return response.to_dict()


@app.post("/v1/rag/credit")
async def rag_credit(request: CreditQueryRequest):
    """RAG query for credit scoring context."""
    if not rag_pipeline:
        raise HTTPException(503, "RAG service not initialized")

    response = await rag_pipeline.query_credit(
        question=request.question,
        worker_type=request.worker_type,
        region=request.region,
    )
    return response.to_dict()


@app.post("/v1/rag/market")
async def rag_market(request: MarketQueryRequest):
    """RAG query for market intelligence."""
    if not rag_pipeline:
        raise HTTPException(503, "RAG service not initialized")

    response = await rag_pipeline.query_market(
        question=request.question,
        category=request.category,
        region=request.region,
    )
    return response.to_dict()


@app.post("/v1/rag/health")
async def rag_health(request: HealthQueryRequest):
    """RAG query for health/insurance recommendations."""
    if not rag_pipeline:
        raise HTTPException(503, "RAG service not initialized")

    response = await rag_pipeline.query_health(
        question=request.question,
        worker_type=request.worker_type,
        region=request.region,
    )
    return response.to_dict()


# ── Ingestion Endpoints ─────────────────────────────────────────────────────


@app.post("/v1/rag/ingest/text")
async def ingest_text(request: IngestTextRequest):
    """Ingest a text document."""
    if not ingestion_pipeline:
        raise HTTPException(503, "RAG service not initialized")

    result = await ingestion_pipeline.ingest_text(
        collection=request.collection,
        text=request.text,
        metadata=request.metadata,
        source=request.source,
    )
    return result


@app.post("/v1/rag/ingest/market")
async def ingest_market(request: IngestMarketRequest):
    """Ingest market intelligence data."""
    if not ingestion_pipeline:
        raise HTTPException(503, "RAG service not initialized")

    result = await ingestion_pipeline.ingest_market_data(
        region=request.region,
        category=request.category,
        data_points=request.data_points,
    )
    return result


@app.post("/v1/rag/ingest/credit")
async def ingest_credit(request: IngestCreditRequest):
    """Ingest credit scoring context data."""
    if not ingestion_pipeline:
        raise HTTPException(503, "RAG service not initialized")

    result = await ingestion_pipeline.ingest_credit_context(
        worker_type=request.worker_type,
        region=request.region,
        context_records=request.context_records,
    )
    return result


# ── Collection Management ────────────────────────────────────────────────────


@app.get("/v1/rag/collections")
async def list_collections():
    """List all RAG collections."""
    if not vector_store:
        raise HTTPException(503, "RAG service not initialized")

    collections = await vector_store.list_collections()
    stats = []
    for col in collections:
        stat = await vector_store.collection_stats(col)
        stats.append(stat)
    return {"collections": stats}


@app.delete("/v1/rag/collections/{collection}")
async def delete_collection(collection: str):
    """Delete a RAG collection."""
    if not vector_store:
        raise HTTPException(503, "RAG service not initialized")

    count = await vector_store.delete_collection(collection)
    return {"collection": collection, "documents_deleted": count}


# ── Evaluation Endpoints ────────────────────────────────────────────────────


@app.post("/v1/rag/evaluate")
async def evaluate(request: EvalRequest):
    """Evaluate RAG pipeline quality."""
    if not evaluator:
        raise HTTPException(503, "RAG service not initialized")

    report = await evaluator.evaluate_batch(
        test_cases=request.test_cases,
        collection=request.collection,
    )
    return report.to_dict()


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    cfg = RAGConfig.from_env()
    uvicorn.run(
        "rag.server:app",
        host=cfg.host,
        port=cfg.port,
        log_level="info",
    )
