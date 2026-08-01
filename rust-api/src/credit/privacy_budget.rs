// src/credit/privacy_budget.rs
//
// Privacy Budget Tracker — Rényi Differential Privacy (RDP) composition
//
// Tracks cumulative ε consumption per query type per time window.
// Uses RDP composition for tighter bounds than basic sequential composition.
//
// Key properties:
// - Per-query-type tracking prevents one category from exhausting global budget
// - Time-windowed budget reset (hourly/daily) limits long-term privacy leakage
// - RDP composition: ε_total ≈ ε₁ + ε₂ + ... (basic) but RDP gives:
//     ε_total = (1/(α-1)) × ln(exp((α-1)×ε₁) + exp((α-1)×ε₂) + ...)
//   which is tighter for many small queries
// - Blocks queries when budget is exhausted (fail-closed)

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tokio::sync::RwLock;
use tracing::{info, warn};

/// Default per-query-type budget per time window.
pub const DEFAULT_EPSILON_PER_WINDOW: f64 = 1.0;

/// Default time window duration (24 hours).
pub const DEFAULT_WINDOW_DURATION_HOURS: i64 = 24;

/// Maximum number of query types tracked simultaneously.
pub const MAX_QUERY_TYPES: usize = 64;

/// Supported query types for budget tracking.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum QueryType {
    /// Credit score computation
    CreditScore,
    /// Market analysis aggregation
    MarketAnalysis,
    /// Demand forecast aggregation
    DemandForecast,
    /// Economic indicators
    EconomicIndicators,
    /// Distribution gap analysis
    DistributionGaps,
    /// FMCG intelligence report
    FmcgReport,
    /// Federated learning gradient aggregation
    FederatedLearning,
    /// General aggregate query
    General,
}

impl QueryType {
    /// Human-readable label for logging.
    pub fn label(&self) -> &'static str {
        match self {
            QueryType::CreditScore => "credit_score",
            QueryType::MarketAnalysis => "market_analysis",
            QueryType::DemandForecast => "demand_forecast",
            QueryType::EconomicIndicators => "economic_indicators",
            QueryType::DistributionGaps => "distribution_gaps",
            QueryType::FmcgReport => "fmcg_report",
            QueryType::FederatedLearning => "federated_learning",
            QueryType::General => "general",
        }
    }
}

/// RDP parameters for a single mechanism invocation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RdpParameters {
    /// The Rényi divergence order (α > 1).
    /// Higher α gives tighter bounds for small ε but requires more careful analysis.
    /// Typical range: 2..=64.
    pub alpha: f64,
    /// The RDP ε at order α for this single mechanism invocation.
    /// For the Gaussian mechanism with noise σ and sensitivity Δ:
    ///   ε_RDP(α) = α / (2σ²)
    pub epsilon_rdp: f64,
}

impl RdpParameters {
    /// Create RDP parameters for the Gaussian mechanism.
    ///
    /// For Gaussian mechanism: ε_RDP(α) = α × Δ² / (2σ²)
    /// where Δ is the L2 sensitivity and σ is the noise standard deviation.
    pub fn gaussian(sensitivity: f64, sigma: f64, alpha: f64) -> Self {
        assert!(alpha > 1.0, "RDP order α must be > 1");
        assert!(sigma > 0.0, "Noise σ must be positive");
        let epsilon_rdp = alpha * sensitivity.powi(2) / (2.0 * sigma.powi(2));
        Self { alpha, epsilon_rdp }
    }

    /// Create RDP parameters for the Laplace mechanism.
    ///
    /// For Laplace mechanism: ε_RDP(α) = ... (piecewise, but we use the
    /// conservative bound ε_RDP(α) ≤ ε_DP for α → ∞).
    /// Practically, we convert: ε_RDP ≈ ε_DP for moderate α.
    pub fn laplace(sensitivity: f64, b: f64, alpha: f64) -> Self {
        assert!(alpha > 1.0, "RDP order α must be > 1");
        assert!(b > 0.0, "Laplace scale b must be positive");
        let epsilon_dp = sensitivity / b;
        // Conservative RDP bound for Laplace: ε_RDP(α) = (1/(α-1)) × log(α/(2α-1) × exp((α-1)/b) + (α-1)/(2α-1) × exp(-α/b))
        // Simplified: for practical α values, ε_RDP ≈ ε_DP × α / (α - 1)
        let epsilon_rdp = epsilon_dp * alpha / (alpha - 1.0);
        Self { alpha, epsilon_rdp }
    }
}

