// =============================================================================
// Angavu Intelligence — Occupation Hazard Matrix Module
// Formal risk scoring per worker type for the orchestrator.
//
// Bridges the health::occupation_hazards profiles into the orchestrator
// message bus, providing standardized risk scores per occupation.
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Formal risk score for a worker type
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OccupationRiskScore {
    pub occupation: String,
    pub display_name: String,
    pub display_name_sw: String,
    pub overall_risk_multiplier: f64,
    pub risk_tier: String,
    pub hazard_count: usize,
    pub critical_hazards: Vec<String>,
    pub high_hazards: Vec<String>,
    pub typical_work_hours: f64,
    pub recommended_insurance_types: Vec<String>,
}

/// Hazard entry in the matrix
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HazardEntry {
    pub id: String,
    pub name: String,
    pub category: String,
    pub severity: String,
    pub base_risk_multiplier: f64,
    pub prevalence: f64,
    pub who_reference: Option<String>,
}

/// Full occupation hazard matrix
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OccupationHazardMatrix {
    pub occupations: Vec<OccupationRiskScore>,
    pub hazard_entries: HashMap<String, Vec<HazardEntry>>,
}

/// Module that computes and serves occupation hazard matrices
pub struct OccupationHazardMatrixModule {
    matrix: OccupationHazardMatrix,
}

impl OccupationHazardMatrixModule {
    pub fn new() -> Self {
        Self {
            matrix: Self::build_matrix(),
        }
    }

    /// Build the complete occupation hazard matrix
    fn build_matrix() -> OccupationHazardMatrix {
        let occupations = vec![
            Self::boda_boda_score(),
            Self::miner_score(),
            Self::construction_score(),
            Self::farmer_score(),
            Self::fisherman_score(),
            Self::market_vendor_score(),
            Self::salon_worker_score(),
            Self::household_worker_score(),
            Self::hawker_score(),
            Self::jua_kali_score(),
            Self::matatu_score(),
            Self::mpesa_agent_score(),
            Self::duka_owner_score(),
            Self::food_seller_score(),
            Self::waste_picker_score(),
            Self::cross_border_trader_score(),
        ];

        let mut hazard_entries = HashMap::new();

        // Boda boda hazards
        hazard_entries.insert(
            "boda_boda".into(),
            vec![
                HazardEntry {
                    id: "boda_accident".into(),
                    name: "Road Traffic Accident".into(),
                    category: "Accident".into(),
                    severity: "Critical".into(),
                    base_risk_multiplier: 4.5,
                    prevalence: 0.35,
                    who_reference: Some("ICD-10: V20-V29".into()),
                },
                HazardEntry {
                    id: "boda_musculoskeletal".into(),
                    name: "Joint and Back Problems".into(),
                    category: "Musculoskeletal".into(),
                    severity: "High".into(),
                    base_risk_multiplier: 2.8,
                    prevalence: 0.45,
                    who_reference: Some("ICD-10: M54".into()),
                },
                HazardEntry {
                    id: "boda_mental_health".into(),
                    name: "Stress and Anxiety".into(),
                    category: "MentalHealth".into(),
                    severity: "High".into(),
                    base_risk_multiplier: 2.5,
                    prevalence: 0.40,
                    who_reference: Some("ICD-10: F41".into()),
                },
                HazardEntry {
                    id: "boda_violence".into(),
                    name: "Robbery and Assault".into(),
                    category: "Violence".into(),
                    severity: "High".into(),
                    base_risk_multiplier: 3.0,
                    prevalence: 0.20,
                    who_reference: None,
                },
            ],
        );

        // Miner hazards
        hazard_entries.insert(
            "miner".into(),
            vec![
                HazardEntry {
                    id: "miner_respiratory".into(),
                    name: "Silicosis and TB".into(),
                    category: "Respiratory".into(),
                    severity: "Critical".into(),
                    base_risk_multiplier: 4.5,
                    prevalence: 0.25,
                    who_reference: Some("ICD-10: J62".into()),
                },
                HazardEntry {
                    id: "miner_heavy_metal".into(),
                    name: "Heavy Metal Exposure".into(),
                    category: "ChemicalExposure".into(),
                    severity: "Critical".into(),
                    base_risk_multiplier: 4.2,
                    prevalence: 0.60,
                    who_reference: Some("ICD-10: T56".into()),
                },
                HazardEntry {
                    id: "miner_cave_in".into(),
                    name: "Cave-In".into(),
                    category: "Accident".into(),
                    severity: "Critical".into(),
                    base_risk_multiplier: 4.0,
                    prevalence: 0.08,
                    who_reference: Some("ICD-10: W20-W49".into()),
                },
            ],
        );

        // Construction hazards
        hazard_entries.insert(
            "construction".into(),
            vec![
                HazardEntry {
                    id: "construction_fall".into(),
                    name: "Fall from Height".into(),
                    category: "Accident".into(),
                    severity: "Critical".into(),
                    base_risk_multiplier: 4.0,
                    prevalence: 0.15,
                    who_reference: Some("ICD-10: W00-W19".into()),
                },
                HazardEntry {
                    id: "construction_dust".into(),
                    name: "Dust Exposure".into(),
                    category: "Respiratory".into(),
                    severity: "High".into(),
                    base_risk_multiplier: 3.0,
                    prevalence: 0.70,
                    who_reference: Some("ICD-10: J60-J67".into()),
                },
            ],
        );

        // Farmer hazards
        hazard_entries.insert(
            "farmer".into(),
            vec![
                HazardEntry {
                    id: "farmer_pesticide".into(),
                    name: "Pesticide Exposure".into(),
                    category: "ChemicalExposure".into(),
                    severity: "Critical".into(),
                    base_risk_multiplier: 3.5,
                    prevalence: 0.50,
                    who_reference: Some("ICD-10: T60".into()),
                },
                HazardEntry {
                    id: "farmer_heat".into(),
                    name: "Heat Stress".into(),
                    category: "EnvironmentalExposure".into(),
                    severity: "High".into(),
                    base_risk_multiplier: 2.5,
                    prevalence: 0.80,
                    who_reference: Some("ICD-10: T67".into()),
                },
            ],
        );

        OccupationHazardMatrix {
            occupations,
            hazard_entries,
        }
    }

