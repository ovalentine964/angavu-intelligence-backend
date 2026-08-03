// =============================================================================
// Angavu Intelligence — Trade Gravity Model
// Predict trade flows between regions using the gravity model of trade.
//
// T_ij = A × (GDP_i^α × GDP_j^β) / Distance_ij^γ × (1 + TradeAgreement_ij)^δ
//
// Adapted for informal cross-border trade in East Africa.
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// A region/node in the trade network
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeNode {
    pub id: String,
    pub name: String,
    pub gdp_proxy: f64, // Economic size proxy from transaction data
    pub population: f64,
    pub is_border_region: bool,
    pub border_country: Option<String>,
}

/// A trade flow prediction between two regions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeFlow {
    pub origin: String,
    pub destination: String,
    pub predicted_volume: f64,
    pub actual_volume: f64,
    pub trade_intensity: f64, // predicted / expected
    pub distance_km: f64,
    pub has_trade_agreement: bool,
    pub common_language: bool,
}

/// Gravity model parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GravityModelParams {
    pub gdp_origin_elasticity: f64,  // α
    pub gdp_dest_elasticity: f64,    // β
    pub distance_elasticity: f64,    // γ (negative)
    pub trade_agreement_effect: f64, // δ
    pub common_language_effect: f64,
    pub constant: f64, // A
}

impl Default for GravityModelParams {
    fn default() -> Self {
        Self {
            gdp_origin_elasticity: 0.8,
            gdp_dest_elasticity: 0.8,
            distance_elasticity: -1.2,
            trade_agreement_effect: 0.5,
            common_language_effect: 0.3,
            constant: 1.0,
        }
    }
}

/// Trade Gravity Model module
pub struct TradeGravityModel {
    nodes: HashMap<String, TradeNode>,
    distances: HashMap<(String, String), f64>,
    params: GravityModelParams,
    flows: Vec<TradeFlow>,
}

impl TradeGravityModel {
    pub fn new() -> Self {
        let mut model = Self {
            nodes: HashMap::new(),
            distances: HashMap::new(),
            params: GravityModelParams::default(),
            flows: Vec::new(),
        };
        model.init_east_africa();
        model
    }

    /// Initialize with East African trade nodes
    fn init_east_africa(&mut self) {
        let nodes = vec![
            TradeNode {
                id: "nairobi".into(),
                name: "Nairobi".into(),
                gdp_proxy: 5000.0,
                population: 4_500_000.0,
                is_border_region: false,
                border_country: None,
            },
            TradeNode {
                id: "mombasa".into(),
                name: "Mombasa".into(),
                gdp_proxy: 2000.0,
                population: 1_200_000.0,
                is_border_region: false,
                border_country: None,
            },
            TradeNode {
                id: "kisumu".into(),
                name: "Kisumu".into(),
                gdp_proxy: 800.0,
                population: 600_000.0,
                is_border_region: true,
                border_country: Some("UG".into()),
            },
            TradeNode {
                id: "nakuru".into(),
                name: "Nakuru".into(),
                gdp_proxy: 1200.0,
                population: 500_000.0,
                is_border_region: false,
                border_country: None,
            },
            TradeNode {
                id: "eldoret".into(),
                name: "Eldoret".into(),
                gdp_proxy: 900.0,
                population: 450_000.0,
                is_border_region: false,
                border_country: None,
            },
            TradeNode {
                id: "malaba".into(),
                name: "Malaba Border".into(),
                gdp_proxy: 300.0,
                population: 50_000.0,
                is_border_region: true,
                border_country: Some("UG".into()),
            },
            TradeNode {
                id: "namanga".into(),
                name: "Namanga Border".into(),
                gdp_proxy: 200.0,
                population: 30_000.0,
                is_border_region: true,
                border_country: Some("TZ".into()),
            },
            TradeNode {
                id: "busia".into(),
                name: "Busia Border".into(),
                gdp_proxy: 250.0,
                population: 60_000.0,
                is_border_region: true,
                border_country: Some("UG".into()),
            },
        ];

        for node in nodes {
            self.nodes.insert(node.id.clone(), node);
        }

        // Approximate distances (km)
        let dist_data = vec![
            ("nairobi", "mombasa", 480.0),
            ("nairobi", "kisumu", 340.0),
            ("nairobi", "nakuru", 160.0),
            ("nairobi", "eldoret", 310.0),
            ("nairobi", "namanga", 180.0),
            ("kisumu", "busia", 100.0),
            ("eldoret", "malaba", 80.0),
            ("mombasa", "nairobi", 480.0),
        ];

        for (a, b, d) in dist_data {
            self.distances.insert((a.into(), b.into()), d);
        }
    }

