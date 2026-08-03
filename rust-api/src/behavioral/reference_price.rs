/// Reference Price Modeling Module
///
/// Estimates fair prices from behavioral data — helping informal workers
/// avoid overpaying and underpricing.
///
/// Reference price theory (Kahneman & Tversky 1979): consumers have
/// an internal "reference price" against which they evaluate all offers.
/// This module estimates reference prices from:
///   - Transaction history (what the worker actually paid)
///   - Market data (what others pay)
///   - Anchoring-adjusted estimates (correcting for cognitive bias)
///
/// The key insight: a mama mboga's reference price for tomatoes is
/// shaped by what she paid last time (anchoring), what her peers pay
/// (social proof), and the market average (objective fair price).
///
/// Reference: Kahneman, D., & Tversky, A. (1979). Prospect Theory.
///            Mazumdar, T., Raj, S. P., & Sinha, I. (2005). Reference
///            Price Research: Review and Propositions.
use serde::{Deserialize, Serialize};

/// A price observation from transaction data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceObservation {
    /// Product identifier
    pub product_id: String,
    /// Observed price in KES
    pub price: f64,
    /// Quantity purchased
    pub quantity: f64,
    /// Unit of measurement (kg, bunch, piece, litre)
    pub unit: String,
    /// Timestamp (Unix seconds)
    pub timestamp: u64,
    /// Source: "self" (worker's own purchase), "peer" (peer data), "market" (market data)
    pub source: PriceSource,
    /// Location/region
    pub region: String,
}

/// Source of price data
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PriceSource {
    /// Worker's own transaction history
    SelfPurchase,
    /// Peer data (anonymized)
    PeerData,
    /// Market data (official/aggregate)
    MarketData,
    /// Negotiated price
    NegotiatedPrice,
}

/// Estimated reference price for a product
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReferencePrice {
    /// Product identifier
    pub product_id: String,
    /// Unit of measurement
    pub unit: String,
    /// Personal reference price (from worker's own history)
    pub personal_ref: f64,
    /// Social reference price (from peer data)
    pub social_ref: f64,
    /// Market reference price (from market data)
    pub market_ref: f64,
    /// Anchoring-adjusted reference price
    pub adjusted_ref: f64,
    /// Confidence in the estimate (0-1)
    pub confidence: f64,
    /// Lower bound of fair price range
    pub fair_range_low: f64,
    /// Upper bound of fair price range
    pub fair_range_high: f64,
    /// Number of observations used
    pub observation_count: usize,
    /// Anchoring bias detected (personal ref deviates from market)
    pub anchoring_bias: Option<AnchoringBias>,
}

/// Detected anchoring bias
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnchoringBias {
    /// The anchor price (typically the most recent or most extreme observation)
    pub anchor: f64,
    /// The market reference price
    pub market_ref: f64,
    /// Deviation from market (positive = overpaying)
    pub deviation_pct: f64,
    /// Severity of the bias
    pub severity: BiasSeverity,
    /// Recommendation
    pub recommendation: String,
}

/// Severity of anchoring bias
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BiasSeverity {
    /// Less than 10% deviation — within normal range
    None,
    /// 10-20% deviation — worth noting
    Mild,
    /// 20-30% deviation — significant bias
    Moderate,
    /// More than 30% deviation — severe bias
    Severe,
}

/// Reference price estimation engine
pub struct ReferencePriceEngine {
    /// Price observations indexed by product
    observations: Vec<PriceObservation>,
    /// Default decay factor for time-weighted observations (per day)
    decay_factor: f64,
    /// Minimum observations for a reliable estimate
    min_observations: usize,
}

impl ReferencePriceEngine {
    /// Create a new engine
    pub fn new() -> Self {
        Self {
            observations: Vec::new(),
            decay_factor: 0.98, // 2% decay per day
            min_observations: 3,
        }
    }

    /// Create with custom settings
    pub fn with_config(decay_factor: f64, min_observations: usize) -> Self {
        Self {
            observations: Vec::new(),
            decay_factor,
            min_observations,
        }
    }

    /// Add a price observation
    pub fn add_observation(&mut self, obs: PriceObservation) {
        self.observations.push(obs);
    }

