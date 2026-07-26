// Model Drift Detection Loop
// Monitors prediction accuracy over time, detects degradation, triggers retraining

use std::collections::VecDeque;
use std::time::Duration;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use tracing::{info, warn};

// ─── Drift Configuration ──────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct DriftConfig {
    /// Minimum samples before drift evaluation
    pub min_samples: usize,
    /// Rolling window size for accuracy tracking
    pub window_size: usize,
    /// Accuracy threshold below which drift is flagged (0.0 - 1.0)
    pub accuracy_threshold: f64,
    /// Relative degradation threshold (e.g., 0.15 = 15% drop from baseline)
    pub relative_degradation_threshold: f64,
    /// Confidence threshold below which model should be retrained
    pub confidence_threshold: f64,
    /// Minimum number of consecutive degraded windows to trigger retraining
    pub consecutive_degraded_windows: usize,
    /// Cooldown between retraining attempts
    pub retrain_cooldown: Duration,
}

impl Default for DriftConfig {
    fn default() -> Self {
        Self {
            min_samples: 100,
            window_size: 500,
            accuracy_threshold: 0.70,
            relative_degradation_threshold: 0.15,
            confidence_threshold: 0.50,
            consecutive_degraded_windows: 3,
            retrain_cooldown: Duration::from_secs(86400), // 24h
        }
    }
}

// ─── Prediction Record ────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PredictionRecord {
    pub prediction_id: String,
    pub model_version: String,
    pub predicted_value: f64,
    pub actual_value: Option<f64>, // None until outcome is known
    pub confidence: f64,
    pub feature_hash: String,     // anonymized feature vector hash
    pub cohort: String,
    pub timestamp: DateTime<Utc>,
    pub outcome_recorded_at: Option<DateTime<Utc>>,
}

