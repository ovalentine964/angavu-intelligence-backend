// =============================================================================
// Angavu Intelligence — Governance Quality Index
// Institutional quality measurement for informal economy regions.
//
// Measures governance dimensions that affect informal workers:
// - Business registration ease
// - Market access (physical infrastructure)
// - Corruption perception
// - Tax fairness
// - Property rights enforcement
// - Financial inclusion infrastructure
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Governance dimensions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GovernanceDimension {
    pub name: String,
    pub name_local: String,
    pub score: f64,  // 0-100
    pub weight: f64, // Contribution to overall index
    pub indicators: Vec<GovernanceIndicator>,
}

/// A single governance indicator
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GovernanceIndicator {
    pub name: String,
    pub value: f64,
    pub unit: String,
    pub source: String,
    pub direction: IndicatorDirection,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IndicatorDirection {
    HigherIsBetter,
    LowerIsBetter,
}

/// Governance quality index for a region
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GovernanceQualityIndex {
    pub region: String,
    pub overall_score: f64, // 0-100
    pub grade: String,      // A, B, C, D, F
    pub dimensions: Vec<GovernanceDimension>,
    pub rank: Option<usize>,
    pub peer_comparison: Vec<PeerComparison>,
    pub period: String,
}

/// Comparison with peer regions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PeerComparison {
    pub peer_region: String,
    pub peer_score: f64,
    pub score_difference: f64,
    pub strongest_dimension: String,
}

/// Governance quality tracker
pub struct GovernanceQualityTracker {
    indices: HashMap<String, Vec<GovernanceQualityIndex>>,
}

impl GovernanceQualityTracker {
    pub fn new() -> Self {
        Self {
            indices: HashMap::new(),
        }
    }

    /// Compute governance quality index for a region
    pub fn compute_index(
        &self,
        region: &str,
        dimensions: Vec<GovernanceDimension>,
        period: &str,
    ) -> GovernanceQualityIndex {
        let total_weight: f64 = dimensions.iter().map(|d| d.weight).sum();
        let overall_score = if total_weight > 0.0 {
            dimensions.iter().map(|d| d.score * d.weight).sum::<f64>() / total_weight
        } else {
            0.0
        };

        let grade = match overall_score as u32 {
            80..=100 => "A",
            65..=79 => "B",
            50..=64 => "C",
            35..=49 => "D",
            _ => "F",
        }
        .to_string();

        GovernanceQualityIndex {
            region: region.to_string(),
            overall_score,
            grade,
            dimensions,
            rank: None,
            peer_comparison: Vec::new(),
            period: period.to_string(),
        }
    }