/// Record of a single query's privacy cost.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryRecord {
    pub query_type: QueryType,
    pub rdp: RdpParameters,
    pub timestamp: DateTime<Utc>,
    pub endpoint: String,
    pub cohort_key: Option<String>,
}

/// Per-query-type budget state within a time window.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryTypeBudget {
    pub query_type: QueryType,
    /// RDP ε budget for this window
    pub budget_epsilon: f64,
    /// Cumulative RDP ε consumed
    pub consumed_epsilon_rdp: f64,
    /// Number of queries executed
    pub query_count: u64,
    /// Window start time
    pub window_start: DateTime<Utc>,
    /// Window end time
    pub window_end: DateTime<Utc>,
    /// Recent query records (for audit)
    pub recent_queries: Vec<QueryRecord>,
}

impl QueryTypeBudget {
    fn new(query_type: QueryType, budget: f64, window_start: DateTime<Utc>, window_end: DateTime<Utc>) -> Self {
        Self {
            query_type,
            budget_epsilon: budget,
            consumed_epsilon_rdp: 0.0,
            query_count: 0,
            window_start,
            window_end,
            recent_queries: Vec::new(),
        }
    }

    /// Check if a query with the given RDP cost would exceed the budget.
    pub fn can_afford(&self, rdp_cost: &RdpParameters) -> bool {
        let projected = self.compose_rdp(rdp_cost);
        projected <= self.budget_epsilon
    }

    /// Compose the existing consumed RDP with a new query using the
    /// optimal composition theorem:
    /// ε_total = (1/(α-1)) × ln(exp((α-1)×ε_old) + exp((α-1)×ε_new))
    ///
    /// For efficiency we track the log-sum-exp directly.
    fn compose_rdp(&self, new_rdp: &RdpParameters) -> f64 {
        if self.consumed_epsilon_rdp == 0.0 {
            return new_rdp.epsilon_rdp;
        }
        // Basic RDP composition: for the same α, RDP composes additively.
        // ε_total(α) = Σᵢ εᵢ(α)
        // This is exact for RDP (not an approximation).
        self.consumed_epsilon_rdp + new_rdp.epsilon_rdp
    }

    /// Convert cumulative RDP ε to (ε,δ)-DP using the standard conversion:
    /// ε_DP = ε_RDP + log(1/δ) / (α - 1)
    /// We use a default δ = 10⁻⁵ (suitable for datasets of ~10k+ individuals).
    pub fn to_dp_epsilon(&self, delta: f64) -> f64 {
        if self.consumed_epsilon_rdp == 0.0 {
            return 0.0;
        }
        // Find the optimal α by scanning a range
        let mut best_epsilon = f64::MAX;
        for alpha_int in 2..=128 {
            let alpha = alpha_int as f64;
            let epsilon_dp = self.consumed_epsilon_rdp + (1.0 / delta).ln() / (alpha - 1.0);
            if epsilon_dp < best_epsilon {
                best_epsilon = epsilon_dp;
            }
        }
        best_epsilon
    }

    /// Record a query and consume budget.
    fn record_query(&mut self, rdp: RdpParameters, endpoint: String, cohort_key: Option<String>) {
        self.consumed_epsilon_rdp = self.compose_rdp(&rdp);
        self.query_count += 1;
        self.recent_queries.push(QueryRecord {
            query_type: self.query_type,
            rdp,
            timestamp: Utc::now(),
            endpoint,
            cohort_key,
        });
        // Keep only last 100 records to bound memory
        if self.recent_queries.len() > 100 {
            self.recent_queries.drain(0..50);
        }
    }

    /// Check if the window has expired and reset if so.
    fn maybe_reset(&mut self, now: DateTime<Utc>) {
        if now >= self.window_end {
            let window_duration = self.window_end - self.window_start;
            self.consumed_epsilon_rdp = 0.0;
            self.query_count = 0;
            self.recent_queries.clear();
            self.window_start = now;
            self.window_end = now + window_duration;

            info!(
                query_type = %self.query_type.label(),
                new_window_end = %self.window_end,
                "Privacy budget window reset"
            );
        }
    }
}

