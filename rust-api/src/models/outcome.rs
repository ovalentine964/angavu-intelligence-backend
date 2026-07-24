use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// Outcome-based pricing model for Angavu Intelligence.
/// Tracks business outcomes derived from intelligence insights.

/// Outcome model.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct Outcome {
    pub id: Uuid,
    pub user_id: Uuid,
    /// The insight/recommendation that led to this outcome
    pub insight_id: Uuid,
    /// Outcome type: revenue_increase, cost_reduction, efficiency_gain, new_customer
    pub outcome_type: OutcomeType,
    /// Measured value (monetary or percentage)
    pub measured_value: f64,
    /// Unit: currency (LKR), percentage, count
    pub unit: OutcomeUnit,
    /// Description of the outcome
    pub description: String,
    /// Verification status
    pub status: OutcomeStatus,
    /// Period start for measurement
    pub period_start: DateTime<Utc>,
    /// Period end for measurement
    pub period_end: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Outcome types.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum OutcomeType {
    RevenueIncrease,
    CostReduction,
    EfficiencyGain,
    NewCustomer,
    RetentionImprovement,
    InventoryOptimization,
}

/// Measurement units.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum OutcomeUnit {
    /// Monetary value in LKR
    Currency,
    /// Percentage improvement
    Percentage,
    /// Absolute count
    Count,
    /// Hours saved
    Hours,
}

/// Outcome verification status.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum OutcomeStatus {
    /// Pending verification
    Pending,
    /// Verified by system data
    Verified,
    /// Manually confirmed by user
    Confirmed,
    /// Disputed or unverifiable
    Disputed,
}

/// Create outcome request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateOutcomeRequest {
    pub insight_id: Uuid,
    pub outcome_type: OutcomeType,
    pub measured_value: f64,
    pub unit: OutcomeUnit,
    pub description: String,
    pub period_start: DateTime<Utc>,
    pub period_end: DateTime<Utc>,
}

/// Outcome summary for pricing.
#[derive(Debug, Serialize, ToSchema)]
pub struct OutcomeSummary {
    /// Total verified outcomes
    pub total_outcomes: u64,
    /// Total monetary value generated
    pub total_value: f64,
    /// Breakdown by type
    pub by_type: Vec<OutcomeTypeSummary>,
    /// Monthly trend
    pub monthly_trend: Vec<MonthlyOutcome>,
}

/// Summary per outcome type.
#[derive(Debug, Serialize, ToSchema)]
pub struct OutcomeTypeSummary {
    pub outcome_type: OutcomeType,
    pub count: u64,
    pub total_value: f64,
    pub average_value: f64,
}

/// Monthly outcome data point.
#[derive(Debug, Serialize, ToSchema)]
pub struct MonthlyOutcome {
    pub month: String,
    pub count: u64,
    pub total_value: f64,
}

/// Outcome pricing tier.
#[derive(Debug, Serialize, ToSchema)]
pub struct PricingTier {
    /// Tier name
    pub name: String,
    /// Base monthly price in LKR
    pub base_price: f64,
    /// Outcome fee percentage (e.g., 5% of verified outcome value)
    pub outcome_fee_pct: f64,
    /// Included features
    pub features: Vec<String>,
}
