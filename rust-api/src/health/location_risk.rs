//! Geographic and environmental risk adjustments

use serde::{Deserialize, Serialize};

/// Geographic and environmental risk adjustments.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocationRiskAdjustment {
    pub facility_access: FacilityAccessScore,
    pub regional_disease: RegionalDiseaseBurden,
    pub water_quality: WaterQualityIndex,
    pub air_quality: AirQualityIndex,
    pub overall_location_multiplier: f64, // 0.8 (favorable) to 1.5 (unfavorable)
}

/// Access to healthcare facilities.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FacilityAccessScore {
    pub score: f64, // 0.0 (no access) to 1.0 (excellent access)
    pub nearest_health_center_km: f64,
    pub nearest_hospital_km: f64,
    pub has_emergency_services: bool,
    pub ambulance_availability: AmbulanceAvailability,
    pub description: String,  // "25km to nearest hospital"
    pub risk_adjustment: f64, // Multiplier: 1.0 (good) to 1.5 (poor)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AmbulanceAvailability {
    ReadilyAvailable, // <30 min response
    Limited,          // 30-60 min response
    Unavailable,      // No ambulance service
}

/// Regional disease prevalence.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionalDiseaseBurden {
    pub malaria_risk: DiseaseRiskLevel,
    pub tuberculosis_risk: DiseaseRiskLevel,
    pub hiv_prevalence: DiseaseRiskLevel,
    pub waterborne_disease_risk: DiseaseRiskLevel,
    pub rift_valley_fever_risk: DiseaseRiskLevel,
    pub schistosomiasis_risk: DiseaseRiskLevel,
    pub overall_disease_multiplier: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DiseaseRiskLevel {
    VeryLow,  // <5% prevalence
    Low,      // 5-10%
    Moderate, // 10-20%
    High,     // 20-35%
    VeryHigh, // >35%
}

/// Water quality and sanitation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WaterQualityIndex {
    pub score: f64, // 0.0 (contaminated) to 1.0 (clean)
    pub water_source: WaterSource,
    pub sanitation_level: SanitationLevel,
    pub risk_adjustment: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum WaterSource {
    PipedWater,      // Treated, reliable
    Borehole,        // Usually safe
    ProtectedWell,   // Moderately safe
    UnprotectedWell, // Risky
    SurfaceWater,    // River, lake — high risk
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SanitationLevel {
    Improved,       // Flush toilet, pit latrine with slab
    Shared,         // Shared facilities
    Unimproved,     // Open pit, no slab
    OpenDefecation, // No facilities
}

/// Air quality for urban workers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AirQualityIndex {
    pub score: f64,              // 0.0 (hazardous) to 1.0 (excellent)
    pub pm25_level: Option<f64>, // µg/m³
    pub primary_pollutant: Option<String>,
    pub risk_adjustment: f64,
}

impl LocationRiskAdjustment {
    /// Calculate overall location multiplier from component scores.
    ///
    /// Each component contributes to the final multiplier:
    /// - Poor facility access → higher multiplier (harder to get treatment)
    /// - High disease burden → higher multiplier (more background health risk)
    /// - Poor water quality → higher multiplier (waterborne disease risk)
    /// - Poor air quality → higher multiplier (respiratory risk for outdoor workers)
    pub fn calculate_multiplier(&self) -> f64 {
        // Weights
        let w_facility = 0.35; // Access to care matters most for outcomes
        let w_disease = 0.30; // Regional disease burden
        let w_water = 0.20; // Water/sanitation
        let w_air = 0.15; // Air quality

        // Each factor is 1.0 (favorable) to ~1.5 (unfavorable)
        let facility_factor = self.facility_access.risk_adjustment;
        let disease_factor = self.regional_disease.overall_disease_multiplier;
        let water_factor = self.water_quality.risk_adjustment;
        let air_factor = self.air_quality.risk_adjustment;

        let weighted = w_facility * facility_factor
            + w_disease * disease_factor
            + w_water * water_factor
            + w_air * air_factor;

        // Clamp to reasonable range
        weighted.clamp(0.8, 1.5)
    }
}

/// Example: Kisumu County (Lake Victoria region)
fn kisumu_location_profile() -> LocationRiskAdjustment {
    LocationRiskAdjustment {
        facility_access: FacilityAccessScore {
            score: 0.6,
            nearest_health_center_km: 5.0,
            nearest_hospital_km: 15.0,
            has_emergency_services: true,
            ambulance_availability: AmbulanceAvailability::Limited,
            description: "Jaramogi Oginga Odinga Hospital available, but rural areas 15-30km away"
                .into(),
            risk_adjustment: 1.15,
        },
        regional_disease: RegionalDiseaseBurden {
            malaria_risk: DiseaseRiskLevel::VeryHigh,
            tuberculosis_risk: DiseaseRiskLevel::High,
            hiv_prevalence: DiseaseRiskLevel::VeryHigh,
            waterborne_disease_risk: DiseaseRiskLevel::High,
            rift_valley_fever_risk: DiseaseRiskLevel::Moderate,
            schistosomiasis_risk: DiseaseRiskLevel::VeryHigh,
            overall_disease_multiplier: 1.35,
        },
        water_quality: WaterQualityIndex {
            score: 0.4,
            water_source: WaterSource::SurfaceWater,
            sanitation_level: SanitationLevel::Shared,
            risk_adjustment: 1.25,
        },
        air_quality: AirQualityIndex {
            score: 0.7,
            pm25_level: Some(35.0),
            primary_pollutant: Some("Particulate matter from roads".into()),
            risk_adjustment: 1.05,
        },
        overall_location_multiplier: 1.20, // Computed via calculate_multiplier()
    }
}

/// Example: Nairobi County
fn nairobi_location_profile() -> LocationRiskAdjustment {
    LocationRiskAdjustment {
        facility_access: FacilityAccessScore {
            score: 0.85,
            nearest_health_center_km: 2.0,
            nearest_hospital_km: 5.0,
            has_emergency_services: true,
            ambulance_availability: AmbulanceAvailability::ReadilyAvailable,
            description: "Multiple hospitals and clinics available".into(),
            risk_adjustment: 1.0,
        },
        regional_disease: RegionalDiseaseBurden {
            malaria_risk: DiseaseRiskLevel::Low,
            tuberculosis_risk: DiseaseRiskLevel::High,
            hiv_prevalence: DiseaseRiskLevel::Moderate,
            waterborne_disease_risk: DiseaseRiskLevel::Low,
            rift_valley_fever_risk: DiseaseRiskLevel::VeryLow,
            schistosomiasis_risk: DiseaseRiskLevel::VeryLow,
            overall_disease_multiplier: 1.10,
        },
        water_quality: WaterQualityIndex {
            score: 0.75,
            water_source: WaterSource::PipedWater,
            sanitation_level: SanitationLevel::Improved,
            risk_adjustment: 1.0,
        },
        air_quality: AirQualityIndex {
            score: 0.45,
            pm25_level: Some(45.0),
            primary_pollutant: Some("Vehicle emissions, industrial".into()),
            risk_adjustment: 1.15,
        },
        overall_location_multiplier: 1.05,
    }
}