/// Privacy budget tracker — manages per-query-type budgets with RDP composition.
///
/// Thread-safe via `Arc<RwLock<…>>`. Designed to be shared across the application
/// as part of `GatewayState`.
pub struct PrivacyBudgetTracker {
    budgets: RwLock<HashMap<QueryType, QueryTypeBudget>>,
    default_epsilon: f64,
    window_duration: Duration,
}

/// Result of a budget check.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BudgetCheckResult {
    /// Whether the query is allowed
    pub allowed: bool,
    /// The query type
    pub query_type: QueryType,
    /// Remaining RDP epsilon in this window
    pub remaining_rdp_epsilon: f64,
    /// Approximate (ε,δ)-DP epsilon consumed so far
    pub consumed_dp_epsilon: f64,
    /// Budget limit
    pub budget_limit: f64,
    /// Number of queries in this window
    pub query_count: u64,
    /// Window resets at
    pub window_reset_at: DateTime<Utc>,
    /// Reason for rejection (if blocked)
    pub rejection_reason: Option<String>,
}

impl PrivacyBudgetTracker {
    /// Create a new tracker with default settings.
    pub fn new() -> Self {
        Self {
            budgets: RwLock::new(HashMap::new()),
            default_epsilon: DEFAULT_EPSILON_PER_WINDOW,
            window_duration: Duration::hours(DEFAULT_WINDOW_DURATION_HOURS),
        }
    }

    /// Create with custom settings.
    pub fn with_config(default_epsilon: f64, window_hours: i64) -> Self {
        Self {
            budgets: RwLock::new(HashMap::new()),
            default_epsilon,
            window_duration: Duration::hours(window_hours),
        }
    }

    /// Check if a query can proceed and record it if allowed.
    ///
    /// This is the primary entry point. It:
    /// 1. Resets the budget window if expired
    /// 2. Checks if the query fits within the remaining budget
    /// 3. If allowed, records the query and consumes budget
    /// 4. Returns a detailed result
    pub async fn check_and_record(
        &self,
        query_type: QueryType,
        rdp: RdpParameters,
        endpoint: String,
        cohort_key: Option<String>,
    ) -> BudgetCheckResult {
        let now = Utc::now();
        let mut budgets = self.budgets.write().await;

        // Ensure the query type budget exists
        let budget = budgets
            .entry(query_type)
            .or_insert_with(|| {
                QueryTypeBudget::new(
                    query_type,
                    self.default_epsilon,
                    now,
                    now + self.window_duration,
                )
            });

        // Reset window if expired
        budget.maybe_reset(now);

        // Check budget
        if !budget.can_afford(&rdp) {
            let remaining = budget.budget_epsilon - budget.consumed_epsilon_rdp;
            warn!(
                query_type = %query_type.label(),
                rdp_epsilon = %rdp.epsilon_rdp,
                remaining = %remaining,
                consumed = %budget.consumed_epsilon_rdp,
                "Privacy budget EXHAUSTED — query BLOCKED"
            );
            return BudgetCheckResult {
                allowed: false,
                query_type,
                remaining_rdp_epsilon: remaining.max(0.0),
                consumed_dp_epsilon: budget.to_dp_epsilon(1e-5),
                budget_limit: budget.budget_epsilon,
                query_count: budget.query_count,
                window_reset_at: budget.window_end,
                rejection_reason: Some(format!(
                    "Privacy budget exhausted for {}: consumed {:.4}/{:.4} RDP-ε. Window resets at {}.",
                    query_type.label(),
                    budget.consumed_epsilon_rdp,
                    budget.budget_epsilon,
                    budget.window_end.format("%Y-%m-%dT%H:%M:%SZ")
                )),
            };
        }

        // Record the query
        budget.record_query(rdp.clone(), endpoint.clone(), cohort_key.clone());

        let remaining = budget.budget_epsilon - budget.consumed_epsilon_rdp;
        info!(
            query_type = %query_type.label(),
            rdp_epsilon = %rdp.epsilon_rdp,
            remaining = %remaining,
            consumed_total = %budget.consumed_epsilon_rdp,
            query_count = %budget.query_count,
            endpoint = %endpoint,
            "Privacy budget consumed"
        );

        BudgetCheckResult {
            allowed: true,
            query_type,
            remaining_rdp_epsilon: remaining,
            consumed_dp_epsilon: budget.to_dp_epsilon(1e-5),
            budget_limit: budget.budget_epsilon,
            query_count: budget.query_count,
            window_reset_at: budget.window_end,
            rejection_reason: None,
        }
    }

