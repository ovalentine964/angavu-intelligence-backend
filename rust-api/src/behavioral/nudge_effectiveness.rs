/// Nudge Effectiveness Tracking Module
///
/// Measures which behavioral nudges actually change worker behavior.
/// Uses a two-proportion z-test framework (same as ABTestEngine.kt)
/// to determine if nudges produce statistically significant changes.
///
/// Reference: Thaler & Sunstein (2008), "Nudge: Improving Decisions
///            about Health, Wealth, and Happiness"
///
/// Each nudge is tracked with:
///   - Exposure count (how many workers saw it)
///   - Action count (how many took the desired action)
///   - Control group behavior (what happened without the nudge)
///   - Effect size (Cohen's h for proportions)
///   - Statistical significance (p-value from z-test)

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// A nudge intervention to be tracked
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NudgeIntervention {
    /// Unique nudge identifier
    pub nudge_id: String,
    /// Type of nudge (framing, social_proof, default, commitment, etc.)
    pub nudge_type: NudgeType,
    /// Human-readable description
    pub description: String,
    /// Target behavior (e.g., "savings_increase", "insurance_enrollment")
    pub target_behavior: String,
    /// Worker type this nudge targets
    pub worker_type: String,
    /// When the nudge was deployed (Unix seconds)
    pub deployed_at: u64,
}

/// Types of behavioral nudges (Thaler & Sunstein taxonomy)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NudgeType {
    /// Present information to emphasize gains or losses
    Framing,
    /// Show what peers are doing
    SocialProof,
    /// Pre-select beneficial options
    DefaultEffect,
    /// Self-imposed restrictions on future choices
    CommitmentDevice,
    /// Make the desired option more visually prominent
    Salience,
    /// Simplify the decision process
    Simplification,
    /// Remind at the right moment
    Timely提醒,
    /// Provide concrete comparisons
    ConcreteComparison,
    /// Use loss aversion to motivate action
    LossFraming,
    /// Anchor on a beneficial reference point
    Anchoring,
}

/// Tracking data for a single nudge
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NudgeTracker {
    /// Nudge being tracked
    pub intervention: NudgeIntervention,
    /// Treatment group: workers who received the nudge
    pub treatment: GroupStats,
    /// Control group: workers who did not receive the nudge
    pub control: GroupStats,
    /// Computed effectiveness metrics
    pub effectiveness: Option<NudgeEffectiveness>,
}

/// Statistics for a group (treatment or control)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupStats {
    /// Total workers in this group
    pub n: usize,
    /// Workers who took the desired action
    pub action_count: usize,
    /// Sum of the outcome variable (e.g., amount saved)
    pub outcome_sum: f64,
    /// Sum of squared outcomes (for variance calculation)
    pub outcome_sum_sq: f64,
}

impl GroupStats {
    /// Create a new empty group
    pub fn new() -> Self {
        Self {
            n: 0,
            action_count: 0,
            outcome_sum: 0.0,
            outcome_sum_sq: 0.0,
        }
    }

    /// Record a worker's outcome
    pub fn record(&mut self, took_action: bool, outcome_value: f64) {
        self.n += 1;
        if took_action {
            self.action_count += 1;
        }
        self.outcome_sum += outcome_value;
        self.outcome_sum_sq += outcome_value * outcome_value;
    }

    /// Proportion of workers who took the desired action
    pub fn action_rate(&self) -> f64 {
        if self.n == 0 {
            0.0
        } else {
            self.action_count as f64 / self.n as f64
        }
    }

    /// Mean outcome value
    pub fn mean_outcome(&self) -> f64 {
        if self.n == 0 {
            0.0
        } else {
            self.outcome_sum / self.n as f64
        }
    }

    /// Variance of outcome
    pub fn outcome_variance(&self) -> f64 {
        if self.n < 2 {
            return 0.0;
        }
        let mean = self.mean_outcome();
        let var = (self.outcome_sum_sq / self.n as f64) - mean * mean;
        var.max(0.0)
    }
}

impl Default for GroupStats {
    fn default() -> Self {
        Self::new()
    }
}

