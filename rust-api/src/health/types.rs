//! Health metrics types — occupation hazard risk assessment

use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Anonymized worker identifier (SHA-256 hash)
pub type AnonymizedId = String;

/// All supported occupation types in the informal economy.
/// Maps to worker_type in kg_worker_cohorts.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum OccupationType {
    BodaBodaRider,
    Miner,
    ConstructionWorker,
    Farmer,
    Fisherman,
    MarketVendor,
    SalonWorker,
    HouseholdWorker,
    Hawker,
    JuaKaliArtisan,
    MatatuOperator,
    MPesaAgent,
    DukaOwner,
    FoodSeller,
    WastePicker,
    CrossBorderTrader,
}

/// Severity levels for individual hazards.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum HazardSeverity {
    Low,       // 1.0–1.5x multiplier
    Moderate,  // 1.5–2.5x multiplier
    High,      // 2.5–3.5x multiplier
    Critical,  // 3.5–5.0x multiplier
}

/// Categories of occupational hazards (ILO/WHO classification).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum HazardCategory {
    Accident,              // Acute injury risk
    Respiratory,           // Dust, fumes, gas exposure
    Musculoskeletal,       // Repetitive strain, heavy lifting
    ChemicalExposure,      // Toxins, carcinogens
    BiologicalExposure,    // Pathogens, zoonotic diseases
    EnvironmentalExposure, // Weather, UV, heat/cold
    MentalHealth,          // Stress, isolation, trauma
    Violence,              // Robbery, assault, harassment
    HearingDamage,         // Noise-induced hearing loss
    Ergonomic,             // Poor posture, vibration
}

/// A single hazard within an occupation's risk profile.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hazard {
    pub id: String,                          // e.g., "boda_accident_road"
    pub category: HazardCategory,
    pub name: String,                        // Human-readable name
    pub description: String,                 // What this hazard is
    pub severity: HazardSeverity,
    pub base_risk_multiplier: f64,           // 1.0–5.0
    pub prevalence: f64,                     // 0.0–1.0, fraction of workers affected
    pub data_signals: Vec<DataSignal>,       // What we can observe from transaction data
    pub mitigation_factors: Vec<String>,     // What reduces this risk
    pub who_reference: Option<String>,       // WHO/ILO reference code
    pub recommended_insurance: Vec<InsuranceProductType>,
}

/// Observable signals from transaction/pattern data that indicate exposure level.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataSignal {
    pub name: String,
    pub description: String,
    pub source: DataSource,
    pub impact_on_risk: RiskDirection,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DataSource {
    TransactionPatterns,  // Inferred from transaction timing/amounts
    WorkHours,            // Inferred from activity patterns
    LocationData,         // Coarse location (urban/rural, region)
    SelfReported,         // Worker-provided occupation details
    SeasonalPatterns,     // Time-of-year risk variation
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RiskDirection {
    Increases,  // Higher signal value → higher risk
    Decreases,  // Higher signal value → lower risk (protective)
}

/// Complete risk profile for an occupation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OccupationRiskProfile {
    pub occupation: OccupationType,
    pub display_name: String,                  // "Boda Boda Rider"
    pub display_name_sw: String,               // "Msafiri wa Boda Boda"
    pub overall_risk_multiplier: f64,          // Composite multiplier
    pub hazards: Vec<Hazard>,
    pub typical_work_hours_per_day: f64,
    pub exposure_duration_years_avg: f64,      // Average years in occupation
    pub notes: String,                         // Context for risk assessors
}

/// The computed risk output for a specific worker.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OccupationalRiskProfile {
    pub occupation: OccupationType,
    pub overall_risk_multiplier: f64,
    pub hazard_scores: Vec<HazardScore>,
    pub top_risks: Vec<TopRisk>,               // Top 3 risks for explanation
    pub protective_factors: Vec<String>,       // What reduces their risk
    pub risk_tier: RiskTier,                   // Low / Moderate / High / Critical
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HazardScore {
    pub hazard_id: String,
    pub hazard_name: String,
    pub category: HazardCategory,
    pub base_severity: HazardSeverity,
    pub adjusted_severity: HazardSeverity,     // After location/signal adjustment
    pub risk_contribution: f64,                // Contribution to overall score
    pub exposure_level: ExposureLevel,         // Inferred from data signals
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ExposureLevel {
    Minimal,    // Very low exposure
    Low,        // Below typical for occupation
    Moderate,   // Typical exposure
    High,       // Above typical (e.g., very long hours)
    Extreme,    // Maximum exposure (e.g., 14+ hour days)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TopRisk {
    pub rank: u8,                              // 1, 2, or 3
    pub hazard_name: String,
    pub hazard_name_local: String,             // Swahili name
    pub severity: HazardSeverity,
    pub explanation: String,                   // "You ride 10+ hours daily on busy roads"
    pub actionable_advice: String,             // "Wear a helmet, avoid night riding"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RiskTier {
    Low,        // Score 1.0–1.5
    Moderate,   // Score 1.5–2.5
    High,       // Score 2.5–3.5
    Critical,   // Score 3.5–5.0
}

/// The composite health risk score combining all factors.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompositeHealthRisk {
    pub overall_score: f64,              // 1.0 (lowest risk) to 5.0 (highest risk)
    pub risk_tier: RiskTier,
    pub components: RiskComponents,
    pub explanation: RiskExplanation,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskComponents {
    pub occupation_risk_score: f64,      // From occupation-hazard matrix
    pub location_risk_score: f64,        // From location adjustment
    pub exposure_adjustment: f64,        // From data signals (work hours, patterns)
    pub income_stability_factor: f64,    // RETAINED but reduced weight
    pub protective_factors_adjustment: f64,  // Negative (reduces risk)
}

/// Worker-facing explanation of their risk score.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskExplanation {
    pub summary: String,                 // One-line summary
    pub summary_local: String,           // In Swahili
    pub top_risks: Vec<TopRisk>,         // Top 3 risks with explanations
    pub protective_actions: Vec<String>, // What they can do to reduce risk
    pub insurance_recommendation: String, // Plain language insurance advice
}

