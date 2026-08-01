// credit/fairness.rs
//
// Fairness Testing Module for Credit Scoring Model Validation
//
// EU AI Act (2026) and anti-discrimination law require that credit scoring
// models do not produce systematically biased outcomes across protected groups.
//
// Three fairness criteria are tested:
//   1. Demographic Parity: P(Ŷ=1|A=a) ≈ P(Ŷ=1|A=b) across worker types
//   2. Equalized Odds: P(Ŷ=1|Y=y,A=a) ≈ P(Ŷ=1|Y=y,A=b) across regions
//   3. Predictive Parity: P(Y=1|Ŷ=1,A=a) ≈ P(Y=1|Ŷ=1,A=b) across groups
//
// All tests use statistical significance testing (z-test for proportions)
// with configurable thresholds.
//
// Reference: Hardt et al. (2016), "Equality of Opportunity in Supervised Learning"
//            Chouldechova (2017), "Fair prediction with disparate impact"

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Fairness test configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FairnessConfig {
    /// Maximum allowed difference in positive prediction rate (demographic parity)
    pub demographic_parity_threshold: f64,
    /// Maximum allowed difference in TPR/FPR (equalized odds)
    pub equalized_odds_threshold: f64,
    /// Maximum allowed difference in PPV (predictive parity)
    pub predictive_parity_threshold: f64,
    /// Significance level for z-tests
    pub significance_level: f64,
    /// Minimum group size to include in analysis
    pub min_group_size: usize,
}

impl Default for FairnessConfig {
    fn default() -> Self {
        Self {
            // EU AI Act "meaningful explanations" standard suggests
            // 80% rule (4/5ths rule) from US EEOC guidelines
            demographic_parity_threshold: 0.20, // max 20% difference
            equalized_odds_threshold: 0.15,     // max 15% difference in TPR/FPR
            predictive_parity_threshold: 0.10,  // max 10% difference in PPV
            significance_level: 0.05,           // 95% confidence
            min_group_size: 30,                 // minimum for statistical validity
        }
    }
}

/// Complete fairness audit report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FairnessReport {
    /// Demographic parity results (by worker type)
    pub demographic_parity: DemographicParityResult,
    /// Equalized odds results (by region)
    pub equalized_odds: EqualizedOddsResult,
    /// Predictive parity results (by group)
    pub predictive_parity: PredictiveParityResult,
    /// Overall fairness verdict
    pub passed: bool,
    /// Summary of all violations
    pub violations: Vec<FairnessViolation>,
    /// Warnings (non-critical issues)
    pub warnings: Vec<String>,
    /// Audit timestamp (Unix seconds)
    pub computed_at: u64,
    /// Configuration used
    pub config: FairnessConfig,
}

/// A fairness violation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FairnessViolation {
    /// Type of fairness violated
    pub violation_type: FairnessCriterion,
    /// Severity of the violation
    pub severity: ViolationSeverity,
    /// Groups compared
    pub groups: (String, String),
    /// Observed difference
    pub observed_difference: f64,
    /// Threshold that was exceeded
    pub threshold: f64,
    /// Human-readable description
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FairnessCriterion {
    DemographicParity,
    EqualizedOdds,
    PredictiveParity,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ViolationSeverity {
    /// Exceeds threshold but within 1.5x — monitoring recommended
    Warning,
    /// Exceeds threshold by 1.5x — remediation recommended
    Moderate,
    /// Exceeds threshold by 2x+ — immediate action required
    Critical,
}

// ── Demographic Parity ──────────────────────────────────────────────────────

/// Demographic parity: P(Ŷ=1|A=a) should be similar across groups.
/// Tested across worker types (vendor, farmer, boda_boda, etc.)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DemographicParityResult {
    /// Per-group positive prediction rates
    pub group_rates: HashMap<String, GroupRate>,
    /// Pairwise comparisons between groups
    pub pairwise_comparisons: Vec<PairwiseComparison>,
    /// Whether demographic parity is satisfied
    pub passed: bool,
    /// Disparate impact ratio (min rate / max rate)
    pub disparate_impact_ratio: f64,
}

