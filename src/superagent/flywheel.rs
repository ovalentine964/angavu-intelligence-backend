//! Flywheel — User action signals → implicit feedback → model improvement
//!
//! Captures every user interaction as a signal, converts it into implicit
//! feedback, uses that feedback for regional model fine-tuning, and runs
//! A/B tests to measure improvement.
//!
//! ## Pipeline
//!
//! ```text
//! User Action → Signal Capture → Implicit Feedback → Feature Extraction
//!   → Regional Model Fine-Tuning → A/B Test → Winner Promotion
//! ```
//!
//! ## Flywheel Stages
//!
//! 1. **Cold Start** — Bootstrap with synthetic data + transfer learning
//! 2. **Data Collection** — Capture signals from all user interactions
//! 3. **Implicit Feedback** — Convert signals to reward/penalty signals
//! 4. **Regional Fine-Tuning** — Train per-region models from local data
//! 5. **A/B Testing** — Compare new model against baseline
//! 6. **Compound Growth** — More users → more data → better model → more users

use anyhow::Result;
use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────
// Signal Types
// ─────────────────────────────────────────────────────────────────────

/// Raw user action captured by the system.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionSignal {
    pub signal_id: Uuid,
    pub user_id: Uuid,
    pub org_id: Uuid,
    pub action_type: ActionType,
    pub context: SignalContext,
    pub timestamp: DateTime<Utc>,
}

/// Categories of user actions that generate signals.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum ActionType {
    /// User viewed a report or dashboard
    ViewReport,
    /// User clicked on a recommendation
    ClickRecommendation,
    /// User followed a recommendation (purchased, reordered, etc.)
    FollowRecommendation,
    /// User dismissed a recommendation
    DismissRecommendation,
    /// User generated a credit score
    RequestCreditScore,
    /// User sent a WhatsApp report
    SendWhatsAppReport,
    /// User synced device data
    SyncData,
    /// User exported data
    ExportData,
    /// User created an alert rule
    CreateAlertRule,
    /// User acknowledged an alert
    AcknowledgeAlert,
    /// User ignored an alert (timeout)
    IgnoreAlert,
    /// User set a revenue goal
    SetGoal,
    /// User achieved a goal
    AchieveGoal,
    /// Custom action
    Custom(String),
}

/// Contextual metadata attached to a signal.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalContext {
    pub region: String,
    pub product_category: Option<String>,
    pub device_type: String,
    pub session_duration_secs: Option<u64>,
    pub confidence_score: Option<f64>,
    pub metadata: serde_json::Value,
}

// ─────────────────────────────────────────────────────────────────────
// Implicit Feedback
// ─────────────────────────────────────────────────────────────────────

/// Derived feedback signal with a reward value in [-1.0, 1.0].
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImplicitFeedback {
    pub feedback_id: Uuid,
    pub user_id: Uuid,
    pub region: String,
    pub reward: f64,
    pub feedback_type: FeedbackType,
    pub features: Vec<f64>,
    pub derived_from: Uuid,
    pub created_at: DateTime<Utc>,
}

/// How the feedback was derived from the raw signal.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum FeedbackType {
    /// Positive: user followed recommendation, achieved goal, etc.
    Positive,
    /// Negative: user dismissed, ignored, or churned
    Negative,
    /// Neutral: informational action with no clear direction
    Neutral,
    /// Implicit: inferred from behavior (session length, repeat visits)
    Implicit,
}

// ─────────────────────────────────────────────────────────────────────
// A/B Testing
// ─────────────────────────────────────────────────────────────────────

/// An A/B test comparing a challenger model against a baseline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ABTest {
    pub test_id: Uuid,
    pub name: String,
    pub baseline_model: String,
    pub challenger_model: String,
    pub traffic_split: f64,
    pub metric: String,
    pub baseline_value: f64,
    pub challenger_value: f64,
    pub sample_size: usize,
    pub status: ABTestStatus,
    pub started_at: DateTime<Utc>,
    pub ended_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ABTestStatus {
    Running,
    BaselineWins,
    ChallengerWins,
    NoSignificantDifference,
    InsufficientData,
}

// ─────────────────────────────────────────────────────────────────────
// Regional Model
// ─────────────────────────────────────────────────────────────────────

