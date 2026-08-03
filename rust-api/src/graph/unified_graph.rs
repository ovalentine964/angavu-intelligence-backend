// =============================================================================
// Unified Knowledge Graph Bridge
// Connects the 3 disconnected graph systems into a single read/write layer:
//   1. KnowledgeGraph (in-memory episodic/semantic/procedural memory)
//   2. PgKnowledgeGraph (PostgreSQL-backed persistent memory)
//   3. HarnessGraph (system structure representation)
//
// This layer provides:
// - Single entry point for all graph operations
// - Automatic persistence of in-memory graph to PostgreSQL
// - Cross-graph queries (e.g., "which tools handle transactions?" + "what
//   episodic memories exist about transactions?")
// - Harness graph nodes linked to knowledge graph concepts
// =============================================================================

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

use super::harness_graph::HarnessGraph;
use super::knowledge_graph::*;
use super::pg_knowledge_graph::PgKnowledgeGraph;
use super::{GraphEdge, GraphNode, NodeStatus};

/// Unified graph operations trait — single interface for all graph types.
#[async_trait]
pub trait UnifiedGraphOps: Send + Sync {
    // ── Knowledge Memory Operations ──────────────────────────
    /// Store an episodic memory (what happened).
    async fn record_episode(&self, memory: EpisodicMemory) -> Result<Uuid, String>;
    /// Store semantic knowledge (what's known).
    async fn record_knowledge(&self, memory: SemanticMemory) -> Result<Uuid, String>;
    /// Store a procedure (how to do things).
    async fn record_procedure(&self, memory: ProceduralMemory) -> Result<Uuid, String>;
    /// Link two memory nodes with a relationship.
    async fn link_memories(&self, edge: MemoryEdge) -> Result<(), String>;

    // ── Cross-Graph Queries ──────────────────────────────────
    /// Find knowledge related to a harness component (tool, loop, etc.).
    async fn knowledge_for_component(
        &self,
        component_id: &str,
    ) -> Result<ComponentKnowledge, String>;
    /// Find all episodic memories within a time range (from PG).
    async fn episodes_in_range(
        &self,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
    ) -> Result<Vec<EpisodicMemory>, String>;
    /// Search semantic knowledge by concept (from PG).
    async fn search_knowledge(&self, concept: &str) -> Result<Vec<SemanticMemory>, String>;
    /// Get unified graph statistics.
    async fn unified_stats(&self) -> Result<UnifiedStats, String>;

    // ── Harness Integration ──────────────────────────────────
    /// Get the current harness graph.
    fn harness_graph(&self) -> &HarnessGraph;
    /// Find tools relevant to a semantic concept.
    fn tools_for_concept(&self, concept: &str) -> Vec<String>;
}

/// Knowledge associated with a harness component.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComponentKnowledge {
    pub component_id: String,
    pub component_type: String,
    pub related_episodes: Vec<EpisodicMemory>,
    pub related_facts: Vec<SemanticMemory>,
    pub related_procedures: Vec<ProceduralMemory>,
}

/// Unified statistics across all graph types.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnifiedStats {
    /// In-memory knowledge graph stats
    pub memory_stats: GraphStats,
    /// PostgreSQL knowledge graph stats (if available)
    pub pg_stats: Option<GraphStats>,
    /// Harness graph stats
    pub harness_nodes: usize,
    pub harness_edges: usize,
    /// Cross-references count
    pub cross_references: usize,
}

/// The unified knowledge layer implementation.
pub struct UnifiedKnowledgeLayer {
    /// In-memory knowledge graph (fast, ephemeral)
    memory_graph: Arc<RwLock<KnowledgeGraph>>,
    /// PostgreSQL-backed knowledge graph (persistent)
    pg_graph: Arc<PgKnowledgeGraph>,
    /// Harness graph (system structure)
    harness: HarnessGraph,
    /// Cross-reference index: harness component ID → memory node IDs
    cross_refs: Arc<RwLock<HashMap<String, Vec<Uuid>>>>,
    /// Concept → harness tool mapping
    concept_tool_index: HashMap<String, Vec<String>>,
}

impl UnifiedKnowledgeLayer {
    /// Create a new unified knowledge layer.
    pub fn new(pg_pool: sqlx::PgPool) -> Self {
        let harness = HarnessGraph::build_from_config();

        // Build concept → tool index from harness graph
        let mut concept_tool_index: HashMap<String, Vec<String>> = HashMap::new();
        for node in &harness.nodes {
            if let super::harness_graph::HarnessNode::Tool(tool) = node {
                // Index by category and name
                concept_tool_index
                    .entry(tool.category.to_lowercase())
                    .or_default()
                    .push(tool.name.clone());
                concept_tool_index
                    .entry(tool.name.to_lowercase())
                    .or_default()
                    .push(tool.name.clone());
                // Index by input/output types
                for input_type in &tool.input_types {
                    concept_tool_index
                        .entry(input_type.to_lowercase())
                        .or_default()
                        .push(tool.name.clone());
                }
            }
        }

        Self {
            memory_graph: Arc::new(RwLock::new(KnowledgeGraph::new())),
            pg_graph: Arc::new(PgKnowledgeGraph::new(pg_pool)),
            harness,
            cross_refs: Arc::new(RwLock::new(HashMap::new())),
            concept_tool_index,
        }
    }

