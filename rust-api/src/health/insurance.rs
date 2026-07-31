//! Insurance eligibility engine and product matching

use super::types::*;
use serde::{Deserialize, Serialize};

/// Types of insurance products in our catalog.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum InsuranceProductType {
    PersonalAccident,      // Covers accidental injury/death
    MotorVehicle,          // Motorcycle/vehicle insurance
    OutpatientCover,       // OPD visits, medication
    InpatientCover,        // Hospitalization
    CriticalIllness,       // Cancer, organ failure, chronic disease
    Disability,            // Permanent/temporary disability
    LifeInsurance,         // Death benefit
    MentalHealthCover,     // Counseling, psychiatric care
}

/// An insurance product in our catalog.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InsuranceProduct {
    pub id: String,
    pub name: String,
    pub name_local: String,
    pub product_type: InsuranceProductType,
    pub provider: String,               // Insurance company name
    pub monthly_premium_base: f64,      // Base monthly premium (KES)
    pub coverage_amount: f64,           // Maximum coverage (KES)
    pub coverage_description: String,
    pub eligibility_criteria: EligibilityCriteria,
    pub risk_loadings: RiskLoadings,    // How risk score affects premium
}

/// Criteria for insurance eligibility.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EligibilityCriteria {
    pub min_age: u8,
    pub max_age: u8,
    pub max_risk_tier: RiskTier,        // Won't sell above this risk
    pub excluded_occupations: Vec<OccupationType>,
    pub min_income_stability: f64,      // Minimum income stability score
    pub requires_health_screening: bool,
}

/// How risk score adjusts premium.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskLoadings {
    pub base_multiplier: f64,           // 1.0 at base risk
    pub per_risk_tier_increment: f64,   // +X% per tier above Low
    pub occupation_loading: HashMap<OccupationType, f64>,
    pub location_loading: f64,          // Multiplier for high-risk locations
    pub max_premium_multiplier: f64,    // Cap on how high premium can go
}