    /// Default dimensions for Kenyan counties
    pub fn default_dimensions() -> Vec<GovernanceDimension> {
        vec![
            GovernanceDimension {
                name: "Business Registration".into(),
                name_local: "Usajili wa Biashara".into(),
                score: 50.0,
                weight: 0.20,
                indicators: vec![
                    GovernanceIndicator {
                        name: "Days to register business".into(),
                        value: 23.0,
                        unit: "days".into(),
                        source: "World Bank Doing Business".into(),
                        direction: IndicatorDirection::LowerIsBetter,
                    },
                    GovernanceIndicator {
                        name: "Cost (% of income)".into(),
                        value: 28.0,
                        unit: "%".into(),
                        source: "World Bank".into(),
                        direction: IndicatorDirection::LowerIsBetter,
                    },
                ],
            },
            GovernanceDimension {
                name: "Market Infrastructure".into(),
                name_local: "Miundombinu ya Soko".into(),
                score: 40.0,
                weight: 0.20,
                indicators: vec![
                    GovernanceIndicator {
                        name: "Covered market stalls (% of vendors)".into(),
                        value: 30.0,
                        unit: "%".into(),
                        source: "County data".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                    GovernanceIndicator {
                        name: "Road access quality".into(),
                        value: 45.0,
                        unit: "score".into(),
                        source: "KNBS".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                ],
            },
            GovernanceDimension {
                name: "Corruption Perception".into(),
                name_local: "Mtazamo wa Rushwa".into(),
                score: 35.0,
                weight: 0.15,
                indicators: vec![
                    GovernanceIndicator {
                        name: "Bribery incidents per 100 transactions".into(),
                        value: 15.0,
                        unit: "incidents".into(),
                        source: "TI Kenya".into(),
                        direction: IndicatorDirection::LowerIsBetter,
                    },
                    GovernanceIndicator {
                        name: "Trust in local government".into(),
                        value: 30.0,
                        unit: "%".into(),
                        source: "Afrobarometer".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                ],
            },
            GovernanceDimension {
                name: "Tax Fairness".into(),
                name_local: "Uadilifu wa Kodi".into(),
                score: 30.0,
                weight: 0.15,
                indicators: vec![
                    GovernanceIndicator {
                        name: "Informal workers paying tax".into(),
                        value: 12.0,
                        unit: "%".into(),
                        source: "KRA estimates".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                    GovernanceIndicator {
                        name: "Tax-to-service ratio (perceived)".into(),
                        value: 25.0,
                        unit: "score".into(),
                        source: "Survey data".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                ],
            },
            GovernanceDimension {
                name: "Property Rights".into(),
                name_local: "Haki za Mali".into(),
                score: 40.0,
                weight: 0.15,
                indicators: vec![
                    GovernanceIndicator {
                        name: "Land title registration rate".into(),
                        value: 35.0,
                        unit: "%".into(),
                        source: "Ministry of Lands".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                    GovernanceIndicator {
                        name: "Eviction protection score".into(),
                        value: 40.0,
                        unit: "score".into(),
                        source: "Legal analysis".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                ],
            },
            GovernanceDimension {
                name: "Financial Inclusion".into(),
                name_local: "Ujumuishaji wa Kifedha".into(),
                score: 60.0,
                weight: 0.15,
                indicators: vec![
                    GovernanceIndicator {
                        name: "Mobile money access".into(),
                        value: 85.0,
                        unit: "%".into(),
                        source: "CBK".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                    GovernanceIndicator {
                        name: "Savings group registration".into(),
                        value: 40.0,
                        unit: "%".into(),
                        source: "SASRA".into(),
                        direction: IndicatorDirection::HigherIsBetter,
                    },
                ],
            },
        ]
    }

    /// Record index in history
    pub fn record(&mut self, index: GovernanceQualityIndex) {
        let entry = self
            .indices
            .entry(index.region.clone())
            .or_insert_with(Vec::new);
        entry.push(index);
        if entry.len() > 100 {
            entry.drain(0..entry.len() - 100);
        }
    }

    /// Compare regions and compute peer comparisons
    pub fn compare_regions(&self, period: &str) -> Vec<PeerComparison> {
        let mut region_scores: Vec<(String, f64, String)> = Vec::new();

        for (region, history) in &self.indices {
            if let Some(latest) = history.last() {
                if latest.period == period {
                    let strongest = latest
                        .dimensions
                        .iter()
                        .max_by(|a, b| a.score.partial_cmp(&b.score).unwrap())
                        .map(|d| d.name.clone())
                        .unwrap_or_default();
                    region_scores.push((region.clone(), latest.overall_score, strongest));
                }
            }
        }

        // Generate comparisons for each pair
        let mut comparisons = Vec::new();
        for (region, score, _) in &region_scores {
            for (peer, peer_score, peer_strongest) in &region_scores {
                if region != peer {
                    comparisons.push(PeerComparison {
                        peer_region: peer.clone(),
                        peer_score: *peer_score,
                        score_difference: score - peer_score,
                        strongest_dimension: peer_strongest.clone(),
                    });
                }
            }
        }
        comparisons
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_dimensions() {
        let dims = GovernanceQualityTracker::default_dimensions();
        assert_eq!(dims.len(), 6);
        let total_weight: f64 = dims.iter().map(|d| d.weight).sum();
        assert!(
            (total_weight - 1.0).abs() < 0.01,
            "Weights should sum to 1.0, got {}",
            total_weight
        );
    }

    #[test]
    fn test_index_computation() {
        let tracker = GovernanceQualityTracker::new();
        let dims = vec![GovernanceDimension {
            name: "Test".into(),
            name_local: "Test".into(),
            score: 80.0,
            weight: 1.0,
            indicators: vec![],
        }];
        let index = tracker.compute_index("nairobi", dims, "2026-08");
        assert!((index.overall_score - 80.0).abs() < 0.01);
        assert_eq!(index.grade, "B");
    }

    #[test]
    fn test_grading() {
        let tracker = GovernanceQualityTracker::new();
        for (score, expected_grade) in vec![(90, "A"), (70, "B"), (55, "C"), (40, "D"), (20, "F")] {
            let dims = vec![GovernanceDimension {
                name: "T".into(),
                name_local: "T".into(),
                score: score as f64,
                weight: 1.0,
                indicators: vec![],
            }];
            let index = tracker.compute_index("test", dims, "2026-08");
            assert_eq!(
                index.grade, expected_grade,
                "Score {} should grade {}",
                score, expected_grade
            );
        }
    }
}
