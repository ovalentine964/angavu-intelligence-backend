// =============================================================================
// RAG Credit Context — Enriches credit scoring with RAG-retrieved context
//
// Before computing the Alama score, this module queries the RAG system
// for relevant credit history, risk factors, and peer comparisons.
// The retrieved context is passed to the LLM for enhanced analysis.
// =============================================================================

use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use super::client::RagClient;
use super::types::RagResponse;

/// Credit context enrichment via RAG.
///
/// Provides historical context and peer comparisons for credit scoring.
pub struct CreditContextEnricher {
    rag_client: RagClient,
}

/// Enriched credit context for LLM analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrichedCreditContext {
    /// Original question/query
    pub query: String,
    /// RAG-retrieved context about similar workers
    pub historical_context: String,
    /// Peer comparison data
    pub peer_comparison: String,
    /// Risk factors from knowledge base
    pub risk_factors: Vec<String>,
    /// RAG sources used
    pub source_count: usize,
    /// RAG latency in milliseconds
    pub rag_latency_ms: f64,
}

impl CreditContextEnricher {
    pub fn new(rag_client: RagClient) -> Self {
        Self { rag_client }
    }

    /// Enrich credit scoring with RAG context.
    ///
    /// Queries the RAG system for:
    /// 1. Historical credit patterns for this worker type and region
    /// 2. Peer comparisons (similar workers' repayment behavior)
    /// 3. Known risk factors and seasonal patterns
    pub async fn enrich(
        &self,
        worker_type: &str,
        region: &str,
        cohort_hash: &str,
    ) -> Result<EnrichedCreditContext, String> {
        // Query 1: Historical credit patterns
        let history_query = format!(
            "What are the typical credit patterns and repayment behavior for {} workers in {}? \
             Include default rates, seasonal variations, and common risk factors.",
            worker_type, region
        );

        let history_response = self
            .rag_client
            .query_credit(&history_query, Some(worker_type), Some(region))
            .await
            .map_err(|e| {
                warn!("RAG credit history query failed: {}", e);
                e.to_string()
            })?;

        // Query 2: Peer comparison
        let peer_query = format!(
            "How do {} workers in {} compare to similar workers in terms of \
             revenue stability, transaction consistency, and payment diversity?",
            worker_type, region
        );

        let peer_response = self
            .rag_client
            .query_credit(&peer_query, Some(worker_type), Some(region))
            .await
            .map_err(|e| {
                warn!("RAG peer comparison query failed: {}", e);
                e.to_string()
            })?;

        // Extract risk factors from sources
        let risk_factors = self.extract_risk_factors(&history_response, &peer_response);

        let total_latency = history_response.latency_ms + peer_response.latency_ms;
        let source_count = history_response.sources.len() + peer_response.sources.len();

        info!(
            worker_type = %worker_type,
            region = %region,
            sources = source_count,
            latency_ms = total_latency,
            "Credit context enrichment complete"
        );

        Ok(EnrichedCreditContext {
            query: format!("Credit context for {} in {}", worker_type, region),
            historical_context: history_response.answer,
            peer_comparison: peer_response.answer,
            risk_factors,
            source_count,
            rag_latency_ms: total_latency,
        })
    }

    /// Generate a system prompt for credit scoring that includes RAG context.
    pub fn build_scoring_prompt(&self, context: &EnrichedCreditContext) -> String {
        format!(
            "You are Angavu Credit Intelligence, analyzing creditworthiness for \
             informal economy workers in Kenya.\n\n\
             ## Historical Context\n{}\n\n\
             ## Peer Comparison\n{}\n\n\
             ## Known Risk Factors\n{}\n\n\
             Based on this context, provide a credit risk assessment. \
             Consider seasonal patterns, peer performance, and identified risk factors. \
             Be specific and cite the provided context.",
            context.historical_context,
            context.peer_comparison,
            context.risk_factors.join(", "),
        )
    }

    /// Extract risk factors from RAG responses.
    fn extract_risk_factors(&self, history: &RagResponse, peer: &RagResponse) -> Vec<String> {
        let mut factors = Vec::new();

        // Extract from source metadata
        for source in history.sources.iter().chain(peer.sources.iter()) {
            if let Some(context_type) = source.metadata.get("context_type") {
                if let Some(ct) = context_type.as_str() {
                    if ct.contains("risk") || ct.contains("hazard") {
                        factors.push(source.content.chars().take(100).collect());
                    }
                }
            }
        }

        // Deduplicate
        factors.sort();
        factors.dedup();
        factors.truncate(10); // Limit to top 10 risk factors

        factors
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_enriched_context_serialization() {
        let ctx = EnrichedCreditContext {
            query: "test".to_string(),
            historical_context: "history".to_string(),
            peer_comparison: "peers".to_string(),
            risk_factors: vec!["risk1".to_string()],
            source_count: 2,
            rag_latency_ms: 150.0,
        };
        let json = serde_json::to_value(&ctx).unwrap();
        assert_eq!(json["query"], "test");
        assert_eq!(json["source_count"], 2);
    }
}