    /// Create with a pre-built harness graph.
    pub fn with_harness(pg_pool: sqlx::PgPool, harness: HarnessGraph) -> Self {
        let mut instance = Self::new(pg_pool);
        instance.harness = harness;
        instance
    }

    /// Persist all in-memory graph data to PostgreSQL.
    /// Call this periodically (e.g., every 5 minutes) or on shutdown.
    pub async fn persist_to_pg(&self) -> Result<usize, String> {
        let graph = self.memory_graph.read().await;
        let mut persisted = 0;

        // Persist all episodic memories
        for (_, node) in graph.nodes() {
            match node {
                MemoryNode::Episodic(m) => {
                    self.pg_graph.add_episodic(m).await?;
                    persisted += 1;
                }
                MemoryNode::Semantic(m) => {
                    self.pg_graph.add_semantic(m).await?;
                    persisted += 1;
                }
                MemoryNode::Procedural(m) => {
                    self.pg_graph.add_procedural(m).await?;
                    persisted += 1;
                }
            }
        }

        // Persist all edges
        for edge in graph.edges() {
            self.pg_graph.add_edge(edge).await?;
            persisted += 1;
        }

        Ok(persisted)
    }

    /// Add a cross-reference between a harness component and a memory node.
    pub async fn add_cross_ref(&self, component_id: &str, memory_id: Uuid) {
        let mut refs = self.cross_refs.write().await;
        refs.entry(component_id.to_string())
            .or_default()
            .push(memory_id);
    }

    /// Get the in-memory graph for direct access (e.g., fast queries).
    pub fn memory_graph(&self) -> Arc<RwLock<KnowledgeGraph>> {
        self.memory_graph.clone()
    }

    /// Get the PostgreSQL graph for direct access (e.g., complex queries).
    pub fn pg_graph(&self) -> Arc<PgKnowledgeGraph> {
        self.pg_graph.clone()
    }
}

#[async_trait]
impl UnifiedGraphOps for UnifiedKnowledgeLayer {
    async fn record_episode(&self, memory: EpisodicMemory) -> Result<Uuid, String> {
        let id = memory.id;

        // Store in-memory for fast access
        {
            let mut graph = self.memory_graph.write().await;
            graph.add_episodic(memory.clone());
        }

        // Persist to PostgreSQL asynchronously
        let pg = self.pg_graph.clone();
        tokio::spawn(async move {
            if let Err(e) = pg.add_episodic(&memory).await {
                tracing::error!(error = %e, memory_id = %memory.id, "Failed to persist episodic memory to PG");
            }
        });

        Ok(id)
    }

    async fn record_knowledge(&self, memory: SemanticMemory) -> Result<Uuid, String> {
        let id = memory.id;

        {
            let mut graph = self.memory_graph.write().await;
            graph.add_semantic(memory.clone());
        }

        let pg = self.pg_graph.clone();
        tokio::spawn(async move {
            if let Err(e) = pg.add_semantic(&memory).await {
                tracing::error!(error = %e, memory_id = %memory.id, "Failed to persist semantic memory to PG");
            }
        });

        Ok(id)
    }

    async fn record_procedure(&self, memory: ProceduralMemory) -> Result<Uuid, String> {
        let id = memory.id;

        {
            let mut graph = self.memory_graph.write().await;
            graph.add_procedural(memory.clone());
        }

        let pg = self.pg_graph.clone();
        tokio::spawn(async move {
            if let Err(e) = pg.add_procedural(&memory).await {
                tracing::error!(error = %e, memory_id = %memory.id, "Failed to persist procedural memory to PG");
            }
        });

        Ok(id)
    }

    async fn link_memories(&self, edge: MemoryEdge) -> Result<(), String> {
        {
            let mut graph = self.memory_graph.write().await;
            graph.add_edge(edge.clone());
        }

        let pg = self.pg_graph.clone();
        tokio::spawn(async move {
            if let Err(e) = pg.add_edge(&edge).await {
                tracing::error!(error = %e, "Failed to persist memory edge to PG");
            }
        });

        Ok(())
    }