    /// Add multiple observations
    pub fn add_observations(&mut self, obs: Vec<PriceObservation>) {
        self.observations.extend(obs);
    }

    /// Estimate reference price for a product
    pub fn estimate(&self, product_id: &str, current_timestamp: u64) -> Option<ReferencePrice> {
        let product_obs: Vec<&PriceObservation> = self
            .observations
            .iter()
            .filter(|o| o.product_id == product_id)
            .collect();

        if product_obs.is_empty() {
            return None;
        }

        // Calculate time-decayed weights
        let weighted_obs: Vec<(f64, f64)> = product_obs
            .iter()
            .map(|obs| {
                let days_ago = (current_timestamp as f64 - obs.timestamp as f64) / 86400.0;
                let weight = self.decay_factor.powf(days_ago.max(0.0));
                (obs.price, weight)
            })
            .collect();

        // Personal reference: weighted average of own purchases
        let personal_obs: Vec<(f64, f64)> = product_obs
            .iter()
            .zip(weighted_obs.iter())
            .filter(|(obs, _)| obs.source == PriceSource::SelfPurchase)
            .map(|(_, w)| *w)
            .collect();

        let personal_ref = self.weighted_average(&personal_obs);

        // Social reference: weighted average of peer data
        let social_obs: Vec<(f64, f64)> = product_obs
            .iter()
            .zip(weighted_obs.iter())
            .filter(|(obs, _)| obs.source == PriceSource::PeerData)
            .map(|(_, w)| *w)
            .collect();

        let social_ref = self.weighted_average(&social_obs);

        // Market reference: weighted average of market data
        let market_obs: Vec<(f64, f64)> = product_obs
            .iter()
            .zip(weighted_obs.iter())
            .filter(|(obs, _)| obs.source == PriceSource::MarketData)
            .map(|(_, w)| *w)
            .collect();

        let market_ref = self.weighted_average(&market_obs);

        // Compute unit from observations
        let unit = product_obs
            .first()
            .map(|o| o.unit.clone())
            .unwrap_or_else(|| "unit".to_string());

        // Determine the best reference (weighted combination)
        // Weights: personal 0.3, social 0.3, market 0.4
        // (market data is most objective, but personal/social are more relevant)
        let adjusted_ref = if market_ref > 0.0 && social_ref > 0.0 && personal_ref > 0.0 {
            personal_ref * 0.3 + social_ref * 0.3 + market_ref * 0.4
        } else if market_ref > 0.0 && personal_ref > 0.0 {
            personal_ref * 0.5 + market_ref * 0.5
        } else if market_ref > 0.0 {
            market_ref
        } else if personal_ref > 0.0 {
            personal_ref
        } else {
            social_ref
        };

        // Fair price range (±15% of adjusted reference)
        let range_pct = 0.15;
        let fair_low = adjusted_ref * (1.0 - range_pct);
        let fair_high = adjusted_ref * (1.0 + range_pct);

        // Detect anchoring bias
        let anchoring_bias = if personal_ref > 0.0 && market_ref > 0.0 {
            let deviation = (personal_ref - market_ref) / market_ref;
            let severity = match deviation.abs() {
                x if x < 0.10 => BiasSeverity::None,
                x if x < 0.20 => BiasSeverity::Mild,
                x if x < 0.30 => BiasSeverity::Moderate,
                _ => BiasSeverity::Severe,
            };

            if severity != BiasSeverity::None {
                let recommendation = if deviation > 0.0 {
                    format!(
                        "Unalipa KES {:.0} zaidi ya bei ya soko (KES {:.0}). \
                         Linganisha na wachuuzi wengine kabla ya kununua.",
                        personal_ref - market_ref,
                        market_ref
                    )
                } else {
                    format!(
                        "Bei yako ni KES {:.0} chini ya bei ya soko — inaweza kuwa nzuri! \
                         Lakini hakikisha ubora ni mzuri.",
                        market_ref - personal_ref
                    )
                };

                Some(AnchoringBias {
                    anchor: personal_ref,
                    market_ref,
                    deviation_pct: deviation * 100.0,
                    severity,
                    recommendation,
                })
            } else {
                None
            }
        } else {
            None
        };

        // Confidence based on observation count and recency
        let obs_count = product_obs.len();
        let confidence = (obs_count as f64 / 10.0).min(1.0)
            * if market_ref > 0.0 { 1.0 } else { 0.7 }
            * if social_ref > 0.0 { 1.0 } else { 0.8 };

        Some(ReferencePrice {
            product_id: product_id.to_string(),
            unit,
            personal_ref,
            social_ref,
            market_ref,
            adjusted_ref,
            confidence,
            fair_range_low: fair_low,
            fair_range_high: fair_high,
            observation_count: obs_count,
            anchoring_bias,
        })
    }

