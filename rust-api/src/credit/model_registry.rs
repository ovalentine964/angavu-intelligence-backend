// =============================================================================
// Angavu Intelligence — Credit Model Registry
// Version tracking, A/B testing, and rollback for credit scoring models.
//
// Addresses B2 P1 gaps:
// - G2.4: Model versioning/registry
// - G2.8: Champion/challenger framework
//
// Each model version tracks:
// - Training data hash (reproducibility)
// - Performance metrics (AUC-ROC, accuracy, calibration)
// - Worker type weights (β) learned from data
// - Deployment status (champion, challenger, archived)
// =============================================================================

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

/// Model version identifier
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct ModelVersionId(pub String);

impl ModelVersionId {
    pub fn new() -> Self {
        Self(format!(
            "mvr_{}",
            Uuid::new_v4().to_string()[..12].to_string()
        ))
    }
}

/// Deployment status for a model version
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentStatus {
    /// Currently serving all production traffic
    Champion,
    /// Receiving a fraction of traffic for A/B testing
    Challenger,
    /// Training/evaluation complete, not deployed
    Staged,
    /// Previously deployed, now archived
    Archived,
    /// Currently being trained
    Training,
    /// Training failed
    Failed,
}

/// A registered model version with full metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelVersion {
    pub id: ModelVersionId,
    pub version_semantic: String, // e.g., "1.2.0"
    pub algorithm: String,        // e.g., "logistic_regression_irls"
    pub deployment_status: DeploymentStatus,
    pub training_data_hash: String, // SHA-256 of training dataset
    pub training_samples: u64,
    pub feature_count: usize,
    pub trained_at: DateTime<Utc>,
    pub deployed_at: Option<DateTime<Utc>>,
    pub archived_at: Option<DateTime<Utc>>,
    /// Learned per-type weights (β) — replaces hardcoded type_weight()
    pub type_weights: HashMap<String, f64>,
    /// Model coefficients (logistic regression weights)
    pub coefficients: Vec<f64>,
    pub intercept: f64,
    /// Performance metrics on held-out test set
    pub metrics: ModelMetrics,
    /// Champion/challenger traffic split (0.0 = no traffic, 1.0 = all traffic)
    pub traffic_fraction: f64,
    /// Description / changelog
    pub description: String,
    /// Who triggered this version
    pub created_by: String,
}

/// Performance metrics for a model version
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelMetrics {
    pub auc_roc: f64,
    pub accuracy: f64,
    pub precision: f64,
    pub recall: f64,
    pub f1_score: f64,
    /// Hosmer-Lemeshow p-value (calibration quality, >0.05 = well-calibrated)
    pub hosmer_lemeshow_p: f64,
    /// Brier score (lower = better calibrated)
    pub brier_score: f64,
    /// Per-worker-type AUC-ROC
    pub type_auc: HashMap<String, f64>,
    /// KS statistic (max separation between good/bad distributions)
    pub ks_statistic: f64,
}

