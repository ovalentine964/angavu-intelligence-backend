// Credit Scoring Feedback Loop — Alama Score Improvement
// Score → Loan Outcome → Model Retrain → Score Calibration

use chrono::{DateTime, Duration as ChronoDuration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use tracing::{info, warn};

use super::drift_detection::BayesianCalibrator;

// ─── Credit Score Record ──────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditScoreRecord {
    pub score_id: String,
    pub worker_id: String,
    pub score: f64,      // 0.0 - 1.0 (probability of repayment)
    pub confidence: f64, // 0.0 - 1.0
    pub features: CreditFeatures,
    pub model_version: String,
    pub scored_at: DateTime<Utc>,
    pub cohort: String, // region|business_type
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditFeatures {
    pub transaction_count_90d: u32,
    pub daily_avg_revenue_bucket: String, // "low" | "medium" | "high"
    pub active_days_ratio: f64,           // 0.0 - 1.0
    pub revenue_volatility: f64,          // coefficient of variation
    pub product_diversity: u8,
    pub consistency_score: f64,
    pub repayment_history_count: u32,
    pub loan_count: u32,
    pub days_since_last_transaction: u32,
    pub region_economic_index: f64,
}

// ─── Loan Outcome ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoanOutcome {
    pub loan_id: String,
    pub worker_id: String,
    pub score_at_origination: f64,
    pub confidence_at_origination: f64,
    pub loan_amount_bucket: String, // "micro" | "small" | "medium"
    pub outcome: OutcomeType,
    pub days_to_outcome: u32,
    pub repaid_amount_ratio: f64, // 0.0 - 1.0+ (1.0 = fully repaid)
    pub recorded_at: DateTime<Utc>,
    pub model_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum OutcomeType {
    Repaid,
    Defaulted,
    PartiallyRepaid,
    Outstanding, // loan still active
}

// ─── Score Calibration ────────────────────────────────────────────────────

/// Tracks how well predicted scores match actual outcomes.
/// Used to recalibrate the Alama Score model.
#[derive(Debug, Clone)]
pub struct ScoreCalibration {
    /// Binned calibration data: (predicted_bin, outcomes)
    bins: Vec<CalibrationBin>,
    /// Number of bins
    n_bins: usize,
    /// Bayesian calibrator for overall model confidence
    overall_calibrator: BayesianCalibrator,
    /// Per-cohort calibrators
    cohort_calibrators: HashMap<String, BayesianCalibrator>,
}

#[derive(Debug, Clone)]
struct CalibrationBin {
    pub lower: f64,
    pub upper: f64,
    pub predicted_mean: f64,
    pub actual_mean: f64,
    pub count: u64,
}

impl ScoreCalibration {
    pub fn new(n_bins: usize) -> Self {
        let mut bins = Vec::with_capacity(n_bins);
        let bin_width = 1.0 / n_bins as f64;
        for i in 0..n_bins {
            bins.push(CalibrationBin {
                lower: i as f64 * bin_width,
                upper: (i + 1) as f64 * bin_width,
                predicted_mean: 0.0,
                actual_mean: 0.0,
                count: 0,
            });
        }

        Self {
            bins,
            n_bins,
            overall_calibrator: BayesianCalibrator::default_prior(),
            cohort_calibrators: HashMap::new(),
        }
    }

    /// Record a score-outcome pair for calibration tracking.
    pub fn record(&mut self, predicted_score: f64, actual_outcome: bool, cohort: &str) {
        // Update overall calibrator
        self.overall_calibrator.update(actual_outcome);

        // Update cohort calibrator
        let cohort_cal = self
            .cohort_calibrators
            .entry(cohort.to_string())
            .or_insert_with(BayesianCalibrator::default_prior);
        cohort_cal.update(actual_outcome);

        // Update bin
        let bin_idx = ((predicted_score * self.n_bins as f64) as usize).min(self.n_bins - 1);
        let bin = &mut self.bins[bin_idx];
        let n = bin.count as f64;
        bin.predicted_mean = (bin.predicted_mean * n + predicted_score) / (n + 1.0);
        bin.actual_mean =
            (bin.actual_mean * n + if actual_outcome { 1.0 } else { 0.0 }) / (n + 1.0);
        bin.count += 1;
    }

    /// Compute calibration error (Expected Calibration Error).
    /// Lower is better. < 0.05 is excellent, > 0.10 needs recalibration.
    pub fn expected_calibration_error(&self) -> f64 {
        let total: u64 = self.bins.iter().map(|b| b.count).sum();
        if total == 0 {
            return 0.0;
        }

        let ece: f64 = self
            .bins
            .iter()
            .map(|bin| {
                if bin.count == 0 {
                    return 0.0;
                }
                let weight = bin.count as f64 / total as f64;
                let gap = (bin.predicted_mean - bin.actual_mean).abs();
                weight * gap
            })
            .sum();

        ece
    }

    /// Check if recalibration is needed.
    pub fn needs_recalibration(&self) -> bool {
        self.expected_calibration_error() > 0.10
    }

    /// Get calibration data for visualization/analysis.
    pub fn calibration_data(&self) -> Vec<(f64, f64, u64)> {
        self.bins
            .iter()
            .map(|b| (b.predicted_mean, b.actual_mean, b.count))
            .collect()
    }

    /// Get calibrated probability for a cohort.
    pub fn cohort_calibrated_probability(&self, cohort: &str) -> f64 {
        self.cohort_calibrators
            .get(cohort)
            .map(|c| c.calibrated_probability())
            .unwrap_or(0.5)
    }

    /// Get overall calibrated probability.
    pub fn overall_calibrated_probability(&self) -> f64 {
        self.overall_calibrator.calibrated_probability()
    }
}

// ─── Credit Feedback Loop ─────────────────────────────────────────────────

/// The Credit Feedback Loop tracks the full lifecycle:
/// Score → Loan → Outcome → Calibration → Retrain → Score
pub struct CreditFeedbackLoop {
    /// Recent score records (for tracking outcomes)
    pending_scores: HashMap<String, CreditScoreRecord>, // score_id → record
    /// Completed loan outcomes
    outcomes: VecDeque<LoanOutcome>,
    /// Score calibration tracker
    calibration: ScoreCalibration,
    /// Model performance metrics
    performance: ModelPerformance,
    /// Maximum pending scores to track
    max_pending: usize,
    /// Maximum outcomes to retain
    max_outcomes: usize,
    /// Minimum outcomes before retraining evaluation
    min_outcomes_for_retrain: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelPerformance {
    pub auc_roc: f64,
    pub precision_at_80_recall: f64,
    pub default_rate_predicted: f64,
    pub default_rate_actual: f64,
    pub total_scored: u64,
    pub total_outcomes_recorded: u64,
    pub calibration_error: f64,
    pub last_retrain: Option<DateTime<Utc>>,
    pub model_version: String,
}

impl Default for ModelPerformance {
    fn default() -> Self {
        Self {
            auc_roc: 0.0,
            precision_at_80_recall: 0.0,
            default_rate_predicted: 0.0,
            default_rate_actual: 0.0,
            total_scored: 0,
            total_outcomes_recorded: 0,
            calibration_error: 0.0,
            last_retrain: None,
            model_version: "v0.1.0".to_string(),
        }
    }
}

impl CreditFeedbackLoop {
    pub fn new(max_pending: usize, max_outcomes: usize) -> Self {
        Self {
            pending_scores: HashMap::with_capacity(max_pending),
            outcomes: VecDeque::with_capacity(max_outcomes),
            calibration: ScoreCalibration::new(10),
            performance: ModelPerformance::default(),
            max_pending,
            max_outcomes,
            min_outcomes_for_retrain: 1000,
        }
    }

    /// Record a new credit score (score generated, waiting for outcome).
    pub fn record_score(&mut self, record: CreditScoreRecord) {
        if self.pending_scores.len() >= self.max_pending {
            // Evict oldest pending score
            if let Some(oldest_key) = self.pending_scores.keys().next().cloned() {
                self.pending_scores.remove(&oldest_key);
            }
        }
        self.pending_scores.insert(record.score_id.clone(), record);
        self.performance.total_scored += 1;
    }

    /// Record a loan outcome. Links back to the original score.
    pub fn record_outcome(&mut self, outcome: LoanOutcome) {
        // Update calibration with the score-outcome pair
        let actual = outcome.outcome == OutcomeType::Repaid;
        let cohort = self
            .pending_scores
            .get(&outcome.loan_id)
            .map(|s| s.cohort.clone())
            .unwrap_or_else(|| "unknown".to_string());

        self.calibration
            .record(outcome.score_at_origination, actual, &cohort);

        // Remove from pending
        self.pending_scores.remove(&outcome.loan_id);

        // Add to outcomes
        if self.outcomes.len() >= self.max_outcomes {
            self.outcomes.pop_front();
        }
        self.outcomes.push_back(outcome);
        self.performance.total_outcomes_recorded += 1;

        // Update performance metrics
        self.update_performance();
    }

    fn update_performance(&mut self) {
        // Update calibration error
        self.performance.calibration_error = self.calibration.expected_calibration_error();

        // Update actual default rate
        let defaults = self
            .outcomes
            .iter()
            .filter(|o| o.outcome == OutcomeType::Defaulted)
            .count();
        let total = self.outcomes.len();
        if total > 0 {
            self.performance.default_rate_actual = defaults as f64 / total as f64;
        }
    }

    /// Check if model retraining should be triggered.
    pub fn should_retrain(&self) -> RetrainDecision {
        if self.performance.total_outcomes_recorded < self.min_outcomes_for_retrain as u64 {
            return RetrainDecision {
                should_retrain: false,
                reason: format!(
                    "Not enough outcomes: {}/{}",
                    self.performance.total_outcomes_recorded, self.min_outcomes_for_retrain
                ),
                priority: RetrainPriority::Low,
            };
        }

        // Check calibration drift
        if self.calibration.needs_recalibration() {
            return RetrainDecision {
                should_retrain: true,
                reason: format!(
                    "Calibration error: {:.3} (threshold: 0.10)",
                    self.calibration.expected_calibration_error()
                ),
                priority: RetrainPriority::High,
            };
        }

        // Check if default rate shifted significantly
        let predicted_default = self.performance.default_rate_predicted;
        let actual_default = self.performance.default_rate_actual;
        if predicted_default > 0.0 {
            let shift = (actual_default - predicted_default).abs() / predicted_default;
            if shift > 0.25 {
                return RetrainDecision {
                    should_retrain: true,
                    reason: format!(
                        "Default rate shift: predicted={:.2}% actual={:.2}% (shift={:.1}%)",
                        predicted_default * 100.0,
                        actual_default * 100.0,
                        shift * 100.0,
                    ),
                    priority: RetrainPriority::High,
                };
            }
        }

        // Check time since last retrain
        if let Some(last_retrain) = self.performance.last_retrain {
            let age = Utc::now().signed_duration_since(last_retrain);
            if age > ChronoDuration::days(30) {
                return RetrainDecision {
                    should_retrain: true,
                    reason: format!("Last retrain was {} days ago", age.num_days()),
                    priority: RetrainPriority::Medium,
                };
            }
        }

        RetrainDecision {
            should_retrain: false,
            reason: "All checks passed".to_string(),
            priority: RetrainPriority::Low,
        }
    }

    /// Apply a retrained model. Resets calibration and updates version.
    pub fn apply_retrained_model(&mut self, version: String, baseline_auc: f64) {
        info!(
            "Applying retrained Alama model: {} (AUC: {:.3})",
            version, baseline_auc
        );
        self.performance.model_version = version;
        self.performance.auc_roc = baseline_auc;
        self.performance.last_retrain = Some(Utc::now());
        self.calibration = ScoreCalibration::new(10); // reset calibration
    }

    /// Get current calibration data.
    pub fn calibration_data(&self) -> Vec<(f64, f64, u64)> {
        self.calibration.calibration_data()
    }

    /// Get model performance metrics.
    pub fn performance(&self) -> &ModelPerformance {
        &self.performance
    }

    /// Get count of pending scores (awaiting outcomes).
    pub fn pending_count(&self) -> usize {
        self.pending_scores.len()
    }

    /// Get count of recorded outcomes.
    pub fn outcome_count(&self) -> usize {
        self.outcomes.len()
    }
}

// ─── Retrain Decision ─────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetrainDecision {
    pub should_retrain: bool,
    pub reason: String,
    pub priority: RetrainPriority,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, PartialOrd)]
