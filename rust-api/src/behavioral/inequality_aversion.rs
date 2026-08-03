/// Inequality Aversion Scoring Module
///
/// Measures fairness preferences in Chama (group savings) contexts.
///
/// Fehr & Schmidt (1999) inequality aversion model:
/// U_i(x) = x_i - α_i * max(x_j - x_i, 0) - β_i * max(x_i - x_j, 0)
///
/// Where:
///   - α_i = envy parameter (disadvantageous inequality aversion)
///   - β_i = guilt parameter (advantageous inequality aversion)
///   - 0 ≤ β_i ≤ 1 and β_i ≤ α_i
///
/// In a Chama context:
///   - α measures how much a member dislikes contributing more than others
///   - β measures how much a member dislikes contributing less than others
///   - Members with high α may defect if they feel others aren't contributing
///   - Members with high β may over-contribute to maintain fairness
///
/// This is critical for Chama stability: groups with mismatched inequality
/// aversion parameters tend to collapse.
///
/// Reference: Fehr, E., & Schmidt, K. M. (1999). A Theory of Fairness,
///            Competition, and Cooperation. Quarterly Journal of Economics.
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// A Chama contribution record used for inequality analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContributionRecord {
    /// Member identifier
    pub member_id: String,
    /// Amount contributed in KES
    pub amount: f64,
    /// Expected contribution amount
    pub expected: f64,
    /// Cycle number
    pub cycle: usize,
    /// Timestamp (Unix seconds)
    pub timestamp: u64,
    /// Whether the contribution was on time
    pub on_time: bool,
    /// Whether a penalty was applied
    pub penalty_applied: bool,
}

/// Inequality aversion parameters for a member
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InequalityAversion {
    /// Member identifier
    pub member_id: String,
    /// Envy parameter α (disadvantageous inequality)
    /// High α = strong dislike of contributing more than others
    pub alpha: f64,
    /// Guilt parameter β (advantageous inequality)
    /// High β = discomfort with contributing less than others
    pub beta: f64,
    /// Fairness type classification
    pub fairness_type: FairnessType,
    /// Utility score given current contribution distribution
    pub utility_score: f64,
    /// Risk of defection (0-1)
    pub defection_risk: f64,
    /// Recommended intervention
    pub intervention: String,
}

/// Fairness type classification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FairnessType {
    /// Low α, low β — doesn't care much about fairness
    Selfish,
    /// High β, low α — wants to be fair but doesn't mind if others aren't
    AltruisticFair,
    /// High α, low β — dislikes being exploited but fine with exploiting
    Envious,
    /// High α, high β — strong equality preference
    Egalitarian,
    /// Moderate α, moderate β — pragmatic fairness
    ReciprocalFair,
}

impl FairnessType {
    /// Human-readable label (Swahili + English)
    pub fn label(&self) -> &'static str {
        match self {
            Self::Selfish => "Anayejali nafsi — Selfish",
            Self::AltruisticFair => "Mwenye haki — Fair-minded",
            Self::Envious => "Mwenye wivu — Envious",
            Self::Egalitarian => "Mwenye usawa — Egalitarian",
            Self::ReciprocalFair => "Mwenye haki ya kubadilishana — Reciprocal",
        }
    }

    /// Recommended Chama management approach
    pub fn chama_strategy(&self) -> &'static str {
        match self {
            Self::Selfish => "Tumia penalty kali na uthibitisho wa kijamii. Mtu huyu anahitaji kuona faida ya kibinafsi.",
            Self::AltruisticFair => "Mtu huyu ni mzuri kwa chama. Ongeza jukumu la uongozi — atafanya vizuri.",
            Self::Envious => "Hakikisha uwazi wa haki — onyesha michango ya kila mtu. Epuka siri.",
            Self::Egalitarian => "Mtu huyu anapenda usawa wa haki. Chama kinapaswa kuwa na kanuni zilizo wazi.",
            Self::ReciprocalFair => "Mtu huyu anafuata kanuni. Weka sheria zilizo wazi na zitekelezwe kwa wote.",
        }
    }
}

