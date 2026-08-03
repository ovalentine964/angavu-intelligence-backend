// =============================================================================
// Angavu Intelligence — Health Economics Module
// QALY/DALY calculations for informal worker health impact assessment.
//
// Addresses cross-cutting gap: Health economics
// - Quality-Adjusted Life Years (QALY) computation
// - Disability-Adjusted Life Years (DALY) computation
// - Cost-effectiveness analysis for health interventions
// - Health utility scores by occupation and condition
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Health utility weights for QALY computation (0.0 = dead, 1.0 = perfect health)
/// Based on EQ-5D value sets adapted for Kenyan context
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthUtilityWeight {
    pub condition: String,
    pub condition_local: String,
    pub utility_weight: f64,
    pub source: String,
}

/// DALY components for a health condition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DalYComponents {
    pub condition: String,
    pub yll: f64,        // Years of Life Lost
    pub yld: f64,        // Years Lived with Disability
    pub total_daly: f64, // YLL + YLD
    pub disability_weight: f64,
    pub incidence: f64, // Cases per 1000 workers
    pub mean_age_onset: f64,
    pub mean_duration_years: f64,
    pub standard_life_expectancy: f64,
}

/// QALY computation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QalyResult {
    pub baseline_qaly: f64,
    pub intervention_qaly: f64,
    pub qaly_gained: f64,
    pub intervention_cost: f64,
    pub cost_per_qaly: f64,
    pub cost_effective: bool, // < 3x GDP per capita
    pub kenya_gdp_per_capita: f64,
}

/// Health economics module
pub struct HealthEconomicsModule {
    utility_weights: HashMap<String, f64>,
    disability_weights: HashMap<String, f64>,
    kenya_gdp_per_capita: f64, // USD 2026
    standard_life_expectancy: f64,
}

impl HealthEconomicsModule {
    pub fn new() -> Self {
        let mut utility_weights = HashMap::new();
        // EQ-5D-like utility weights for common conditions in informal workers
        utility_weights.insert("perfect_health".into(), 1.0);
        utility_weights.insert("mild_back_pain".into(), 0.85);
        utility_weights.insert("chronic_back_pain".into(), 0.65);
        utility_weights.insert("mild_depression".into(), 0.70);
        utility_weights.insert("moderate_depression".into(), 0.50);
        utility_weights.insert("severe_depression".into(), 0.30);
        utility_weights.insert("mild_anxiety".into(), 0.75);
        utility_weights.insert("moderate_anxiety".into(), 0.55);
        utility_weights.insert("silicosis".into(), 0.55);
        utility_weights.insert("tuberculosis".into(), 0.60);
        utility_weights.insert("hearing_loss_mild".into(), 0.88);
        utility_weights.insert("hearing_loss_severe".into(), 0.65);
        utility_weights.insert("permanent_disability".into(), 0.30);
        utility_weights.insert("amputation".into(), 0.40);
        utility_weights.insert("burns_moderate".into(), 0.60);
        utility_weights.insert("burns_severe".into(), 0.35);
        utility_weights.insert("pesticide_poisoning_acute".into(), 0.45);
        utility_weights.insert("pesticide_chronic".into(), 0.65);
        utility_weights.insert("mercury_poisoning".into(), 0.50);
        utility_weights.insert("fracture".into(), 0.70);
        utility_weights.insert("traumatic_brain_injury".into(), 0.35);

        let mut disability_weights = HashMap::new();
        // Global Burden of Disease disability weights
        disability_weights.insert("low_back_pain".into(), 0.067);
        disability_weights.insert("depression".into(), 0.352);
        disability_weights.insert("anxiety".into(), 0.133);
        disability_weights.insert("hearing_loss".into(), 0.165);
        disability_weights.insert("silicosis".into(), 0.295);
        disability_weights.insert("tuberculosis".into(), 0.333);
        disability_weights.insert("amputation_lower_limb".into(), 0.167);
        disability_weights.insert("burns".into(), 0.188);
        disability_weights.insert("traumatic_brain_injury".into(), 0.289);
        disability_weights.insert("chronic_respiratory".into(), 0.187);
        disability_weights.insert("pesticide_poisoning".into(), 0.250);
        disability_weights.insert("mercury_neurological".into(), 0.350);

        Self {
            utility_weights,
            disability_weights,
            kenya_gdp_per_capita: 2100.0,   // USD 2026 estimate
            standard_life_expectancy: 63.0, // Kenya average
        }
    }