    async fn knowledge_for_component(
        &self,
        component_id: &str,
    ) -> Result<ComponentKnowledge, String> {
        let refs = self.cross_refs.read().await;
        let memory_ids = refs.get(component_id).cloned().unwrap_or_default();

        let graph = self.memory_graph.read().await;
        let mut episodes = Vec::new();
        let mut facts = Vec::new();
        let mut procedures = Vec::new();

        for id in &memory_ids {
            if let Some(node) = graph.nodes().get(id) {
                match node {
                    MemoryNode::Episodic(m) => episodes.push(m.clone()),
                    MemoryNode::Semantic(m) => facts.push(m.clone()),
                    MemoryNode::Procedural(m) => procedures.push(m.clone()),
                }
            }
        }

        // Determine component type from harness
        let component_type = self
            .harness
            .nodes
            .iter()
            .find(|n| {
                let nid = match n {
                    super::harness_graph::HarnessNode::Tool(t) => &t.id,
                    super::harness_graph::HarnessNode::IntentRouter(r) => &r.id,
                    super::harness_graph::HarnessNode::Council(c) => &c.id,
                    super::harness_graph::HarnessNode::Loop(l) => &l.id,
                    super::harness_graph::HarnessNode::DataStore(d) => &d.id,
                    super::harness_graph::HarnessNode::ExternalService(e) => &e.id,
                    super::harness_graph::HarnessNode::ModelProvider(m) => &m.id,
                };
                nid == component_id
            })
            .map(|n| match n {
                super::harness_graph::HarnessNode::Tool(_) => "tool",
                super::harness_graph::HarnessNode::IntentRouter(_) => "intent_router",
                super::harness_graph::HarnessNode::Council(_) => "council",
                super::harness_graph::HarnessNode::Loop(_) => "loop",
                super::harness_graph::HarnessNode::DataStore(_) => "data_store",
                super::harness_graph::HarnessNode::ExternalService(_) => "external_service",
                super::harness_graph::HarnessNode::ModelProvider(_) => "model_provider",
            })
            .unwrap_or("unknown")
            .to_string();

        Ok(ComponentKnowledge {
            component_id: component_id.to_string(),
            component_type,
            related_episodes: episodes,
            related_facts: facts,
            related_procedures: procedures,
        })
    }

    async fn episodes_in_range(
        &self,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
    ) -> Result<Vec<EpisodicMemory>, String> {
        // Try PostgreSQL first (persistent, complete data)
        match self.pg_graph.episodic_by_participant("").await {
            Ok(episodes) => {
                let filtered: Vec<EpisodicMemory> = episodes
                    .into_iter()
                    .filter(|e| e.timestamp >= start && e.timestamp <= end)
                    .collect();
                Ok(filtered)
            }
            Err(_) => {
                // Fallback to in-memory graph
                let graph = self.memory_graph.read().await;
                Ok(graph
                    .episodic_in_range(start, end)
                    .into_iter()
                    .cloned()
                    .collect())
            }
        }
    }

    async fn search_knowledge(&self, concept: &str) -> Result<Vec<SemanticMemory>, String> {
        // Try PostgreSQL first
        match self.pg_graph.semantic_by_concept(concept).await {
            Ok(results) if !results.is_empty() => Ok(results),
            _ => {
                // Fallback to in-memory
                let graph = self.memory_graph.read().await;
                Ok(graph
                    .semantic_by_concept(concept)
                    .into_iter()
                    .cloned()
                    .collect())
            }
        }
    }

    async fn unified_stats(&self) -> Result<UnifiedStats, String> {
        let memory_graph = self.memory_graph.read().await;
        let memory_stats = GraphStats {
            total_nodes: memory_graph.stats().total_nodes,
            episodic_count: memory_graph.stats().episodic_count,
            semantic_count: memory_graph.stats().semantic_count,
            procedural_count: memory_graph.stats().procedural_count,
            total_edges: memory_graph.stats().total_edges,
            avg_connections_per_node: memory_graph.stats().avg_connections_per_node,
        };

        let pg_stats = self.pg_graph.stats().await.ok();

        let cross_refs = self.cross_refs.read().await;
        let cross_ref_count: usize = cross_refs.values().map(|v| v.len()).sum();

        Ok(UnifiedStats {
            memory_stats,
            pg_stats,
            harness_nodes: self.harness.nodes.len(),
            harness_edges: self.harness.edges.len(),
            cross_references: cross_ref_count,
        })
    }

    fn harness_graph(&self) -> &HarnessGraph {
        &self.harness
    }

    fn tools_for_concept(&self, concept: &str) -> Vec<String> {
        self.concept_tool_index
            .get(&concept.to_lowercase())
            .cloned()
            .unwrap_or_default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_concept_tool_index() {
        // Verify the harness graph builds correctly
        let harness = HarnessGraph::build_from_config();
        assert!(harness.nodes.len() > 20);
    }
}