/// Prediction rate for a single group
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupRate {
    pub group_name: String,
    pub n_total: usize,
    pub n_positive: usize,
    pub positive_rate: f64,
    pub standard_error: f64,
}

/// Pairwise comparison between two groups
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PairwiseComparison {
    pub group_a: String,
    pub group_b: String,
    pub rate_a: f64,
    pub rate_b: f64,
    pub difference: f64,
    pub z_score: f64,
    pub p_value: f64,
    pub is_significant: bool,
    pub violates_threshold: bool,
}

/// Compute demographic parity across worker types.
///
/// # Arguments
/// * `predictions` - (worker_type, predicted_label) pairs
/// * `config` - Fairness configuration
pub fn compute_demographic_parity(
    predictions: &[(String, u8)],
    config: &FairnessConfig,
) -> DemographicParityResult {
    // Group by worker type
    let mut groups: HashMap<String, Vec<u8>> = HashMap::new();
    for (group, pred) in predictions {
        groups.entry(group.clone()).or_default().push(*pred);
    }

    // Compute per-group rates
    let mut group_rates: HashMap<String, GroupRate> = HashMap::new();
    for (group_name, preds) in &groups {
        let n = preds.len();
        if n < config.min_group_size {
            continue; // skip groups too small for statistical validity
        }
        let n_pos = preds.iter().filter(|&&p| p == 1).count();
        let rate = n_pos as f64 / n as f64;
        let se = (rate * (1.0 - rate) / n as f64).sqrt();

        group_rates.insert(
            group_name.clone(),
            GroupRate {
                group_name: group_name.clone(),
                n_total: n,
                n_positive: n_pos,
                positive_rate: rate,
                standard_error: se,
            },
        );
    }

    // Pairwise comparisons
    let group_names: Vec<&String> = group_rates.keys().collect();
    let mut pairwise = Vec::new();
    let mut all_passed = true;
    let mut min_rate = f64::MAX;
    let mut max_rate = f64::MIN;

    for i in 0..group_names.len() {
        let rate_a = &group_rates[*group_names[i]];
        min_rate = min_rate.min(rate_a.positive_rate);
        max_rate = max_rate.max(rate_a.positive_rate);

        for j in (i + 1)..group_names.len() {
            let rate_b = &group_rates[*group_names[j]];

            let diff = (rate_a.positive_rate - rate_b.positive_rate).abs();
            let se_diff = (rate_a.standard_error.powi(2) + rate_b.standard_error.powi(2)).sqrt();
            let z = if se_diff > 0.0 { diff / se_diff } else { 0.0 };
            let p_value = 2.0 * (1.0 - standard_normal_cdf(z));
            let is_significant = p_value < config.significance_level;
            let violates = diff > config.demographic_parity_threshold && is_significant;

            if violates {
                all_passed = false;
            }

            pairwise.push(PairwiseComparison {
                group_a: rate_a.group_name.clone(),
                group_b: rate_b.group_name.clone(),
                rate_a: rate_a.positive_rate,
                rate_b: rate_b.positive_rate,
                difference: diff,
                z_score: z,
                p_value,
                is_significant,
                violates_threshold: violates,
            });
        }
    }

    let disparate_impact = if max_rate > 0.0 {
        min_rate / max_rate
    } else {
        1.0
    };

    DemographicParityResult {
        group_rates,
        pairwise_comparisons: pairwise,
        passed: all_passed,
        disparate_impact_ratio: disparate_impact,
    }
}

// ── Equalized Odds ──────────────────────────────────────────────────────────