/// Chama inequality analysis result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChamaInequalityAnalysis {
    /// Chama identifier
    pub chama_id: String,
    /// Per-member inequality aversion
    pub member_profiles: Vec<InequalityAversion>,
    /// Gini coefficient of contributions (0 = perfect equality)
    pub gini_coefficient: f64,
    /// Average envy parameter
    pub avg_alpha: f64,
    /// Average guilt parameter
    pub avg_beta: f64,
    /// Overall group stability score (0-1)
    pub stability_score: f64,
    /// Members at risk of defection
    pub defection_risks: Vec<String>,
    /// Recommended group interventions
    pub group_interventions: Vec<String>,
}

/// Inequality aversion engine
pub struct InequalityAversionEngine {
    /// Minimum cycles of data for reliable estimation
    min_cycles: usize,
}

impl InequalityAversionEngine {
    /// Create a new engine
    pub fn new() -> Self {
        Self { min_cycles: 3 }
    }

    /// Create with custom settings
    pub fn with_config(min_cycles: usize) -> Self {
        Self { min_cycles }
    }

    /// Analyze inequality aversion for a Chama
    pub fn analyze_chama(
        &self,
        chama_id: &str,
        contributions: &[ContributionRecord],
        expected_contribution: f64,
    ) -> Option<ChamaInequalityAnalysis> {
        if contributions.is_empty() {
            return None;
        }

        // Group by member
        let mut by_member: HashMap<String, Vec<&ContributionRecord>> = HashMap::new();
        for c in contributions {
            by_member.entry(c.member_id.clone()).or_default().push(c);
        }

        // Need at least 2 members with enough data
        if by_member.len() < 2 {
            return None;
        }

        // Calculate per-member statistics
        let member_stats: Vec<(String, MemberStats)> = by_member
            .iter()
            .map(|(id, records)| {
                let amounts: Vec<f64> = records.iter().map(|r| r.amount).collect();
                let avg = amounts.iter().sum::<f64>() / amounts.len() as f64;
                let on_time_rate =
                    records.iter().filter(|r| r.on_time).count() as f64 / records.len() as f64;
                let penalty_rate = records.iter().filter(|r| r.penalty_applied).count() as f64
                    / records.len() as f64;
                let cycle_count = records.len();

                (
                    id.clone(),
                    MemberStats {
                        avg_contribution: avg,
                        on_time_rate,
                        penalty_rate,
                        cycle_count,
                        amounts,
                    },
                )
            })
            .collect();

        // Calculate group average contribution
        let group_avg = member_stats
            .iter()
            .map(|(_, s)| s.avg_contribution)
            .sum::<f64>()
            / member_stats.len() as f64;

        // Estimate α and β for each member
        let mut profiles = Vec::new();
        for (member_id, stats) in &member_stats {
            if stats.cycle_count < self.min_cycles {
                continue;
            }

            let (alpha, beta) =
                self.estimate_inequality_aversion(stats, group_avg, expected_contribution);

            let fairness_type = self.classify_fairness_type(alpha, beta);

            // Utility score: how happy is this member with the current distribution?
            let utility = self.compute_utility(stats.avg_contribution, group_avg, alpha, beta);

            // Defection risk
            let defection_risk = self.estimate_defection_risk(
                alpha,
                beta,
                stats.on_time_rate,
                stats.penalty_rate,
                stats.avg_contribution,
                group_avg,
            );

            let intervention = self.recommend_intervention(fairness_type, defection_risk, stats);

            profiles.push(InequalityAversion {
                member_id: member_id.clone(),
                alpha,
                beta,
                fairness_type,
                utility_score: utility,
                defection_risk,
                intervention,
            });
        }

        // Gini coefficient
        let gini = self.gini_coefficient(
            &member_stats
                .iter()
                .map(|(_, s)| s.avg_contribution)
                .collect::<Vec<_>>(),
        );

        // Group stability
        let avg_alpha = profiles.iter().map(|p| p.alpha).sum::<f64>() / profiles.len() as f64;
        let avg_beta = profiles.iter().map(|p| p.beta).sum::<f64>() / profiles.len() as f64;

        let defection_risks: Vec<String> = profiles
            .iter()
            .filter(|p| p.defection_risk > 0.6)
            .map(|p| p.member_id.clone())
            .collect();

        let stability = self.group_stability_score(&profiles, gini);

        let interventions = self.group_interventions(&profiles, gini, stability);

        Some(ChamaInequalityAnalysis {
            chama_id: chama_id.to_string(),
            member_profiles: profiles,
            gini_coefficient: gini,
            avg_alpha,
            avg_beta,
            stability_score: stability,
            defection_risks,
            group_interventions: interventions,
        })
    }