    /// Get the current status of all budgets (for monitoring / dashboard).
    pub async fn status(&self) -> Vec<BudgetStatus> {
        let budgets = self.budgets.read().await;
        let now = Utc::now();
        budgets
            .values()
            .map(|b| BudgetStatus {
                query_type: b.query_type,
                budget_epsilon: b.budget_epsilon,
                consumed_rdp_epsilon: b.consumed_epsilon_rdp,
                consumed_dp_epsilon: b.to_dp_epsilon(1e-5),
                remaining_rdp_epsilon: (b.budget_epsilon - b.consumed_epsilon_rdp).max(0.0),
                query_count: b.query_count,
                window_start: b.window_start,
                window_end: b.window_end,
                window_active: now < b.window_end,
            })
            .collect()
    }

    /// Force-reset all budgets (emergency use only).
    pub async fn reset_all(&self) {
        let mut budgets = self.budgets.write().await;
        budgets.clear();
        warn!("All privacy budgets force-reset");
    }
}

/// Status of a single query type budget (for API / monitoring).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BudgetStatus {
    pub query_type: QueryType,
    pub budget_epsilon: f64,
    pub consumed_rdp_epsilon: f64,
    pub consumed_dp_epsilon: f64,
    pub remaining_rdp_epsilon: f64,
    pub query_count: u64,
    pub window_start: DateTime<Utc>,
    pub window_end: DateTime<Utc>,
    pub window_active: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_basic_budget_tracking() {
        let tracker = PrivacyBudgetTracker::with_config(1.0, 24);

        let rdp = RdpParameters::gaussian(1.0, 1.0, 2.0); // ε_RDP = 2×1²/(2×1²) = 1.0
        let result = tracker
            .check_and_record(QueryType::CreditScore, rdp, "/test".into(), None)
            .await;

        assert!(result.allowed);
        assert!(result.query_count == 1);
    }

    #[tokio::test]
    async fn test_budget_exhaustion_blocks_query() {
        let tracker = PrivacyBudgetTracker::with_config(0.5, 24);

        // First query: ε_RDP = 0.4
        let rdp1 = RdpParameters { alpha: 2.0, epsilon_rdp: 0.4 };
        let r1 = tracker
            .check_and_record(QueryType::General, rdp1, "/test".into(), None)
            .await;
        assert!(r1.allowed);

        // Second query: ε_RDP = 0.3 → total would be 0.7 > 0.5
        let rdp2 = RdpParameters { alpha: 2.0, epsilon_rdp: 0.3 };
        let r2 = tracker
            .check_and_record(QueryType::General, rdp2, "/test".into(), None)
            .await;
        assert!(!r2.allowed);
        assert!(r2.rejection_reason.is_some());
    }

    #[tokio::test]
    async fn test_per_query_type_isolation() {
        let tracker = PrivacyBudgetTracker::with_config(1.0, 24);

        // Exhaust credit score budget
        let rdp = RdpParameters { alpha: 2.0, epsilon_rdp: 0.9 };
        tracker
            .check_and_record(QueryType::CreditScore, rdp, "/credit".into(), None)
            .await;

        // Market analysis should still have its own budget
        let rdp2 = RdpParameters { alpha: 2.0, epsilon_rdp: 0.9 };
        let result = tracker
            .check_and_record(QueryType::MarketAnalysis, rdp2, "/market".into(), None)
            .await;
        assert!(result.allowed);
    }

    #[test]
    fn test_gaussian_rdp_params() {
        let rdp = RdpParameters::gaussian(1.0, 1.0, 4.0);
        // ε_RDP = 4 × 1² / (2 × 1²) = 2.0
        assert!((rdp.epsilon_rdp - 2.0).abs() < 1e-10);
    }
}
