// src/orchestrator/collective_intelligence.rs

use super::message_bus::*;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// CollectiveIntelligence: Emergent patterns from cross-module correlation
///
/// Subscribes to all module outputs and detects patterns that no single
/// module could find alone:
/// - Market + Credit correlation (demand up + credit improving = growth signal)
/// - Health + Economic link (income stability + inflation = real wage change)
/// - Distribution + Demand mismatch (gap + high demand = investment opportunity)
pub struct CollectiveIntelligence {
    /// Recent module outputs indexed by region
    market_signals: HashMap<String, Vec<TimestampedSignal<MarketSignalData>>>,
    credit_signals: HashMap<String, Vec<TimestampedSignal<CreditSignalData>>>,
    health_signals: HashMap<String, Vec<TimestampedSignal<HealthSignalData>>>,
    economic_signals: HashMap<String, Vec<TimestampedSignal<EconomicSignalData>>>,
    distribution_signals: HashMap<String, Vec<TimestampedSignal<DistributionSignalData>>>,

    /// Correlation computation window (hours)
    correlation_window_hours: i64,
    /// Minimum correlation strength to report
    min_correlation_strength: f64,
}

struct TimestampedSignal<T> {
    data: T,
    timestamp: DateTime<Utc>,
}

#[derive(Clone)]
struct MarketSignalData {
    demand_index: f64,
    price_volatility: f64,
}

#[derive(Clone)]
struct CreditSignalData {
    alama_score: u32,
    risk_level: RiskLevel,
}

#[derive(Clone)]
struct HealthSignalData {
    income_stability: f64,
    health_risk: f64,
}

#[derive(Clone)]
struct EconomicSignalData {
    inflation_rate: f64,
    volume_index: f64,
}

#[derive(Clone)]
struct DistributionSignalData {
    gap_severity: f64,
    opportunity_size: f64,
}

impl CollectiveIntelligence {
    pub fn new() -> Self {
        Self {
            market_signals: HashMap::new(),
            credit_signals: HashMap::new(),
            health_signals: HashMap::new(),
            economic_signals: HashMap::new(),
            distribution_signals: HashMap::new(),
            correlation_window_hours: 24,
            min_correlation_strength: 0.5,
        }
    }

    /// Ingest a module output for correlation analysis
    pub fn ingest(&mut self, message: &ModuleMessage) {
        let now = Utc::now();

        match message {
            ModuleMessage::MarketSignal {
                region,
                demand_index,
                volatility,
                ..
            } => {
                self.market_signals
                    .entry(region.clone())
                    .or_default()
                    .push(TimestampedSignal {
                        data: MarketSignalData {
                            demand_index: *demand_index,
                            price_volatility: *volatility,
                        },
                        timestamp: now,
                    });
                self.prune_old(region, &mut self.market_signals);
            }
            ModuleMessage::CreditAssessment {
                worker_id_hash,
                alama_score,
                risk_level,
                ..
            } => {
                // Aggregate by worker's region (would need region lookup in production)
                let region = "aggregate".to_string();
                self.credit_signals
                    .entry(region.clone())
                    .or_default()
                    .push(TimestampedSignal {
                        data: CreditSignalData {
                            alama_score: *alama_score,
                            risk_level: risk_level.clone(),
                        },
                        timestamp: now,
                    });
            }
            ModuleMessage::HealthAssessment {
                region,
                income_stability_score,
                health_risk_score,
                ..
            } => {
                self.health_signals
                    .entry(region.clone())
                    .or_default()
                    .push(TimestampedSignal {
                        data: HealthSignalData {
                            income_stability: *income_stability_score,
                            health_risk: *health_risk_score,
                        },
                        timestamp: now,
                    });
            }
            ModuleMessage::EconomicIndicator {
                region,
                inflation_rate,
                transaction_volume_index,
                ..
            } => {
                self.economic_signals
                    .entry(region.clone())
                    .or_default()
                    .push(TimestampedSignal {
                        data: EconomicSignalData {
                            inflation_rate: *inflation_rate,
                            volume_index: *transaction_volume_index,
                        },
                        timestamp: now,
                    });
            }
            ModuleMessage::DistributionGap {
                region,
                gap_severity,
                opportunity_size_usd,
                ..
            } => {
                self.distribution_signals
                    .entry(region.clone())
                    .or_default()
                    .push(TimestampedSignal {
                        data: DistributionSignalData {
                            gap_severity: *gap_severity,
                            opportunity_size: *opportunity_size_usd,
                        },
                        timestamp: now,
                    });
            }
            _ => {}
        }
    }

