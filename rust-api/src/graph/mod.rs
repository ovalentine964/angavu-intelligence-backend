//! Graph Engineering module — core abstractions for all graph types.

pub mod federated;
pub mod ooda;
pub mod pipeline;

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Core trait for all graph node types.
#[async_trait]
pub trait GraphNode: Send + Sync + Serialize + for<'de> Deserialize<'de> {
    /// Unique identifier for this node.
    fn id(&self) -> Uuid;

    /// Human-readable label.
    fn label(&self) -> String;

    /// Node type discriminator.
    fn node_type(&self) -> String;

    /// Current status of the node.
    fn status(&self) -> NodeStatus;

    /// Embedding vector for similarity search (if available).
    fn embedding(&self) -> Option<&[f64]> {
        None
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum NodeStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Skipped,
}

/// Core trait for graph edges.
#[async_trait]
pub trait GraphEdge: Send + Sync + Serialize + for<'de> Deserialize<'de> {
    fn source_id(&self) -> Uuid;
    fn target_id(&self) -> Uuid;
    fn relationship(&self) -> String;
    fn weight(&self) -> f64;
}

/// Trait for graph traversal operations.
#[async_trait]
pub trait GraphTraversal {
    type Node: GraphNode;
    type Edge: GraphEdge;

    /// Get all neighbors of a node (outgoing edges).
    async fn neighbors(&self, node_id: Uuid) -> anyhow::Result<Vec<(Self::Node, Self::Edge)>>;

    /// Get all nodes within N hops of a node.
    async fn neighborhood(
        &self,
        node_id: Uuid,
        max_hops: u32,
    ) -> anyhow::Result<Vec<Self::Node>>;

    /// Find shortest path between two nodes.
    async fn shortest_path(
        &self,
        from: Uuid,
        to: Uuid,
    ) -> anyhow::Result<Option<Vec<Self::Node>>>;

    /// Get nodes similar to a given node (by embedding).
    async fn similar_nodes(
        &self,
        node_id: Uuid,
        limit: usize,
    ) -> anyhow::Result<Vec<(Self::Node, f64)>>;
}

/// Trait for graph mutation operations.
#[async_trait]
pub trait GraphMutation {
    type Node: GraphNode;
    type Edge: GraphEdge;

    async fn add_node(&mut self, node: Self::Node) -> anyhow::Result<()>;
    async fn add_edge(&mut self, edge: Self::Edge) -> anyhow::Result<()>;
    async fn update_node(&mut self, node: Self::Node) -> anyhow::Result<()>;
    async fn remove_node(&mut self, node_id: Uuid) -> anyhow::Result<()>;
    async fn remove_edge(&mut self, source_id: Uuid, target_id: Uuid, relationship: &str)
        -> anyhow::Result<()>;
}

/// Trait for graph analytics operations.
#[async_trait]
pub trait GraphAnalytics {
    /// PageRank — rank nodes by importance.
    async fn pagerank(&self, iterations: u32, damping: f64)
        -> anyhow::Result<Vec<(Uuid, f64)>>;

    /// Community detection — find clusters of related nodes.
    async fn detect_communities(&self) -> anyhow::Result<Vec<Vec<Uuid>>>;

    /// Centrality measures — find the most connected nodes.
    async fn degree_centrality(&self, top_k: usize) -> anyhow::Result<Vec<(Uuid, usize)>>;
}

/// k-Anonymity enforcement for all graph queries.
pub struct KAnonymityGuard {
    pub min_cohort_size: u32,
}

impl KAnonymityGuard {
    pub fn new(k: u32) -> Self {
        Self {
            min_cohort_size: k.max(10), // Enforce minimum k=10
        }
    }

    /// Check if a query result set satisfies k-anonymity.
    pub fn check(&self, group_size: u32) -> bool {
        group_size >= self.min_cohort_size
    }

    /// Suppress results that don't meet k-anonymity.
    pub fn suppress<T>(&self, groups: Vec<(String, Vec<T>)>) -> Vec<(String, Vec<T>)> {
        groups
            .into_iter()
            .filter(|(_, members)| members.len() as u32 >= self.min_cohort_size)
            .collect()
    }
}
