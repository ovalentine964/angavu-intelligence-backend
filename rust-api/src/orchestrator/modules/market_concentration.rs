// =============================================================================
// Angavu Intelligence — Market Concentration Tracker
// HHI, concentration ratios, and market structure assessment by sector.
//
// HHI = Σ(market_share_i × 100)²
// CR4 = sum of top 4 firms' market shares
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Market structure classification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MarketStructure {
    PerfectCompetition, // HHI < 1500
    MonopolisticComp,   // HHI 1500-2500
    Oligopoly,          // HHI > 2500
    Monopoly,           // Single dominant seller
}

/// Market concentration metrics for a sector/region
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConcentrationMetrics {
    pub sector: String,
    pub region: String,
    pub hhi: f64, // Herfindahl-Hirschman Index
    pub cr1: f64, // Top 1 market share
    pub cr4: f64, // Top 4 market share
    pub cr8: f64, // Top 8 market share
    pub num_sellers: usize,
    pub num_effective_competitors: f64, // 1/HHI × 10000
    pub entropy: f64,                   // Shannon entropy
    pub market_structure: MarketStructure,
    pub period: String,
}

/// Seller data point
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SellerData {
    pub seller_id: String,
    pub market_share: f64, // 0.0-1.0
    pub revenue: f64,
    pub transactions: u64,
}

/// Market concentration tracker
pub struct MarketConcentrationTracker {
    /// Historical metrics by sector+region
    history: HashMap<String, Vec<ConcentrationMetrics>>,
}

impl MarketConcentrationTracker {
    pub fn new() -> Self {
        Self {
            history: HashMap::new(),
        }
    }

    /// Compute HHI from market shares
    ///
    /// HHI = Σ(share_i × 100)²
    /// Range: 0 (infinite competition) to 10000 (monopoly)
    pub fn compute_hhi(market_shares: &[f64]) -> f64 {
        market_shares.iter().map(|s| (s * 100.0).powi(2)).sum()
    }

    /// Compute concentration ratio (sum of top-k shares)
    pub fn compute_crk(market_shares: &[f64], k: usize) -> f64 {
        let mut sorted = market_shares.to_vec();
        sorted.sort_by(|a, b| b.partial_cmp(a).unwrap());
        sorted.iter().take(k).sum()
    }

    /// Compute Shannon entropy for market diversity
    ///
    /// H = -Σ(share_i × ln(share_i))
    pub fn compute_entropy(market_shares: &[f64]) -> f64 {
        -market_shares
            .iter()
            .filter(|&&s| s > 0.0)
            .map(|&s| s * s.ln())
            .sum::<f64>()
    }

    /// Classify market structure from HHI
    pub fn classify_market(hhi: f64) -> MarketStructure {
        if hhi < 1500.0 {
            MarketStructure::PerfectCompetition
        } else if hhi < 2500.0 {
            MarketStructure::MonopolisticComp
        } else {
            MarketStructure::Oligopoly
        }
    }

    /// Compute full concentration metrics for a market
    pub fn compute_metrics(
        sellers: &[SellerData],
        sector: &str,
        region: &str,
        period: &str,
    ) -> ConcentrationMetrics {
        let shares: Vec<f64> = sellers.iter().map(|s| s.market_share).collect();

        let hhi = Self::compute_hhi(&shares);
        let cr1 = Self::compute_crk(&shares, 1);
        let cr4 = Self::compute_crk(&shares, 4);
        let cr8 = Self::compute_crk(&shares, 8);
        let entropy = Self::compute_entropy(&shares);

        let num_effective = if hhi > 0.0 {
            10000.0 / hhi
        } else {
            sellers.len() as f64
        };

        ConcentrationMetrics {
            sector: sector.to_string(),
            region: region.to_string(),
            hhi,
            cr1,
            cr4,
            cr8,
            num_sellers: sellers.len(),
            num_effective_competitors: num_effective,
            entropy,
            market_structure: Self::classify_market(hhi),
            period: period.to_string(),
        }
    }

    /// Record metrics in history
    pub fn record(&mut self, metrics: ConcentrationMetrics) {
        let key = format!("{}:{}", metrics.sector, metrics.region);
        let entry = self.history.entry(key).or_insert_with(Vec::new);
        entry.push(metrics);
        if entry.len() > 365 {
            entry.drain(0..entry.len() - 365);
        }
    }

    /// Get trend for a sector/region
    pub fn trend(&self, sector: &str, region: &str) -> Option<ConcentrationTrend> {
        let key = format!("{}:{}", sector, region);
        let history = self.history.get(&key)?;
        if history.len() < 2 {
            return None;
        }
        let recent = history.last()?;
        let previous = &history[history.len() - 2];

        Some(ConcentrationTrend {
            sector: sector.to_string(),
            region: region.to_string(),
            hhi_change: recent.hhi - previous.hhi,
            cr4_change: recent.cr4 - previous.cr4,
            structure_changed: std::mem::discriminant(&recent.market_structure)
                != std::mem::discriminant(&previous.market_structure),
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConcentrationTrend {
    pub sector: String,
    pub region: String,
    pub hhi_change: f64,
    pub cr4_change: f64,
    pub structure_changed: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hhi_perfect_competition() {
        // 100 equal sellers: each has 1% share
        let shares = vec![0.01; 100];
        let hhi = MarketConcentrationTracker::compute_hhi(&shares);
        assert!(
            (hhi - 100.0).abs() < 1.0,
            "HHI for 100 equal sellers should be ~100, got {}",
            hhi
        );
    }

    #[test]
    fn test_hhi_monopoly() {
        let shares = vec![1.0];
        let hhi = MarketConcentrationTracker::compute_hhi(&shares);
        assert!(
            (hhi - 10000.0).abs() < 1.0,
            "HHI for monopoly should be 10000, got {}",
            hhi
        );
    }

    #[test]
    fn test_cr4() {
        let shares = vec![0.30, 0.25, 0.20, 0.15, 0.05, 0.03, 0.02];
        let cr4 = MarketConcentrationTracker::compute_crk(&shares, 4);
        assert!((cr4 - 0.90).abs() < 0.01);
    }

    #[test]
    fn test_entropy_diversity() {
        let equal_shares = vec![0.25, 0.25, 0.25, 0.25];
        let concentrated = vec![0.90, 0.05, 0.03, 0.02];
        let entropy_equal = MarketConcentrationTracker::compute_entropy(&equal_shares);
        let entropy_concentrated = MarketConcentrationTracker::compute_entropy(&concentrated);
        assert!(
            entropy_equal > entropy_concentrated,
            "Equal market should have higher entropy"
        );
    }

    #[test]
    fn test_full_metrics() {
        let sellers = vec![
            SellerData {
                seller_id: "a".into(),
                market_share: 0.4,
                revenue: 4000.0,
                transactions: 100,
            },
            SellerData {
                seller_id: "b".into(),
                market_share: 0.3,
                revenue: 3000.0,
                transactions: 80,
            },
            SellerData {
                seller_id: "c".into(),
                market_share: 0.2,
                revenue: 2000.0,
                transactions: 50,
            },
            SellerData {
                seller_id: "d".into(),
                market_share: 0.1,
                revenue: 1000.0,
                transactions: 20,
            },
        ];
        let metrics = MarketConcentrationTracker::compute_metrics(
            &sellers,
            "groceries",
            "nairobi",
            "2026-08",
        );
        assert!(metrics.hhi > 1500.0); // Concentrated
        assert!(matches!(
            metrics.market_structure,
            MarketStructure::MonopolisticComp | MarketStructure::Oligopoly
        ));
    }
}