// ─── Drift Report ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftReport {
    pub report_id: String,
    pub generated_at: DateTime<Utc>,
    pub drift_detected: bool,
    pub drift_type: Option<DriftType>,
    pub confidence: f64,
    pub current_accuracy: f64,
    pub baseline_accuracy: f64,
    pub relative_degradation: f64,
    pub consecutive_degraded_windows: usize,
    pub recommendation: DriftRecommendation,
    pub cohort_details: Vec<CohortDrift>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DriftType {
    /// Gradual accuracy decline over time
    GradualDrift,
    /// Sudden accuracy drop (data distribution shift)
    SuddenDrift,
    /// Model confidence calibration off
    CalibrationDrift,
    /// Specific cohort performing poorly
    CohortDrift { cohort: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DriftRecommendation {
    /// No action needed
    NoAction,
    /// Monitor closely
    Monitor,
    /// Recalibrate confidence scores
    Recalibrate,
    /// Trigger full model retraining
    Retrain,
    /// Rollback to previous model version
    Rollback,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CohortDrift {
    pub cohort: String,
    pub accuracy: f64,
    pub sample_size: usize,
    pub drift_detected: bool,
}

// ─── Accuracy Window ──────────────────────────────────────────────────────

#[derive(Debug, Clone)]
struct AccuracyWindow {
    samples: VecDeque<WindowSample>,
    max_size: usize,
}

#[derive(Debug, Clone)]
struct WindowSample {
    correct: bool,
    confidence: f64,
    timestamp: DateTime<Utc>,
}

impl AccuracyWindow {
    fn new(max_size: usize) -> Self {
        Self {
            samples: VecDeque::with_capacity(max_size),
            max_size,
        }
    }

    fn push(&mut self, correct: bool, confidence: f64) {
        if self.samples.len() >= self.max_size {
            self.samples.pop_front();
        }
        self.samples.push_back(WindowSample {
            correct,
            confidence,
            timestamp: Utc::now(),
        });
    }

    fn accuracy(&self) -> f64 {
        if self.samples.is_empty() {
            return 0.0;
        }
        let correct = self.samples.iter().filter(|s| s.correct).count();
        correct as f64 / self.samples.len() as f64
    }

    fn mean_confidence(&self) -> f64 {
        if self.samples.is_empty() {
            return 0.0;
        }
        let sum: f64 = self.samples.iter().map(|s| s.confidence).sum();
        sum / self.samples.len() as f64
    }

    fn len(&self) -> usize {
        self.samples.len()
    }

    fn is_empty(&self) -> bool {
        self.samples.is_empty()
    }
}

// ─── Drift Detector ───────────────────────────────────────────────────────

pub struct DriftDetector {
    config: DriftConfig,
    /// Global accuracy tracking window
    global_window: AccuracyWindow,
    /// Per-cohort accuracy tracking
    cohort_windows: std::collections::HashMap<String, AccuracyWindow>,
    /// Baseline accuracy (from initial model deployment)
    baseline_accuracy: f64,
    /// Number of consecutive windows that showed degradation
    consecutive_degraded: usize,
    /// Last retraining attempt timestamp
    last_retrain_attempt: Option<DateTime<Utc>>,
    /// Current model version
    current_model_version: String,
    /// History of drift reports
    report_history: VecDeque<DriftReport>,
    /// Whether we're currently in a rollback state
    is_rolled_back: bool,
}

impl DriftDetector {
    pub fn new(config: DriftConfig) -> Self {
        let window_size = config.window_size;
        Self {
            config,
            global_window: AccuracyWindow::new(window_size),
            cohort_windows: std::collections::HashMap::new(),
            baseline_accuracy: 0.85, // Set from initial model evaluation
            consecutive_degraded: 0,
            last_retrain_attempt: None,
            current_model_version: "v0.1.0".to_string(),
            report_history: VecDeque::with_capacity(100),
            is_rolled_back: false,
        }
    }

    /// Set the baseline accuracy from initial model evaluation.
    pub fn set_baseline(&mut self, accuracy: f64) {
        self.baseline_accuracy = accuracy;
        info!("Drift detector baseline set to {:.2}%", accuracy * 100.0);
    }

    /// Set the current model version.
    pub fn set_model_version(&mut self, version: String) {
        self.current_model_version = version;
    }

    /// Record a prediction outcome. Called when ground truth becomes available.
    pub fn record_outcome(&mut self, prediction: &PredictionRecord, actual: f64) {
        let correct = self.is_prediction_correct(prediction.predicted_value, actual, prediction.confidence);

        self.global_window.push(correct, prediction.confidence);

        // Per-cohort tracking
        let cohort_window = self.cohort_windows
            .entry(prediction.cohort.clone())
            .or_insert_with(|| AccuracyWindow::new(self.config.window_size));
        cohort_window.push(correct, prediction.confidence);
    }

    /// Check if a prediction is "correct" within tolerance.
    fn is_prediction_correct(&self, predicted: f64, actual: f64, confidence: f64) -> bool {
        // For classification (0/1): exact match
        if actual == 0.0 || actual == 1.0 {
            return (predicted >= 0.5) == (actual >= 0.5);
        }
        // For regression: within confidence-scaled tolerance
        let tolerance = 0.1 + (1.0 - confidence) * 0.2; // wider tolerance for low confidence
        (predicted - actual).abs() <= tolerance
    }

    /// Generate a drift report. Called by the slow OODA loop (daily).
    pub async fn generate_report(&self) -> DriftReport {
        let current_accuracy = self.global_window.accuracy();
        let current_confidence = self.global_window.mean_confidence();
        let relative_degradation = if self.baseline_accuracy > 0.0 {
            (self.baseline_accuracy - current_accuracy) / self.baseline_accuracy
        } else {
            0.0
        };

        let drift_detected = self.global_window.len() >= self.config.min_samples && (
            current_accuracy < self.config.accuracy_threshold ||
            relative_degradation > self.config.relative_degradation_threshold ||
            current_confidence < self.config.confidence_threshold
        );

        let drift_type = if drift_detected {
            if relative_degradation > 0.3 {
                Some(DriftType::SuddenDrift)
            } else if relative_degradation > self.config.relative_degradation_threshold {
                Some(DriftType::GradualDrift)
            } else if current_confidence < self.config.confidence_threshold {
                Some(DriftType::CalibrationDrift)
            } else {
                // Check if specific cohort is causing the issue
                self.find_worst_cohort().map(|c| DriftType::CohortDrift { cohort: c })
            }
        } else {
            None
        };

        let recommendation = self.determine_recommendation(
            drift_detected,
            &drift_type,
            relative_degradation,
            current_confidence,
        );

        // Build cohort details
        let cohort_details: Vec<CohortDrift> = self.cohort_windows.iter().map(|(cohort, window)| {
            CohortDrift {
                cohort: cohort.clone(),
                accuracy: window.accuracy(),
                sample_size: window.len(),
                drift_detected: window.accuracy() < self.config.accuracy_threshold,
            }
        }).collect();

        DriftReport {
            report_id: uuid::Uuid::new_v4().to_string(),
            generated_at: Utc::now(),
            drift_detected,
            drift_type,
            confidence: if self.global_window.len() >= self.config.min_samples {
                0.9
            } else {
                0.5
            },
            current_accuracy,
            baseline_accuracy: self.baseline_accuracy,
            relative_degradation,
            consecutive_degraded_windows: self.consecutive_degraded,
            recommendation,
            cohort_details,
        }
    }

    fn find_worst_cohort(&self) -> Option<String> {
        self.cohort_windows.iter()
            .filter(|(_, w)| w.len() >= 20) // minimum samples
            .min_by(|(_, a), (_, b)| a.accuracy().partial_cmp(&b.accuracy()).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(name, _)| name.clone())
    }

    fn determine_recommendation(
        &self,
        drift_detected: bool,
        drift_type: &Option<DriftType>,
        relative_degradation: f64,
        current_confidence: f64,
    ) -> DriftRecommendation {
        if !drift_detected {
            return DriftRecommendation::NoAction;
        }

        // Severe degradation: rollback
        if relative_degradation > 0.3 || current_confidence < 0.3 {
            return DriftRecommendation::Rollback;
        }

        // Multiple consecutive degraded windows: retrain
        if self.consecutive_degraded >= self.config.consecutive_degraded_windows {
            // Check cooldown
            if let Some(last) = self.last_retrain_attempt {
                if Utc::now().signed_duration_since(last).to_std().unwrap_or(Duration::ZERO) < self.config.retrain_cooldown {
                    return DriftRecommendation::Monitor;
                }
            }
            return DriftRecommendation::Retrain;
        }

        // Calibration issue
        if matches!(drift_type, Some(DriftType::CalibrationDrift)) {
            return DriftRecommendation::Recalibrate;
        }

        DriftRecommendation::Monitor
    }

    /// Apply a new model after retraining. Resets drift counters.
    pub fn apply_new_model(&mut self, version: String, baseline_accuracy: f64) {
        info!("Applying new model: {} (baseline: {:.2}%)", version, baseline_accuracy * 100.0);
        self.current_model_version = version;
        self.baseline_accuracy = baseline_accuracy;
        self.consecutive_degraded = 0;
        self.last_retrain_attempt = Some(Utc::now());
        self.is_rolled_back = false;
        // Keep global_window — we want to track how the new model performs
    }

    /// Rollback to a previous model version.
    pub fn rollback(&mut self, version: String) {
        warn!("Rolling back to model version: {}", version);
        self.current_model_version = version;
        self.consecutive_degraded = 0;
        self.is_rolled_back = true;
    }

    /// Get current model accuracy (for external queries).
    pub fn current_accuracy(&self) -> f64 {
        self.global_window.accuracy()
    }

    /// Get sample count in the current window.
    pub fn sample_count(&self) -> usize {
        self.global_window.len()
    }

    /// Whether the system is in a rolled-back state.
    pub fn is_rolled_back(&self) -> bool {
        self.is_rolled_back
    }
}

// ─── Bayesian Calibration ─────────────────────────────────────────────────

/// Bayesian calibration for credit score confidence.
/// Uses Beta distribution to model prediction reliability.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BayesianCalibrator {
    /// Prior correct predictions (Beta distribution alpha)
    pub alpha: f64,
    /// Prior incorrect predictions (Beta distribution beta)
    pub beta: f64,
    /// Number of observations
    pub n_observations: u64,
}

impl BayesianCalibrator {
    pub fn new(prior_alpha: f64, prior_beta: f64) -> Self {
        Self {
            alpha: prior_alpha,
            beta: prior_beta,
            n_observations: 0,
        }
    }

    /// Default prior: weakly informative (equivalent to 2 correct, 2 incorrect)
    pub fn default_prior() -> Self {
        Self::new(2.0, 2.0)
    }

    /// Update with a new observation.
    pub fn update(&mut self, correct: bool) {
        if correct {
            self.alpha += 1.0;
        } else {
            self.beta += 1.0;
        }
        self.n_observations += 1;
    }

    /// Get the calibrated probability (posterior mean).
    pub fn calibrated_probability(&self) -> f64 {
        self.alpha / (self.alpha + self.beta)
    }

    /// Get the 95% credible interval.
    pub fn credible_interval_95(&self) -> (f64, f64) {
        // Approximation using normal distribution for large n
        let mean = self.calibrated_probability();
        let n = self.alpha + self.beta;
        let variance = (self.alpha * self.beta) / (n * n * (n + 1.0));
        let std_dev = variance.sqrt();
        let z = 1.96; // 95%

        (
            (mean - z * std_dev).max(0.0),
            (mean + z * std_dev).min(1.0),
        )
    }

    /// Get the posterior distribution parameters.
    pub fn posterior_params(&self) -> (f64, f64) {
        (self.alpha, self.beta)
    }
}

// ─── Tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_accuracy_window() {
        let mut window = AccuracyWindow::new(5);
        assert!(window.is_empty());

        window.push(true, 0.9);
        window.push(true, 0.8);
        window.push(false, 0.6);
        assert_eq!(window.accuracy(), 2.0 / 3.0);
        assert_eq!(window.len(), 3);

        // Fill beyond max
        window.push(true, 0.9);
        window.push(true, 0.9);
        window.push(true, 0.9); // this pushes out the first
        assert_eq!(window.len(), 5);
        assert_eq!(window.accuracy(), 4.0 / 5.0); // first true is evicted
    }

    #[test]
    fn test_drift_detection_no_drift() {
        let mut detector = DriftDetector::new(DriftConfig {
            min_samples: 5,
            ..Default::default()
        });
        detector.set_baseline(0.85);

        // Record good predictions
        for i in 0..10 {
            let pred = PredictionRecord {
                prediction_id: format!("p{}", i),
                model_version: "v1".to_string(),
                predicted_value: 0.9,
                actual_value: Some(1.0),
                confidence: 0.85,
                feature_hash: "hash".to_string(),
                cohort: "nairobi|mboga".to_string(),
                timestamp: Utc::now(),
                outcome_recorded_at: Some(Utc::now()),
            };
            detector.record_outcome(&pred, 1.0);
        }

        // Use tokio runtime for async test
        let rt = tokio::runtime::Runtime::new().unwrap();
        let report = rt.block_on(detector.generate_report());
        assert!(!report.drift_detected);
    }

    #[test]
    fn test_drift_detection_with_degradation() {
        let mut detector = DriftDetector::new(DriftConfig {
            min_samples: 5,
            accuracy_threshold: 0.70,
            ..Default::default()
        });
        detector.set_baseline(0.85);

        // Record mostly wrong predictions
        for i in 0..20 {
            let pred = PredictionRecord {
                prediction_id: format!("p{}", i),
                model_version: "v1".to_string(),
                predicted_value: 0.9,
                actual_value: Some(0.0),
                confidence: 0.4,
                feature_hash: "hash".to_string(),
                cohort: "nairobi|mboga".to_string(),
                timestamp: Utc::now(),
                outcome_recorded_at: Some(Utc::now()),
            };
            detector.record_outcome(&pred, 0.0); // wrong
        }

        let rt = tokio::runtime::Runtime::new().unwrap();
        let report = rt.block_on(detector.generate_report());
        assert!(report.drift_detected);
        assert!(report.current_accuracy < 0.3);
    }

    #[test]
    fn test_bayesian_calibrator() {
        let mut cal = BayesianCalibrator::default_prior();
        assert_eq!(cal.calibrated_probability(), 0.5); // 2/(2+2)

        cal.update(true);
        cal.update(true);
        cal.update(true);
        assert_eq!(cal.calibrated_probability(), 5.0 / 7.0); // 5/(5+2)

        cal.update(false);
        let prob = cal.calibrated_probability();
        assert!((prob - 5.0 / 8.0).abs() < 1e-10);

        let (lo, hi) = cal.credible_interval_95();
        assert!(lo < prob);
        assert!(hi > prob);
    }

    #[test]
    fn test_model_version_tracking() {
        let mut detector = DriftDetector::new(DriftConfig::default());
        detector.set_model_version("v2.1.0".to_string());
        assert_eq!(detector.current_model_version, "v2.1.0");

        detector.rollback("v2.0.0".to_string());
        assert!(detector.is_rolled_back());
        assert_eq!(detector.current_model_version, "v2.0.0");

        detector.apply_new_model("v2.2.0".to_string(), 0.87);
        assert!(!detector.is_rolled_back());
    }
}


// === Council Integration: AggregationAdjustment ===
#[async_trait]
trait CircuitBreakerProtected: Send + Sync {
    type Response;
    type Error: Display;
    
    fn service_name(&self) -> &str;
    async fn execute_request(&self) -> Result<Self::Response, Self::Error>;
    fn registry(&self) -> &CircuitBreakerRegistry;
    
    async fn call(&self) -> Result<Self::Response, ProtectedCallError<Self::Error>> {
        // 1. Check circuit
        // 2. Execute request
        // 3. Record success/failure
    }
}
