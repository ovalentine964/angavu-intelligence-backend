use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// Worker profile model.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct Worker {
    pub id: Uuid,
    pub user_id: Uuid,
    pub business_name: String,
    pub business_type: String,
    /// Geographic location (lat, lng)
    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub address: Option<String>,
    pub district: Option<String>,
    pub province: Option<String>,
    /// Alama Score (credit score 0-1000)
    pub alama_score: Option<u32>,
    /// Daily transaction volume (average)
    pub avg_daily_volume: f64,
    /// Number of employees
    pub employee_count: Option<u32>,
    /// Registration number
    pub registration_number: Option<String>,
    /// Years in business
    pub years_in_business: Option<f64>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Create worker profile request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateWorkerRequest {
    pub business_name: String,
    pub business_type: String,
    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub address: Option<String>,
    pub district: Option<String>,
    pub province: Option<String>,
    pub employee_count: Option<u32>,
    pub registration_number: Option<String>,
    pub years_in_business: Option<f64>,
}

/// Update worker profile request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateWorkerRequest {
    pub business_name: Option<String>,
    pub business_type: Option<String>,
    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub address: Option<String>,
    pub district: Option<String>,
    pub province: Option<String>,
    pub employee_count: Option<u32>,
    pub registration_number: Option<String>,
}

/// Alama Score response.
#[derive(Debug, Serialize, ToSchema)]
pub struct AlamaScoreResponse {
    /// Current Alama Score (0-1000)
    pub score: u32,
    /// Score grade (A, B, C, D, E)
    pub grade: String,
    /// Score breakdown
    pub breakdown: ScoreBreakdown,
    /// Last calculated timestamp
    pub calculated_at: DateTime<Utc>,
    /// Trend: improving, stable, declining
    pub trend: String,
}

/// Score breakdown by category.
#[derive(Debug, Serialize, ToSchema)]
pub struct ScoreBreakdown {
    /// Transaction consistency score (0-200)
    pub consistency: u32,
    /// Volume growth score (0-200)
    pub volume_growth: u32,
    /// Business stability score (0-200)
    pub stability: u32,
    /// Financial health score (0-200)
    pub financial_health: u32,
    /// Engagement score (0-200)
    pub engagement: u32,
}

/// Worker goal model.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct Goal {
    pub id: Uuid,
    pub user_id: Uuid,
    pub title: String,
    pub description: Option<String>,
    /// Goal type: daily_revenue, monthly_revenue, transaction_count, savings
    pub goal_type: String,
    /// Target value
    pub target_value: f64,
    /// Current progress value
    pub current_value: f64,
    /// Progress percentage (0-100)
    pub progress_pct: f64,
    /// Goal deadline
    pub deadline: Option<DateTime<Utc>>,
    pub is_completed: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Create goal request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateGoalRequest {
    pub title: String,
    pub description: Option<String>,
    /// Goal type: daily_revenue, monthly_revenue, transaction_count, savings
    pub goal_type: String,
    /// Target value
    pub target_value: f64,
    /// Optional deadline
    pub deadline: Option<DateTime<Utc>>,
}

/// Update goal request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateGoalRequest {
    pub title: Option<String>,
    pub description: Option<String>,
    pub target_value: Option<f64>,
    pub current_value: Option<f64>,
    pub deadline: Option<DateTime<Utc>>,
    pub is_completed: Option<bool>,
}