impl CompositeHealthRisk {
    /// Calculate composite risk from all components.
    ///
    /// Formula:
    ///   composite = occupation_risk × location_multiplier × exposure_adjustment
    ///               × (0.7 + 0.3 × income_instability_factor)
    ///               - protective_adjustment
    ///
    /// Where:
    ///   - occupation_risk: from hazard matrix (1.0-5.0)
    ///   - location_multiplier: from location profile (0.8-1.5)
    ///   - exposure_adjustment: from data signals (0.8-1.5)
    ///   - income_instability_factor: 0.0 (stable) to 1.0 (volatile) — reduced weight
    ///   - protective_adjustment: 0.0-0.5 based on mitigation factors observed
    pub fn calculate(
        occupation_risk: &OccupationalRiskProfile,
        location_risk: &LocationRiskAdjustment,
        exposure_signals: &ExposureSignals,
        income_stability: f64,  // 0.0 (volatile) to 1.0 (stable)
    ) -> Self {
        let occupation_score = occupation_risk.overall_risk_multiplier;
        let location_mult = location_risk.calculate_multiplier();
        let exposure_adj = exposure_signals.calculate_adjustment();

        // Income instability: stable income (1.0) reduces risk slightly, volatile (0.0) increases
        // Weight reduced from 1.0 (old model) to 0.3 (new model)
        let income_factor = 0.7 + 0.3 * (1.0 - income_stability);

        // Protective factors reduce risk (observed from data)
        let protective_adj = occupation_risk.protective_adjustment();

        let raw_score = occupation_score * location_mult * exposure_adj * income_factor - protective_adj;
        let overall_score = raw_score.clamp(1.0, 5.0);

        let risk_tier = match overall_score {
            s if s < 1.5 => RiskTier::Low,
            s if s < 2.5 => RiskTier::Moderate,
            s if s < 3.5 => RiskTier::High,
            _ => RiskTier::Critical,
        };

        CompositeHealthRisk {
            overall_score,
            risk_tier,
            components: RiskComponents {
                occupation_risk_score: occupation_score,
                location_risk_score: location_mult,
                exposure_adjustment: exposure_adj,
                income_stability_factor: income_factor,
                protective_factors_adjustment: protective_adj,
            },
            explanation: RiskExplanation::generate(occupation_risk, &risk_tier, overall_score),
        }
    }
}

/// Observable signals from transaction patterns that modify risk.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExposureSignals {
    pub estimated_daily_hours: f64,      // Inferred from transaction timing
    pub night_activity_ratio: f64,       // Fraction of activity after 8PM
    pub weekend_activity_ratio: f64,     // No rest days = higher risk
    pub seasonal_consistency: f64,       // How consistent across seasons
    pub income_volatility: f64,          // Coefficient of variation
    pub cash_dominance: f64,             // Fraction of cash vs M-Pesa
}

impl ExposureSignals {
    /// Calculate exposure adjustment multiplier from observable signals.
    ///
    /// Range: 0.8 (favorable patterns) to 1.5 (unfavorable patterns)
    pub fn calculate_adjustment(&self) -> f64 {
        let mut adjustment = 1.0;

        // Long hours increase risk
        if self.estimated_daily_hours > 12.0 {
            adjustment += 0.15;
        } else if self.estimated_daily_hours > 10.0 {
            adjustment += 0.08;
        } else if self.estimated_daily_hours < 6.0 {
            adjustment -= 0.05;  // Part-time = lower exposure
        }

        // Night activity increases risk (accidents, robbery)
        if self.night_activity_ratio > 0.3 {
            adjustment += 0.15;
        } else if self.night_activity_ratio > 0.15 {
            adjustment += 0.08;
        }

        // No rest days increases risk
        if self.weekend_activity_ratio > 0.8 {
            adjustment += 0.10;
        }

        // High cash dominance increases robbery risk
        if self.cash_dominance > 0.7 {
            adjustment += 0.08;
        }

        adjustment.clamp(0.8, 1.5)
    }
}
