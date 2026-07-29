// =============================================================================
// RAG Health Context — Enriches health/insurance recommendations with RAG
//
// Retrieves occupation-specific health risks, insurance options, and
// preventive care recommendations from the knowledge base.
// =============================================================================

use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use super::client::RagClient;
use super::types::RagResponse;

/// Health context enrichment via RAG.
pub struct HealthContextEnricher {
    rag_client: RagClient,
}

/// Enriched health context
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrichedHealthContext {
    pub query: String,
    /// Occupation-specific health risks
    pub occupation_risks: String,
    /// Insurance eligibility and recommendations
    pub insurance_recommendations: String,
    /// Preventive care suggestions
    pub preventive_care: Vec<String>,
    /// Location-based health risks
    pub location_risks: String,
    pub source_count: usize,
    pub rag_latency_ms: f64,
}

impl HealthContextEnricher {
    pub fn new(rag_client: RagClient) -> Self {
        Self { rag_client }
    }

    /// Enrich health/insurance analysis with RAG context.
    pub async fn enrich(
        &self,
        worker_type: &str,
        region: &str,
    ) -> Result<EnrichedHealthContext, String> {
        // Query 1: Occupation health risks
        let risk_query = format!(
            "What are the occupational health hazards and risks for {} workers in Kenya? \
             Include common injuries, chronic conditions, and exposure risks.",
            worker_type
        );

        let risk_response = self
            .rag_client
            .query_health(&risk_query, Some(worker_type), Some(region))
            .await
            .map_err(|e| {
                warn!("RAG health risk query failed: {}", e);
                e.to_string()
            })?;

        // Query 2: Insurance options
        let insurance_query = format!(
            "What insurance options and health coverage are available for {} workers in {}? \
             Include NHIF, private insurance, and micro-insurance options.",
            worker_type, region
        );

        let insurance_response = self
            .rag_client
            .query_health(&insurance_query, Some(worker_type), Some(region))
            .await
            .map_err(|e| {
                warn!("RAG insurance query failed: {}", e);
                e.to_string()
            })?;

        let preventive_care = self.extract_preventive_care(&risk_response);

        let total_latency = risk_response.latency_ms + insurance_response.latency_ms;
        let source_count = risk_response.sources.len() + insurance_response.sources.len();

        info!(
            worker_type = %worker_type,
            region = %region,
            sources = source_count,
            "Health context enrichment complete"
        );

        Ok(EnrichedHealthContext {
            query: format!("Health context for {} in {}", worker_type, region),
            occupation_risks: risk_response.answer,
            insurance_recommendations: insurance_response.answer,
            preventive_care,
            location_risks: String::new(), // Could be enriched separately
            source_count,
            rag_latency_ms: total_latency,
        })
    }

    /// Build a system prompt for health recommendations with RAG context.
    pub fn build_recommendation_prompt(&self, context: &EnrichedHealthContext) -> String {
        format!(
            "You are Angavu Health Intelligence, providing health and insurance \
             recommendations for informal economy workers in Kenya.\n\n\
             ## Occupation Risks\n{}\n\n\
             ## Insurance Options\n{}\n\n\
             ## Preventive Care\n{}\n\n\
             Provide actionable health recommendations and insurance guidance \
             based on this context. Be specific about available options.",
            context.occupation_risks,
            context.insurance_recommendations,
            context.preventive_care.join("; "),
        )
    }

    /// Extract preventive care suggestions from RAG response.
    fn extract_preventive_care(&self, response: &RagResponse) -> Vec<String> {
        let mut care = Vec::new();

        for source in &response.sources {
            let content = source.content.to_lowercase();
            if content.contains("prevent")
                || content.contains("protective")
                || content.contains("safety")
                || content.contains("vaccin")
            {
                care.push(source.content.chars().take(150).collect());
            }
        }

        care.sort();
        care.dedup();
        care.truncate(5);
        care
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_enriched_health_context_serialization() {
        let ctx = EnrichedHealthContext {
            query: "test".to_string(),
            occupation_risks: "risks".to_string(),
            insurance_recommendations: "insurance".to_string(),
            preventive_care: vec!["wear gloves".to_string()],
            location_risks: "location".to_string(),
            source_count: 2,
            rag_latency_ms: 180.0,
        };
        let json = serde_json::to_value(&ctx).unwrap();
        assert_eq!(json["source_count"], 2);
        assert!(json["preventive_care"].is_array());
    }
}