/// A region-specific model with performance metrics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionalModel {
    pub model_id: Uuid,
    pub region: String,
    pub version: u32,
    pub weights: Vec<f64>,
    pub training_samples: usize,
    pub avg_reward: f64,
    pub created_at: DateTime<Utc>,
}

// ─────────────────────────────────────────────────────────────────────
// Flywheel Stage
// ─────────────────────────────────────────────────────────────────────

/// The current stage of the flywheel for a given region.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum FlywheelStage {
    ColdStart,
    DataCollection,
    ImplicitFeedback,
    RegionalFineTuning,
    ABTesting,
    CompoundGrowth,
}

// ─────────────────────────────────────────────────────────────────────
// Flywheel Engine
// ─────────────────────────────────────────────────────────────────────

/// The flywheel engine — converts user actions into model improvements.
pub struct FlywheelEngine {
    /// Recent signals awaiting feedback conversion
    signal_buffer: Arc<RwLock<Vec<ActionSignal>>>,
    /// Implicit feedback history per region
    feedback_by_region: Arc<RwLock<HashMap<String, Vec<ImplicitFeedback>>>>,
    /// Active regional models
    regional_models: Arc<RwLock<HashMap<String, RegionalModel>>>,
    /// Active A/B tests
    ab_tests: Arc<RwLock<Vec<ABTest>>>,
    /// Current flywheel stage per region
    stages: Arc<RwLock<HashMap<String, FlywheelStage>>>,
    /// Configuration
    config: FlywheelConfig,
}

/// Flywheel configuration.
#[derive(Debug, Clone)]
pub struct FlywheelConfig {
    /// Minimum signals before converting to feedback
    pub min_signals_for_feedback: usize,
    /// Minimum feedback before regional fine-tuning
    pub min_feedback_for_training: usize,
    /// Minimum training samples before A/B test
    pub min_samples_for_ab_test: usize,
    /// A/B test traffic split (fraction going to challenger)
    pub ab_test_traffic_split: f64,
    /// A/B test minimum sample size
    pub ab_test_min_sample_size: usize,
    /// Signal buffer flush interval
    pub flush_interval: Duration,
}

impl Default for FlywheelConfig {
    fn default() -> Self {
        Self {
            min_signals_for_feedback: 10,
            min_feedback_for_training: 100,
            min_samples_for_ab_test: 500,
            ab_test_traffic_split: 0.1,
            ab_test_min_sample_size: 1000,
            flush_interval: Duration::minutes(5),
        }
    }
}

impl FlywheelEngine {
    pub fn new() -> Self {
        Self {
            signal_buffer: Arc::new(RwLock::new(Vec::new())),
            feedback_by_region: Arc::new(RwLock::new(HashMap::new())),
            regional_models: Arc::new(RwLock::new(HashMap::new())),
            ab_tests: Arc::new(RwLock::new(Vec::new())),
            stages: Arc::new(RwLock::new(HashMap::new())),
            config: FlywheelConfig::default(),
        }
    }

    pub fn with_config(mut self, config: FlywheelConfig) -> Self {
        self.config = config;
        self
    }

    // ── Signal Capture ────────────────────────────────────────────────

    /// Ingest a raw user action signal.
    pub async fn capture_signal(&self, signal: ActionSignal) -> Result<()> {
        debug!(
            user_id = %signal.user_id,
            action = ?signal.action_type,
            region = %signal.context.region,
            "Signal captured"
        );

        let region = signal.context.region.clone();
        let mut buffer = self.signal_buffer.write().await;
        buffer.push(signal);

        // Trigger feedback conversion if buffer is large enough
        if buffer.len() >= self.config.min_signals_for_feedback {
            let signals: Vec<ActionSignal> = buffer.drain(..).collect();
            drop(buffer);
            self.convert_to_feedback(signals).await?;
        }

        // Update flywheel stage
        self.advance_stage(&region).await;

        Ok(())
    }

    // ── Implicit Feedback ─────────────────────────────────────────────