/// Equalized Odds: P(Ŷ=1|Y=y,A=a) should be similar across groups.
/// Tested across regions for both TPR (Y=1) and FPR (Y=0).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EqualizedOddsResult {
    /// Per-group TPR and FPR
    pub group_metrics: HashMap<String, GroupOddsMetrics>,
    /// TPR comparisons across regions
    pub tpr_comparisons: Vec<PairwiseComparison>,
    /// FPR comparisons across regions
    pub fpr_comparisons: Vec<PairwiseComparison>,
    /// Whether equalized odds is satisfied
    pub passed: bool,
}

/// TPR/FPR metrics for a single group
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupOddsMetrics {
    pub group_name: String,
    /// True Positive Rate: P(Ŷ=1|Y=1)
    pub tpr: f64,
    /// False Positive Rate: P(Ŷ=1|Y=0)
    pub fpr: f64,
    /// Number of actual positives
    pub n_actual_positive: usize,
    /// Number of actual negatives
    pub n_actual_negative: usize,
    pub tpr_standard_error: f64,
    pub fpr_standard_error: f64,
}

/// Compute equalized odds across regions.
///
/// # Arguments
/// * `predictions` - (region, predicted_label, actual_label) tuples
/// * `config` - Fairness configuration
pub fn compute_equalized_odds(
    predictions: &[(String, u8, u8)],
    config: &FairnessConfig,
) -> EqualizedOddsResult {
    // Group by region
    let mut groups: HashMap<String, Vec<(u8, u8)>> = HashMap::new();
    for (region, pred, actual) in predictions {
        groups.entry(region.clone()).or_default().push((*pred, *actual));
    }

    // Compute per-group TPR and FPR
    let mut group_metrics: HashMap<String, GroupOddsMetrics> = HashMap::new();
    for (region, pairs) in &groups {
        let actual_pos: Vec<&(u8, u8)> = pairs.iter().filter(|(_, a)| *a == 1).collect();
        let actual_neg: Vec<&(u8, u8)> = pairs.iter().filter(|(_, a)| *a == 0).collect();

        if actual_pos.len() < config.min_group_size || actual_neg.len() < config.min_group_size {
            continue;
        }

        let tp = actual_pos.iter().filter(|(p, _)| *p == 1).count();
        let fp = actual_neg.iter().filter(|(p, _)| *p == 1).count();

        let tpr = tp as f64 / actual_pos.len() as f64;
        let fpr = fp as f64 / actual_neg.len() as f64;

        let tpr_se = (tpr * (1.0 - tpr) / actual_pos.len() as f64).sqrt();
        let fpr_se = (fpr * (1.0 - fpr) / actual_neg.len() as f64).sqrt();

        group_metrics.insert(
            region.clone(),
            GroupOddsMetrics {
                group_name: region.clone(),
                tpr,
                fpr,
                n_actual_positive: actual_pos.len(),
                n_actual_negative: actual_neg.len(),
                tpr_standard_error: tpr_se,
                fpr_standard_error: fpr_se,
            },
        );
    }

    // Pairwise TPR and FPR comparisons
    let group_names: Vec<&String> = group_metrics.keys().collect();
    let mut tpr_comparisons = Vec::new();
    let mut fpr_comparisons = Vec::new();
    let mut all_passed = true;

    for i in 0..group_names.len() {
        let metrics_a = &group_metrics[*group_names[i]];
        for j in (i + 1)..group_names.len() {
            let metrics_b = &group_metrics[*group_names[j]];

            // TPR comparison
            let tpr_diff = (metrics_a.tpr - metrics_b.tpr).abs();
            let tpr_se_diff =
                (metrics_a.tpr_standard_error.powi(2) + metrics_b.tpr_standard_error.powi(2)).sqrt();
            let tpr_z = if tpr_se_diff > 0.0 {
                tpr_diff / tpr_se_diff
            } else {
                0.0
            };
            let tpr_p = 2.0 * (1.0 - standard_normal_cdf(tpr_z));
            let tpr_violates =
                tpr_diff > config.equalized_odds_threshold && tpr_p < config.significance_level;

            tpr_comparisons.push(PairwiseComparison {
                group_a: metrics_a.group_name.clone(),
                group_b: metrics_b.group_name.clone(),
                rate_a: metrics_a.tpr,
                rate_b: metrics_b.tpr,
                difference: tpr_diff,
                z_score: tpr_z,
                p_value: tpr_p,
                is_significant: tpr_p < config.significance_level,
                violates_threshold: tpr_violates,
            });

            // FPR comparison
            let fpr_diff = (metrics_a.fpr - metrics_b.fpr).abs();
            let fpr_se_diff =
                (metrics_a.fpr_standard_error.powi(2) + metrics_b.fpr_standard_error.powi(2)).sqrt();
            let fpr_z = if fpr_se_diff > 0.0 {
                fpr_diff / fpr_se_diff
            } else {
                0.0
            };
            let fpr_p = 2.0 * (1.0 - standard_normal_cdf(fpr_z));
            let fpr_violates =
                fpr_diff > config.equalized_odds_threshold && fpr_p < config.significance_level;

            fpr_comparisons.push(PairwiseComparison {
                group_a: metrics_a.group_name.clone(),
                group_b: metrics_b.group_name.clone(),
                rate_a: metrics_a.fpr,
                rate_b: metrics_b.fpr,
                difference: fpr_diff,
                z_score: fpr_z,
                p_value: fpr_p,
                is_significant: fpr_p < config.significance_level,
                violates_threshold: fpr_violates,
            });

            if tpr_violates || fpr_violates {
                all_passed = false;
            }
        }
    }

    EqualizedOddsResult {
        group_metrics,
        tpr_comparisons,
        fpr_comparisons,
        passed: all_passed,
    }
}