pub enum RetrainPriority {
    Low,
    Medium,
    High,
    Critical,
}

// ─── Champion-Challenger Framework ────────────────────────────────────────

/// Manages the champion-challenger model evaluation pattern.
/// The champion is the current production model.
/// The challenger is a candidate replacement.
pub struct ChampionChallenger {
    pub champion_version: String,
    pub champion_auc: f64,
    pub challenger_version: Option<String>,
    pub challenger_auc: Option<f64>,
    pub evaluation_samples: u64,
    pub min_evaluation_samples: u64,
    pub min_improvement: f64, // minimum AUC improvement to promote
}

impl ChampionChallenger {
    pub fn new(champion_version: String, champion_auc: f64) -> Self {
        Self {
            champion_version,
            champion_auc,
            challenger_version: None,
            challenger_auc: None,
            evaluation_samples: 0,
            min_evaluation_samples: 500,
            min_improvement: 0.005,
        }
    }

    /// Start evaluating a challenger model.
    pub fn start_challenger(&mut self, version: String) {
        info!("Starting challenger evaluation: {}", version);
        self.challenger_version = Some(version);
        self.challenger_auc = None;
        self.evaluation_samples = 0;
    }

    /// Record evaluation results.
    pub fn record_evaluation(&mut self, champion_correct: bool, challenger_correct: bool) {
        self.evaluation_samples += 1;
        // In production: maintain running AUC calculation
        // Simplified here: track as running averages
    }