/// Result of insurance eligibility assessment.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InsuranceEligibility {
    pub eligible_products: Vec<EligibleProduct>,
    pub ineligible_products: Vec<IneligibleProduct>,
    pub recommended_product: Option<EligibleProduct>,
    pub total_monthly_premium_range: PremiumRange,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EligibleProduct {
    pub product: InsuranceProduct,
    pub risk_adjusted_premium: f64,     // Monthly premium after risk loading
    pub premium_explanation: String,     // "Your premium is KES 800/month because..."
    pub coverage_adequacy: CoverageAdequacy,
    pub match_score: f64,               // How well this matches their risks (0-1)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IneligibleProduct {
    pub product_name: String,
    pub reason: String,                  // "Risk tier Critical exceeds maximum High"
    pub alternative: Option<String>,     // "Consider Personal Accident cover instead"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum CoverageAdequacy {
    FullyCovered,       // All top risks covered
    PartiallyCovered,   // Some risks covered, some not
    Insufficient,       // Coverage too low for risk level
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PremiumRange {
    pub min_monthly: f64,
    pub max_monthly: f64,
    pub currency: String,  // "KES"
}

/// Insurance eligibility engine.
pub struct InsuranceEligibilityEngine {
    product_catalog: Vec<InsuranceProduct>,
}

impl InsuranceEligibilityEngine {
    /// Find eligible insurance products for a worker based on their risk profile.
    pub fn assess_eligibility(
        &self,
        risk_profile: &CompositeHealthRisk,
        occupation: &OccupationType,
        age: u8,
        income_stability: f64,
    ) -> InsuranceEligibility {
        let mut eligible = Vec::new();
        let mut ineligible = Vec::new();

        for product in &self.product_catalog {
            match self.check_eligibility(product, risk_profile, occupation, age, income_stability) {
                Ok(adjusted_premium) => {
                    let match_score = self.calculate_match_score(product, risk_profile, occupation);
                    eligible.push(EligibleProduct {
                        product: product.clone(),
                        risk_adjusted_premium: adjusted_premium,
                        premium_explanation: self.explain_premium(product, adjusted_premium, risk_profile),
                        coverage_adequacy: self.assess_coverage(product, risk_profile),
                        match_score,
                    });
                }
                Err(reason) => {
                    ineligible.push(IneligibleProduct {
                        product_name: product.name.clone(),
                        reason,
                        alternative: self.suggest_alternative(product, risk_profile, occupation),
                    });
                }
            }
        }

        // Sort eligible by match score (best match first)
        eligible.sort_by(|a, b| b.match_score.partial_cmp(&a.match_score).unwrap_or(std::cmp::Ordering::Equal));

        let recommended = eligible.first().cloned();

        let premium_range = if eligible.is_empty() {
            PremiumRange { min_monthly: 0.0, max_monthly: 0.0, currency: "KES".into() }
        } else {
            let premiums: Vec<f64> = eligible.iter().map(|e| e.risk_adjusted_premium).collect();
            PremiumRange {
                min_monthly: premiums.iter().cloned().fold(f64::INFINITY, f64::min),
                max_monthly: premiums.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
                currency: "KES".into(),
            }
        };

        InsuranceEligibility {
            eligible_products: eligible,
            ineligible_products: ineligible,
            recommended_product: recommended,
            total_monthly_premium_range: premium_range,
        }
    }

    fn calculate_risk_adjusted_premium(
        &self,
        product: &InsuranceProduct,
        risk: &CompositeHealthRisk,
    ) -> f64 {
        let base = product.monthly_premium_base;
        let tier_multiplier = match risk.risk_tier {
            RiskTier::Low => 1.0,
            RiskTier::Moderate => 1.0 + product.risk_loadings.per_risk_tier_increment,
            RiskTier::High => 1.0 + 2.0 * product.risk_loadings.per_risk_tier_increment,
            RiskTier::Critical => 1.0 + 3.0 * product.risk_loadings.per_risk_tier_increment,
        };

        let raw_premium = base * tier_multiplier;
        let capped = raw_premium.min(base * product.risk_loadings.max_premium_multiplier);

        // Round to nearest 50 KES
        (capped / 50.0).ceil() * 50.0
    }

    fn calculate_match_score(
        &self,
        product: &InsuranceProduct,
        risk: &CompositeHealthRisk,
        occupation: &OccupationType,
    ) -> f64 {
        // Score based on how well the product covers the worker's top risks
        let mut score: f64 = 0.0;
        let occupation_profile = get_occupation_profile(occupation);

        for top_risk in &risk.explanation.top_risks {
            for hazard in &occupation_profile.hazards {
                if hazard.id == top_risk.hazard_name {
                    if hazard.recommended_insurance.contains(&product.product_type) {
                        score += match top_risk.severity {
                            HazardSeverity::Critical => 0.4,
                            HazardSeverity::High => 0.3,
                            HazardSeverity::Moderate => 0.2,
                            HazardSeverity::Low => 0.1,
                        };
                    }
                }
            }
        }

        score.min(1.0)
    }
}

impl InsuranceEligibilityEngine {
    fn explain_premium(
        &self,
        product: &InsuranceProduct,
        adjusted_premium: f64,
        risk: &CompositeHealthRisk,
    ) -> String {
        let base = product.monthly_premium_base;
        let increase_pct = ((adjusted_premium / base) - 1.0) * 100.0;

        if increase_pct < 5.0 {
            format!(
                "Your monthly premium is KES {:.0}. This is the standard rate because your risk level is {}.",
                adjusted_premium,
                match risk.risk_tier {
                    RiskTier::Low => "low",
                    RiskTier::Moderate => "moderate",
                    RiskTier::High => "high",
                    RiskTier::Critical => "very high",
                }
            )
        } else {
            format!(
                "Your monthly premium is KES {:.0} ({}% above base rate of KES {:.0}). \
                 This is because your occupation has {} health risks. \
                 You can reduce your premium by: {}",
                adjusted_premium,
                increase_pct as u32,
                base,
                match risk.risk_tier {
                    RiskTier::Low => "low",
                    RiskTier::Moderate => "moderate",
                    RiskTier::High => "elevated",
                    RiskTier::Critical => "very high",
                },
                risk.explanation.protective_actions.join(", ")
            )
        }
    }
}

impl RiskExplanation {
    fn generate(
        occupation_risk: &OccupationalRiskProfile,
        risk_tier: &RiskTier,
        overall_score: f64,
    ) -> RiskExplanation {
        let summary = match risk_tier {
            RiskTier::Low => format!(
                "Your health risk is LOW ({:.1}/5.0). Your occupation has relatively few hazards.",
                overall_score
            ),
            RiskTier::Moderate => format!(
                "Your health risk is MODERATE ({:.1}/5.0). You face some occupational hazards that you should manage.",
                overall_score
            ),
            RiskTier::High => format!(
                "Your health risk is HIGH ({:.1}/5.0). Your occupation exposes you to significant health hazards. \
                 Insurance is strongly recommended.",
                overall_score
            ),
            RiskTier::Critical => format!(
                "Your health risk is CRITICAL ({:.1}/5.0). Your occupation has severe health hazards. \
                 Insurance is essential. Please also consider safety improvements.",
                overall_score
            ),
        };

        let summary_local = translate_to_swahili(&summary);

        let top_risks: Vec<TopRisk> = occupation_risk.hazard_scores
            .iter()
            .sorted_by(|a, b| b.risk_contribution.partial_cmp(&a.risk_contribution).unwrap_or(std::cmp::Ordering::Equal))
            .take(3)
            .enumerate()
            .map(|(i, hs)| TopRisk {
                rank: (i + 1) as u8,
                hazard_name: hs.hazard_name.clone(),
                hazard_name_local: translate_hazard_name(&hs.hazard_id),
                severity: hs.adjusted_severity,
                explanation: explain_hazard(hs),
                actionable_advice: advise_for_hazard(hs),
            })
            .collect();

        let protective_actions: Vec<String> = occupation_risk.protective_factors
            .iter()
            .map(|pf| pf.clone())
            .collect();

        let insurance_recommendation = match risk_tier {
            RiskTier::Low => "Basic outpatient cover is sufficient for your risk level.".into(),
            RiskTier::Moderate => "We recommend outpatient + personal accident cover.".into(),
            RiskTier::High => "We strongly recommend comprehensive cover including inpatient and personal accident.".into(),
            RiskTier::Critical => "You need comprehensive insurance covering critical illness, inpatient, and personal accident. \
                                  Please also consider life insurance.".into(),
        };

        RiskExplanation {
            summary,
            summary_local,
            top_risks,
            protective_actions,
            insurance_recommendation,
        }
    }
}