    /// Estimate α (envy) and β (guilt) from behavioral data
    fn estimate_inequality_aversion(
        &self,
        stats: &MemberStats,
        group_avg: f64,
        expected: f64,
    ) -> (f64, f64) {
        // α (envy): estimated from behavior when contributing MORE than average
        // Members with high α will reduce contributions when they see others contributing less
        let above_avg_contributions: Vec<f64> = stats
            .amounts
            .iter()
            .filter(|&&a| a > group_avg)
            .copied()
            .collect();

        let alpha = if !above_avg_contributions.is_empty() && group_avg > 0.0 {
            // How much does the member reduce contributions when above average?
            let avg_above =
                above_avg_contributions.iter().sum::<f64>() / above_avg_contributions.len() as f64;
            let excess = (avg_above - group_avg) / group_avg;
            // Members who barely go above average have high α (strong envy)
            // Members who go far above have low α (don't mind)
            (1.0 - excess).max(0.0).min(1.0)
        } else {
            0.3 // default moderate
        };

        // β (guilt): estimated from consistency and on-time behavior
        // Members with high β feel guilty about under-contributing
        let below_expected_count = stats
            .amounts
            .iter()
            .filter(|&&a| a < expected * 0.9)
            .count();
        let below_rate = below_expected_count as f64 / stats.amounts.len() as f64;

        let beta = if expected > 0.0 {
            // Low below-rate + high on-time = high guilt (β)
            let consistency = 1.0 - below_rate;
            let punctuality = stats.on_time_rate;
            ((consistency + punctuality) / 2.0).max(0.0).min(1.0)
        } else {
            0.3
        };

        // Ensure β ≤ α (Fehr-Schmidt constraint)
        let beta = beta.min(alpha);

        (alpha, beta)
    }

    /// Classify fairness type from α and β
    fn classify_fairness_type(&self, alpha: f64, beta: f64) -> FairnessType {
        let alpha_high = alpha > 0.5;
        let beta_high = beta > 0.4;

        match (alpha_high, beta_high) {
            (true, true) => FairnessType::Egalitarian,
            (true, false) => FairnessType::Envious,
            (false, true) => FairnessType::AltruisticFair,
            (false, false) => {
                if alpha < 0.2 && beta < 0.2 {
                    FairnessType::Selfish
                } else {
                    FairnessType::ReciprocalFair
                }
            }
        }
    }

    /// Compute Fehr-Schmidt utility
    /// U_i = x_i - α * max(x_avg - x_i, 0) - β * max(x_i - x_avg, 0)
    fn compute_utility(&self, own: f64, avg: f64, alpha: f64, beta: f64) -> f64 {
        let disadvantageous = (avg - own).max(0.0);
        let advantageous = (own - avg).max(0.0);
        own - alpha * disadvantageous - beta * advantageous
    }

