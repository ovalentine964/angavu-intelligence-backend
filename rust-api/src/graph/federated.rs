//! Federated Learning Graph — Tracks model aggregation workflow,
//! device contributions, and cohort formation.
//!
//! Flow: Device Gradients → Secure Aggregation → Global Model →
//!       Delta Encoding → Distribution
//!
//! The graph tracks which devices contributed to which model versions
//! and manages cohort formation as graph clustering.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

/// A federated learning round as a graph node.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlRound {
    pub id: Uuid,
    pub model_name: String,
    pub round_number: u32,
    pub parent_version: Option<String>,
    pub status: FlRoundStatus,
    pub aggregation_algorithm: AggregationAlgorithm,
    pub participant_selection: ParticipantSelection,
    pub global_metrics: ModelMetrics,
    pub privacy_budget: PrivacyBudget,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub cohort_contributions: HashMap<String, CohortContribution>,
    pub delta_info: Option<DeltaInfo>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FlRoundStatus {
    Collecting,
    Aggregating,
    Distributing,
    Completed,
    Failed,
    RolledBack,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AggregationAlgorithm {
    /// Federated Averaging — weighted by data samples
    FedAvg,
    /// FedProx — proximal term for non-IID data
    FedProx,
    /// FedMA — Bayesian non-parametric matching
    FedMA,
    /// Coordinate-wise median (robust to malicious devices)
    RobustMedian,
}

/// How participants are selected for a round.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParticipantSelection {
    pub strategy: SelectionStrategy,
    pub target_count: u32,
    pub actual_count: u32,
    pub minimum_per_cohort: u32,
    pub eligibility_criteria: EligibilityCriteria,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SelectionStrategy {
    /// Random uniform selection
    Random,
    /// Stratified by cohort (ensures representation)
    Stratified,
    /// Power-of-choice (select devices with highest loss)
    PowerOfChoice,
    /// Contribution-weighted (prefer reliable devices)
    ContributionWeighted,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EligibilityCriteria {
    pub min_battery_pct: u8,
    pub require_charging_or_wifi: bool,
    pub min_model_version: String,
    pub cooldown_hours: u32,
    pub min_local_samples: u32,
}

/// A cohort's contribution to a federated round.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CohortContribution {
    pub cohort_hash: String,
    pub participant_count: u32,
    pub total_samples: u32,
    pub gradient_norm: f64,
    pub local_loss: f64,
    pub local_accuracy: f64,
    pub contribution_weight: f64,
    pub submitted_at: DateTime<Utc>,
}

/// Privacy budget tracking per round.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrivacyBudget {
    pub epsilon_per_round: f64,
    pub delta: f64,
    pub clip_norm: f64,
    pub noise_multiplier: f64,
    pub cumulative_epsilon: f64,
    pub rounds_remaining: u32, // before budget exhaustion
}

/// Model metrics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelMetrics {
    pub loss: f64,
    pub accuracy: f64,
    pub auc_roc: Option<f64>,
    pub calibration_error: Option<f64>,
    pub worst_cohort_accuracy: f64,
    pub best_cohort_accuracy: f64,
    pub accuracy_parity: f64, // max difference across cohorts
}

/// Delta encoding info for model distribution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeltaInfo {
    pub delta_size_bytes: u64,
    pub full_model_size_bytes: u64,
    pub compression_ratio: f64,
    pub changed_layers: Vec<String>,
    pub checksum_sha256: String,
}

/// Edge in the FL graph: represents a contribution relationship.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlEdge {
    pub source: FlNodeRef,
    pub target: FlNodeRef,
    pub edge_type: FlEdgeType,
    pub weight: f64,
    pub properties: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlNodeRef {
    pub node_type: FlNodeType,
    pub id: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FlNodeType {
    Device,
    Cohort,
    ModelVersion,
    AggregationServer,
    RegionalAggregator,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FlEdgeType {
    /// Device contributed gradients to a model version
    ContributedTo,
    /// Cohort aggregates device contributions
    AggregatesDevice,
    /// Model version derives from parent
    DerivesFrom,
    /// Regional aggregator feeds central server
    FeedsTo,
    /// Model version distributed to device/region
    DistributedTo,
    /// Device belongs to cohort
    BelongsToCohort,
}

/// The complete Federated Learning graph.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlGraph {
    pub model_name: String,
    pub rounds: Vec<FlRound>,
    pub edges: Vec<FlEdge>,
    pub cohorts: HashMap<String, CohortInfo>,
    pub devices: HashMap<String, DeviceInfo>,
}

/// Cohort information (mirrors kg_worker_cohorts but for FL context).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CohortInfo {
    pub cohort_hash: String,
    pub worker_type: String,
    pub region: String,
    pub device_count: u32,
    pub avg_data_quality: f64,
    pub model_head_version: Option<String>, // cohort-specific head
    pub last_participation: Option<DateTime<Utc>>,
}

/// Device information for FL tracking.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceInfo {
    pub device_id_hash: String,
    pub cohort_hash: String,
    pub model_version: String,
    pub total_rounds_participated: u32,
    pub avg_gradient_norm: f64,
    pub reliability_score: f64,
    pub last_participation: Option<DateTime<Utc>>,
    pub rollback_history: Vec<RollbackEvent>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RollbackEvent {
    pub from_version: String,
    pub to_version: String,
    pub reason: String,
    pub timestamp: DateTime<Utc>,
}

