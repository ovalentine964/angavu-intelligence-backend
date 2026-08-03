// src/orchestrator/modules/health.rs

use super::*;
use crate::orchestrator::message_bus::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// HealthMetrics: Worker health economics
///
/// Analyzes income stability, work patterns, and health risk factors.
/// Outputs health assessments for insurance eligibility and health savings advice.
///
/// ⚠️  LIMITATION: All state is held in-memory HashMaps. Income profiles are
/// lost on process restart. For production, wire to PostgreSQL (table: worker_income_profiles).
/// See: TODO(HealthMetrics-Persistence)
pub struct HealthMetrics {
    /// Worker income profiles (by hashed ID)
    income_profiles: HashMap<String, IncomeProfile>,
}

#[derive(Serialize, Deserialize, Clone)]
struct IncomeProfile {
    daily_incomes: Vec<f64>,
    active_days: u32,
    total_days: u32,
    last_transaction: chrono::DateTime<chrono::Utc>,
}

impl IncomeProfile {
    fn income_stability_score(&self) -> f64 {
        if self.daily_incomes.len() < 7 {
            return 0.5; // Insufficient data
        }

        let mean = self.daily_incomes.iter().sum::<f64>() / self.daily_incomes.len() as f64;
        if mean == 0.0 {
            return 0.0;
        }

        let variance = self
            .daily_incomes
            .iter()
            .map(|x| (x - mean).powi(2))
            .sum::<f64>()
            / self.daily_incomes.len() as f64;
        let cv = variance.sqrt() / mean; // Coefficient of variation

        // Lower CV = more stable = higher score
        (1.0 - cv.min(1.0)).max(0.0)
    }

    fn activity_consistency(&self) -> f64 {
        if self.total_days == 0 {
            return 0.0;
        }
        self.active_days as f64 / self.total_days as f64
    }
}

impl HealthMetrics {
    pub fn new() -> Self {
        Self {
            income_profiles: HashMap::new(),
        }
    }
}

#[async_trait::async_trait]
impl CapabilityModule for HealthMetrics {
    fn id(&self) -> ModuleId {
        ModuleId::HealthMetrics
    }

    async fn process(
        &mut self,
        message: ModuleMessage,
    ) -> Result<Option<ModuleMessage>, ModuleError> {
        match message {
            ModuleMessage::TransactionBatch {
                trace_id,
                worker_id_hash,
                transactions,
                region,
                ..
            } => {
                let profile = self
                    .income_profiles
                    .entry(worker_id_hash.clone())
                    .or_insert_with(|| IncomeProfile {
                        daily_incomes: Vec::with_capacity(365),
                        active_days: 0,
                        total_days: 0,
                        last_transaction: chrono::Utc::now(),
                    });

                // Update income tracking
                let daily_income: f64 = transactions
                    .iter()
                    .filter(|t| t.amount > 0.0)
                    .map(|t| t.amount)
                    .sum();

                if daily_income > 0.0 {
                    profile.daily_incomes.push(daily_income);
                    profile.active_days += 1;
                    if profile.daily_incomes.len() > 365 {
                        profile.daily_incomes.remove(0);
                    }
                }
                profile.total_days += 1;
                profile.last_transaction = chrono::Utc::now();

                // Compute health metrics
                let stability = profile.income_stability_score();
                let consistency = profile.activity_consistency();

                // Health risk score: lower income stability → higher health risk
                let health_risk = 1.0 - (stability * 0.6 + consistency * 0.4);

                // Insurance eligibility: stable income for 90+ days
                let eligible = profile.daily_incomes.len() >= 90 && stability > 0.5;

                // Determine worker type from transaction patterns
                let worker_type = if transactions.iter().any(|t| {
                    t.product_category.contains("vegetable") || t.product_category.contains("food")
                }) {
                    "mama_mboga"
                } else if transactions
                    .iter()
                    .any(|t| t.product_category.contains("transport"))
                {
                    "boda_boda"
                } else {
                    "general"
                };

                return Ok(Some(ModuleMessage::HealthAssessment {
                    trace_id,
                    region,
                    worker_type: worker_type.to_string(),
                    income_stability_score: stability,
                    health_risk_score: health_risk,
                    insurance_eligibility: eligible,
                }));
            }
            _ => Ok(None),
        }
    }

    fn snapshot_state(&self) -> Option<Vec<u8>> {
        #[derive(Serialize)]
        struct Snapshot {
            profiles: Vec<(String, IncomeProfile)>,
        }
        let profiles: Vec<(String, IncomeProfile)> = self
            .income_profiles
            .iter()
            .map(|entry| (entry.key().clone(), entry.value().clone()))
            .collect();
        bincode::serialize(&Snapshot { profiles }).ok()
    }

    fn restore_state(&mut self, data: &[u8]) {
        #[derive(Deserialize)]
        struct Snapshot {
            profiles: Vec<(String, IncomeProfile)>,
        }
        if let Ok(snap) = bincode::deserialize::<Snapshot>(data) {
            for (id, profile) in snap.profiles {
                self.income_profiles.insert(id, profile);
            }
            tracing::info!(
                count = self.income_profiles.len(),
                "HealthMetrics state restored"
            );
        }
    }
}
