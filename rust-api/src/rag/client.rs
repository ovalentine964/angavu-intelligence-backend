// =============================================================================
// RAG Client — HTTP client for the Python RAG service
//
// Provides async methods for all RAG operations:
// - Query (generic, credit, market, health)
// - Ingestion (text, market data, credit context)
// - Collection management
// - Evaluation
// =============================================================================

use reqwest::Client;
use std::time::Duration;
use tracing::{debug, error, info, warn};

use super::types::*;

/// HTTP client for the Python RAG service.
///
/// The RAG service runs as a separate FastAPI process and exposes
/// the full RAG pipeline (embed → retrieve → rerank → generate) via HTTP.
///
/// # Example
/// ```no_run
/// use angavu_intelligence_backend::rag::RagClient;
///
/// let client = RagClient::new("http://localhost:8090");
/// let response = client.query_credit(
///     "What is the credit risk for mama mbogas in Nairobi?",
///     Some("mama_mboga"),
///     Some("nairobi"),
/// ).await?;
/// ```
#[derive(Clone)]
pub struct RagClient {
    base_url: String,
    http: Client,
}

impl RagClient {
    /// Create a new RAG client pointing to the given service URL.
    pub fn new(base_url: &str) -> Self {
        let http = Client::builder()
            .timeout(Duration::from_secs(60))
            .build()
            .expect("Failed to build HTTP client");

        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            http,
        }
    }

    /// Create a RAG client with custom HTTP client.
    pub fn with_client(base_url: &str, http: Client) -> Self {
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            http,
        }
    }

    // ── Health ───────────────────────────────────────────────────────────

    /// Check RAG service health.
    pub async fn health(&self) -> Result<RagHealthResponse, RagError> {
        let url = format!("{}/health", self.base_url);
        let resp = self
            .http
            .get(&url)
            .send()
            .await
            .map_err(|e| RagError::ServiceUnavailable(e.to_string()))?;

        resp.json::<RagHealthResponse>()
            .await
            .map_err(|e| RagError::SerializationError(e.to_string()))
    }

    // ── Generic RAG Query ────────────────────────────────────────────────

    /// Execute a generic RAG query against any collection.
    pub async fn query(&self, request: &RagQueryRequest) -> Result<RagResponse, RagError> {
        let url = format!("{}/v1/rag/query", self.base_url);
        self.post_rag(url, request).await
    }

    // ── Domain-Specific RAG Queries ──────────────────────────────────────

    /// Query credit scoring context.
    ///
    /// Retrieves relevant credit history, risk factors, and scoring context
    /// for the given worker type and region.
    pub async fn query_credit(
        &self,
        question: &str,
        worker_type: Option<&str>,
        region: Option<&str>,
    ) -> Result<RagResponse, RagError> {
        let request = CreditRagRequest {
            question: question.to_string(),
            worker_type: worker_type.map(|s| s.to_string()),
            region: region.map(|s| s.to_string()),
        };

        let url = format!("{}/v1/rag/credit", self.base_url);
        self.post_rag(url, &request).await
    }

    /// Query market intelligence.
    ///
    /// Retrieves relevant market data, price trends, and demand signals
    /// for the given product category and region.
    pub async fn query_market(
        &self,
        question: &str,
        category: Option<&str>,
        region: Option<&str>,
    ) -> Result<RagResponse, RagError> {
        let request = MarketRagRequest {
            question: question.to_string(),
            category: category.map(|s| s.to_string()),
            region: region.map(|s| s.to_string()),
        };

        let url = format!("{}/v1/rag/market", self.base_url);
        self.post_rag(url, &request).await
    }

    /// Query health and insurance recommendations.
    ///
    /// Retrieves relevant health risk data, occupation hazards, and
    /// insurance options for the given worker type and region.
    pub async fn query_health(
        &self,
        question: &str,
        worker_type: Option<&str>,
        region: Option<&str>,
    ) -> Result<RagResponse, RagError> {
        let request = HealthRagRequest {
            question: question.to_string(),
            worker_type: worker_type.map(|s| s.to_string()),
            region: region.map(|s| s.to_string()),
        };

        let url = format!("{}/v1/rag/health", self.base_url);
        self.post_rag(url, &request).await
    }

    // ── Ingestion ────────────────────────────────────────────────────────

    /// Ingest a text document into a collection.
    pub async fn ingest_text(
        &self,
        collection: &str,
        text: &str,
        metadata: Option<serde_json::Value>,
        source: &str,
    ) -> Result<IngestResponse, RagError> {
        let request = IngestTextRequest {
            collection: collection.to_string(),
            text: text.to_string(),
            metadata,
            source: source.to_string(),
        };

        let url = format!("{}/v1/rag/ingest/text", self.base_url);
        self.post_rag(url, &request).await
    }

    /// Ingest market intelligence data.
    pub async fn ingest_market(
        &self,
        region: &str,
        category: &str,
        data_points: Vec<serde_json::Value>,
    ) -> Result<IngestResponse, RagError> {
        let request = IngestMarketRequest {
            region: region.to_string(),
            category: category.to_string(),
            data_points,
        };

        let url = format!("{}/v1/rag/ingest/market", self.base_url);
        self.post_rag(url, &request).await
    }

    /// Ingest credit scoring context data.
    pub async fn ingest_credit(
        &self,
        worker_type: &str,
        region: &str,
        context_records: Vec<serde_json::Value>,
    ) -> Result<IngestResponse, RagError> {
        let request = IngestCreditRequest {
            worker_type: worker_type.to_string(),
            region: region.to_string(),
            context_records,
        };

        let url = format!("{}/v1/rag/ingest/credit", self.base_url);
        self.post_rag(url, &request).await
    }

    // ── Collection Management ────────────────────────────────────────────

    /// List all RAG collections with statistics.
    pub async fn list_collections(&self) -> Result<Vec<CollectionStats>, RagError> {
        let url = format!("{}/v1/rag/collections", self.base_url);
        let resp = self
            .http
            .get(&url)
            .send()
            .await
            .map_err(|e| RagError::ServiceUnavailable(e.to_string()))?;

        let body: serde_json::Value = resp
            .json()
            .await
            .map_err(|e| RagError::SerializationError(e.to_string()))?;

        let collections = body["collections"]
            .as_array()
            .map(|arr| {
                serde_json::from_value(serde_json::Value::Array(arr.clone())).unwrap_or_default()
            })
            .unwrap_or_default();

        Ok(collections)
    }

    /// Delete a RAG collection.
    pub async fn delete_collection(&self, collection: &str) -> Result<u32, RagError> {
        let url = format!("{}/v1/rag/collections/{}", self.base_url, collection);
        let resp = self
            .http
            .delete(&url)
            .send()
            .await
            .map_err(|e| RagError::ServiceUnavailable(e.to_string()))?;

        let body: serde_json::Value = resp
            .json()
            .await
            .map_err(|e| RagError::SerializationError(e.to_string()))?;

        Ok(body["documents_deleted"].as_u64().unwrap_or(0) as u32)
    }

    // ── Evaluation ───────────────────────────────────────────────────────

    /// Run RAG evaluation on test cases.
    pub async fn evaluate(
        &self,
        test_cases: Vec<serde_json::Value>,
        collection: &str,
    ) -> Result<EvalReport, RagError> {
        let request = serde_json::json!({
            "test_cases": test_cases,
            "collection": collection,
        });

        let url = format!("{}/v1/rag/evaluate", self.base_url);
        self.post_rag(url, &request).await
    }

    // ── Internal ─────────────────────────────────────────────────────────

    /// Generic POST to a RAG endpoint.
    async fn post_rag<T: serde::Serialize + ?Sized, R: serde::de::DeserializeOwned>(
        &self,
        url: String,
        body: &T,
    ) -> Result<R, RagError> {
        debug!("RAG POST {}", url);

        let resp = self.http.post(&url).json(body).send().await.map_err(|e| {
            error!("RAG request failed: {}", e);
            RagError::ServiceUnavailable(e.to_string())
        })?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body_text = resp.text().await.unwrap_or_default();
            error!("RAG error {}: {}", status, body_text);
            return Err(RagError::QueryFailed(format!(
                "HTTP {}: {}",
                status, body_text
            )));
        }

        resp.json::<R>().await.map_err(|e| {
            error!("RAG response parse error: {}", e);
            RagError::SerializationError(e.to_string())
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rag_client_creation() {
        let client = RagClient::new("http://localhost:8090");
        assert_eq!(client.base_url, "http://localhost:8090");
    }

    #[test]
    fn test_rag_client_trailing_slash() {
        let client = RagClient::new("http://localhost:8090/");
        assert_eq!(client.base_url, "http://localhost:8090");
    }

    #[test]
    fn test_rag_query_request_serialization() {
        let req = RagQueryRequest {
            question: "test".to_string(),
            collection: "credit".to_string(),
            top_k: Some(10),
            rerank_top_k: Some(5),
            metadata_filter: None,
            system_prompt: None,
        };
        let json = serde_json::to_value(&req).unwrap();
        assert_eq!(json["question"], "test");
        assert_eq!(json["collection"], "credit");
        assert_eq!(json["top_k"], 10);
    }

    #[test]
    fn test_rag_response_deserialization() {
        let json = serde_json::json!({
            "answer": "test answer",
            "sources": [{"id": "1", "content": "test", "score": 0.9, "metadata": {}}],
            "query": "test query",
            "pipeline": "credit_scoring",
            "latency_ms": 150.0,
            "metadata": {}
        });
        let resp: RagResponse = serde_json::from_value(json).unwrap();
        assert_eq!(resp.answer, "test answer");
        assert_eq!(resp.sources.len(), 1);
        assert_eq!(resp.pipeline, "credit_scoring");
    }
}