    fn boda_boda_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "boda_boda".into(),
            display_name: "Boda Boda Rider".into(),
            display_name_sw: "Msafiri wa Boda Boda".into(),
            overall_risk_multiplier: 3.5,
            risk_tier: "Critical".into(),
            hazard_count: 6,
            critical_hazards: vec!["Road Traffic Accident".into()],
            high_hazards: vec!["Joint Problems".into(), "Stress".into(), "Robbery".into()],
            typical_work_hours: 11.0,
            recommended_insurance_types: vec![
                "PersonalAccident".into(),
                "MotorVehicle".into(),
                "MentalHealth".into(),
            ],
        }
    }

    fn miner_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "miner".into(),
            display_name: "Artisanal Miner".into(),
            display_name_sw: "Mchimbaji Madini".into(),
            overall_risk_multiplier: 4.0,
            risk_tier: "Critical".into(),
            hazard_count: 5,
            critical_hazards: vec![
                "Silicosis/TB".into(),
                "Heavy Metal".into(),
                "Cave-In".into(),
            ],
            high_hazards: vec!["Hearing Loss".into(), "Back Injuries".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec![
                "CriticalIllness".into(),
                "InpatientCover".into(),
                "PersonalAccident".into(),
            ],
        }
    }

    fn construction_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "construction".into(),
            display_name: "Construction Worker".into(),
            display_name_sw: "Mjenzi".into(),
            overall_risk_multiplier: 3.0,
            risk_tier: "High".into(),
            hazard_count: 5,
            critical_hazards: vec!["Fall from Height".into()],
            high_hazards: vec!["Musculoskeletal".into(), "Dust".into(), "Electrical".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec!["PersonalAccident".into(), "Disability".into()],
        }
    }

    fn farmer_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "farmer".into(),
            display_name: "Farmer".into(),
            display_name_sw: "Mkulima".into(),
            overall_risk_multiplier: 2.5,
            risk_tier: "High".into(),
            hazard_count: 5,
            critical_hazards: vec!["Pesticide Exposure".into()],
            high_hazards: vec![
                "Heat Stress".into(),
                "Snake Bite".into(),
                "Zoonotic Disease".into(),
            ],
            typical_work_hours: 9.0,
            recommended_insurance_types: vec!["CriticalIllness".into(), "InpatientCover".into()],
        }
    }

    fn fisherman_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "fisherman".into(),
            display_name: "Fisherman".into(),
            display_name_sw: "Mvuvi".into(),
            overall_risk_multiplier: 3.2,
            risk_tier: "High".into(),
            hazard_count: 5,
            critical_hazards: vec!["Drowning".into()],
            high_hazards: vec!["UV Exposure".into(), "Waterborne Disease".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec!["PersonalAccident".into(), "LifeInsurance".into()],
        }
    }

    fn market_vendor_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "market_vendor".into(),
            display_name: "Market Vendor".into(),
            display_name_sw: "Mama Mboga".into(),
            overall_risk_multiplier: 1.8,
            risk_tier: "Moderate".into(),
            hazard_count: 3,
            critical_hazards: vec![],
            high_hazards: vec![],
            typical_work_hours: 12.0,
            recommended_insurance_types: vec!["OutpatientCover".into()],
        }
    }

    fn salon_worker_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "salon_worker".into(),
            display_name: "Salon Worker".into(),
            display_name_sw: "Mfanyakazi wa Saluni".into(),
            overall_risk_multiplier: 2.2,
            risk_tier: "High".into(),
            hazard_count: 3,
            critical_hazards: vec![],
            high_hazards: vec!["Chemical Exposure".into(), "Respiratory".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec!["CriticalIllness".into(), "OutpatientCover".into()],
        }
    }

    fn household_worker_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "household_worker".into(),
            display_name: "Household Worker".into(),
            display_name_sw: "Mfanyakazi wa Nyumbani".into(),
            overall_risk_multiplier: 2.0,
            risk_tier: "Moderate".into(),
            hazard_count: 4,
            critical_hazards: vec![],
            high_hazards: vec!["Mental Health".into(), "Violence".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec![
                "MentalHealthCover".into(),
                "PersonalAccident".into(),
            ],
        }
    }

    fn hawker_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "hawker".into(),
            display_name: "Hawker".into(),
            display_name_sw: "Mtuza Bidhaa".into(),
            overall_risk_multiplier: 2.2,
            risk_tier: "High".into(),
            hazard_count: 4,
            critical_hazards: vec![],
            high_hazards: vec!["Traffic Accident".into(), "Police Harassment".into()],
            typical_work_hours: 12.0,
            recommended_insurance_types: vec!["PersonalAccident".into(), "OutpatientCover".into()],
        }
    }

    fn jua_kali_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "jua_kali".into(),
            display_name: "Jua Kali Artisan".into(),
            display_name_sw: "Mfundi Jua Kali".into(),
            overall_risk_multiplier: 2.8,
            risk_tier: "High".into(),
            hazard_count: 4,
            critical_hazards: vec![],
            high_hazards: vec!["Metal Fume".into(), "Noise".into(), "Eye Injury".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec!["PersonalAccident".into(), "OutpatientCover".into()],
        }
    }

    fn matatu_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "matatu".into(),
            display_name: "Matatu Operator".into(),
            display_name_sw: "Dereva wa Matatu".into(),
            overall_risk_multiplier: 2.5,
            risk_tier: "High".into(),
            hazard_count: 3,
            critical_hazards: vec![],
            high_hazards: vec!["Accident".into(), "Stress".into()],
            typical_work_hours: 12.0,
            recommended_insurance_types: vec!["PersonalAccident".into(), "MotorVehicle".into()],
        }
    }

    fn mpesa_agent_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "mpesa_agent".into(),
            display_name: "M-Pesa Agent".into(),
            display_name_sw: "Wakala wa M-Pesa".into(),
            overall_risk_multiplier: 1.5,
            risk_tier: "Moderate".into(),
            hazard_count: 2,
            critical_hazards: vec![],
            high_hazards: vec!["Robbery".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec!["PersonalAccident".into()],
        }
    }

    fn duka_owner_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "duka_owner".into(),
            display_name: "Duka Owner".into(),
            display_name_sw: "Mmiliki wa Duka".into(),
            overall_risk_multiplier: 1.5,
            risk_tier: "Moderate".into(),
            hazard_count: 2,
            critical_hazards: vec![],
            high_hazards: vec![],
            typical_work_hours: 12.0,
            recommended_insurance_types: vec!["StockProtection".into(), "OutpatientCover".into()],
        }
    }

    fn food_seller_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "food_seller".into(),
            display_name: "Food Seller".into(),
            display_name_sw: "Mzaa Chakula".into(),
            overall_risk_multiplier: 2.0,
            risk_tier: "Moderate".into(),
            hazard_count: 3,
            critical_hazards: vec![],
            high_hazards: vec!["Smoke Inhalation".into()],
            typical_work_hours: 11.0,
            recommended_insurance_types: vec!["OutpatientCover".into(), "PersonalAccident".into()],
        }
    }

    fn waste_picker_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "waste_picker".into(),
            display_name: "Waste Picker".into(),
            display_name_sw: "Mkusanyaji Taka".into(),
            overall_risk_multiplier: 3.5,
            risk_tier: "Critical".into(),
            hazard_count: 4,
            critical_hazards: vec!["Biological Exposure".into()],
            high_hazards: vec!["Chemical Exposure".into(), "Respiratory".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec![
                "CriticalIllness".into(),
                "InpatientCover".into(),
                "PersonalAccident".into(),
            ],
        }
    }

    fn cross_border_trader_score() -> OccupationRiskScore {
        OccupationRiskScore {
            occupation: "cross_border_trader".into(),
            display_name: "Cross-Border Trader".into(),
            display_name_sw: "Mfanyabiashara wa Mpakani".into(),
            overall_risk_multiplier: 2.0,
            risk_tier: "Moderate".into(),
            hazard_count: 3,
            critical_hazards: vec![],
            high_hazards: vec!["Road Accident".into(), "Robbery".into()],
            typical_work_hours: 10.0,
            recommended_insurance_types: vec!["PersonalAccident".into(), "TravelInsurance".into()],
        }
    }

    /// Get risk score for a specific occupation
    pub fn get_risk_score(&self, occupation: &str) -> Option<&OccupationRiskScore> {
        self.matrix
            .occupations
            .iter()
            .find(|o| o.occupation == occupation)
    }

    /// Get all occupations sorted by risk (highest first)
    pub fn get_ranked(&self) -> Vec<&OccupationRiskScore> {
        let mut ranked: Vec<_> = self.matrix.occupations.iter().collect();
        ranked.sort_by(|a, b| {
            b.overall_risk_multiplier
                .partial_cmp(&a.overall_risk_multiplier)
                .unwrap()
        });
        ranked
    }

    /// Get hazards for an occupation
    pub fn get_hazards(&self, occupation: &str) -> Option<&Vec<HazardEntry>> {
        self.matrix.hazard_entries.get(occupation)
    }

    /// Get the full matrix
    pub fn matrix(&self) -> &OccupationHazardMatrix {
        &self.matrix
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_all_occupations_have_scores() {
        let module = OccupationHazardMatrixModule::new();
        assert_eq!(module.matrix().occupations.len(), 16);
    }

    #[test]
    fn test_miner_is_highest_risk() {
        let module = OccupationHazardMatrixModule::new();
        let ranked = module.get_ranked();
        assert_eq!(ranked[0].occupation, "miner");
    }

    #[test]
    fn test_risk_tiers_valid() {
        let module = OccupationHazardMatrixModule::new();
        for occ in &module.matrix().occupations {
            assert!(matches!(
                occ.risk_tier.as_str(),
                "Low" | "Moderate" | "High" | "Critical"
            ));
            assert!(occ.overall_risk_multiplier >= 1.0 && occ.overall_risk_multiplier <= 5.0);
        }
    }

    #[test]
    fn test_get_hazards() {
        let module = OccupationHazardMatrixModule::new();
        let hazards = module.get_hazards("boda_boda").unwrap();
        assert!(!hazards.is_empty());
        assert!(hazards.iter().any(|h| h.severity == "Critical"));
    }
}