    /// Weighted average helper
    fn weighted_average(&self, values: &[(f64, f64)]) -> f64 {
        if values.is_empty() {
            return 0.0;
        }
        let total_weight: f64 = values.iter().map(|(_, w)| w).sum();
        if total_weight == 0.0 {
            return 0.0;
        }
        values.iter().map(|(v, w)| v * w).sum::<f64>() / total_weight
    }

    /// Get all observations
    pub fn observations(&self) -> &[PriceObservation] {
        &self.observations
    }
}

impl Default for ReferencePriceEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_obs(product: &str, price: f64, source: PriceSource, days_ago: u64) -> PriceObservation {
        PriceObservation {
            product_id: product.to_string(),
            price,
            quantity: 1.0,
            unit: "kg".to_string(),
            timestamp: 1700000000 - days_ago * 86400,
            source,
            region: "Nairobi".to_string(),
        }
    }

    #[test]
    fn test_reference_price_basic() {
        let mut engine = ReferencePriceEngine::new();

        engine.add_observation(make_obs("nyanya", 60.0, PriceSource::SelfPurchase, 7));
        engine.add_observation(make_obs("nyanya", 65.0, PriceSource::SelfPurchase, 3));
        engine.add_observation(make_obs("nyanya", 55.0, PriceSource::MarketData, 1));
        engine.add_observation(make_obs("nyanya", 58.0, PriceSource::PeerData, 2));

        let ref_price = engine.estimate("nyanya", 1700000000).unwrap();

        assert!(ref_price.adjusted_ref > 0.0);
        assert!(ref_price.fair_range_low < ref_price.adjusted_ref);
        assert!(ref_price.fair_range_high > ref_price.adjusted_ref);
        assert!(ref_price.confidence > 0.0);
        assert_eq!(ref_price.observation_count, 4);
    }

    #[test]
    fn test_anchoring_bias_detection() {
        let mut engine = ReferencePriceEngine::new();

        // Worker consistently pays 80 while market is 55
        engine.add_observation(make_obs("nyanya", 80.0, PriceSource::SelfPurchase, 7));
        engine.add_observation(make_obs("nyanya", 85.0, PriceSource::SelfPurchase, 3));
        engine.add_observation(make_obs("nyanya", 55.0, PriceSource::MarketData, 1));

        let ref_price = engine.estimate("nyanya", 1700000000).unwrap();

        let bias = ref_price.anchoring_bias.unwrap();
        assert!(
            bias.deviation_pct > 20.0,
            "Should detect significant anchoring"
        );
        assert!(matches!(
            bias.severity,
            BiasSeverity::Moderate | BiasSeverity::Severe
        ));
    }

    #[test]
    fn test_no_observations() {
        let engine = ReferencePriceEngine::new();
        assert!(engine.estimate("nonexistent", 1700000000).is_none());
    }

    #[test]
    fn test_time_decay() {
        let mut engine = ReferencePriceEngine::with_config(0.95, 1);

        // Old observation at 100
        engine.add_observation(make_obs("sukuma", 100.0, PriceSource::SelfPurchase, 30));
        // Recent observation at 50
        engine.add_observation(make_obs("sukuma", 50.0, PriceSource::SelfPurchase, 1));

        let ref_price = engine.estimate("sukuma", 1700000000).unwrap();

        // Recent price should dominate due to time decay
        assert!(
            ref_price.personal_ref < 75.0,
            "Recent price should have more weight: got {}",
            ref_price.personal_ref
        );
    }
}