// ── Predictive Parity ───────────────────────────────────────────────────────

/// Predictive Parity: P(Y=1|Ŷ=1,A=a) should be similar across groups.
/// i.e., the precision of the model should be similar across groups.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PredictiveParityResult {
    /// Per-group precision (PPV)
    pub group_precision: HashMap<String, GroupPrecision>,
    /// Pairwise precision comparisons
    pub pairwise_comparisons: Vec<PairwiseComparison>,
    /// Whether predictive parity is satisfied
    pub passed: bool,
}

/// Precision metrics for a single group
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupPrecision {
    pub group_name: String,
    /// Positive Predictive Value: P(Y=1|Ŷ=1)
    pub precision: f64,
    /// Number of predicted positives
    pub n_predicted_positive: usize,
    /// True positives among predicted positives
    pub n_true_positive: usize,
    pub standard_error: f64,
}

/// Compute predictive parity across groups.
///
/// # Arguments
/// * `predictions` - (group, predicted_label, actual_label) tuples
/// * `config` - Fairness configuration
pub fn compute_predictive_parity(
    predictions: &[(String, u8, u8)],
    config: &FairnessConfig,
) -> PredictiveParityResult {
    // Group by group name
    let mut groups: HashMap<String, Vec<(u8, u8)>> = HashMap::new();
    for (group, pred, actual) in predictions {
        groups.entry(group.clone()).or_default().push((*pred, *actual));
    }

    // Compute per-group precision
    let mut group_precision: HashMap<String, GroupPrecision> = HashMap::new();
    for (group_name, pairs) in &groups {
        let predicted_pos: Vec<&(u8, u8)> = pairs.iter().filter(|(p, _)| *p == 1).collect();

        if predicted_pos.len() < config.min_group_size {
            continue;
        }

        let tp = predicted_pos.iter().filter(|(_, a)| *a == 1).count();
        let precision = tp as f64 / predicted_pos.len() as f64;
        let se = (precision * (1.0 - precision) / predicted_pos.len() as f64).sqrt();

        group_precision.insert(
            group_name.clone(),
            GroupPrecision {
                group_name: group_name.clone(),
                precision,
                n_predicted_positive: predicted_pos.len(),
                n_true_positive: tp,
                standard_error: se,
            },
        );
    }

    // Pairwise comparisons
    let group_names: Vec<&String> = group_precision.keys().collect();
    let mut pairwise = Vec::new();
    let mut all_passed = true;

    for i in 0..group_names.len() {
        let prec_a = &group_precision[*group_names[i]];
        for j in (i + 1)..group_names.len() {
            let prec_b = &group_precision[*group_names[j]];

            let diff = (prec_a.precision - prec_b.precision).abs();
            let se_diff = (prec_a.standard_error.powi(2) + prec_b.standard_error.powi(2)).sqrt();
            let z = if se_diff > 0.0 { diff / se_diff } else { 0.0 };
            let p_value = 2.0 * (1.0 - standard_normal_cdf(z));
            let is_significant = p_value < config.significance_level;
            let violates = diff > config.predictive_parity_threshold && is_significant;

            if violates {
                all_passed = false;
            }

            pairwise.push(PairwiseComparison {
                group_a: prec_a.group_name.clone(),
                group_b: prec_b.group_name.clone(),
                rate_a: prec_a.precision,
                rate_b: prec_b.precision,
                difference: diff,
                z_score: z,
                p_value,
                is_significant,
                violates_threshold: violates,
            });
        }
    }

    PredictiveParityResult {
        group_precision,
        pairwise_comparisons: pairwise,
        passed: all_passed,
    }
}