    /// Check if challenger should be promoted.
    pub fn should_promote_challenger(&self) -> Option<PromotionDecision> {
        let challenger = self.challenger_version.as_ref()?;
        let challenger_auc = self.challenger_auc?;

        if self.evaluation_samples < self.min_evaluation_samples {
            return Some(PromotionDecision {
                action: PromotionAction::ContinueEvaluation,
                reason: format!(
                    "Need more samples: {}/{}",
                    self.evaluation_samples, self.min_evaluation_samples
                ),
            });
        }

        if challenger_auc > self.champion_auc + self.min_improvement {
            Some(PromotionDecision {
                action: PromotionAction::Promote,
                reason: format!(
                    "Challenger {} (AUC: {:.3}) beats champion {} (AUC: {:.3}) by {:.3}",
                    challenger,
                    challenger_auc,
                    self.champion_version,
                    self.champion_auc,
                    challenger_auc - self.champion_auc,
                ),
            })
        } else {
            Some(PromotionDecision {
                action: PromotionAction::Reject,
                reason: format!(
                    "Challenger {} (AUC: {:.3}) does not beat champion {} (AUC: {:.3})",
                    challenger, challenger_auc, self.champion_version, self.champion_auc,
                ),
            })
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromotionDecision {
    pub action: PromotionAction,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PromotionAction {
    ContinueEvaluation,
    Promote,
    Reject,
}

// ─── Tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_score_calibration() {
        let mut cal = ScoreCalibration::new(10);

        // Record well-calibrated predictions
        for _ in 0..100 {
            cal.record(0.8, true, "nairobi|mboga");
        }
        for _ in 0..100 {
            cal.record(0.2, false, "nairobi|mboga");
        }

        // Should be well-calibrated
        let ece = cal.expected_calibration_error();
        assert!(
            ece < 0.1,
            "ECE should be low for well-calibrated predictions, got {}",
            ece
        );
    }

    #[test]
    fn test_credit_feedback_loop_lifecycle() {
        let mut loop_ = CreditFeedbackLoop::new(1000, 5000);

        // Record a score
        let score = CreditScoreRecord {
            score_id: "score-001".to_string(),
            worker_id: "wrk-001".to_string(),
            score: 0.75,
            confidence: 0.8,
            features: CreditFeatures {
                transaction_count_90d: 150,
                daily_avg_revenue_bucket: "medium".to_string(),
                active_days_ratio: 0.85,
                revenue_volatility: 0.3,
                product_diversity: 5,
                consistency_score: 0.8,
                repayment_history_count: 2,
                loan_count: 3,
                days_since_last_transaction: 1,
                region_economic_index: 0.7,
            },
            model_version: "v1.0.0".to_string(),
            scored_at: Utc::now(),
            cohort: "nairobi|mama_mboga".to_string(),
        };
        loop_.record_score(score);
        assert_eq!(loop_.pending_count(), 1);

        // Record loan outcome
        let outcome = LoanOutcome {
            loan_id: "score-001".to_string(),
            worker_id: "wrk-001".to_string(),
            score_at_origination: 0.75,
            confidence_at_origination: 0.8,
            loan_amount_bucket: "micro".to_string(),
            outcome: OutcomeType::Repaid,
            days_to_outcome: 30,
            repaid_amount_ratio: 1.0,
            recorded_at: Utc::now(),
            model_version: "v1.0.0".to_string(),
        };
        loop_.record_outcome(outcome);
        assert_eq!(loop_.pending_count(), 0);
        assert_eq!(loop_.outcome_count(), 1);
    }

    #[test]
    fn test_retrain_decision_insufficient_data() {
        let loop_ = CreditFeedbackLoop::new(1000, 5000);
        let decision = loop_.should_retrain();
        assert!(!decision.should_retrain);
        assert!(decision.reason.contains("Not enough outcomes"));
    }

    #[test]
    fn test_champion_challenger() {
        let mut cc = ChampionChallenger::new("v1.0".to_string(), 0.78);
        cc.start_challenger("v1.1".to_string());

        // Not enough samples yet
        let decision = cc.should_promote_challenger();
        // challenger_auc is None, so returns None
        assert!(decision.is_none());
    }
}
