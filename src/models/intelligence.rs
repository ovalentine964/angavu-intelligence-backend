use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Intelligence module types
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum IntelligenceModule {
    RevenueForecasting,
    CustomerBehavior,
    MarketAnalysis,
    RiskAssessment,
    PricingOptimization,
    ChurnPrediction,
}

/// OODA Loop phases
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum OODAPhase {
    Observe,
    Orient,
    Decide,
    Act,
}

/// Intelligence task status
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum TaskStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Cancelled,
}

/// Intelligence task
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct IntelligenceTask {
    pub id: Uuid,
    pub module: IntelligenceModule,
    pub phase: OODAPhase,
    pub status: TaskStatus,
    pub input_data: serde_json::Value,
    pub output_data: Option<serde_json::Value>,
    pub error: Option<String>,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub created_by: Uuid,
    pub organization_id: Uuid,
    pub metadata: serde_json::Value,
}

/// Revenue forecast
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct RevenueForecast {
    pub id: Uuid,
    pub organization_id: Uuid,
    pub forecast_date: chrono::NaiveDate,
    pub period_start: chrono::NaiveDate,
    pub period_end: chrono::NaiveDate,
    pub predicted_revenue: f64,
    pub confidence_lower: f64,
    pub confidence_upper: f64,
    pub confidence_level: f64,
    pub model_version: String,
    pub features_used: serde_json::Value,
    pub created_at: DateTime<Utc>,
}

/// Customer behavior analysis
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct CustomerBehavior {
    pub id: Uuid,
    pub customer_id: Uuid,
    pub organization_id: Uuid,
    pub behavior_type: String,
    pub score: f64,
    pub features: serde_json::Value,
    pub segments: Vec<String>,
    pub risk_level: String,
    pub analyzed_at: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
}

/// Market analysis
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct MarketAnalysis {
    pub id: Uuid,
    pub organization_id: Uuid,
    pub market_segment: String,
    pub analysis_type: String,
    pub metrics: serde_json::Value,
    pub insights: Vec<String>,
    pub recommendations: Vec<String>,
    pub confidence_score: f64,
    pub period: String,
    pub created_at: DateTime<Utc>,
}

/// Risk assessment
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct RiskAssessment {
    pub id: Uuid,
    pub organization_id: Uuid,
    pub entity_type: String,
    pub entity_id: Uuid,
    pub risk_score: f64,
    pub risk_level: String,
    pub risk_factors: serde_json::Value,
    pub mitigation_strategies: Vec<String>,
    pub assessed_at: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
}

/// Pricing optimization result
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct PricingOptimization {
    pub id: Uuid,
    pub organization_id: Uuid,
    pub product_id: Uuid,
    pub current_price: f64,
    pub recommended_price: f64,
    pub expected_revenue_impact: f64,
    pub elasticity: f64,
    pub competitive_position: String,
    pub confidence: f64,
    pub created_at: DateTime<Utc>,
}

/// Churn prediction
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct ChurnPrediction {
    pub id: Uuid,
    pub customer_id: Uuid,
    pub organization_id: Uuid,
    pub churn_probability: f64,
    pub churn_risk: String,
    pub key_factors: serde_json::Value,
    pub retention_actions: Vec<String>,
    pub predicted_churn_date: Option<chrono::NaiveDate>,
    pub created_at: DateTime<Utc>,
}

/// Intelligence insight
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct IntelligenceInsight {
    pub id: Uuid,
    pub organization_id: Uuid,
    pub module: IntelligenceModule,
    pub insight_type: String,
    pub title: String,
    pub description: String,
    pub severity: String,
    pub confidence: f64,
    pub data: serde_json::Value,
    pub actionable: bool,
    pub acknowledged: bool,
    pub acknowledged_by: Option<Uuid>,
    pub acknowledged_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

/// Intelligence request/response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntelligenceRequest {
    pub module: IntelligenceModule,
    pub parameters: serde_json::Value,
    pub priority: Option<String>,
    pub callback_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntelligenceResponse {
    pub task_id: Uuid,
    pub status: TaskStatus,
    pub result: Option<serde_json::Value>,
    pub message: String,
}

/// Dashboard metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DashboardMetrics {
    pub total_revenue: f64,
    pub revenue_growth: f64,
    pub active_customers: i64,
    pub churn_rate: f64,
    pub risk_score: f64,
    pub forecast_accuracy: f64,
    pub insights_count: i64,
    pub last_updated: DateTime<Utc>,
}