// ── Full Fairness Audit ─────────────────────────────────────────────────────

/// Run a complete fairness audit on a credit scoring model.
///
/// # Arguments
/// * `worker_type_predictions` - (worker_type, predicted_label) for demographic parity
/// * `region_outcomes` - (region, predicted_label, actual_label) for equalized odds
/// * `group_outcomes` - (group, predicted_label, actual_label) for predictive parity
/// * `config` - Fairness configuration
pub fn run_fairness_audit(
    worker_type_predictions: &[(String, u8)],
    region_outcomes: &[(String, u8, u8)],
    group_outcomes: &[(String, u8, u8)],
    config: &FairnessConfig,
) -> FairnessReport {
    let dp = compute_demographic_parity(worker_type_predictions, config);
    let eo = compute_equalized_odds(region_outcomes, config);
    let pp = compute_predictive_parity(group_outcomes, config);

    let mut violations = Vec::new();
    let mut warnings = Vec::new();

    // Collect demographic parity violations
    for comp in &dp.pairwise_comparisons {
        if comp.violates_threshold {
            let severity = classify_severity(comp.difference, config.demographic_parity_threshold);
            violations.push(FairnessViolation {
                violation_type: FairnessCriterion::DemographicParity,
                severity,
                groups: (comp.group_a.clone(), comp.group_b.clone()),
                observed_difference: comp.difference,
                threshold: config.demographic_parity_threshold,
                description: format!(
                    "Demographic parity violation: {} has {:.1}% positive rate vs {:.1}% for {} (diff: {:.1}%)",
                    comp.group_a, comp.rate_a * 100.0, comp.rate_b * 100.0, comp.group_b, comp.difference * 100.0
                ),
            });
        }
    }

    // Collect equalized odds violations
    for comp in &eo.tpr_comparisons {
        if comp.violates_threshold {
            let severity = classify_severity(comp.difference, config.equalized_odds_threshold);
            violations.push(FairnessViolation {
                violation_type: FairnessCriterion::EqualizedOdds,
                severity,
                groups: (comp.group_a.clone(), comp.group_b.clone()),
                observed_difference: comp.difference,
                threshold: config.equalized_odds_threshold,
                description: format!(
                    "Equalized odds (TPR) violation: {} has TPR {:.1}% vs {:.1}% for {}",
                    comp.group_a, comp.rate_a * 100.0, comp.rate_b * 100.0, comp.group_b
                ),
            });
        }
    }
    for comp in &eo.fpr_comparisons {
        if comp.violates_threshold {
            let severity = classify_severity(comp.difference, config.equalized_odds_threshold);
            violations.push(FairnessViolation {
                violation_type: FairnessCriterion::EqualizedOdds,
                severity,
                groups: (comp.group_a.clone(), comp.group_b.clone()),
                observed_difference: comp.difference,
                threshold: config.equalized_odds_threshold,
                description: format!(
                    "Equalized odds (FPR) violation: {} has FPR {:.1}% vs {:.1}% for {}",
                    comp.group_a, comp.rate_a * 100.0, comp.rate_b * 100.0, comp.group_b
                ),
            });
        }
    }

    // Collect predictive parity violations
    for comp in &pp.pairwise_comparisons {
        if comp.violates_threshold {
            let severity = classify_severity(comp.difference, config.predictive_parity_threshold);
            violations.push(FairnessViolation {
                violation_type: FairnessCriterion::PredictiveParity,
                severity,
                groups: (comp.group_a.clone(), comp.group_b.clone()),
                observed_difference: comp.difference,
                threshold: config.predictive_parity_threshold,
                description: format!(
                    "Predictive parity violation: {} has precision {:.1}% vs {:.1}% for {}",
                    comp.group_a, comp.rate_a * 100.0, comp.rate_b * 100.0, comp.group_b
                ),
            });
        }
    }

    // Disparate impact warning (4/5ths rule)
    if dp.disparate_impact_ratio < 0.8 && dp.disparate_impact_ratio > 0.0 {
        warnings.push(format!(
            "Disparate impact ratio {:.2} is below 0.80 (4/5ths rule). Minimum group rate / maximum group rate.",
            dp.disparate_impact_ratio
        ));
    }

    let passed = dp.passed && eo.passed && pp.passed && violations.iter().all(|v| !matches!(v.severity, ViolationSeverity::Critical));

    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    FairnessReport {
        demographic_parity: dp,
        equalized_odds: eo,
        predictive_parity: pp,
        passed,
        violations,
        warnings,
        computed_at: now,
        config: config.clone(),
    }
}