impl FlGraph {
    /// Create a new empty FL graph for a model.
    pub fn new(model_name: String) -> Self {
        Self {
            model_name,
            rounds: Vec::new(),
            edges: Vec::new(),
            cohorts: HashMap::new(),
            devices: HashMap::new(),
        }
    }

    /// Record a completed FL round.
    pub fn record_round(&mut self, round: FlRound) {
        // Create edges from contributing cohorts to this round
        for (cohort_hash, contribution) in &round.cohort_contributions {
            self.edges.push(FlEdge {
                source: FlNodeRef {
                    node_type: FlNodeType::Cohort,
                    id: cohort_hash.clone(),
                },
                target: FlNodeRef {
                    node_type: FlNodeType::ModelVersion,
                    id: format!("{}:v{}", self.model_name, round.round_number),
                },
                edge_type: FlEdgeType::ContributedTo,
                weight: contribution.contribution_weight,
                properties: serde_json::json!({
                    "participant_count": contribution.participant_count,
                    "total_samples": contribution.total_samples,
                    "local_accuracy": contribution.local_accuracy,
                }),
            });

            // Update cohort info
            if let Some(cohort) = self.cohorts.get_mut(cohort_hash) {
                cohort.last_participation = Some(round.completed_at.unwrap_or_else(Utc::now));
            }
        }

        // Create derivation edge from parent version
        if let Some(ref parent) = round.parent_version {
            self.edges.push(FlEdge {
                source: FlNodeRef {
                    node_type: FlNodeType::ModelVersion,
                    id: parent.clone(),
                },
                target: FlNodeRef {
                    node_type: FlNodeType::ModelVersion,
                    id: format!("{}:v{}", self.model_name, round.round_number),
                },
                edge_type: FlEdgeType::DerivesFrom,
                weight: 1.0,
                properties: serde_json::json!({
                    "aggregation_algorithm": round.aggregation_algorithm,
                    "global_metrics": round.global_metrics,
                }),
            });
        }

        self.rounds.push(round);
    }

    /// Get the contribution history of a specific cohort.
    pub fn cohort_contributions(&self, cohort_hash: &str) -> Vec<(&FlRound, &CohortContribution)> {
        self.rounds
            .iter()
            .filter_map(|round| {
                round
                    .cohort_contributions
                    .get(cohort_hash)
                    .map(|contrib| (round, contrib))
            })
            .collect()
    }

    /// Get the model version lineage (chain of derivations).
    pub fn version_lineage(&self) -> Vec<&FlRound> {
        self.rounds.iter().collect()
    }

    /// Detect cohorts that haven't contributed recently (potential dropout).
    pub fn stale_cohorts(&self, threshold_hours: i64) -> Vec<&CohortInfo> {
        let cutoff = Utc::now() - chrono::Duration::hours(threshold_hours);
        self.cohorts
            .values()
            .filter(|c| c.last_participation.map(|ts| ts < cutoff).unwrap_or(true))
            .collect()
    }

    /// Check if a rollback is needed based on device rollback rate.
    pub fn should_rollback(&self, current_round: &FlRound, threshold: f64) -> bool {
        // In production, this would check actual device rollback reports
        // For now, check if worst cohort accuracy dropped significantly
        let prev_accuracy = self
            .rounds
            .iter()
            .rev()
            .nth(1) // second-to-last round
            .map(|r| r.global_metrics.accuracy);

        if let Some(prev) = prev_accuracy {
            let degradation = prev - current_round.global_metrics.accuracy;
            return degradation > threshold;
        }

        false
    }

    /// Get cohort formation recommendations based on contribution patterns.
    pub fn recommend_cohort_splits(&self) -> Vec<CohortSplitRecommendation> {
        let mut recommendations = Vec::new();

        for (cohort_hash, cohort) in &self.cohorts {
            // If cohort has very high variance in contributions, suggest splitting
            let contributions: Vec<f64> = self
                .cohort_contributions(cohort_hash)
                .iter()
                .map(|(_, c)| c.local_accuracy)
                .collect();

            if contributions.len() >= 5 {
                let mean: f64 = contributions.iter().sum::<f64>() / contributions.len() as f64;
                let variance: f64 = contributions
                    .iter()
                    .map(|x| (x - mean).powi(2))
                    .sum::<f64>()
                    / contributions.len() as f64;

                if variance > 0.01 {
                    // High variance — might benefit from splitting
                    recommendations.push(CohortSplitRecommendation {
                        cohort_hash: cohort_hash.clone(),
                        current_size: cohort.device_count,
                        variance,
                        suggested_splits: vec![
                            format!("{}_high_performers", cohort_hash),
                            format!("{}_low_performers", cohort_hash),
                        ],
                        reason: format!(
                            "High accuracy variance ({:.4}) suggests heterogeneous data distribution",
                            variance
                        ),
                    });
                }
            }
        }

        recommendations
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CohortSplitRecommendation {
    pub cohort_hash: String,
    pub current_size: u32,
    pub variance: f64,
    pub suggested_splits: Vec<String>,
    pub reason: String,
}
