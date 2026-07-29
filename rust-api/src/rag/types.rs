// RAG Module — Type Definitions

use serde::{Deserialize, Serialize};

/// RAG query request to the Python RAG service
#[derive(Debug, Clone, Serialize)]
pub struct RagQueryRequest {
    pub question: String,
    pub collection: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub top_k: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rerank_top_k: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata_filter: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_prompt: Option<String>,
}

/// Credit-specific RAG query request
#[derive(Debug, Clone, Serialize)]
pub struct CreditRagRequest {
    pub question: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub worker_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub region: Option<String>,
}

/// Market-specific RAG query request
#[derive(Debug, Clone, Serialize)]
pub struct MarketRagRequest {
    pub question: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub category: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub region: Option<String>,
}

/// Health-specific RAG query request
#[derive(Debug, Clone, Serialize)]
pub struct HealthRagRequest {
    pub question: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub worker_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub region: Option<String>,
}

/// RAG query response from the Python RAG service
#[derive(Debug, Clone, Deserialize)]
pub struct RagResponse {
    pub answer: String,
    pub sources: Vec<RagSource>,
    pub query: String,
    pub pipeline: String,
    pub latency_ms: f64,
    #[serde(default)]
    pub metadata: serde_json::Value,
}

/// A retrieved source document
#[derive(Debug, Clone, Deserialize)]
pub struct RagSource {
    pub id: String,
    pub content: String,
    pub score: f64,
    #[serde(default)]
    pub metadata: serde_json::Value,
}

/// Ingest text request
#[derive(Debug, Clone, Serialize)]
pub struct IngestTextRequest {
    pub collection: String,
    pub text: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<serde_json::Value>,
    #[serde(default)]
    pub source: String,
}

/// Ingest market data request
#[derive(Debug, Clone, Serialize)]
pub struct IngestMarketRequest {
    pub region: String,
    pub category: String,
    pub data_points: Vec<serde_json::Value>,
}

/// Ingest credit context request
#[derive(Debug, Clone, Serialize)]
pub struct IngestCreditRequest {
    pub worker_type: String,
    pub region: String,
    pub context_records: Vec<serde_json::Value>,
}

/// Ingestion response
#[derive(Debug, Clone, Deserialize)]
pub struct IngestResponse {
    pub collection: String,
    #[serde(default)]
    pub chunks_ingested: Option<u32>,
    #[serde(default)]
    pub records_ingested: Option<u32>,
    #[serde(default)]
    pub document_ids: Vec<i64>,
}

/// Collection statistics
#[derive(Debug, Clone, Deserialize)]
pub struct CollectionStats {
    pub collection: String,
    pub document_count: i64,
    pub table_size: String,
}

/// RAG health response
#[derive(Debug, Clone, Deserialize)]
pub struct RagHealthResponse {
    pub status: String,
    pub service: String,
    pub version: String,
    pub collections: Vec<String>,
}

/// Evaluation metrics for a single query
#[derive(Debug, Clone, Deserialize)]
pub struct EvalMetrics {
    pub query: String,
    pub answer: String,
    pub retrieval_precision: f64,
    pub retrieval_recall: f64,
    pub mrr: f64,
    pub faithfulness: f64,
    pub relevance: f64,
    pub citation_count: u32,
    pub citation_accuracy: f64,
    pub latency_ms: f64,
}

/// Evaluation report
#[derive(Debug, Clone, Deserialize)]
pub struct EvalReport {
    pub total_queries: u32,
    pub avg_precision: f64,
    pub avg_recall: f64,
    pub avg_mrr: f64,
    pub avg_faithfulness: f64,
    pub avg_relevance: f64,
    pub avg_citation_accuracy: f64,
    pub avg_latency_ms: f64,
    pub timestamp: String,
}

/// RAG error types
#[derive(Debug, thiserror::Error)]
pub enum RagError {
    #[error("RAG service unavailable: {0}")]
    ServiceUnavailable(String),
    #[error("RAG query failed: {0}")]
    QueryFailed(String),
    #[error("RAG ingestion failed: {0}")]
    IngestionFailed(String),
    #[error("HTTP error: {0}")]
    HttpError(String),
    #[error("Serialization error: {0}")]
    SerializationError(String),
}