/// Computed effectiveness of a nudge
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NudgeEffectiveness {
    /// Absolute difference in action rates (treatment - control)
    pub rate_difference: f64,
    /// Relative improvement ((treatment - control) / control)
    pub relative_improvement: f64,
    /// Cohen's h effect size for proportions
    pub cohens_h: f64,
    /// Effect size label (small/medium/large)
    pub effect_size_label: String,
    /// Two-proportion z-test statistic
    pub z_statistic: f64,
    /// p-value (two-tailed)
    pub p_value: f64,
    /// Whether the result is significant at α=0.05
    pub significant_at_05: bool,
    /// Whether the result is significant at α=0.01
    pub significant_at_01: bool,
    /// Number needed to treat (how many workers need the nudge for 1 extra action)
    pub nnt: f64,
    /// Cost-effectiveness ratio (if cost data available)
    pub cost_per_action: Option<f64>,
    /// Verdict
    pub verdict: NudgeVerdict,
}

/// Verdict on nudge effectiveness
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum NudgeVerdict {
    /// Statistically significant and practically meaningful
    Effective,
    /// Statistically significant but small effect
    Marginal,
    /// Not statistically significant
    Ineffective,
    /// Negative effect (nudge made things worse)
    Counterproductive,
    /// Insufficient data
    InsufficientData,
}

/// The nudge effectiveness engine
pub struct NudgeEffectivenessEngine {
    /// All tracked nudges
    trackers: HashMap<String, NudgeTracker>,
    /// Significance level
    alpha: f64,
    /// Minimum sample size per group
    min_sample: usize,
}

impl NudgeEffectivenessEngine {
    /// Create a new engine with default settings
    pub fn new() -> Self {
        Self {
            trackers: HashMap::new(),
            alpha: 0.05,
            min_sample: 30,
        }
    }

    /// Create with custom settings
    pub fn with_config(alpha: f64, min_sample: usize) -> Self {
        Self {
            trackers: HashMap::new(),
            alpha,
            min_sample,
        }
    }

    /// Register a new nudge for tracking
    pub fn register_nudge(&mut self, intervention: NudgeIntervention) {
        let nudge_id = intervention.nudge_id.clone();
        self.trackers.insert(
            nudge_id.clone(),
            NudgeTracker {
                intervention,
                treatment: GroupStats::new(),
                control: GroupStats::new(),
                effectiveness: None,
            },
        );
    }

    /// Record a treatment group observation
    pub fn record_treatment(&mut self, nudge_id: &str, took_action: bool, outcome: f64) {
        if let Some(tracker) = self.trackers.get_mut(nudge_id) {
            tracker.treatment.record(took_action, outcome);
        }
    }

    /// Record a control group observation
    pub fn record_control(&mut self, nudge_id: &str, took_action: bool, outcome: f64) {
        if let Some(tracker) = self.trackers.get_mut(nudge_id) {
            tracker.control.record(took_action, outcome);
        }
    }

