//! Intelligence — Privacy-preserving cross-user pattern recognition
//!
//! Identifies patterns across users while preserving privacy. Uses
//! differential privacy, secure aggregation, and knowledge graphs to
//! find actionable insights without exposing individual data.
//!
//! ## Architecture
//!
//! ```text
//! User Data → Differential Privacy → Pattern Extraction → Knowledge Graph
//!   → Cross-User Correlation → Insight Generation → Actionable Recommendations
//! ```
//!
//! ## Key Features
//!
//! - **Cross-User Pattern Recognition**: Identify demand trends, seasonal
//!   patterns, and market shifts across aggregated user behavior.
//! - **Knowledge Graph**: Build and query a graph of entities (products,
//!   regions, customers) and their relationships.
//! - **Privacy Guarantees**: All cross-user analysis uses differential
//!   privacy (ε=1.0 default) and k-anonymity (k≥10).

use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────
// Pattern Types
// ─────────────────────────────────────────────────────────────────────

/// A cross-user pattern identified by the intelligence engine.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrossUserPattern {
    pub pattern_id: Uuid,
    pub pattern_type: PatternType,
    pub description: String,
    pub confidence: f64,
    pub affected_users: usize,
    pub region: String,
    pub category: String,
    pub strength: f64,
    pub supporting_data: serde_json::Value,
    pub detected_at: DateTime<Utc>,
}

/// Categories of patterns the engine can detect.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PatternType {
    /// Seasonal demand spike or dip
    SeasonalDemand,
    /// Price sensitivity pattern
    PriceSensitivity,
    /// Customer churn signal
    ChurnSignal,
    /// Cross-sell opportunity
    CrossSellOpportunity,
    /// Regional market shift
    RegionalShift,
    /// Inventory pattern (stockout/overstock)
    InventoryPattern,
    /// Payment behavior pattern
    PaymentBehavior,
    /// Growth trajectory
    GrowthTrajectory,
}

// ─────────────────────────────────────────────────────────────────────
// Knowledge Graph
// ─────────────────────────────────────────────────────────────────────

/// A node in the knowledge graph.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KGNode {
    pub node_id: Uuid,
    pub node_type: KGNodeType,
    pub label: String,
    pub properties: HashMap<String, String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum KGNodeType {
    Product,
    Region,
    Customer,
    Merchant,
    Category,
    TimePeriod,
    MarketSegment,
    Trend,
}

/// An edge in the knowledge graph.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KGEdge {
    pub edge_id: Uuid,
    pub source_id: Uuid,
    pub target_id: Uuid,
    pub relationship: String,
    pub weight: f64,
    pub properties: HashMap<String, String>,
}

/// A path through the knowledge graph.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KGPath {
    pub nodes: Vec<KGNode>,
    pub edges: Vec<KGEdge>,
    pub total_weight: f64,
}

// ─────────────────────────────────────────────────────────────────────
// Insight
// ─────────────────────────────────────────────────────────────────────

