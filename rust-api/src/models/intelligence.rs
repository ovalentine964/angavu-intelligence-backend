use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// Intelligence query types.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum IntelligenceQueryType {
    /// Cash flow analysis and prediction
    CashFlow,
    /// Revenue trend analysis
    RevenueTrend,
    /// Expense categorization and optimization
    ExpenseOptimization,
    /// Customer behavior analysis
    CustomerBehavior,
    /// Inventory insights
    Inventory,
    /// Business health overview
    HealthCheck,
    /// Custom natural language query
    Custom,
}

/// Intelligence query request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct IntelligenceQueryRequest {
    /// Type of intelligence query
    pub query_type: IntelligenceQueryType,
    /// Time period for analysis (days)
    #[serde(default = "default_period_days")]
    pub period_days: u32,
    /// Natural language question (required for Custom type)
    pub question: Option<String>,
    /// Additional filters
    pub filters: Option<IntelligenceFilters>,
}

fn default_period_days() -> u32 { 30 }

/// Additional filters for intelligence queries.
#[derive(Debug, Deserialize, ToSchema)]
pub struct IntelligenceFilters {
    pub category: Option<String>,
    pub min_amount: Option<f64>,
    pub max_amount: Option<f64>,
    pub transaction_type: Option<String>,
}

/// Intelligence query response.
#[derive(Debug, Serialize, ToSchema)]
pub struct IntelligenceResponse {
    /// Query ID for caching/reference
    pub query_id: Uuid,
    /// Query type
    pub query_type: IntelligenceQueryType,
    /// Human-readable summary
    pub summary: String,
    /// Detailed insights
    pub insights: Vec<Insight>,
    /// Recommendations
    pub recommendations: Vec<Recommendation>,
    /// Data points for visualization
    pub data_points: Option<serde_json::Value>,
    /// Confidence score (0.0 - 1.0)
    pub confidence: f64,
    /// Generated at
    pub generated_at: DateTime<Utc>,
}

/// Individual insight.
#[derive(Debug, Serialize, ToSchema)]
pub struct Insight {
    /// Insight title
    pub title: String,
    /// Detailed description
    pub description: String,
    /// Impact level: high, medium, low
    pub impact: String,
    /// Category: financial, operational, growth, risk
    pub category: String,
    /// Supporting data
    pub data: Option<serde_json::Value>,
}

/// Actionable recommendation.
#[derive(Debug, Serialize, ToSchema)]
pub struct Recommendation {
    /// Recommendation title
    pub title: String,
    /// Detailed description
    pub description: String,
    /// Priority: high, medium, low
    pub priority: String,
    /// Expected impact description
    pub expected_impact: String,
    /// Action type: immediate, short_term, long_term
    pub action_type: String,
}

/// Voice input request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct VoiceInputRequest {
    /// Base64-encoded audio data
    pub audio_data: String,
    /// Audio format (wav, mp3, ogg)
    pub format: String,
    /// Language code (si, ta, en)
    #[serde(default = "default_language")]
    pub language: String,
}

fn default_language() -> String {
    "si".to_string()
}

/// Voice input response.
#[derive(Debug, Serialize, ToSchema)]
pub struct VoiceInputResponse {
    /// Transcribed text
    pub transcription: String,
    /// Detected language
    pub detected_language: String,
    /// Confidence score (0.0 - 1.0)
    pub confidence: f64,
    /// Parsed transaction (if applicable)
    pub parsed_transaction: Option<ParsedTransaction>,
}

/// Transaction parsed from voice input.
#[derive(Debug, Serialize, ToSchema)]
pub struct ParsedTransaction {
    pub transaction_type: String,
    pub amount: f64,
    pub category: String,
    pub description: String,
    pub confidence: f64,
}