/// Classify violation severity based on how much the threshold is exceeded
fn classify_severity(observed: f64, threshold: f64) -> ViolationSeverity {
    if observed > threshold * 2.0 {
        ViolationSeverity::Critical
    } else if observed > threshold * 1.5 {
        ViolationSeverity::Moderate
    } else {
        ViolationSeverity::Warning
    }
}

/// Standard normal CDF approximation (Abramowitz and Stegun)
fn standard_normal_cdf(x: f64) -> f64 {
    0.5 * (1.0 + erf(x / std::f64::consts::SQRT_2))
}

/// Error function approximation (Abramowitz and Stegun 7.1.26)
fn erf(x: f64) -> f64 {
    let a1 = 0.254829592;
    let a2 = -0.284496736;
    let a3 = 1.421413741;
    let a4 = -1.453152027;
    let a5 = 1.061405429;
    let p = 0.3275911;

    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let x = x.abs();
    let t = 1.0 / (1.0 + p * x);
    let y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x * x).exp();
    sign * y
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_demographic_parity_equal_groups() {
        // All groups have same rate → should pass
        let predictions = vec![
            ("vendor".to_string(), 1),
            ("vendor".to_string(), 1),
            ("vendor".to_string(), 0),
            ("vendor".to_string(), 0),
            ("farmer".to_string(), 1),
            ("farmer".to_string(), 1),
            ("farmer".to_string(), 0),
            ("farmer".to_string(), 0),
        ];
        let config = FairnessConfig::default();
        let result = compute_demographic_parity(&predictions, &config);
        assert!(result.passed, "Equal rates should pass demographic parity");
    }

    #[test]
    fn test_demographic_parity_unequal_groups() {
        // Vendor: 100% positive, Farmer: 0% positive → should fail
        let mut predictions = Vec::new();
        for _ in 0..50 {
            predictions.push(("vendor".to_string(), 1u8));
        }
        for _ in 0..50 {
            predictions.push(("farmer".to_string(), 0u8));
        }
        let config = FairnessConfig::default();
        let result = compute_demographic_parity(&predictions, &config);
        assert!(!result.passed, "Maximally unequal rates should fail");
        assert!(result.disparate_impact_ratio < 0.1);
    }

    #[test]
    fn test_equalized_odds_no_bias() {
        // Same TPR and FPR across regions
        let mut predictions = Vec::new();
        // Region A: 50 actual positives, TPR=0.8
        for _ in 0..40 { predictions.push(("region_a".to_string(), 1u8, 1u8)); }
        for _ in 0..10 { predictions.push(("region_a".to_string(), 0u8, 1u8)); }
        // Region A: 50 actual negatives, FPR=0.2
        for _ in 0..10 { predictions.push(("region_a".to_string(), 1u8, 0u8)); }
        for _ in 0..40 { predictions.push(("region_a".to_string(), 0u8, 0u8)); }

        // Region B: same rates
        for _ in 0..40 { predictions.push(("region_b".to_string(), 1u8, 1u8)); }
        for _ in 0..10 { predictions.push(("region_b".to_string(), 0u8, 1u8)); }
        for _ in 0..10 { predictions.push(("region_b".to_string(), 1u8, 0u8)); }
        for _ in 0..40 { predictions.push(("region_b".to_string(), 0u8, 0u8)); }

        let config = FairnessConfig::default();
        let result = compute_equalized_odds(&predictions, &config);
        assert!(result.passed, "Same rates across regions should pass");
    }

    #[test]
    fn test_predictive_parity() {
        let mut predictions = Vec::new();
        // Group A: precision = 0.8 (40 TP out of 50 predicted positive)
        for _ in 0..40 { predictions.push(("group_a".to_string(), 1u8, 1u8)); }
        for _ in 0..10 { predictions.push(("group_a".to_string(), 1u8, 0u8)); }
        for _ in 0..50 { predictions.push(("group_a".to_string(), 0u8, 0u8)); }

        // Group B: precision = 0.8 (40 TP out of 50 predicted positive)
        for _ in 0..40 { predictions.push(("group_b".to_string(), 1u8, 1u8)); }
        for _ in 0..10 { predictions.push(("group_b".to_string(), 1u8, 0u8)); }
        for _ in 0..50 { predictions.push(("group_b".to_string(), 0u8, 0u8)); }

        let config = FairnessConfig::default();
        let result = compute_predictive_parity(&predictions, &config);
        assert!(result.passed, "Same precision should pass");
    }

    #[test]
    fn test_full_audit() {
        let worker_preds = vec![
            ("vendor".to_string(), 1u8),
            ("vendor".to_string(), 1u8),
            ("vendor".to_string(), 0u8),
            ("farmer".to_string(), 1u8),
            ("farmer".to_string(), 0u8),
            ("farmer".to_string(), 0u8),
        ];
        let region_outcomes = vec![
            ("nairobi".to_string(), 1u8, 1u8),
            ("nairobi".to_string(), 0u8, 0u8),
            ("mombasa".to_string(), 1u8, 1u8),
            ("mombasa".to_string(), 0u8, 0u8),
        ];
        let group_outcomes = region_outcomes.clone();

        let config = FairnessConfig {
            min_group_size: 2, // small for test
            ..Default::default()
        };
        let report = run_fairness_audit(&worker_preds, &region_outcomes, &group_outcomes, &config);
        // Just verify it runs without panicking
        assert!(report.computed_at > 0);
    }

    #[test]
    fn test_severity_classification() {
        assert!(matches!(
            classify_severity(0.50, 0.20),
            ViolationSeverity::Critical
        ));
        assert!(matches!(
            classify_severity(0.35, 0.20),
            ViolationSeverity::Moderate
        ));
        assert!(matches!(
            classify_severity(0.25, 0.20),
            ViolationSeverity::Warning
        ));
    }
}