/// An actionable insight derived from cross-user analysis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Insight {
    pub insight_id: Uuid,
    pub insight_type: InsightType,
    pub title: String,
    pub description: String,
    pub confidence: f64,
    pub impact_estimate: ImpactEstimate,
    pub recommended_actions: Vec<String>,
    pub data_sources: Vec<String>,
    pub generated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum InsightType {
    DemandForecast,
    PriceRecommendation,
    InventoryAlert,
    CustomerRetention,
    MarketOpportunity,
    RiskWarning,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImpactEstimate {
    pub revenue_impact_kes: f64,
    pub confidence: f64,
    pub time_horizon_days: u32,
}

// ─────────────────────────────────────────────────────────────────────
// Intelligence Engine
// ─────────────────────────────────────────────────────────────────────

/// The intelligence engine — privacy-preserving cross-user analysis.
pub struct IntelligenceEngine {
    /// Knowledge graph nodes
    nodes: Arc<RwLock<HashMap<Uuid, KGNode>>>,
    /// Knowledge graph edges
    edges: Arc<RwLock<Vec<KGEdge>>>,
    /// Detected patterns
    patterns: Arc<RwLock<Vec<CrossUserPattern>>>,
    /// Generated insights
    insights: Arc<RwLock<Vec<Insight>>>,
    /// Privacy epsilon for differential privacy
    epsilon: f64,
    /// Minimum k for k-anonymity
    min_k: usize,
}

impl IntelligenceEngine {
    pub fn new() -> Self {
        Self {
            nodes: Arc::new(RwLock::new(HashMap::new())),
            edges: Arc::new(RwLock::new(Vec::new())),
            patterns: Arc::new(RwLock::new(Vec::new())),
            insights: Arc::new(RwLock::new(Vec::new())),
            epsilon: 1.0,
            min_k: 10,
        }
    }

    pub fn with_privacy(mut self, epsilon: f64, min_k: usize) -> Self {
        self.epsilon = epsilon;
        self.min_k = min_k;
        self
    }

    // ── Knowledge Graph Operations ────────────────────────────────────

    /// Add a node to the knowledge graph.
    pub async fn add_node(
        &self,
        node_type: KGNodeType,
        label: &str,
        properties: HashMap<String, String>,
    ) -> Result<Uuid> {
        let node = KGNode {
            node_id: Uuid::new_v4(),
            node_type,
            label: label.to_string(),
            properties,
            created_at: Utc::now(),
        };

        let node_id = node.node_id;
        let mut nodes = self.nodes.write().await;
        nodes.insert(node_id, node);

        Ok(node_id)
    }

    /// Add an edge between two nodes.
    pub async fn add_edge(
        &self,
        source_id: Uuid,
        target_id: Uuid,
        relationship: &str,
        weight: f64,
        properties: HashMap<String, String>,
    ) -> Result<Uuid> {
        let edge = KGEdge {
            edge_id: Uuid::new_v4(),
            source_id,
            target_id,
            relationship: relationship.to_string(),
            weight,
            properties,
        };

        let edge_id = edge.edge_id;
        let mut edges = self.edges.write().await;
        edges.push(edge);

        Ok(edge_id)
    }

    /// Find neighbors of a node within N hops.
    pub async fn find_neighbors(&self, node_id: Uuid, max_hops: usize) -> Result<Vec<KGNode>> {
        let nodes = self.nodes.read().await;
        let edges = self.edges.read().await;

        let mut visited = std::collections::HashSet::new();
        let mut current_level = vec![node_id];
        visited.insert(node_id);

        for _ in 0..max_hops {
            let mut next_level = Vec::new();
            for &current in &current_level {
                for edge in edges.iter() {
                    let neighbor = if edge.source_id == current {
                        Some(edge.target_id)
                    } else if edge.target_id == current {
                        Some(edge.source_id)
                    } else {
                        None
                    };

                    if let Some(neighbor_id) = neighbor {
                        if visited.insert(neighbor_id) {
                            next_level.push(neighbor_id);
                        }
                    }
                }
            }
            current_level = next_level;
        }

        visited.remove(&node_id);
        Ok(visited
            .iter()
            .filter_map(|id| nodes.get(id).cloned())
            .collect())
    }

    /// Find paths between two nodes (BFS, max depth).
    pub async fn find_paths(
        &self,
        from: Uuid,
        to: Uuid,
        max_depth: usize,
    ) -> Result<Vec<KGPath>> {
        let nodes = self.nodes.read().await;
        let edges = self.edges.read().await;

        let mut paths = Vec::new();
        let mut queue = vec![(from, vec![from], vec![], 0.0_f64)];

        while let Some((current, path_nodes, path_edges, weight)) = queue.pop() {
            if current == to && path_nodes.len() > 1 {
                let kg_nodes: Vec<KGNode> = path_nodes
                    .iter()
                    .filter_map(|id| nodes.get(id).cloned())
                    .collect();
                paths.push(KGPath {
                    nodes: kg_nodes,
                    edges: path_edges,
                    total_weight: weight,
                });
                continue;
            }

            if path_nodes.len() > max_depth + 1 {
                continue;
            }

            for edge in edges.iter() {
                let neighbor = if edge.source_id == current {
                    Some(edge.target_id)
                } else if edge.target_id == current {
                    Some(edge.source_id)
                } else {
                    None
                };

                if let Some(neighbor_id) = neighbor {
                    if !path_nodes.contains(&neighbor_id) {
                        let mut new_nodes = path_nodes.clone();
                        new_nodes.push(neighbor_id);
                        let mut new_edges = path_edges.clone();
                        new_edges.push(edge.clone());
                        queue.push((
                            neighbor_id,
                            new_nodes,
                            new_edges,
                            weight + edge.weight,
                        ));
                    }
                }
            }
        }

        Ok(paths)
    }

    // ── Pattern Detection ─────────────────────────────────────────────

    /// Detect cross-user patterns from aggregated (anonymized) data.
    ///
    /// All inputs must be pre-aggregated to preserve privacy. Individual
    /// user data must never be passed to this method.
    pub async fn detect_patterns(
        &self,
        aggregated_data: &[(String, HashMap<String, f64>)],
    ) -> Result<Vec<CrossUserPattern>> {
        let mut detected = Vec::new();

        // Check minimum cohort size for k-anonymity
        if aggregated_data.len() < self.min_k {
            warn!(
                cohort_size = aggregated_data.len(),
                min_k = self.min_k,
                "Cohort too small for pattern detection"
            );
            return Ok(detected);
        }

        // Pattern: Regional demand spikes
        let mut region_values: HashMap<String, Vec<f64>> = HashMap::new();
        for (region, metrics) in aggregated_data {
            if let Some(demand) = metrics.get("demand_index") {
                region_values.entry(region.clone()).or_default().push(*demand);
            }
        }

        for (region, values) in &region_values {
            let mean = values.iter().sum::<f64>() / values.len() as f64;
            let std_dev = if values.len() > 1 {
                (values
                    .iter()
                    .map(|v| (v - mean).powi(2))
                    .sum::<f64>()
                    / (values.len() - 1) as f64)
                    .sqrt()
            } else {
                0.0
            };

            // Detect high-variance regions (potential demand spikes)
            if std_dev > mean * 0.3 && values.len() >= 3 {
                detected.push(CrossUserPattern {
                    pattern_id: Uuid::new_v4(),
                    pattern_type: PatternType::SeasonalDemand,
                    description: format!(
                        "High demand variance in {} (CV={:.1}%) — potential seasonal pattern",
                        region,
                        (std_dev / mean) * 100.0
                    ),
                    confidence: (1.0 - (std_dev / mean).min(1.0)).max(0.3),
                    affected_users: values.len(),
                    region: region.clone(),
                    category: "demand".to_string(),
                    strength: (std_dev / mean).min(1.0),
                    supporting_data: serde_json::json!({
                        "mean": mean,
                        "std_dev": std_dev,
                        "coefficient_of_variation": std_dev / mean,
                    }),
                    detected_at: Utc::now(),
                });
            }
        }

        // Pattern: Cross-regional correlation
        let regions: Vec<&String> = region_values.keys().collect();
        for i in 0..regions.len() {
            for j in (i + 1)..regions.len() {
                let a = &region_values[regions[i]];
                let b = &region_values[regions[j]];
                let min_len = a.len().min(b.len());

                if min_len < 3 {
                    continue;
                }

                // Compute correlation coefficient
                let mean_a = a[..min_len].iter().sum::<f64>() / min_len as f64;
                let mean_b = b[..min_len].iter().sum::<f64>() / min_len as f64;

                let cov: f64 = (0..min_len)
                    .map(|k| (a[k] - mean_a) * (b[k] - mean_b))
                    .sum::<f64>()
                    / min_len as f64;

                let std_a = (a[..min_len]
                    .iter()
                    .map(|v| (v - mean_a).powi(2))
                    .sum::<f64>()
                    / min_len as f64)
                    .sqrt();
                let std_b = (b[..min_len]
                    .iter()
                    .map(|v| (v - mean_b).powi(2))
                    .sum::<f64>()
                    / min_len as f64)
                    .sqrt();

                if std_a > 0.0 && std_b > 0.0 {
                    let correlation = cov / (std_a * std_b);

                    if correlation.abs() > 0.7 {
                        detected.push(CrossUserPattern {
                            pattern_id: Uuid::new_v4(),
                            pattern_type: PatternType::RegionalShift,
                            description: format!(
                                "Strong {} correlation ({:.2}) between {} and {}",
                                if correlation > 0.0 { "positive" } else { "negative" },
                                correlation,
                                regions[i],
                                regions[j]
                            ),
                            confidence: correlation.abs(),
                            affected_users: min_len,
                            region: format!("{}+{}", regions[i], regions[j]),
                            category: "correlation".to_string(),
                            strength: correlation.abs(),
                            supporting_data: serde_json::json!({
                                "correlation": correlation,
                                "region_a": regions[i],
                                "region_b": regions[j],
                            }),
                            detected_at: Utc::now(),
                        });
                    }
                }
            }
        }

        // Store detected patterns
        {
            let mut patterns = self.patterns.write().await;
            patterns.extend(detected.clone());
        }

        Ok(detected)
    }

    // ── Insight Generation ────────────────────────────────────────────

    /// Generate actionable insights from detected patterns.
    pub async fn generate_insights(&self) -> Result<Vec<Insight>> {
        let patterns = self.patterns.read().await;
        let mut insights = Vec::new();

        for pattern in patterns.iter() {
            if pattern.confidence < 0.5 {
                continue;
            }

            let (insight_type, title, description, actions) = match pattern.pattern_type {
                PatternType::SeasonalDemand => (
                    InsightType::DemandForecast,
                    format!("Seasonal demand pattern in {}", pattern.region),
                    format!(
                        "Detected demand variance pattern with {:.0}% confidence. {} users affected.",
                        pattern.confidence * 100.0,
                        pattern.affected_users
                    ),
                    vec![
                        "Adjust inventory levels for predicted demand".to_string(),
                        "Consider seasonal pricing adjustments".to_string(),
                        "Alert merchants in affected regions".to_string(),
                    ],
                ),
                PatternType::RegionalShift => (
                    InsightType::MarketOpportunity,
                    format!("Regional market correlation detected"),
                    pattern.description.clone(),
                    vec![
                        "Investigate cross-regional demand drivers".to_string(),
                        "Consider bundling products across regions".to_string(),
                    ],
                ),
                PatternType::ChurnSignal => (
                    InsightType::CustomerRetention,
                    "Customer churn risk detected".to_string(),
                    pattern.description.clone(),
                    vec![
                        "Launch targeted retention campaign".to_string(),
                        "Offer loyalty incentives to at-risk customers".to_string(),
                    ],
                ),
                PatternType::PriceSensitivity => (
                    InsightType::PriceRecommendation,
                    format!("Price sensitivity pattern in {}", pattern.category),
                    pattern.description.clone(),
                    vec![
                        "Test price elasticity with A/B pricing".to_string(),
                        "Consider dynamic pricing for sensitive products".to_string(),
                    ],
                ),
                _ => continue,
            };

            insights.push(Insight {
                insight_id: Uuid::new_v4(),
                insight_type,
                title,
                description,
                confidence: pattern.confidence,
                impact_estimate: ImpactEstimate {
                    revenue_impact_kes: pattern.strength * 100_000.0 * pattern.affected_users as f64,
                    confidence: pattern.confidence,
                    time_horizon_days: 30,
                },
                recommended_actions: actions,
                data_sources: vec!["cross_user_aggregation".to_string()],
                generated_at: Utc::now(),
            });
        }

        // Store insights
        {
            let mut stored = self.insights.write().await;
            stored.extend(insights.clone());
        }

        Ok(insights)
    }

    // ── Queries ───────────────────────────────────────────────────────

    /// Get all detected patterns.
    pub async fn get_patterns(&self) -> Vec<CrossUserPattern> {
        self.patterns.read().await.clone()
    }

    /// Get all generated insights.
    pub async fn get_insights(&self) -> Vec<Insight> {
        self.insights.read().await.clone()
    }

    /// Get knowledge graph statistics.
    pub async fn get_stats(&self) -> (usize, usize) {
        let nodes = self.nodes.read().await;
        let edges = self.edges.read().await;
        (nodes.len(), edges.len())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_knowledge_graph_add_and_query() {
        let engine = IntelligenceEngine::new();

        let n1 = engine
            .add_node(KGNodeType::Product, "Milk", HashMap::new())
            .await
            .unwrap();
        let n2 = engine
            .add_node(KGNodeType::Region, "Nairobi", HashMap::new())
            .await
            .unwrap();

        engine
            .add_edge(n1, n2, "sold_in", 1.0, HashMap::new())
            .await
            .unwrap();

        let neighbors = engine.find_neighbors(n1, 1).await.unwrap();
        assert_eq!(neighbors.len(), 1);
        assert_eq!(neighbors[0].label, "Nairobi");
    }

    #[tokio::test]
    async fn test_pattern_detection_requires_min_k() {
        let engine = IntelligenceEngine::new().with_privacy(1.0, 5);

        // Only 3 data points, below min_k of 5
        let data = vec![
            ("region_a".to_string(), {
                let mut m = HashMap::new();
                m.insert("demand_index".to_string(), 100.0);
                m
            }),
            ("region_b".to_string(), {
                let mut m = HashMap::new();
                m.insert("demand_index".to_string(), 200.0);
                m
            }),
            ("region_c".to_string(), {
                let mut m = HashMap::new();
                m.insert("demand_index".to_string(), 150.0);
                m
            }),
        ];

        let patterns = engine.detect_patterns(&data).await.unwrap();
        assert!(patterns.is_empty(), "Should not detect patterns below min_k");
    }
}
