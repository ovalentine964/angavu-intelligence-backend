// =============================================================================
// Angavu Intelligence — Harness-as-Graph Representation
// Represents the entire harness (ToolGraph, IntentRouter, Councils, Loops)
// as a graph structure for future quantum graph algorithm optimization
//
// The harness is the permanent investment. By representing it as a graph:
// 1. Quantum graph algorithms can optimize routing, scheduling, resource allocation
// 2. The harness structure can be analyzed, visualized, and reasoned about
// 3. Changes to the harness can be evaluated for their graph-theoretic impact
// 4. Future AGI can reason about and optimize its own harness structure
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ── Harness Node Types ───────────────────────────────────────────────────────

/// All components of the Angavu Intelligence harness
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum HarnessNode {
    /// Tool in the ToolGraph (e.g., TransactionRecorder, MarketPriceLookup)
    Tool(ToolNode),
    /// Intent router entry point
    IntentRouter(IntentRouterNode),
    /// Council (e.g., Credit Council, Market Council)
    Council(CouncilNode),
    /// OODA Loop (fast/hourly/daily/weekly)
    Loop(LoopNode),
    /// Data store (ClickHouse, PostgreSQL, Redis)
    DataStore(DataStoreNode),
    /// External service (M-Pesa, weather API, market feed)
    ExternalService(ExternalServiceNode),
    /// Model provider (DeepSeek, Qwen, future AGI)
    ModelProvider(ModelProviderNode),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolNode {
    pub id: String,
    pub name: String,
    pub category: String,
    pub input_types: Vec<String>,
    pub output_types: Vec<String>,
    pub average_latency_ms: u64,
    pub success_rate: f64,
    pub cost_per_call: f64,
    pub dependencies: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntentRouterNode {
    pub id: String,
    pub supported_intents: Vec<String>,
    pub routing_model: String,
    pub accuracy: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CouncilNode {
    pub id: String,
    pub council_type: String,
    pub members: Vec<String>,
    pub decision_method: String,
    pub quorum_size: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoopNode {
    pub id: String,
    pub loop_type: String, // "fast", "hourly", "daily", "weekly"
    pub interval_ms: u64,
    pub phases: Vec<String>,
    pub circuit_breaker_threshold: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataStoreNode {
    pub id: String,
    pub store_type: String, // "clickhouse", "postgres", "redis", "sqlite"
    pub purpose: String,
    pub capacity_gb: f64,
    pub replication_factor: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExternalServiceNode {
    pub id: String,
    pub service_name: String,
    pub api_type: String,
    pub reliability: f64,
    pub cost_model: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelProviderNode {
    pub id: String,
    pub provider_name: String,
    pub model_name: String,
    pub tier: String, // "classical", "quantum_inspired", "hybrid", "quantum", "agi"
    pub capabilities: Vec<String>,
}

// ── Harness Edge Types ───────────────────────────────────────────────────────

/// Relationships between harness components
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum HarnessEdge {
    /// Data flow: source produces data consumed by target
    DataFlow {
        source: String,
        target: String,
        data_type: String,
        frequency_hz: f64,
    },
    /// Control flow: source triggers/controls target
    ControlFlow {
        source: String,
        target: String,
        trigger_type: String,
    },
    /// Dependency: source depends on target
    Dependency {
        source: String,
        target: String,
        dependency_type: DependencyType,
        critical: bool,
    },
    /// Feedback: target's output feeds back to source
    Feedback {
        source: String,
        target: String,
        feedback_type: String,
        delay_ms: u64,
    },
    /// Routing: router directs to target based on intent
    Routing {
        router: String,
        target: String,
        intent: String,
        probability: f64,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DependencyType {
    /// Hard dependency: fails without it
    Hard,
    /// Soft dependency: degrades without it
    Soft,
    /// Optional: can operate without it
    Optional,
}

// ── Harness Graph ────────────────────────────────────────────────────────────

/// Complete graph representation of the Angavu Intelligence harness
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HarnessGraph {
    pub nodes: Vec<HarnessNode>,
    pub edges: Vec<HarnessEdge>,
    pub metadata: HarnessMetadata,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HarnessMetadata {
    pub version: String,
    pub generated_at: String,
    pub total_nodes: usize,
    pub total_edges: usize,
    pub graph_density: f64,
    pub critical_paths: Vec<Vec<String>>,
    pub strongly_connected_components: Vec<Vec<String>>,
}

impl HarnessGraph {
    /// Build the harness graph from the current system configuration
    pub fn build_from_config() -> Self {
        let mut nodes = Vec::new();
        let mut edges = Vec::new();

        // ── Intent Router ─────────────────────────────────────────────
        nodes.push(HarnessNode::IntentRouter(IntentRouterNode {
            id: "intent-router-main".to_string(),
            supported_intents: vec![
                "record_transaction".to_string(),
                "check_balance".to_string(),
                "market_price".to_string(),
                "credit_score".to_string(),
                "cfo_report".to_string(),
                "chama_update".to_string(),
                "weather_forecast".to_string(),
                "help".to_string(),
            ],
            routing_model: "qwen-0.8b-on-device".to_string(),
            accuracy: 0.87,
        }));

        // ── Tools (from ToolGraph) ────────────────────────────────────
        let tools = vec![
            (
                "transaction-recorder",
                "Finance",
                "VoiceText",
                "TransactionRecord",
                200,
                0.95,
            ),
            (
                "market-price-lookup",
                "Market",
                "ProductQuery",
                "PriceData",
                500,
                0.92,
            ),
            (
                "credit-scorer",
                "Credit",
                "WorkerProfile",
                "AlamaScore",
                1500,
                0.89,
            ),
            (
                "cfo-report-generator",
                "Analytics",
                "TimeRange",
                "FinancialReport",
                3000,
                0.91,
            ),
            (
                "inventory-tracker",
                "Inventory",
                "StockUpdate",
                "InventoryState",
                300,
                0.94,
            ),
            (
                "weather-api",
                "External",
                "Location",
                "WeatherData",
                800,
                0.98,
            ),
            (
                "chama-manager",
                "Social",
                "ChamaCommand",
                "ChamaState",
                400,
                0.90,
            ),
            (
                "job-matcher",
                "Employment",
                "WorkerProfile",
                "JobMatches",
                2000,
                0.85,
            ),
            (
                "supplier-finder",
                "SupplyChain",
                "ProductNeed",
                "SupplierList",
                1200,
                0.88,
            ),
            (
                "savings-advisor",
                "Finance",
                "FinancialState",
                "SavingsPlan",
                1000,
                0.87,
            ),
        ];

        for (name, cat, input, output, latency, success) in &tools {
            nodes.push(HarnessNode::Tool(ToolNode {
                id: format!("tool-{}", name),
                name: name.to_string(),
                category: cat.to_string(),
                input_types: vec![input.to_string()],
                output_types: vec![output.to_string()],
                average_latency_ms: *latency,
                success_rate: *success,
                cost_per_call: 0.001,
                dependencies: vec![],
            }));

            // Intent router → tool routing edge
            edges.push(HarnessEdge::Routing {
                router: "intent-router-main".to_string(),
                target: format!("tool-{}", name),
                intent: name.to_string(),
                probability: 0.1,
            });
        }

        // ── Councils ──────────────────────────────────────────────────
        let councils = vec![
            (
                "credit-council",
                "CreditApproval",
                vec!["credit-scorer", "approval-gate"],
                "majority_vote",
                3,
            ),
            (
                "market-council",
                "MarketAnalysis",
                vec!["market-price-lookup", "weather-api"],
                "weighted_consensus",
                2,
            ),
            (
                "social-council",
                "SocialDynamics",
                vec!["chama-manager", "job-matcher"],
                "deliberation",
                2,
            ),
        ];

        for (id, ctype, members, method, quorum) in &councils {
            nodes.push(HarnessNode::Council(CouncilNode {
                id: id.to_string(),
                council_type: ctype.to_string(),
                members: members.iter().map(|s| s.to_string()).collect(),
                decision_method: method.to_string(),
                quorum_size: *quorum,
            }));

            for member in *members {
                edges.push(HarnessEdge::ControlFlow {
                    source: id.to_string(),
                    target: format!("tool-{}", member),
                    trigger_type: "council_decision".to_string(),
                });
            }
        }

        // ── OODA Loops ────────────────────────────────────────────────
        let loops = vec![
            (
                "loop-fast",
                "fast",
                1000,
                vec!["observe", "orient", "decide", "act"],
            ),
            (
                "loop-hourly",
                "hourly",
                3600000,
                vec!["observe", "orient", "decide", "act"],
            ),
            (
                "loop-daily",
                "daily",
                86400000,
                vec!["observe", "orient", "decide", "act", "learn"],
            ),
            (
                "loop-weekly",
                "weekly",
                604800000,
                vec!["observe", "orient", "decide", "act", "learn", "retrain"],
            ),
        ];

        for (id, ltype, interval, phases) in &loops {
            nodes.push(HarnessNode::Loop(LoopNode {
                id: id.to_string(),
                loop_type: ltype.to_string(),
                interval_ms: *interval,
                phases: phases.iter().map(|s| s.to_string()).collect(),
                circuit_breaker_threshold: 5,
            }));
        }

        // ── Data Stores ───────────────────────────────────────────────
        nodes.push(HarnessNode::DataStore(DataStoreNode {
            id: "db-postgres".to_string(),
            store_type: "postgres".to_string(),
            purpose: "Primary transactional database".to_string(),
            capacity_gb: 100.0,
            replication_factor: 2,
        }));

        nodes.push(HarnessNode::DataStore(DataStoreNode {
            id: "db-clickhouse".to_string(),
            store_type: "clickhouse".to_string(),
            purpose: "Analytics and time-series data".to_string(),
            capacity_gb: 500.0,
            replication_factor: 3,
        }));

        nodes.push(HarnessNode::DataStore(DataStoreNode {
            id: "cache-redis".to_string(),
            store_type: "redis".to_string(),
            purpose: "Session cache, rate limiting, real-time data".to_string(),
            capacity_gb: 10.0,
            replication_factor: 1,
        }));

        // ── Model Providers ───────────────────────────────────────────
        let models = vec![
            (
                "deepseek-reasoner",
                "DeepSeek",
                "deepseek-reasoner",
                "classical",
                vec!["reasoning", "credit_analysis"],
            ),
            (
                "deepseek-chat",
                "DeepSeek",
                "deepseek-chat",
                "classical",
                vec!["conversation", "general"],
            ),
            (
                "qwen-7b",
                "Qwen",
                "qwen-7b",
                "classical",
                vec!["multilingual", "conversation"],
            ),
            (
                "qwen-0.8b",
                "Qwen",
                "qwen-0.8b-on-device",
                "classical",
                vec!["intent_classification", "on_device"],
            ),
            (
                "agi-placeholder",
                "Future",
                "agi-v1",
                "agi",
                vec!["reasoning", "planning", "creative", "social"],
            ),
        ];

        for (id, provider, model, tier, caps) in &models {
            nodes.push(HarnessNode::ModelProvider(ModelProviderNode {
                id: id.to_string(),
                provider_name: provider.to_string(),
                model_name: model.to_string(),
                tier: tier.to_string(),
                capabilities: caps.iter().map(|s| s.to_string()).collect(),
            }));
        }

        // ── External Services ─────────────────────────────────────────
        let externals = vec![
            ("mpesa-api", "M-Pesa", "REST", 0.999, "per_transaction"),
            (
                "weather-service",
                "OpenWeather",
                "REST",
                0.99,
                "per_request",
            ),
            (
                "market-feed",
                "Gikomba Market Feed",
                "WebSocket",
                0.95,
                "subscription",
            ),
        ];

        for (id, name, api, reliability, cost) in &externals {
            nodes.push(HarnessNode::ExternalService(ExternalServiceNode {
                id: id.to_string(),
                service_name: name.to_string(),
                api_type: api.to_string(),
                reliability: *reliability,
                cost_model: cost.to_string(),
            }));
        }

        // ── Data Flow Edges ───────────────────────────────────────────
        edges.push(HarnessEdge::DataFlow {
            source: "tool-transaction-recorder".to_string(),
            target: "db-postgres".to_string(),
            data_type: "TransactionRecord".to_string(),
            frequency_hz: 0.1,
        });

        edges.push(HarnessEdge::DataFlow {
            source: "tool-transaction-recorder".to_string(),
            target: "db-clickhouse".to_string(),
            data_type: "TransactionAnalytics".to_string(),
            frequency_hz: 0.1,
        });

        edges.push(HarnessEdge::DataFlow {
            source: "tool-credit-scorer".to_string(),
            target: "credit-council".to_string(),
            data_type: "AlamaScore".to_string(),
            frequency_hz: 0.01,
        });

        edges.push(HarnessEdge::DataFlow {
            source: "mpesa-api".to_string(),
            target: "tool-transaction-recorder".to_string(),
            data_type: "MpesaTransaction".to_string(),
            frequency_hz: 1.0,
        });

        // ── Feedback Edges ────────────────────────────────────────────
        edges.push(HarnessEdge::Feedback {
            source: "loop-daily".to_string(),
            target: "tool-credit-scorer".to_string(),
            feedback_type: "model_drift_alert".to_string(),
            delay_ms: 86400000,
        });

        edges.push(HarnessEdge::Feedback {
            source: "loop-weekly".to_string(),
            target: "deepseek-reasoner".to_string(),
            feedback_type: "retrain_trigger".to_string(),
            delay_ms: 604800000,
        });

        // ── Metadata ──────────────────────────────────────────────────
        let n = nodes.len();
        let max_edges = n * (n - 1);
        let density = if max_edges > 0 {
            edges.len() as f64 / max_edges as f64
        } else {
            0.0
        };

        HarnessGraph {
            nodes,
            edges,
            metadata: HarnessMetadata {
                version: "1.0.0".to_string(),
                generated_at: chrono::Utc::now().to_rfc3339(),
                total_nodes: n,
                total_edges: edges.len(),
                graph_density: density,
                critical_paths: vec![
                    vec![
                        "mpesa-api".to_string(),
                        "tool-transaction-recorder".to_string(),
                        "db-postgres".to_string(),
                    ],
                    vec![
                        "intent-router-main".to_string(),
                        "tool-credit-scorer".to_string(),
                        "credit-council".to_string(),
                        "approval-gate".to_string(),
                    ],
                ],
                strongly_connected_components: vec![],
            },
        }
    }

    /// Export as adjacency list (for graph algorithms)
    pub fn to_adjacency_list(&self) -> HashMap<String, Vec<String>> {
        let mut adj: HashMap<String, Vec<String>> = HashMap::new();

        for edge in &self.edges {
            let (source, target) = match edge {
                HarnessEdge::DataFlow { source, target, .. }
                | HarnessEdge::ControlFlow { source, target, .. }
                | HarnessEdge::Dependency { source, target, .. }
                | HarnessEdge::Feedback { source, target, .. } => (source.clone(), target.clone()),
                HarnessEdge::Routing { router, target, .. } => (router.clone(), target.clone()),
            };

            adj.entry(source).or_default().push(target);
        }

        adj
    }

    /// Export as adjacency matrix (for quantum algorithms)
    pub fn to_adjacency_matrix(&self) -> (Vec<String>, Vec<Vec<f64>>) {
        // Collect all node IDs
        let mut node_ids: Vec<String> = self.nodes.iter().map(|n| self.node_id(n)).collect();
        node_ids.sort();
        node_ids.dedup();

        let n = node_ids.len();
        let id_to_idx: HashMap<&str, usize> = node_ids
            .iter()
            .enumerate()
            .map(|(i, id)| (id.as_str(), i))
            .collect();

        let mut matrix = vec![vec![0.0f64; n]; n];

        for edge in &self.edges {
            let (source, target, weight) = match edge {
                HarnessEdge::DataFlow {
                    source,
                    target,
                    frequency_hz,
                    ..
                } => (
                    source.as_str(),
                    target.as_str(),
                    frequency_hz.log2().max(0.1),
                ),
                HarnessEdge::ControlFlow { source, target, .. } => {
                    (source.as_str(), target.as_str(), 1.0)
                }
                HarnessEdge::Dependency {
                    source,
                    target,
                    critical,
                    ..
                } => (
                    source.as_str(),
                    target.as_str(),
                    if *critical { 2.0 } else { 1.0 },
                ),
                HarnessEdge::Feedback { source, target, .. } => {
                    (source.as_str(), target.as_str(), 0.5)
                }
                HarnessEdge::Routing {
                    router,
                    target,
                    probability,
                    ..
                } => (router.as_str(), target.as_str(), *probability),
            };

            if let (Some(&si), Some(&ti)) = (id_to_idx.get(source), id_to_idx.get(target)) {
                matrix[si][ti] = weight;
            }
        }

        (node_ids, matrix)
    }

    /// Export as JSON for visualization
    pub fn to_json(&self) -> serde_json::Value {
        serde_json::json!({
            "nodes": self.nodes.iter().map(|n| {
                serde_json::json!({
                    "id": self.node_id(n),
                    "type": self.node_type_name(n),
                    "label": self.node_label(n),
                })
            }).collect::<Vec<_>>(),
            "edges": self.edges.iter().map(|e| {
                let (source, target, relationship) = match e {
                    HarnessEdge::DataFlow { source, target, .. } => (source, target, "data_flow"),
                    HarnessEdge::ControlFlow { source, target, .. } => (source, target, "control_flow"),
                    HarnessEdge::Dependency { source, target, .. } => (source, target, "dependency"),
                    HarnessEdge::Feedback { source, target, .. } => (source, target, "feedback"),
                    HarnessEdge::Routing { router, target, .. } => (router, target, "routing"),
                };
                serde_json::json!({
                    "source": source,
                    "target": target,
                    "type": relationship,
                })
            }).collect::<Vec<_>>(),
            "metadata": self.metadata,
        })
    }

    fn node_id(&self, node: &HarnessNode) -> String {
        match node {
            HarnessNode::Tool(n) => n.id.clone(),
            HarnessNode::IntentRouter(n) => n.id.clone(),
            HarnessNode::Council(n) => n.id.clone(),
            HarnessNode::Loop(n) => n.id.clone(),
            HarnessNode::DataStore(n) => n.id.clone(),
            HarnessNode::ExternalService(n) => n.id.clone(),
            HarnessNode::ModelProvider(n) => n.id.clone(),
        }
    }

    fn node_type_name(&self, node: &HarnessNode) -> String {
        match node {
            HarnessNode::Tool(_) => "tool".to_string(),
            HarnessNode::IntentRouter(_) => "intent_router".to_string(),
            HarnessNode::Council(_) => "council".to_string(),
            HarnessNode::Loop(_) => "loop".to_string(),
            HarnessNode::DataStore(_) => "data_store".to_string(),
            HarnessNode::ExternalService(_) => "external_service".to_string(),
            HarnessNode::ModelProvider(_) => "model_provider".to_string(),
        }
    }

    fn node_label(&self, node: &HarnessNode) -> String {
        match node {
            HarnessNode::Tool(n) => n.name.clone(),
            HarnessNode::IntentRouter(_) => "Intent Router".to_string(),
            HarnessNode::Council(n) => n.council_type.clone(),
            HarnessNode::Loop(n) => format!("OODA ({})", n.loop_type),
            HarnessNode::DataStore(n) => format!("{} ({})", n.purpose, n.store_type),
            HarnessNode::ExternalService(n) => n.service_name.clone(),
            HarnessNode::ModelProvider(n) => format!("{} ({})", n.provider_name, n.model_name),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_harness_graph_builds() {
        let graph = HarnessGraph::build_from_config();
        assert!(
            graph.nodes.len() > 20,
            "Expected >20 nodes, got {}",
            graph.nodes.len()
        );
        assert!(
            graph.edges.len() > 10,
            "Expected >10 edges, got {}",
            graph.edges.len()
        );
    }

    #[test]
    fn test_adjacency_list_export() {
        let graph = HarnessGraph::build_from_config();
        let adj = graph.to_adjacency_list();
        // Intent router should have outgoing edges
        assert!(adj.contains_key("intent-router-main"));
    }

    #[test]
    fn test_adjacency_matrix_export() {
        let graph = HarnessGraph::build_from_config();
        let (ids, matrix) = graph.to_adjacency_matrix();
        assert_eq!(ids.len(), matrix.len());
        assert_eq!(ids.len(), matrix[0].len());
    }

    #[test]
    fn test_json_export() {
        let graph = HarnessGraph::build_from_config();
        let json = graph.to_json();
        assert!(json["nodes"].as_array().unwrap().len() > 20);
        assert!(json["edges"].as_array().unwrap().len() > 10);
    }

    #[test]
    fn test_metadata_populated() {
        let graph = HarnessGraph::build_from_config();
        assert_eq!(graph.metadata.version, "1.0.0");
        assert!(graph.metadata.total_nodes > 20);
        assert!(graph.metadata.graph_density > 0.0);
        assert!(!graph.metadata.critical_paths.is_empty());
    }
}