    /// Convert raw signals into implicit feedback with reward values.
    async fn convert_to_feedback(&self, signals: Vec<ActionSignal>) -> Result<()> {
        let mut by_region: HashMap<String, Vec<ActionSignal>> = HashMap::new();
        for signal in signals {
            by_region
                .entry(signal.context.region.clone())
                .or_default()
                .push(signal);
        }

        let mut feedback_map = self.feedback_by_region.write().await;

        for (region, region_signals) in by_region {
            for signal in region_signals {
                let reward = self.compute_reward(&signal);
                let features = self.extract_features(&signal);
                let feedback_type = if reward > 0.1 {
                    FeedbackType::Positive
                } else if reward < -0.1 {
                    FeedbackType::Negative
                } else {
                    FeedbackType::Neutral
                };

                let feedback = ImplicitFeedback {
                    feedback_id: Uuid::new_v4(),
                    user_id: signal.user_id,
                    region: region.clone(),
                    reward,
                    feedback_type,
                    features,
                    derived_from: signal.signal_id,
                    created_at: Utc::now(),
                };

                feedback_map
                    .entry(region.clone())
                    .or_default()
                    .push(feedback);
            }
        }

        Ok(())
    }

    /// Map a raw action type to a reward value in [-1.0, 1.0].
    fn compute_reward(&self, signal: &ActionSignal) -> f64 {
        match &signal.action_type {
            ActionType::FollowRecommendation => 1.0,
            ActionType::ClickRecommendation => 0.5,
            ActionType::AchieveGoal => 1.0,
            ActionType::SetGoal => 0.3,
            ActionType::ViewReport => 0.2,
            ActionType::RequestCreditScore => 0.3,
            ActionType::SendWhatsAppReport => 0.4,
            ActionType::SyncData => 0.2,
            ActionType::AcknowledgeAlert => 0.1,
            ActionType::DismissRecommendation => -0.3,
            ActionType::IgnoreAlert => -0.5,
            ActionType::ExportData => 0.1,
            ActionType::CreateAlertRule => 0.2,
            ActionType::Custom(_) => 0.0,
        }
    }

    /// Extract a feature vector from a signal for model training.
    fn extract_features(&self, signal: &ActionSignal) -> Vec<f64> {
        let mut features = Vec::with_capacity(8);

        // Action type encoding (one-hot-ish)
        let action_code = match &signal.action_type {
            ActionType::ViewReport => 0.1,
            ActionType::ClickRecommendation => 0.2,
            ActionType::FollowRecommendation => 0.3,
            ActionType::DismissRecommendation => 0.4,
            ActionType::RequestCreditScore => 0.5,
            ActionType::SendWhatsAppReport => 0.6,
            ActionType::SyncData => 0.7,
            ActionType::ExportData => 0.8,
            ActionType::CreateAlertRule => 0.85,
            ActionType::AcknowledgeAlert => 0.9,
            ActionType::IgnoreAlert => 0.95,
            ActionType::SetGoal => 0.15,
            ActionType::AchieveGoal => 0.25,
            ActionType::Custom(_) => 0.0,
        };
        features.push(action_code);

        // Confidence score (if available)
        features.push(signal.context.confidence_score.unwrap_or(0.5));

        // Session duration (normalized)
        features.push(
            signal
                .context
                .session_duration_secs
                .unwrap_or(0)
                .min(3600) as f64
                / 3600.0,
        );

        // Has product category
        features.push(if signal.context.product_category.is_some() {
            1.0
        } else {
            0.0
        });

        // Device type encoding
        let device_code = match signal.context.device_type.as_str() {
            "mobile" => 0.3,
            "desktop" => 0.6,
            "tablet" => 0.5,
            "api" => 0.9,
            _ => 0.4,
        };
        features.push(device_code);

        // Padding to fixed dimension
        features.resize(8, 0.0);
        features
    }

    // ── Regional Model Fine-Tuning ────────────────────────────────────

