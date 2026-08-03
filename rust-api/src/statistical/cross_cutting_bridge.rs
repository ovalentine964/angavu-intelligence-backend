/// Cross-Cutting Models Bridge
///
/// Rust bridge to Python cross-cutting models via subprocess.
/// Provides voice emotion detection, cultural sensitivity, health risk scoring,
/// wage gap analysis, care economy tracking, property rights, citizen monitoring,
/// decentralization tracking, practical validation, and internship tracking.
///
/// Academic references: ECO 404, Development Economics
use serde::{Deserialize, Serialize};
use std::process::Command;

use super::econometrics_bridge::EconometricResult;

/// Run a cross-cutting model method via Python subprocess.
pub fn run_cross_cutting_method(method: &str, args: serde_json::Value) -> EconometricResult {
    let input = serde_json::json!({
        "method": method,
        "args": args
    });

    let input_str = match serde_json::to_string(&input) {
        Ok(s) => s,
        Err(e) => {
            return EconometricResult {
                method: method.to_string(),
                data: serde_json::Value::Null,
                error: Some(format!("JSON serialization error: {}", e)),
            }
        }
    };

    let output = match Command::new("python3")
        .arg("python/statistical/cross_cutting_models.py")
        .arg(&input_str)
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            return EconometricResult {
                method: method.to_string(),
                data: serde_json::Value::Null,
                error: Some(format!("Failed to run cross_cutting_models: {}", e)),
            }
        }
    };

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return EconometricResult {
            method: method.to_string(),
            data: serde_json::Value::Null,
            error: Some(format!("Runner error: {}", stderr)),
        };
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    match serde_json::from_str::<serde_json::Value>(&stdout) {
        Ok(data) => EconometricResult {
            method: method.to_string(),
            data,
            error: None,
        },
        Err(e) => EconometricResult {
            method: method.to_string(),
            data: serde_json::Value::Null,
            error: Some(format!("JSON parse error: {}", e)),
        },
    }
}

/// Voice emotion detection parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmotionDetectionParams {
    pub audio_data: Vec<f64>,
    pub sample_rate: Option<u32>,
}

/// Detect emotion from voice audio data
pub fn detect_voice_emotion(params: EmotionDetectionParams) -> EconometricResult {
    run_cross_cutting_method("detect_emotion", serde_json::to_value(params).unwrap())
}

/// Cultural sensitivity adaptation parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CulturalAdaptParams {
    pub cultural_group: String,
    pub message: Option<String>,
    pub context: Option<String>,
}

/// Adapt communication to cultural context
pub fn cultural_adapt(params: CulturalAdaptParams) -> EconometricResult {
    run_cross_cutting_method("cultural_adapt", serde_json::to_value(params).unwrap())
}

/// Health risk scoring parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthRiskParams {
    pub occupation: String,
    pub years_experience: Option<u32>,
    pub has_ppe: Option<bool>,
    pub region: Option<String>,
}

/// Score occupation health risk
pub fn health_risk_score(params: HealthRiskParams) -> EconometricResult {
    run_cross_cutting_method("health_risk_score", serde_json::to_value(params).unwrap())
}

/// Wage gap analysis parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WageGapParams {
    pub wages_a: Vec<f64>,
    pub wages_b: Vec<f64>,
    pub group_a_name: Option<String>,
    pub group_b_name: Option<String>,
}

/// Analyze wage gap between two groups
pub fn wage_gap_analyze(params: WageGapParams) -> EconometricResult {
    run_cross_cutting_method("wage_gap", serde_json::to_value(params).unwrap())
}

/// Care economy estimation parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CareEconomyParams {
    pub care_hours: Option<serde_json::Value>,
    pub gender: Option<String>,
    pub days_per_month: Option<u32>,
}

/// Estimate care economy contribution
pub fn care_economy_estimate(params: CareEconomyParams) -> EconometricResult {
    run_cross_cutting_method("care_economy", serde_json::to_value(params).unwrap())
}

/// Property rights assessment parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PropertyRightsParams {
    pub tenure_type: String,
    pub has_title_deed: Option<bool>,
    pub has_survey: Option<bool>,
    pub has_beacons: Option<bool>,
    pub has_consent: Option<bool>,
    pub area_sqm: Option<f64>,
    pub value_estimate_kes: Option<f64>,
    pub county: Option<String>,
}

/// Assess property rights documentation
pub fn property_rights_assess(params: PropertyRightsParams) -> EconometricResult {
    run_cross_cutting_method("property_rights", serde_json::to_value(params).unwrap())
}