    /// Detect cross-module patterns
    pub fn detect_patterns(&self) -> Vec<DetectedPattern> {
        let mut patterns = Vec::new();

        // Pattern 1: Market-Credit Correlation
        // Rising demand + improving credit scores = economic growth signal
        for (region, market_data) in &self.market_signals {
            if let Some(credit_data) = self.credit_signals.get(region) {
                let correlation = self.compute_market_credit_correlation(market_data, credit_data);
                if correlation.abs() > self.min_correlation_strength {
                    patterns.push(DetectedPattern {
                        pattern_type: PatternType::MarketCreditCorrelation,
                        region: region.clone(),
                        modules_involved: vec![ModuleId::MarketAnalyzer, ModuleId::CreditScorer],
                        correlation_strength: correlation,
                        description: if correlation > 0.0 {
                            format!("Positive correlation: demand rising with credit improvement in {}", region)
                        } else {
                            format!("Inverse correlation: demand rising but credit risk increasing in {}", region)
                        },
                        actionable: correlation.abs() > 0.7,
                    });
                }
            }
        }

        // Pattern 2: Health-Economic Link
        // Income stability + inflation = real wage change
        for (region, health_data) in &self.health_signals {
            if let Some(econ_data) = self.economic_signals.get(region) {
                let correlation = self.compute_health_economic_correlation(health_data, econ_data);
                if correlation.abs() > self.min_correlation_strength {
                    patterns.push(DetectedPattern {
                        pattern_type: PatternType::HealthEconomicLink,
                        region: region.clone(),
                        modules_involved: vec![ModuleId::HealthMetrics, ModuleId::EconomicAnalyzer],
                        correlation_strength: correlation,
                        description: format!(
                            "Health-economic link detected in {}: income stability correlates with economic indicators (r={:.2})",
                            region, correlation
                        ),
                        actionable: true,
                    });
                }
            }
        }

        // Pattern 3: Distribution-Demand Mismatch
        // Distribution gap + high demand = investment opportunity
        for (region, dist_data) in &self.distribution_signals {
            if let Some(market_data) = self.market_signals.get(region) {
                let correlation =
                    self.compute_distribution_demand_correlation(dist_data, market_data);
                if correlation > self.min_correlation_strength {
                    patterns.push(DetectedPattern {
                        pattern_type: PatternType::DistributionDemandMismatch,
                        region: region.clone(),
                        modules_involved: vec![ModuleId::DistributionAnalyzer, ModuleId::MarketAnalyzer],
                        correlation_strength: correlation,
                        description: format!(
                            "Distribution gap aligns with high demand in {} — investment opportunity (r={:.2})",
                            region, correlation
                        ),
                        actionable: true,
                    });
                }
            }
        }

        patterns
    }

    // ── Correlation Computations ──────────────────────────────

    fn compute_market_credit_correlation(
        &self,
        market: &[TimestampedSignal<MarketSignalData>],
        credit: &[TimestampedSignal<CreditSignalData>],
    ) -> f64 {
        // Pearson correlation between demand_index and alama_score
        let pairs = self.temporal_join(market, credit, |m, c| {
            (m.demand_index, c.alama_score as f64)
        });

        pearson_correlation(&pairs)
    }

    fn compute_health_economic_correlation(
        &self,
        health: &[TimestampedSignal<HealthSignalData>],
        economic: &[TimestampedSignal<EconomicSignalData>],
    ) -> f64 {
        let pairs = self.temporal_join(health, economic, |h, e| {
            (h.income_stability, 1.0 - e.inflation_rate.abs() / 100.0)
        });

        pearson_correlation(&pairs)
    }

    fn compute_distribution_demand_correlation(
        &self,
        dist: &[TimestampedSignal<DistributionSignalData>],
        market: &[TimestampedSignal<MarketSignalData>],
    ) -> f64 {
        let pairs = self.temporal_join(dist, market, |d, m| (d.gap_severity, m.demand_index));

        pearson_correlation(&pairs)
    }

    /// Join two signal streams by closest timestamp within window
    fn temporal_join<A, B, F>(
        &self,
        signals_a: &[TimestampedSignal<A>],
        signals_b: &[TimestampedSignal<B>],
        extract: F,
    ) -> Vec<(f64, f64)>
    where
        F: Fn(&A, &B) -> (f64, f64),
    {
        let mut pairs = Vec::new();
        let window = chrono::Duration::hours(self.correlation_window_hours);

        for a in signals_a {
            // Find closest b within window
            if let Some(b) = signals_b
                .iter()
                .filter(|b| (a.timestamp - b.timestamp).abs() < window)
                .min_by_key(|b| (a.timestamp - b.timestamp).num_seconds().abs())
            {
                pairs.push(extract(&a.data, &b.data));
            }
        }

        pairs
    }

    fn prune_old<T>(
        &self,
        _region: &str,
        _signals: &mut HashMap<String, Vec<TimestampedSignal<T>>>,
    ) {
        // In production: prune signals older than correlation_window_hours
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectedPattern {
    pub pattern_type: PatternType,
    pub region: String,
    pub modules_involved: Vec<ModuleId>,
    pub correlation_strength: f64,
    pub description: String,
    pub actionable: bool,
}

/// Pearson correlation coefficient
fn pearson_correlation(pairs: &[(f64, f64)]) -> f64 {
    let n = pairs.len() as f64;
    if n < 3.0 {
        return 0.0;
    }

    let sum_x: f64 = pairs.iter().map(|(x, _)| x).sum();
    let sum_y: f64 = pairs.iter().map(|(_, y)| y).sum();
    let sum_xx: f64 = pairs.iter().map(|(x, _)| x * x).sum();
    let sum_yy: f64 = pairs.iter().map(|(_, y)| y * y).sum();
    let sum_xy: f64 = pairs.iter().map(|(x, y)| x * y).sum();

    let numerator = n * sum_xy - sum_x * sum_y;
    let denominator = ((n * sum_xx - sum_x * sum_x) * (n * sum_yy - sum_y * sum_y)).sqrt();

    if denominator.abs() < 1e-10 {
        0.0
    } else {
        (numerator / denominator).clamp(-1.0, 1.0)
    }
}