    /// Fine-tune a regional model using accumulated feedback.
    pub async fn fine_tune_region(&self, region: &str) -> Result<Option<RegionalModel>> {
        let feedback_map = self.feedback_by_region.read().await;
        let feedback = match feedback_map.get(region) {
            Some(f) if f.len() >= self.config.min_feedback_for_training => f,
            _ => {
                debug!(
                    region = %region,
                    "Insufficient feedback for fine-tuning"
                );
                return Ok(None);
            }
        };

        // Compute new weights as weighted average of features
        let feature_dim = feedback.first().map(|f| f.features.len()).unwrap_or(8);
        let mut weights = vec![0.0_f64; feature_dim];
        let mut total_weight = 0.0_f64;

        for fb in feedback {
            let w = fb.reward.abs() + 0.01; // Avoid zero-weight
            for (i, feat) in fb.features.iter().enumerate() {
                if i < feature_dim {
                    weights[i] += feat * fb.reward * w;
                }
            }
            total_weight += w;
        }

        if total_weight > 0.0 {
            for w in weights.iter_mut() {
                *w /= total_weight;
            }
        }

        // Compute average reward
        let avg_reward = feedback.iter().map(|f| f.reward).sum::<f64>() / feedback.len() as f64;

        // Get current version
        let models = self.regional_models.read().await;
        let version = models
            .get(region)
            .map(|m| m.version + 1)
            .unwrap_or(1);
        drop(models);

        let model = RegionalModel {
            model_id: Uuid::new_v4(),
            region: region.to_string(),
            version,
            weights,
            training_samples: feedback.len(),
            avg_reward,
            created_at: Utc::now(),
        };

        info!(
            region = %region,
            version = model.version,
            samples = model.training_samples,
            avg_reward = avg_reward,
            "Regional model fine-tuned"
        );

        let mut models = self.regional_models.write().await;
        models.insert(region.to_string(), model.clone());

        Ok(Some(model))
    }

    // ── A/B Testing ───────────────────────────────────────────────────

    /// Start an A/B test comparing the latest regional model against baseline.
    pub async fn start_ab_test(
        &self,
        region: &str,
        name: &str,
    ) -> Result<Option<ABTest>> {
        let models = self.regional_models.read().await;
        let challenger = match models.get(region) {
            Some(m) => m.clone(),
            None => {
                warn!(region = %region, "No regional model for A/B test");
                return Ok(None);
            }
        };

        // Check if there's already a running test for this region
        let tests = self.ab_tests.read().await;
        if tests.iter().any(|t| {
            t.status == ABTestStatus::Running
                && (t.baseline_model.contains(region) || t.challenger_model.contains(region))
        }) {
            debug!(region = %region, "A/B test already running");
            return Ok(None);
        }
        drop(tests);

        let test = ABTest {
            test_id: Uuid::new_v4(),
            name: name.to_string(),
            baseline_model: format!("{}-v{}", region, challenger.version.saturating_sub(1)),
            challenger_model: format!("{}-v{}", region, challenger.version),
            traffic_split: self.config.ab_test_traffic_split,
            metric: "avg_reward".to_string(),
            baseline_value: 0.0,
            challenger_value: challenger.avg_reward,
            sample_size: 0,
            status: ABTestStatus::Running,
            started_at: Utc::now(),
            ended_at: None,
        };

        info!(
            test_id = %test.test_id,
            region = %region,
            challenger_version = challenger.version,
            "A/B test started"
        );

        let mut tests = self.ab_tests.write().await;
        tests.push(test.clone());

        Ok(Some(test))
    }

    /// Record a measurement for an active A/B test.
    pub async fn record_ab_measurement(
        &self,
        test_id: Uuid,
        is_challenger: bool,
        reward: f64,
    ) -> Result<()> {
        let mut tests = self.ab_tests.write().await;
        if let Some(test) = tests.iter_mut().find(|t| t.test_id == test_id) {
            test.sample_size += 1;

            // Running average
            let n = test.sample_size as f64;
            if is_challenger {
                test.challenger_value =
                    test.challenger_value * (n - 1.0) / n + reward / n;
            } else {
                test.baseline_value =
                    test.baseline_value * (n - 1.0) / n + reward / n;
            }

            // Check for significance
            if test.sample_size >= self.config.ab_test_min_sample_size {
                let diff = test.challenger_value - test.baseline_value;
                // Simple significance check: >10% improvement
                if diff > 0.1 * test.baseline_value.abs().max(0.01) {
                    test.status = ABTestStatus::ChallengerWins;
                    test.ended_at = Some(Utc::now());
                    info!(
                        test_id = %test_id,
                        challenger = test.challenger_value,
                        baseline = test.baseline_value,
                        "A/B test: challenger wins"
                    );
                } else if diff < -0.1 * test.baseline_value.abs().max(0.01) {
                    test.status = ABTestStatus::BaselineWins;
                    test.ended_at = Some(Utc::now());
                    info!(
                        test_id = %test_id,
                        challenger = test.challenger_value,
                        baseline = test.baseline_value,
                        "A/B test: baseline wins"
                    );
                } else if test.sample_size >= self.config.ab_test_min_sample_size * 2 {
                    test.status = ABTestStatus::NoSignificantDifference;
                    test.ended_at = Some(Utc::now());
                    info!(test_id = %test_id, "A/B test: no significant difference");
                }
            }
        }

        Ok(())
    }