/// A/B test configuration between champion and challenger
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ABTestConfig {
    pub test_id: String,
    pub champion_id: ModelVersionId,
    pub challenger_id: ModelVersionId,
    pub challenger_traffic_pct: f64, // 0.0-1.0
    pub min_samples_per_arm: u64,
    pub significance_level: f64, // typically 0.05
    pub started_at: DateTime<Utc>,
    pub ends_at: Option<DateTime<Utc>>,
    pub status: ABTestStatus,
    /// Current observed metrics for each arm
    pub champion_observed: Option<ObservedMetrics>,
    pub challenger_observed: Option<ObservedMetrics>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ABTestStatus {
    Running,
    ChampionWins,
    ChallengerWins,
    NoSignificantDifference,
    Cancelled,
}

/// Observed production metrics during an A/B test
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObservedMetrics {
    pub total_predictions: u64,
    pub default_rate: f64,
    pub avg_score: f64,
    pub score_stddev: f64,
    pub approval_rate: f64,
    pub actual_default_rate: f64,
}

/// Model Registry — manages all model versions and A/B tests
pub struct ModelRegistry {
    versions: HashMap<ModelVersionId, ModelVersion>,
    ab_tests: HashMap<String, ABTestConfig>,
    /// Current champion model ID
    champion_id: Option<ModelVersionId>,
    /// Active challenger model IDs
    challenger_ids: Vec<ModelVersionId>,
}

impl ModelRegistry {
    pub fn new() -> Self {
        Self {
            versions: HashMap::new(),
            ab_tests: HashMap::new(),
            champion_id: None,
            challenger_ids: Vec::new(),
        }
    }

    /// Register a new model version
    pub fn register(&mut self, version: ModelVersion) -> ModelVersionId {
        let id = version.id.clone();
        tracing::info!(
            model_id = %id.0,
            version = %version.version_semantic,
            algorithm = %version.version_semantic,
            auc_roc = %version.metrics.auc_roc,
            "Model version registered"
        );
        self.versions.insert(id.clone(), version);
        id
    }

    /// Deploy a model version as champion (replaces current champion)
    pub fn deploy_champion(&mut self, model_id: &ModelVersionId) -> Result<(), String> {
        let version = self
            .versions
            .get_mut(model_id)
            .ok_or_else(|| format!("Model version {} not found", model_id.0))?;

        // Archive current champion
        if let Some(ref current_id) = self.champion_id.clone() {
            if let Some(current) = self.versions.get_mut(current_id) {
                current.deployment_status = DeploymentStatus::Archived;
                current.archived_at = Some(Utc::now());
                current.traffic_fraction = 0.0;
            }
        }

        version.deployment_status = DeploymentStatus::Champion;
        version.deployed_at = Some(Utc::now());
        version.traffic_fraction = 1.0;
        self.champion_id = Some(model_id.clone());

        tracing::info!(model_id = %model_id.0, "Deployed as champion");
        Ok(())
    }

    /// Start an A/B test between champion and challenger
    pub fn start_ab_test(
        &mut self,
        challenger_id: &ModelVersionId,
        traffic_pct: f64,
        min_samples: u64,
    ) -> Result<String, String> {
        let champion_id = self
            .champion_id
            .clone()
            .ok_or("No champion model deployed")?;

        if !self.versions.contains_key(challenger_id) {
            return Err(format!("Challenger {} not found", challenger_id.0));
        }

        // Update traffic splits
        if let Some(champion) = self.versions.get_mut(&champion_id) {
            champion.traffic_fraction = 1.0 - traffic_pct;
        }
        if let Some(challenger) = self.versions.get_mut(challenger_id) {
            challenger.deployment_status = DeploymentStatus::Challenger;
            challenger.deployed_at = Some(Utc::now());
            challenger.traffic_fraction = traffic_pct;
        }

        let test_id = format!("ab_{}", Uuid::new_v4().to_string()[..8].to_string());
        let config = ABTestConfig {
            test_id: test_id.clone(),
            champion_id: champion_id.clone(),
            challenger_id: challenger_id.clone(),
            challenger_traffic_pct: traffic_pct,
            min_samples_per_arm: min_samples,
            significance_level: 0.05,
            started_at: Utc::now(),
            ends_at: None,
            status: ABTestStatus::Running,
            champion_observed: None,
            challenger_observed: None,
        };

        self.ab_tests.insert(test_id.clone(), config);
        self.challenger_ids.push(challenger_id.clone());

        tracing::info!(
            test_id = %test_id,
            champion = %champion_id.0,
            challenger = %challenger_id.0,
            traffic_pct = %traffic_pct,
            "A/B test started"
        );

        Ok(test_id)
    }

    /// Route a prediction request to champion or challenger based on traffic split
    pub fn route_prediction(&self, org_id: &str) -> &ModelVersionId {
        // Deterministic routing based on org_id hash for consistency
        let hash = org_id.bytes().map(|b| b as u64).sum::<u64>();
        let bucket = (hash % 100) as f64 / 100.0;

        for challenger_id in &self.challenger_ids {
            if let Some(challenger) = self.versions.get(challenger_id) {
                if challenger.deployment_status == DeploymentStatus::Challenger
                    && bucket < challenger.traffic_fraction
                {
                    return challenger_id;
                }
            }
        }

        self.champion_id.as_ref().unwrap_or_else(|| {
            // Fallback: return first available version
            self.versions.keys().next().expect("No models registered")
        })
    }

    /// Get the current champion model
    pub fn champion(&self) -> Option<&ModelVersion> {
        self.champion_id
            .as_ref()
            .and_then(|id| self.versions.get(id))
    }

    /// Get a specific model version
    pub fn get(&self, id: &ModelVersionId) -> Option<&ModelVersion> {
        self.versions.get(id)
    }

    /// Get learned type weights from the champion model
    /// Falls back to default type_weight() if no champion is deployed
    pub fn type_weights(&self) -> HashMap<String, f64> {
        self.champion()
            .map(|m| m.type_weights.clone())
            .unwrap_or_default()
    }

    /// List all model versions
    pub fn list_versions(&self) -> Vec<&ModelVersion> {
        self.versions.values().collect()
    }

    /// List active A/B tests
    pub fn list_ab_tests(&self) -> Vec<&ABTestConfig> {
        self.ab_tests
            .values()
            .filter(|t| t.status == ABTestStatus::Running)
            .collect()
    }

    /// Record outcome for A/B test evaluation
    pub fn record_outcome(
        &mut self,
        test_id: &str,
        model_id: &ModelVersionId,
        predicted_score: f64,
        actual_default: bool,
    ) {
        if let Some(test) = self.ab_tests.get_mut(test_id) {
            let observed = if *model_id == test.champion_id {
                test.champion_observed
                    .get_or_insert_with(|| ObservedMetrics {
                        total_predictions: 0,
                        default_rate: 0.0,
                        avg_score: 0.0,
                        score_stddev: 0.0,
                        approval_rate: 0.0,
                        actual_default_rate: 0.0,
                    })
            } else if *model_id == test.challenger_id {
                test.challenger_observed
                    .get_or_insert_with(|| ObservedMetrics {
                        total_predictions: 0,
                        default_rate: 0.0,
                        avg_score: 0.0,
                        score_stddev: 0.0,
                        approval_rate: 0.0,
                        actual_default_rate: 0.0,
                    })
            } else {
                return;
            };

            // Update running statistics
            let n = observed.total_predictions as f64;
            observed.total_predictions += 1;
            observed.avg_score = (observed.avg_score * n + predicted_score) / (n + 1.0);
            if actual_default {
                observed.actual_default_rate = (observed.actual_default_rate * n + 1.0) / (n + 1.0);
            } else {
                observed.actual_default_rate = (observed.actual_default_rate * n) / (n + 1.0);
            }
        }
    }

    /// Check if any A/B test has reached significance
    pub fn check_ab_test_results(&mut self) -> Vec<String> {
        let mut completed = Vec::new();

        for (test_id, test) in self.ab_tests.iter_mut() {
            if test.status != ABTestStatus::Running {
                continue;
            }

            let champ = match &test.champion_observed {
                Some(m) if m.total_predictions >= test.min_samples_per_arm => m,
                _ => continue,
            };
            let chall = match &test.challenger_observed {
                Some(m) if m.total_predictions >= test.min_samples_per_arm => m,
                _ => continue,
            };

            // Simple z-test for difference in default rates
            let p1 = champ.actual_default_rate;
            let p2 = chall.actual_default_rate;
            let n1 = champ.total_predictions as f64;
            let n2 = chall.total_predictions as f64;

            let p_pool = (p1 * n1 + p2 * n2) / (n1 + n2);
            let se = if p_pool > 0.0 && p_pool < 1.0 {
                (p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2)).sqrt()
            } else {
                continue;
            };

            if se > 0.0 {
                let z = (p1 - p2).abs() / se;
                let significant = z > 1.96; // 95% confidence

                if significant {
                    // Lower default rate = better model
                    if p2 < p1 {
                        test.status = ABTestStatus::ChallengerWins;
                        tracing::info!(
                            test_id = %test_id,
                            champion_default_rate = %p1,
                            challenger_default_rate = %p2,
                            "A/B test: Challenger wins"
                        );
                    } else {
                        test.status = ABTestStatus::ChampionWins;
                        tracing::info!(
                            test_id = %test_id,
                            "A/B test: Champion retains"
                        );
                    }
                    completed.push(test_id.clone());
                }
            }
        }

        completed
    }
}