    /// Estimate defection risk
    fn estimate_defection_risk(
        &self,
        alpha: f64,
        beta: f64,
        on_time_rate: f64,
        penalty_rate: f64,
        own_avg: f64,
        group_avg: f64,
    ) -> f64 {
        let mut risk = 0.0;

        // High α + contributing more than average → frustration → defection risk
        if alpha > 0.5 && own_avg > group_avg * 1.1 {
            risk += 0.3;
        }

        // Low on-time rate → already disengaging
        risk += (1.0 - on_time_rate) * 0.3;

        // High penalty rate → repeated violations
        risk += penalty_rate * 0.2;

        // Contributing much less than average → may be leaving
        if own_avg < group_avg * 0.7 {
            risk += 0.2;
        }

        risk.min(1.0)
    }

    /// Recommend intervention for a member
    fn recommend_intervention(
        &self,
        fairness: FairnessType,
        risk: f64,
        stats: &MemberStats,
    ) -> String {
        if risk > 0.7 {
            return format!(
                "🚨 MTU HUYU ANA HATARI KUBWA YA KUONDOKA (risk: {:.0}%). \
                 Ongea naye moja kwa moja. Pendekeza mabadiliko ya michango au ratiba.",
                risk * 100.0
            );
        }

        let base = fairness.chama_strategy();
        if risk > 0.4 {
            format!("⚠️ {} (risk: {:.0}%)", base, risk * 100.0)
        } else {
            format!("✅ {}", base)
        }
    }

    /// Calculate Gini coefficient
    fn gini_coefficient(&self, values: &[f64]) -> f64 {
        if values.len() < 2 {
            return 0.0;
        }

        let n = values.len() as f64;
        let mean = values.iter().sum::<f64>() / n;

        if mean == 0.0 {
            return 0.0;
        }

        let mut sorted = values.to_vec();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());

        let mut gini_sum = 0.0;
        for (i, val) in sorted.iter().enumerate() {
            gini_sum += (2.0 * (i as f64 + 1.0) - n - 1.0) * val;
        }

        (gini_sum / (n * n * mean)).abs()
    }

    /// Calculate group stability score
    fn group_stability_score(&self, profiles: &[InequalityAversion], gini: f64) -> f64 {
        if profiles.is_empty() {
            return 0.0;
        }

        let mut score = 1.0;

        // High Gini → less stable
        score -= gini * 0.3;

        // Members with high defection risk → less stable
        let high_risk_count = profiles.iter().filter(|p| p.defection_risk > 0.5).count();
        score -= (high_risk_count as f64 / profiles.len() as f64) * 0.3;

        // Mismatched fairness types → less stable
        let egalitarian_count = profiles
            .iter()
            .filter(|p| p.fairness_type == FairnessType::Egalitarian)
            .count();
        let selfish_count = profiles
            .iter()
            .filter(|p| p.fairness_type == FairnessType::Selfish)
            .count();
        if selfish_count > 0 && egalitarian_count > 0 {
            score -= 0.2; // clash of fairness values
        }

        // Low average utility → less stable
        let avg_utility =
            profiles.iter().map(|p| p.utility_score).sum::<f64>() / profiles.len() as f64;
        if avg_utility < 0.0 {
            score -= 0.2;
        }

        score.max(0.0).min(1.0)
    }

    /// Generate group-level interventions
    fn group_interventions(
        &self,
        profiles: &[InequalityAversion],
        gini: f64,
        stability: f64,
    ) -> Vec<String> {
        let mut interventions = Vec::new();

        if gini > 0.3 {
            interventions.push(
                "⚠️ Utoaji wa michango si sawa. Fikiria kurekebisha michango kulingana na uwezo wa kila mtu."
                    .to_string(),
            );
        }

        if stability < 0.5 {
            interventions.push(
                "🚨 Chama hii si thabiti. Fanya mkutano wa dharura kujadili michango na malengo."
                    .to_string(),
            );
        }

        let envious_count = profiles
            .iter()
            .filter(|p| p.fairness_type == FairnessType::Envious)
            .count();
        if envious_count > profiles.len() / 3 {
            interventions.push(
                "📋 Wanachama wengi wana wivu. Onyesha ripoti ya michango ya kila mtu kwa uwazi."
                    .to_string(),
            );
        }

        let high_defection = profiles.iter().filter(|p| p.defection_risk > 0.6).count();
        if high_defection > 0 {
            interventions.push(format!(
                "🔔 Wanachama {} wanaweza kuondoka. Ongea nao na pendekeza mabadiliko.",
                high_defection
            ));
        }

        if interventions.is_empty() {
            interventions
                .push("✅ Chama iko sawa! Endelea na michango ya kawaida na uwazi.".to_string());
        }

        interventions
    }
}