    // ── Stage Advancement ─────────────────────────────────────────────

    /// Advance the flywheel stage for a region based on data maturity.
    async fn advance_stage(&self, region: &str) {
        let feedback_map = self.feedback_by_region.read().await;
        let feedback_count = feedback_map
            .get(region)
            .map(|f| f.len())
            .unwrap_or(0);

        let models = self.regional_models.read().await;
        let has_model = models.contains_key(region);

        let tests = self.ab_tests.read().await;
        let has_test = tests.iter().any(|t| {
            t.baseline_model.contains(region) || t.challenger_model.contains(region)
        });

        let stage = if feedback_count == 0 {
            FlywheelStage::ColdStart
        } else if feedback_count < self.config.min_feedback_for_training {
            FlywheelStage::DataCollection
        } else if !has_model {
            FlywheelStage::ImplicitFeedback
        } else if !has_test {
            FlywheelStage::RegionalFineTuning
        } else if tests.iter().any(|t| {
            t.status == ABTestStatus::Running
                && (t.baseline_model.contains(region) || t.challenger_model.contains(region))
        }) {
            FlywheelStage::ABTesting
        } else {
            FlywheelStage::CompoundGrowth
        };

        let mut stages = self.stages.write().await;
        stages.insert(region.to_string(), stage);
    }

    // ── Queries ───────────────────────────────────────────────────────

    /// Get the current flywheel stage for a region.
    pub async fn get_stage(&self, region: &str) -> FlywheelStage {
        let stages = self.stages.read().await;
        stages
            .get(region)
            .cloned()
            .unwrap_or(FlywheelStage::ColdStart)
    }

    /// Get all regional models.
    pub async fn get_models(&self) -> HashMap<String, RegionalModel> {
        self.regional_models.read().await.clone()
    }

    /// Get all A/B tests.
    pub async fn get_ab_tests(&self) -> Vec<ABTest> {
        self.ab_tests.read().await.clone()
    }

    /// Get feedback count for a region.
    pub async fn feedback_count(&self, region: &str) -> usize {
        self.feedback_by_region
            .read()
            .await
            .get(region)
            .map(|f| f.len())
            .unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_signal(action: ActionType, region: &str) -> ActionSignal {
        ActionSignal {
            signal_id: Uuid::new_v4(),
            user_id: Uuid::new_v4(),
            org_id: Uuid::new_v4(),
            action_type: action,
            context: SignalContext {
                region: region.to_string(),
                product_category: Some("groceries".to_string()),
                device_type: "mobile".to_string(),
                session_duration_secs: Some(120),
                confidence_score: Some(0.8),
                metadata: serde_json::json!({}),
            },
            timestamp: Utc::now(),
        }
    }

    #[tokio::test]
    async fn test_signal_capture_and_feedback() {
        let engine = FlywheelEngine::new().with_config(FlywheelConfig {
            min_signals_for_feedback: 3,
            min_feedback_for_training: 2,
            ..Default::default()
        });

        for _ in 0..4 {
            engine
                .capture_signal(make_signal(ActionType::FollowRecommendation, "nairobi"))
                .await
                .unwrap();
        }

        let count = engine.feedback_count("nairobi").await;
        assert!(count >= 2, "Expected at least 2 feedback entries, got {}", count);

        let stage = engine.get_stage("nairobi").await;
        assert_ne!(stage, FlywheelStage::ColdStart);
    }

    #[tokio::test]
    async fn test_reward_computation() {
        let engine = FlywheelEngine::new();

        let positive = make_signal(ActionType::FollowRecommendation, "test");
        assert!(engine.compute_reward(&positive) > 0.5);

        let negative = make_signal(ActionType::IgnoreAlert, "test");
        assert!(engine.compute_reward(&negative) < -0.3);
    }
}