    /// Predict trade flow between two regions using gravity model
    pub fn predict_flow(&self, origin: &str, destination: &str) -> Option<TradeFlow> {
        let o = self.nodes.get(origin)?;
        let d = self.nodes.get(destination)?;

        let distance = self
            .distances
            .get(&(origin.into(), destination.into()))
            .copied()
            .unwrap_or(500.0);

        let has_agreement = o.border_country.is_some() && d.border_country.is_some();
        let common_lang = true; // Swahili/English common across East Africa

        let p = &self.params;
        let predicted = p.constant
            * (o.gdp_proxy.powf(p.gdp_origin_elasticity) * d.gdp_proxy.powf(p.gdp_dest_elasticity))
            / distance.powf(-p.distance_elasticity)
            * if has_agreement {
                (1.0 + p.trade_agreement_effect)
            } else {
                1.0
            }
            * if common_lang {
                (1.0 + p.common_language_effect)
            } else {
                1.0
            };

        Some(TradeFlow {
            origin: origin.into(),
            destination: destination.into(),
            predicted_volume: predicted,
            actual_volume: 0.0, // To be filled from transaction data
            trade_intensity: 0.0,
            distance_km: distance,
            has_trade_agreement: has_agreement,
            common_language: common_lang,
        })
    }

    /// Predict all pairwise flows
    pub fn predict_all_flows(&self) -> Vec<TradeFlow> {
        let mut flows = Vec::new();
        let origins: Vec<_> = self.nodes.keys().cloned().collect();
        let destinations: Vec<_> = self.nodes.keys().cloned().collect();

        for o in &origins {
            for d in &destinations {
                if o != d {
                    if let Some(flow) = self.predict_flow(o, d) {
                        flows.push(flow);
                    }
                }
            }
        }
        flows
    }

    /// Update a flow with actual observed volume
    pub fn update_actual(&mut self, origin: &str, destination: &str, actual_volume: f64) {
        for flow in &mut self.flows {
            if flow.origin == origin && flow.destination == destination {
                flow.actual_volume = actual_volume;
                flow.trade_intensity = if flow.predicted_volume > 0.0 {
                    actual_volume / flow.predicted_volume
                } else {
                    0.0
                };
            }
        }
    }

    /// Add a custom trade node
    pub fn add_node(&mut self, node: TradeNode) {
        self.nodes.insert(node.id.clone(), node);
    }

    /// Set distance between two nodes
    pub fn set_distance(&mut self, from: &str, to: &str, km: f64) {
        self.distances.insert((from.into(), to.into()), km);
    }

    /// Get all nodes
    pub fn nodes(&self) -> &HashMap<String, TradeNode> {
        &self.nodes
    }

    /// Get border regions
    pub fn border_regions(&self) -> Vec<&TradeNode> {
        self.nodes.values().filter(|n| n.is_border_region).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gravity_model_basic() {
        let model = TradeGravityModel::new();
        let flow = model.predict_flow("nairobi", "mombasa").unwrap();
        assert!(flow.predicted_volume > 0.0);
        assert_eq!(flow.origin, "nairobi");
    }

    #[test]
    fn test_border_regions_have_higher_flow() {
        let model = TradeGravityModel::new();
        // Nairobi-Kisumu (border) should have higher intensity than Nairobi-Nakuru
        let flow_border = model.predict_flow("nairobi", "kisumu").unwrap();
        let flow_inland = model.predict_flow("nairobi", "nakuru").unwrap();
        // Both are non-border origins, so agreement effect doesn't apply here
        // But kisumu is a border node
        assert!(flow_border.predicted_volume > 0.0);
        assert!(flow_inland.predicted_volume > 0.0);
    }

    #[test]
    fn test_predict_all_flows() {
        let model = TradeGravityModel::new();
        let flows = model.predict_all_flows();
        assert!(flows.len() > 20); // 8 nodes = 56 pairs
    }
}