impl Default for InequalityAversionEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Internal member statistics
struct MemberStats {
    avg_contribution: f64,
    on_time_rate: f64,
    penalty_rate: f64,
    cycle_count: usize,
    amounts: Vec<f64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_contribution(
        member: &str,
        amount: f64,
        cycle: usize,
        on_time: bool,
    ) -> ContributionRecord {
        ContributionRecord {
            member_id: member.to_string(),
            amount,
            expected: 1000.0,
            cycle,
            timestamp: 1700000000 + cycle as u64 * 604800,
            on_time,
            penalty_applied: !on_time,
        }
    }

    #[test]
    fn test_inequality_analysis_basic() {
        let engine = InequalityAversionEngine::new();

        let contributions = vec![
            // Member A: always pays on time, slightly above average
            make_contribution("A", 1100.0, 1, true),
            make_contribution("A", 1050.0, 2, true),
            make_contribution("A", 1100.0, 3, true),
            // Member B: sometimes late, average
            make_contribution("B", 1000.0, 1, true),
            make_contribution("B", 950.0, 2, false),
            make_contribution("B", 1000.0, 3, true),
            // Member C: often late, below average
            make_contribution("C", 800.0, 1, false),
            make_contribution("C", 750.0, 2, false),
            make_contribution("C", 850.0, 3, true),
        ];

        let analysis = engine
            .analyze_chama("chama_1", &contributions, 1000.0)
            .unwrap();

        assert_eq!(analysis.member_profiles.len(), 3);
        assert!(analysis.gini_coefficient > 0.0);
        assert!(analysis.stability_score > 0.0);
        assert!(analysis.stability_score <= 1.0);

        // Member C should have highest defection risk
        let c_profile = analysis
            .member_profiles
            .iter()
            .find(|p| p.member_id == "C")
            .unwrap();
        assert!(c_profile.defection_risk > 0.3);
    }

    #[test]
    fn test_gini_perfect_equality() {
        let engine = InequalityAversionEngine::new();
        let values = vec![100.0, 100.0, 100.0, 100.0];
        let gini = engine.gini_coefficient(&values);
        assert!(gini < 0.01, "Perfect equality should have Gini ≈ 0");
    }

    #[test]
    fn test_gini_inequality() {
        let engine = InequalityAversionEngine::new();
        let values = vec![0.0, 0.0, 0.0, 1000.0];
        let gini = engine.gini_coefficient(&values);
        assert!(gini > 0.5, "High inequality should have high Gini");
    }

    #[test]
    fn test_fairness_type_classification() {
        let engine = InequalityAversionEngine::new();

        // High α, high β → Egalitarian
        assert_eq!(
            engine.classify_fairness_type(0.8, 0.6),
            FairnessType::Egalitarian
        );
        // High α, low β → Envious
        assert_eq!(
            engine.classify_fairness_type(0.7, 0.2),
            FairnessType::Envious
        );
        // Low α, high β → AltruisticFair
        assert_eq!(
            engine.classify_fairness_type(0.3, 0.5),
            FairnessType::AltruisticFair
        );
    }

    #[test]
    fn test_insufficient_members() {
        let engine = InequalityAversionEngine::new();
        let contributions = vec![make_contribution("A", 1000.0, 1, true)];
        assert!(engine
            .analyze_chama("chama_1", &contributions, 1000.0)
            .is_none());
    }
}