    /// Compute effectiveness for a specific nudge
    pub fn compute_effectiveness(&mut self, nudge_id: &str) -> Option<NudgeEffectiveness> {
        let tracker = self.trackers.get(nudge_id)?;

        // Need minimum sample size
        if tracker.treatment.n < self.min_sample || tracker.control.n < self.min_sample {
            let eff = NudgeEffectiveness {
                rate_difference: 0.0,
                relative_improvement: 0.0,
                cohens_h: 0.0,
                effect_size_label: "insufficient_data".to_string(),
                z_statistic: 0.0,
                p_value: 1.0,
                significant_at_05: false,
                significant_at_01: false,
                nnt: f64::INFINITY,
                cost_per_action: None,
                verdict: NudgeVerdict::InsufficientData,
            };
            self.trackers.get_mut(nudge_id).unwrap().effectiveness = Some(eff.clone());
            return Some(eff);
        }

        let p1 = tracker.treatment.action_rate();
        let p2 = tracker.control.action_rate();
        let n1 = tracker.treatment.n as f64;
        let n2 = tracker.control.n as f64;

        // Rate difference
        let rate_diff = p1 - p2;

        // Relative improvement
        let relative = if p2 > 0.0 { rate_diff / p2 } else { 0.0 };

        // Cohen's h effect size for proportions
        // h = 2 * arcsin(sqrt(p1)) - 2 * arcsin(sqrt(p2))
        let h = 2.0 * (p1.sqrt()).asin() - 2.0 * (p2.sqrt()).asin();
        let h_abs = h.abs();
        let effect_label = match h_abs {
            x if x < 0.2 => "small",
            x if x < 0.5 => "medium",
            x if x < 0.8 => "large",
            _ => "very_large",
        }
        .to_string();

        // Two-proportion z-test
        // H0: p1 = p2
        let p_pooled = (tracker.treatment.action_count as f64
            + tracker.control.action_count as f64)
            / (n1 + n2);
        let se = if p_pooled > 0.0 && p_pooled < 1.0 {
            (p_pooled * (1.0 - p_pooled) * (1.0 / n1 + 1.0 / n2)).sqrt()
        } else {
            return None; // degenerate case
        };

        let z = if se > 0.0 { rate_diff / se } else { 0.0 };

        // Two-tailed p-value (normal approximation)
        let p_value = 2.0 * normal_cdf(-z.abs());

        // Number needed to treat
        let nnt = if rate_diff > 0.0 {
            1.0 / rate_diff
        } else {
            f64::INFINITY
        };

        // Verdict
        let significant = p_value < self.alpha;
        let verdict = if !significant {
            NudgeVerdict::Ineffective
        } else if rate_diff < 0.0 {
            NudgeVerdict::Counterproductive
        } else if h_abs >= 0.2 {
            NudgeVerdict::Effective
        } else {
            NudgeVerdict::Marginal
        };

        let eff = NudgeEffectiveness {
            rate_difference: rate_diff,
            relative_improvement: relative,
            cohens_h: h,
            effect_size_label: effect_label,
            z_statistic: z,
            p_value,
            significant_at_05: p_value < 0.05,
            significant_at_01: p_value < 0.01,
            nnt,
            cost_per_action: None,
            verdict,
        };

        self.trackers.get_mut(nudge_id).unwrap().effectiveness = Some(eff.clone());
        Some(eff)
    }

    /// Compute effectiveness for all tracked nudges
    pub fn compute_all(&mut self) -> Vec<(String, NudgeEffectiveness)> {
        let nudge_ids: Vec<String> = self.trackers.keys().cloned().collect();
        let mut results = Vec::new();
        for id in nudge_ids {
            if let Some(eff) = self.compute_effectiveness(&id) {
                results.push((id, eff));
            }
        }
        results
    }

    /// Get the most effective nudge for a given behavior
    pub fn best_nudge_for_behavior(&mut self, behavior: &str) -> Option<(String, NudgeEffectiveness)> {
        self.compute_all()
            .into_iter()
            .filter(|(_, eff)| {
                matches!(
                    eff.verdict,
                    NudgeVerdict::Effective | NudgeVerdict::Marginal
                )
            })
            .filter(|(id, _)| {
                self.trackers
                    .get(id)
                    .map(|t| t.intervention.target_behavior == behavior)
                    .unwrap_or(false)
            })
            .max_by(|a, b| a.1.cohens_h.partial_cmp(&b.1.cohens_h).unwrap())
    }

    /// Get all trackers
    pub fn get_trackers(&self) -> &HashMap<String, NudgeTracker> {
        &self.trackers
    }
}