    /// Compute QALYs for a health intervention
    ///
    /// QALY = Σ (utility_weight × years_in_state)
    /// Cost-effectiveness threshold: 3× GDP per capita = ~$6,300
    pub fn compute_qaly(
        &self,
        condition: &str,
        intervention_cost_usd: f64,
        years_benefit: f64,
        utility_without: f64,
        utility_with: f64,
    ) -> QalyResult {
        let baseline_qaly = utility_without * years_benefit;
        let intervention_qaly = utility_with * years_benefit;
        let qaly_gained = intervention_qaly - baseline_qaly;

        let cost_per_qaly = if qaly_gained > 0.0 {
            intervention_cost_usd / qaly_gained
        } else {
            f64::INFINITY
        };

        let threshold = self.kenya_gdp_per_capita * 3.0;

        QalyResult {
            baseline_qaly,
            intervention_qaly,
            qaly_gained,
            intervention_cost: intervention_cost_usd,
            cost_per_qaly,
            cost_effective: cost_per_qaly <= threshold,
            kenya_gdp_per_capita: self.kenya_gdp_per_capita,
        }
    }

    /// Compute DALY for a condition in a worker population
    ///
    /// DALY = YLL + YLD
    /// YLL = deaths × standard_life_expectancy_at_death_age
    /// YLD = incidence × disability_weight × mean_duration
    pub fn compute_daly(
        &self,
        condition: &str,
        incidence_per_1000: f64,
        mortality_per_1000: f64,
        mean_age_onset: f64,
        mean_duration_years: f64,
        disability_weight: f64,
    ) -> DalYComponents {
        // YLL: years of life lost per case
        let remaining_life = (self.standard_life_expectancy - mean_age_onset).max(0.0);
        let yll_per_case = remaining_life;
        let yll = (mortality_per_1000 / 1000.0) * yll_per_case;

        // YLD: years lived with disability per case
        let yld_per_case = disability_weight * mean_duration_years;
        let yld = (incidence_per_1000 / 1000.0) * yld_per_case;

        DalYComponents {
            condition: condition.to_string(),
            yll,
            yld,
            total_daly: yll + yld,
            disability_weight,
            incidence: incidence_per_1000,
            mean_age_onset,
            mean_duration_years,
            standard_life_expectancy: self.standard_life_expectancy,
        }
    }

    /// Get utility weight for a condition
    pub fn utility_weight(&self, condition: &str) -> f64 {
        self.utility_weights.get(condition).copied().unwrap_or(1.0)
    }

    /// Get disability weight for a condition
    pub fn disability_weight(&self, condition: &str) -> f64 {
        self.disability_weights
            .get(condition)
            .copied()
            .unwrap_or(0.0)
    }

    /// Cost-effectiveness analysis for a set of interventions
    pub fn rank_interventions(&self, interventions: &[(String, QalyResult)]) -> Vec<(String, f64)> {
        let mut ranked: Vec<_> = interventions
            .iter()
            .filter(|(_, q)| q.cost_effective && q.qaly_gained > 0.0)
            .map(|(name, q)| (name.clone(), q.cost_per_qaly))
            .collect();
        ranked.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap());
        ranked
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_qaly_computation() {
        let module = HealthEconomicsModule::new();
        let result = module.compute_qaly(
            "depression",
            50.0, // $50 intervention (group therapy)
            5.0,  // 5 years benefit
            0.50, // moderate depression utility
            0.80, // mild depression after treatment
        );
        assert!(result.qaly_gained > 0.0);
        assert!(result.cost_per_qaly < 200.0); // Very cost-effective
        assert!(result.cost_effective);
    }

    #[test]
    fn test_daly_computation() {
        let module = HealthEconomicsModule::new();
        let daly = module.compute_daly(
            "silicosis",
            25.0,  // 25 per 1000 miners
            5.0,   // 5 deaths per 1000
            35.0,  // onset at 35
            20.0,  // 20 years duration
            0.295, // disability weight
        );
        assert!(daly.total_daly > 0.0);
        assert!(daly.yll > 0.0);
        assert!(daly.yld > 0.0);
    }

    #[test]
    fn test_utility_weights() {
        let module = HealthEconomicsModule::new();
        assert_eq!(module.utility_weight("perfect_health"), 1.0);
        assert!(module.utility_weight("severe_depression") < 0.5);
        assert!(module.utility_weight("nonexistent") == 1.0); // default
    }
}
