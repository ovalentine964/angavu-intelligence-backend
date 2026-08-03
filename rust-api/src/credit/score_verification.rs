// credit/score_verification.rs
// Fix 3 (backend): Verify Alama Score for range, consistency, and confidence.
//
// Before returning a FusedAlamaScore to the client:
//   1. Range check: score must be 300–850
//   2. Confidence interval must be valid (ci_lower <= score <= ci_upper)
//   3. Confidence must be in 0.0–1.0 range
//   4. Type weight must be in valid range
//   5. Raw score must be in 0.0–1.0 range
//   6. Factor impacts must be reasonable

use super::score_fusion::{FusedAlamaScore, ScoreFactor};
use super::types::WorkerType;

/// Valid score range constants
pub const MIN_SCORE: u16 = 300;
pub const MAX_SCORE: u16 = 850;

/// Score validation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreVerificationResult {
    pub passed: bool,
    pub issues: Vec<ScoreVerificationIssue>,
    pub warnings: Vec<String>,
    /// Corrected score (clamped to valid range if needed)
    pub corrected_score: u16,
    /// Corrected confidence interval
    pub corrected_ci_lower: u16,
    pub corrected_ci_upper: u16,
    /// Verification confidence (how much we trust the score after verification)
    pub verification_confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreVerificationIssue {
    pub issue_type: ScoreVerificationIssueType,
    pub severity: IssueSeverity,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ScoreVerificationIssueType {
    OutOfRange,
    CiInverted,
    CiTooWide,
    ConfidenceOutOfRange,
    RawScoreOutOfRange,
    TypeWeightOutOfRange,
    FactorImpactOutOfRange,
    InsufficientData,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IssueSeverity {
    Low,
    Medium,
    High,
}

/// Verify a FusedAlamaScore before delivery.
pub fn verify_score(score: &FusedAlamaScore) -> ScoreVerificationResult {
    let mut issues = Vec::new();
    let mut warnings = Vec::new();

    // ── Check 1: Score range ─────────────────────────────────
    if score.alama_score < MIN_SCORE || score.alama_score > MAX_SCORE {
        issues.push(ScoreVerificationIssue {
            issue_type: ScoreVerificationIssueType::OutOfRange,
            severity: IssueSeverity::High,
            message: format!(
                "Score {} is outside valid range ({}-{})",
                score.alama_score, MIN_SCORE, MAX_SCORE
            ),
        });
    }

    // ── Check 2: Confidence interval validity ────────────────
    if score.ci_lower > score.ci_upper {
        issues.push(ScoreVerificationIssue {
            issue_type: ScoreVerificationIssueType::CiInverted,
            severity: IssueSeverity::High,
            message: format!(
                "CI is inverted: lower ({}) > upper ({})",
                score.ci_lower, score.ci_upper
            ),
        });
    }

    if score.ci_lower < MIN_SCORE || score.ci_upper > MAX_SCORE {
        issues.push(ScoreVerificationIssue {
            issue_type: ScoreVerificationIssueType::OutOfRange,
            severity: IssueSeverity::Medium,
            message: format!(
                "CI bounds ({}, {}) exceed valid range",
                score.ci_lower, score.ci_upper
            ),
        });
    }

    let ci_width = score.ci_upper.saturating_sub(score.ci_lower);
    if ci_width > 200 {
        warnings.push(format!(
            "CI is very wide ({} points) — low precision",
            ci_width
        ));
    }

    // ── Check 3: Score within CI ─────────────────────────────
    if score.alama_score < score.ci_lower || score.alama_score > score.ci_upper {
        issues.push(ScoreVerificationIssue {
            issue_type: ScoreVerificationIssueType::CiInverted,
            severity: IssueSeverity::Medium,
            message: format!(
                "Score {} is outside its own CI ({}, {})",
                score.alama_score, score.ci_lower, score.ci_upper
            ),
        });
    }

    // ── Check 4: Confidence range ────────────────────────────
    if score.confidence < 0.0 || score.confidence > 1.0 {
        issues.push(ScoreVerificationIssue {
            issue_type: ScoreVerificationIssueType::ConfidenceOutOfRange,
            severity: IssueSeverity::High,
            message: format!("Confidence {} is outside [0.0, 1.0]", score.confidence),
        });
    }

    if score.confidence < 0.3 {
        warnings.push(format!(
            "Very low confidence ({:.2}) — score may be unreliable",
            score.confidence
        ));
    }

    // ── Check 5: Raw score range ─────────────────────────────
    if score.raw_score < 0.0 || score.raw_score > 1.0 {
        issues.push(ScoreVerificationIssue {
            issue_type: ScoreVerificationIssueType::RawScoreOutOfRange,
            severity: IssueSeverity::High,
            message: format!("Raw score {} is outside [0.0, 1.0]", score.raw_score),
        });
    }

    // ── Check 6: Type weight range ───────────────────────────
    if score.type_weight < 0.0 || score.type_weight > 1.0 {
        issues.push(ScoreVerificationIssue {
            issue_type: ScoreVerificationIssueType::TypeWeightOutOfRange,
            severity: IssueSeverity::Medium,
            message: format!("Type weight {} is outside [0.0, 1.0]", score.type_weight),
        });
    }

    // ── Check 7: Factor impact reasonableness ────────────────
    for factor in &score.factors {
        if factor.impact.abs() > 1.0 {
            issues.push(ScoreVerificationIssue {
                issue_type: ScoreVerificationIssueType::FactorImpactOutOfRange,
                severity: IssueSeverity::Low,
                message: format!(
                    "Factor '{}' has extreme impact: {:.3}",
                    factor.name, factor.impact
                ),
            });
        }
    }

    // ── Check 8: Standard error reasonableness ───────────────
    if score.standard_error < 0.0 || score.standard_error > 1.0 {
        issues.push(ScoreVerificationIssue {
            issue_type: ScoreVerificationIssueType::OutOfRange,
            severity: IssueSeverity::Medium,
            message: format!(
                "Standard error {} is outside [0.0, 1.0]",
                score.standard_error
            ),
        });
    }

    // ── Compute corrected values ─────────────────────────────
    let corrected_score = score.alama_score.clamp(MIN_SCORE, MAX_SCORE);
    let corrected_ci_lower = score.ci_lower.clamp(MIN_SCORE, corrected_score);
    let corrected_ci_upper = score.ci_upper.clamp(corrected_score, MAX_SCORE);

    // ── Compute verification confidence ──────────────────────
    let verification_confidence = compute_verification_confidence(score, &issues);

    ScoreVerificationResult {
        passed: !issues
            .iter()
            .any(|i| matches!(i.severity, IssueSeverity::High)),
        issues,
        warnings,
        corrected_score,
        corrected_ci_lower,
        corrected_ci_upper,
        verification_confidence,
    }
}

/// Compute how much we trust the score after verification.
fn compute_verification_confidence(
    score: &FusedAlamaScore,
    issues: &[ScoreVerificationIssue],
) -> f64 {
    let mut conf = score.confidence;

    // Reduce for each issue by severity
    for issue in issues {
        match issue.severity {
            IssueSeverity::High => conf -= 0.3,
            IssueSeverity::Medium => conf -= 0.15,
            IssueSeverity::Low => conf -= 0.05,
        }
    }

    // Reduce for wide CI (low precision)
    let ci_width = score.ci_upper.saturating_sub(score.ci_lower) as f64;
    if ci_width > 100.0 {
        conf -= 0.1;
    }

    conf.clamp(0.0, 1.0)
}

/// Quick range-only validation (no full verification).
pub fn validate_score_range(score: u16) -> bool {
    score >= MIN_SCORE && score <= MAX_SCORE
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_score(alama_score: u16, confidence: f64) -> FusedAlamaScore {
        FusedAlamaScore {
            alama_score,
            raw_score: (alama_score as f64 - 300.0) / 550.0,
            base_score: 0.5,
            type_score: None,
            worker_type: WorkerType::MarketVendor,
            type_weight: 0.3,
            confidence,
            factors: vec![],
            explanation: None,
            seasonally_adjusted: false,
            ci_lower: alama_score.saturating_sub(20),
            ci_upper: (alama_score + 20).min(850),
            standard_error: 0.05,
        }
    }

    #[test]
    fn valid_score_passes() {
        let score = make_score(600, 0.8);
        let result = verify_score(&score);
        assert!(result.passed, "Valid score should pass verification");
        assert!(result.issues.is_empty());
    }

    #[test]
    fn score_below_300_fails() {
        let score = make_score(250, 0.5);
        let result = verify_score(&score);
        assert!(!result.passed, "Score below 300 should fail");
        assert!(result
            .issues
            .iter()
            .any(|i| matches!(i.issue_type, ScoreVerificationIssueType::OutOfRange)));
    }

    #[test]
    fn score_above_850_fails() {
        let score = make_score(900, 0.5);
        let result = verify_score(&score);
        assert!(!result.passed, "Score above 850 should fail");
    }

    #[test]
    fn inverted_ci_fails() {
        let mut score = make_score(600, 0.8);
        score.ci_lower = 700;
        score.ci_upper = 500;
        let result = verify_score(&score);
        assert!(!result.passed, "Inverted CI should fail");
    }

    #[test]
    fn wide_ci_warns() {
        let mut score = make_score(600, 0.5);
        score.ci_lower = 400;
        score.ci_upper = 800;
        let result = verify_score(&score);
        assert!(
            result.warnings.iter().any(|w| w.contains("wide")),
            "Wide CI should generate warning"
        );
    }

    #[test]
    fn out_of_range_confidence_fails() {
        let score = make_score(600, 1.5);
        let result = verify_score(&score);
        assert!(!result.passed, "Confidence > 1.0 should fail");
    }

    #[test]
    fn corrected_score_clamped() {
        let score = make_score(900, 0.5);
        let result = verify_score(&score);
        assert_eq!(result.corrected_score, 850);
    }

    #[test]
    fn corrected_ci_within_bounds() {
        let mut score = make_score(310, 0.5);
        score.ci_lower = 250; // below min
        score.ci_upper = 900; // above max
        let result = verify_score(&score);
        assert!(result.corrected_ci_lower >= 300);
        assert!(result.corrected_ci_upper <= 850);
    }

    #[test]
    fn low_confidence_warns() {
        let score = make_score(600, 0.1);
        let result = verify_score(&score);
        assert!(
            result.warnings.iter().any(|w| w.contains("low confidence")),
            "Low confidence should generate warning"
        );
    }

    #[test]
    fn quick_range_check() {
        assert!(validate_score_range(300));
        assert!(validate_score_range(575));
        assert!(validate_score_range(850));
        assert!(!validate_score_range(299));
        assert!(!validate_score_range(851));
    }
}