/// Citizen monitoring parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CitizenServiceParams {
    pub county: String,
    pub services: serde_json::Value,
}

/// Track service delivery for a county
pub fn citizen_service_delivery(params: CitizenServiceParams) -> EconometricResult {
    run_cross_cutting_method(
        "citizen_service_delivery",
        serde_json::to_value(params).unwrap(),
    )
}

/// Devolution assessment parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DevolutionParams {
    pub county: String,
    pub scores: serde_json::Value,
}

/// Assess devolution progress for a county
pub fn devolution_assess(params: DevolutionParams) -> EconometricResult {
    run_cross_cutting_method("devolution_assess", serde_json::to_value(params).unwrap())
}

/// Practical validation design parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PracticalDesignParams {
    pub intervention: String,
    pub outcome: String,
    pub n_treatment: Option<usize>,
    pub n_control: Option<usize>,
    pub baseline_mean: Option<f64>,
    pub baseline_std: Option<f64>,
    pub min_detectable_effect: Option<f64>,
}

/// Design a practical validation experiment
pub fn practical_design(params: PracticalDesignParams) -> EconometricResult {
    run_cross_cutting_method("practical_design", serde_json::to_value(params).unwrap())
}

/// Internship tracking parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InternshipParams {
    pub student_id: String,
    pub entries: Vec<serde_json::Value>,
}

/// Track internship/practical progress
pub fn internship_track(params: InternshipParams) -> EconometricResult {
    run_cross_cutting_method("internship_track", serde_json::to_value(params).unwrap())
}

/// Voice emotion detection bridge (Rust-side feature extraction)
pub struct VoiceEmotionBridge {
    pub sample_rate: u32,
}

impl VoiceEmotionBridge {
    pub fn new(sample_rate: u32) -> Self {
        Self { sample_rate }
    }

    /// Extract basic acoustic features from PCM audio (Rust-side)
    pub fn extract_features_rust(&self, audio: &[f32]) -> AcousticFeatures {
        if audio.is_empty() {
            return AcousticFeatures::default();
        }

        // Energy (RMS)
        let energy: f64 = audio
            .iter()
            .map(|x| (*x as f64).powi(2))
            .sum::<f64>()
            .sqrt()
            / audio.len() as f64;

        // Zero-crossing rate
        let zcr: f64 = audio
            .windows(2)
            .map(|w| {
                if (w[0] >= 0.0) != (w[1] >= 0.0) {
                    1.0
                } else {
                    0.0
                }
            })
            .sum::<f64>()
            / audio.len() as f64;

        // Peak amplitude
        let peak = audio.iter().map(|x| x.abs()).fold(0.0f32, f32::max);

        AcousticFeatures {
            energy,
            zcr,
            peak_amplitude: peak as f64,
            duration_samples: audio.len(),
            duration_seconds: audio.len() as f64 / self.sample_rate as f64,
        }
    }
}

/// Acoustic features extracted from audio
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcousticFeatures {
    pub energy: f64,
    pub zcr: f64,
    pub peak_amplitude: f64,
    pub duration_samples: usize,
    pub duration_seconds: f64,
}

impl Default for AcousticFeatures {
    fn default() -> Self {
        Self {
            energy: 0.0,
            zcr: 0.0,
            peak_amplitude: 0.0,
            duration_samples: 0,
            duration_seconds: 0.0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_voice_emotion_bridge_features() {
        let bridge = VoiceEmotionBridge::new(16000);
        // Generate a simple sine wave
        let audio: Vec<f32> = (0..16000)
            .map(|i| (2.0 * std::f32::consts::PI * 440.0 * i as f32 / 16000.0).sin())
            .collect();
        let features = bridge.extract_features_rust(&audio);
        assert!(features.energy > 0.0);
        assert!(features.duration_seconds > 0.99);
    }

    #[test]
    fn test_cultural_params_serialize() {
        let params = CulturalAdaptParams {
            cultural_group: "kikuyu".to_string(),
            message: Some("Hello".to_string()),
            context: Some("business".to_string()),
        };
        let json = serde_json::to_string(&params).unwrap();
        assert!(json.contains("kikuyu"));
    }

    #[test]
    fn test_health_risk_params() {
        let params = HealthRiskParams {
            occupation: "boda_boda".to_string(),
            years_experience: Some(5),
            has_ppe: Some(false),
            region: Some("urban".to_string()),
        };
        let json = serde_json::to_string(&params).unwrap();
        assert!(json.contains("boda_boda"));
    }
}