impl Default for NudgeEffectivenessEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Standard normal CDF approximation (Abramowitz & Stegun)
fn normal_cdf(x: f64) -> f64 {
    let a1 = 0.254829592;
    let a2 = -0.284496736;
    let a3 = 1.421413741;
    let a4 = -1.453152027;
    let a5 = 1.061405429;
    let p = 0.3275911;

    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let x_abs = x.abs();
    let t = 1.0 / (1.0 + p * x_abs);
    let y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x_abs * x_abs / 2.0).exp();

    0.5 * (1.0 + sign * y)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_nudge_effectiveness_significant() {
        let mut engine = NudgeEffectivenessEngine::new();

        let intervention = NudgeIntervention {
            nudge_id: "social_proof_savings_001".to_string(),
            nudge_type: NudgeType::SocialProof,
            description: "Show peer savings rate".to_string(),
            target_behavior: "savings_increase".to_string(),
            worker_type: "mama_mboga".to_string(),
            deployed_at: 1700000000,
        };

        engine.register_nudge(intervention);

        // Treatment: 60% took action (saved more)
        for i in 0..100 {
            engine.record_treatment("social_proof_savings_001", i < 60, if i < 60 { 500.0 } else { 200.0 });
        }
        // Control: 40% took action
        for i in 0..100 {
            engine.record_control("social_proof_savings_001", i < 40, if i < 40 { 500.0 } else { 200.0 });
        }

        let eff = engine.compute_effectiveness("social_proof_savings_001").unwrap();

        assert!(eff.significant_at_05, "Should be significant");
        assert!(eff.rate_difference > 0.0, "Should have positive effect");
        assert_eq!(eff.verdict, NudgeVerdict::Effective);
        assert!(eff.cohens_h > 0.0);
    }

    #[test]
    fn test_nudge_ineffective() {
        let mut engine = NudgeEffectivenessEngine::new();

        engine.register_nudge(NudgeIntervention {
            nudge_id: "test_ineffective".to_string(),
            nudge_type: NudgeType::Framing,
            description: "Test".to_string(),
            target_behavior: "test".to_string(),
            worker_type: "test".to_string(),
            deployed_at: 0,
        });

        // Same rates in both groups
        for i in 0..50 {
            engine.record_treatment("test_ineffective", i < 25, 100.0);
            engine.record_control("test_ineffective", i < 25, 100.0);
        }

        let eff = engine.compute_effectiveness("test_ineffective").unwrap();
        assert!(!eff.significant_at_05);
        assert_eq!(eff.verdict, NudgeVerdict::Ineffective);
    }

    #[test]
    fn test_insufficient_data() {
        let mut engine = NudgeEffectivenessEngine::new();

        engine.register_nudge(NudgeIntervention {
            nudge_id: "small_sample".to_string(),
            nudge_type: NudgeType::DefaultEffect,
            description: "Test".to_string(),
            target_behavior: "test".to_string(),
            worker_type: "test".to_string(),
            deployed_at: 0,
        });

        // Only 5 observations
        for i in 0..5 {
            engine.record_treatment("small_sample", i < 3, 100.0);
            engine.record_control("small_sample", i < 2, 100.0);
        }

        let eff = engine.compute_effectiveness("small_sample").unwrap();
        assert_eq!(eff.verdict, NudgeVerdict::InsufficientData);
    }

    #[test]
    fn test_best_nudge_selection() {
        let mut engine = NudgeEffectivenessEngine::new();

        // Nudge A: small effect
        engine.register_nudge(NudgeIntervention {
            nudge_id: "nudge_a".to_string(),
            nudge_type: NudgeType::Framing,
            description: "A".to_string(),
            target_behavior: "save".to_string(),
            worker_type: "test".to_string(),
            deployed_at: 0,
        });
        for i in 0..100 {
            engine.record_treatment("nudge_a", i < 55, 100.0);
            engine.record_control("nudge_a", i < 50, 100.0);
        }

        // Nudge B: larger effect
        engine.register_nudge(NudgeIntervention {
            nudge_id: "nudge_b".to_string(),
            nudge_type: NudgeType::SocialProof,
            description: "B".to_string(),
            target_behavior: "save".to_string(),
            worker_type: "test".to_string(),
            deployed_at: 0,
        });
        for i in 0..100 {
            engine.record_treatment("nudge_b", i < 70, 100.0);
            engine.record_control("nudge_b", i < 40, 100.0);
        }

        let best = engine.best_nudge_for_behavior("save").unwrap();
        assert_eq!(best.0, "nudge_b");
    }
}
