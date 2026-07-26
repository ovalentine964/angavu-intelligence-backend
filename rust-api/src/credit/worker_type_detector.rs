// credit/worker_type_detector.rs

use super::types::{WorkerType, WorkerTypeDetection, DetectionSignal};
use crate::loops::credit_feedback::CreditFeatures;

/// Detects worker type from transaction patterns.
/// No manual input required — purely data-driven.
pub struct WorkerTypeDetector {
    /// Thresholds for each detection signal
    config: DetectorConfig,
}

struct DetectorConfig {
    /// Minimum unique counterparties for vendor classification
    vendor_min_counterparties: u32,
    /// Fuel purchase frequency threshold for boda boda
    boda_fuel_frequency: f64,
    /// Income periodicity threshold for farmer
    farmer_periodicity_threshold: f64,
    /// Float turnover threshold for M-Pesa agent
    mpesa_float_turnover: f64,
}

impl Default for DetectorConfig {
    fn default() -> Self {
        Self {
            vendor_min_counterparties: 20,
            boda_fuel_frequency: 0.7,      // 70% of days have fuel purchases
            farmer_periodicity_threshold: 0.6,
            mpesa_float_turnover: 3.0,     // 3x daily float turnover
        }
    }
}

impl WorkerTypeDetector {
    pub fn new() -> Self {
        Self { config: DetectorConfig::default() }
    }

    /// Classify worker from base features + raw transaction metadata
    pub fn detect(
        &self,
        features: &CreditFeatures,
        transaction_meta: &TransactionMetadata,
    ) -> WorkerTypeDetection {
        let mut signals = Vec::new();
        let mut scores: std::collections::HashMap<WorkerType, f64> = 
            std::collections::HashMap::new();

        // Signal 1: High unique counterparty count → vendor
        if features.transaction_count_90d > 100 {
            let counterparty_ratio = transaction_meta.unique_counterparties as f64 
                / features.transaction_count_90d as f64;
            if counterparty_ratio > 0.5 {
                *scores.entry(WorkerType::MarketVendor).or_insert(0.0) += 0.4;
                signals.push(DetectionSignal {
                    signal_name: "high_counterparty_diversity".to_string(),
                    weight: 0.4,
                    value: format!("{:.0}%", counterparty_ratio * 100.0),
                });
            }
        }

        // Signal 2: Regular fuel purchases → boda boda
        if transaction_meta.fuel_purchase_frequency > self.config.boda_fuel_frequency {
            *scores.entry(WorkerType::BodaBodaRider).or_insert(0.0) += 0.6;
            signals.push(DetectionSignal {
                signal_name: "fuel_purchase_pattern".to_string(),
                weight: 0.6,
                value: format!("{:.0}% of days", transaction_meta.fuel_purchase_frequency * 100.0),
            });
        }

        // Signal 3: Periodic income spikes → farmer/fisherman
        if transaction_meta.income_periodicity_score > self.config.farmer_periodicity_threshold {
            if transaction_meta.product_categories.contains(&"fish".to_string()) 
                || transaction_meta.product_categories.contains(&"samaki".to_string()) {
                *scores.entry(WorkerType::Fisherman).or_insert(0.0) += 0.5;
            } else {
                *scores.entry(WorkerType::Farmer).or_insert(0.0) += 0.5;
            }
            signals.push(DetectionSignal {
                signal_name: "periodic_income_pattern".to_string(),
                weight: 0.5,
                value: format!("periodicity={:.2}", transaction_meta.income_periodicity_score),
            });
        }

        // Signal 4: Float turnover pattern → M-Pesa agent
        if transaction_meta.float_turnover_ratio > self.config.mpesa_float_turnover {
            *scores.entry(WorkerType::MpesaAgent).or_insert(0.0) += 0.7;
            signals.push(DetectionSignal {
                signal_name: "high_float_turnover".to_string(),
                weight: 0.7,
                value: format!("{:.1}x daily turnover", transaction_meta.float_turnover_ratio),
            });
        }

        // Signal 5: Irregular large payments from few sources → construction
        if transaction_meta.avg_transaction_size > 1000.0 
            && transaction_meta.unique_counterparties < 5
            && features.revenue_volatility > 0.5 {
            *scores.entry(WorkerType::ConstructionWorker).or_insert(0.0) += 0.4;
            signals.push(DetectionSignal {
                signal_name: "irregular_wage_pattern".to_string(),
                weight: 0.4,
                value: "few_payers_high_variance".to_string(),
            });
        }

        // Signal 6: Material purchases + project-based income → jua kali
        if transaction_meta.material_purchase_frequency > 0.2 
            && features.revenue_volatility > 0.4 {
            *scores.entry(WorkerType::JuaKaliArtisan).or_insert(0.0) += 0.4;
            signals.push(DetectionSignal {
                signal_name: "material_project_pattern".to_string(),
                weight: 0.4,
                value: format!("material_freq={:.0}%", transaction_meta.material_purchase_frequency * 100.0),
            });
        }

        // Select highest scoring type
        let (best_type, best_score) = scores.iter()
            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
            .map(|(t, s)| (*t, *s))
            .unwrap_or((WorkerType::Generic, 0.0));

        let confidence = best_score.min(1.0);

        // If confidence < 0.6, fall back to Generic
        let final_type = if confidence < 0.6 {
            WorkerType::Generic
        } else {
            best_type
        };

        WorkerTypeDetection {
            worker_type: final_type,
            confidence,
            signals,
        }
    }
}

/// Metadata extracted from raw transaction stream
/// (before feature engineering, used for type detection)
pub struct TransactionMetadata {
    pub unique_counterparties: u32,
    pub fuel_purchase_frequency: f64,
    pub income_periodicity_score: f64,
    pub float_turnover_ratio: f64,
    pub avg_transaction_size: f64,
    pub material_purchase_frequency: f64,
    pub product_categories: Vec<String>,
}
