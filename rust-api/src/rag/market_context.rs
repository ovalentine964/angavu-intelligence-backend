// =============================================================================
// RAG Market Context — Enriches market intelligence with RAG-retrieved context
//
// Before generating market signals, this module queries the RAG system
// for historical market data, price trends, and demand patterns.
// =============================================================================

use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use super::client::RagClient;
use super::types::RagResponse;

/// Market context enrichment via RAG.
pub struct MarketContextEnricher {
    rag_client: RagClient,
}

/// Enriched market context
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrichedMarketContext {
    pub query: String,
    /// Historical price and demand data
    pub market_history: String,
    /// Seasonal patterns and trends
    pub seasonal_patterns: String,
    /// Supply chain insights
    pub supply_insights: String,
    /// Opportunities identified
    pub opportunities: Vec<String>,
    /// Risks identified
    pub risks: Vec<String>,
    pub source_count: usize,
    pub rag_latency_ms: f64,
}

impl MarketContextEnricher {
    pub fn new(rag_client: RagClient) -> Self {
        Self { rag_client }
    }

    /// Enrich market analysis with RAG context.
    pub async fn enrich(
        &self,
        category: &str,
        region: &str,
    ) -> Result<EnrichedMarketContext, String> {
        // Query 1: Market history
        let history_query = format!(
            "What is the price history and demand pattern for {} in {} over the \
             past 6 months? Include seasonal trends and price volatility.",
            category, region
        );

        let history_response = self
            .rag_client
            .query_market(&history_query, Some(category), Some(region))
            .await
            .map_err(|e| {
                warn!("RAG market history query failed: {}", e);
                e.to_string()
            })?;

        // Query 2: Opportunities and risks
        let opportunity_query = format!(
            "What are the current market opportunities and risks for {} traders in {}? \
             Consider supply disruptions, price arbitrage, and demand shifts.",
            category, region
        );

        let opportunity_response = self
            .rag_client
            .query_market(&opportunity_query, Some(category), Some(region))
            .await
            .map_err(|e| {
                warn!("RAG opportunity query failed: {}", e);
                e.to_string()
            })?;

        let opportunities = self.extract_insights(&opportunity_response, "opportunity");
        let risks = self.extract_insights(&opportunity_response, "risk");

        let total_latency = history_response.latency_ms + opportunity_response.latency_ms;
        let source_count = history_response.sources.len() + opportunity_response.sources.len();

        info!(
            category = %category,
            region = %region,
            sources = source_count,
            "Market context enrichment complete"
        );

        Ok(EnrichedMarketContext {
            query: format!("Market context for {} in {}", category, region),
            market_history: history_response.answer,
            seasonal_patterns: String::new(), // Extracted from history
            supply_insights: opportunity_response.answer,
            opportunities,
            risks,
            source_count,
            rag_latency_ms: total_latency,
        })
    }

    /// Build a system prompt for market analysis with RAG context.
    pub fn build_analysis_prompt(&self, context: &EnrichedMarketContext) -> String {
        format!(
            "You are Angavu Market Intelligence, analyzing market conditions for \
             informal economy workers in Kenya.\n\n\
             ## Market History\n{}\n\n\
             ## Supply Chain Insights\n{}\n\n\
             ## Opportunities\n{}\n\n\
             ## Risks\n{}\n\n\
             Provide actionable market recommendations based on this context.",
            context.market_history,
            context.supply_insights,
            context.opportunities.join("; "),
            context.risks.join("; "),
        )
    }

    /// Extract insights (opportunities or risks) from RAG response.
    fn extract_insights(&self, response: &RagResponse, insight_type: &str) -> Vec<String> {
        let mut insights = Vec::new();

        for source in &response.sources {
            let content = source.content.to_lowercase();
            if insight_type == "opportunity"
                && (content.contains("opportunity")
                    || content.contains("arbitrage")
                    || content.contains("demand"))
            {
                insights.push(source.content.chars().take(150).collect());
            } else if insight_type == "risk"
                && (content.contains("risk")
                    || content.contains("disruption")
                    || content.contains("shortage"))
            {
                insights.push(source.content.chars().take(150).collect());
            }
        }

        insights.sort();
        insights.dedup();
        insights.truncate(5);
        insights
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_enriched_market_context_serialization() {
        let ctx = EnrichedMarketContext {
            query: "test".to_string(),
            market_history: "history".to_string(),
            seasonal_patterns: "patterns".to_string(),
            supply_insights: "insights".to_string(),
            opportunities: vec!["opp1".to_string()],
            risks: vec!["risk1".to_string()],
            source_count: 3,
            rag_latency_ms: 200.0,
        };
        let json = serde_json::to_value(&ctx).unwrap();
        assert_eq!(json["source_count"], 3);
    }
}