/// SQL migration for model registry tables
pub const MODEL_REGISTRY_MIGRATION: &str = r#"
CREATE TABLE IF NOT EXISTS model_versions (
    id VARCHAR(64) PRIMARY KEY,
    version_semantic VARCHAR(32) NOT NULL,
    algorithm VARCHAR(64) NOT NULL,
    deployment_status VARCHAR(32) NOT NULL DEFAULT 'staged',
    training_data_hash VARCHAR(128) NOT NULL,
    training_samples BIGINT NOT NULL DEFAULT 0,
    feature_count INT NOT NULL DEFAULT 0,
    trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deployed_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    type_weights JSONB NOT NULL DEFAULT '{}',
    coefficients JSONB NOT NULL DEFAULT '[]',
    intercept DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    metrics JSONB NOT NULL DEFAULT '{}',
    traffic_fraction DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    description TEXT NOT NULL DEFAULT '',
    created_by VARCHAR(128) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_versions_status ON model_versions(deployment_status);
CREATE INDEX IF NOT EXISTS idx_model_versions_algorithm ON model_versions(algorithm);

CREATE TABLE IF NOT EXISTS ab_tests (
    test_id VARCHAR(64) PRIMARY KEY,
    champion_id VARCHAR(64) NOT NULL REFERENCES model_versions(id),
    challenger_id VARCHAR(64) NOT NULL REFERENCES model_versions(id),
    challenger_traffic_pct DOUBLE PRECISION NOT NULL DEFAULT 0.1,
    min_samples_per_arm BIGINT NOT NULL DEFAULT 1000,
    significance_level DOUBLE PRECISION NOT NULL DEFAULT 0.05,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ends_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    champion_observed JSONB,
    challenger_observed JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ab_tests_status ON ab_tests(status);
"#;

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_model(id: &str, auc: f64) -> ModelVersion {
        ModelVersion {
            id: ModelVersionId(id.to_string()),
            version_semantic: "1.0.0".to_string(),
            algorithm: "logistic_regression".to_string(),
            deployment_status: DeploymentStatus::Staged,
            training_data_hash: "abc123".to_string(),
            training_samples: 10000,
            feature_count: 16,
            trained_at: Utc::now(),
            deployed_at: None,
            archived_at: None,
            type_weights: HashMap::new(),
            coefficients: vec![0.1; 16],
            intercept: -1.5,
            metrics: ModelMetrics {
                auc_roc: auc,
                accuracy: 0.8,
                precision: 0.75,
                recall: 0.7,
                f1_score: 0.72,
                hosmer_lemeshow_p: 0.3,
                brier_score: 0.15,
                type_auc: HashMap::new(),
                ks_statistic: 0.4,
            },
            traffic_fraction: 0.0,
            description: "Test model".to_string(),
            created_by: "test".to_string(),
        }
    }

    #[test]
    fn test_register_and_deploy() {
        let mut registry = ModelRegistry::new();
        let id = registry.register(make_test_model("v1", 0.82));
        registry.deploy_champion(&id).unwrap();

        let champion = registry.champion().unwrap();
        assert_eq!(champion.deployment_status, DeploymentStatus::Champion);
        assert_eq!(champion.traffic_fraction, 1.0);
    }

    #[test]
    fn test_ab_test_traffic_routing() {
        let mut registry = ModelRegistry::new();
        let champ_id = registry.register(make_test_model("champ", 0.80));
        let chall_id = registry.register(make_test_model("chall", 0.83));

        registry.deploy_champion(&champ_id).unwrap();
        registry.start_ab_test(&chall_id, 0.1, 100).unwrap();

        // Verify traffic split
        let champion = registry.get(&champ_id).unwrap();
        assert!((champion.traffic_fraction - 0.9).abs() < 0.01);
        let challenger = registry.get(&chall_id).unwrap();
        assert!((challenger.traffic_fraction - 0.1).abs() < 0.01);
    }

    #[test]
    fn test_champion_rollover() {
        let mut registry = ModelRegistry::new();
        let v1 = registry.register(make_test_model("v1", 0.80));
        let v2 = registry.register(make_test_model("v2", 0.85));

        registry.deploy_champion(&v1).unwrap();
        assert_eq!(registry.champion().unwrap().id.0, "v1");

        registry.deploy_champion(&v2).unwrap();
        assert_eq!(registry.champion().unwrap().id.0, "v2");
        assert_eq!(
            registry.get(&v1).unwrap().deployment_status,
            DeploymentStatus::Archived
        );
    }
}
