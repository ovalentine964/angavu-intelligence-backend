// =============================================================================
// Angavu Intelligence — Knowledge Graph as AGI Memory
// Long-term memory system for future AGI integration
//
// Three memory types:
// 1. Episodic Memory: What happened (events, experiences, interactions)
// 2. Semantic Memory: What's known (facts, relationships, domain knowledge)
// 3. Procedural Memory: How to do things (workflows, strategies, skills)
//
// Design: Graph-based representation enables future AGI to reason over
// knowledge using graph algorithms (path finding, community detection,
// influence propagation).
// =============================================================================

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use super::{GraphEdge, GraphNode, GraphTraversal, NodeStatus};

// ── Memory Node Types ────────────────────────────────────────────────────────

/// All memory nodes in the knowledge graph
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MemoryNode {
    Episodic(EpisodicMemory),
    Semantic(SemanticMemory),
    Procedural(ProceduralMemory),
}

/// Episodic Memory: What happened
/// Records specific events, experiences, and interactions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodicMemory {
    pub id: Uuid,
    pub event_type: EpisodicEventType,
    pub description: String,
    pub timestamp: DateTime<Utc>,
    pub participants: Vec<String>,
    pub location: Option<String>,
    pub emotional_valence: Option<f64>, // -1.0 (negative) to 1.0 (positive)
    pub importance: f64,                // 0.0 to 1.0
    pub context: serde_json::Value,
    pub outcome: Option<String>,
    pub embedding: Option<Vec<f64>>,
    pub status: NodeStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum EpisodicEventType {
    Transaction,
    Conversation,
    Decision,
    Observation,
    Milestone,
    Failure,
    Learning,
    SocialInteraction,
    MarketEvent,
    Custom(String),
}

/// Semantic Memory: What's known
/// Facts, relationships, domain knowledge, and beliefs
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticMemory {
    pub id: Uuid,
    pub concept: String,
    pub category: SemanticCategory,
    pub statement: String,
    pub confidence: f64, // 0.0 to 1.0
    pub source: String,  // where this knowledge came from
    pub last_verified: Option<DateTime<Utc>>,
    pub contradiction_count: u32,
    pub embedding: Option<Vec<f64>>,
    pub status: NodeStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SemanticCategory {
    DomainKnowledge, // "Mama mbogas lose 15-30% to spoilage"
    UserPreference,  // "User prefers morning deliveries"
    MarketFact,      // "Tomato prices peak in December"
    SocialFact,      // "User is treasurer of Chama A"
    BusinessRule,    // "Never approve loans > 3x monthly revenue"
    GeographicFact,  // "Gikomba market is cheapest for vegetables"
    TemporalPattern, // "Demand peaks on Fridays"
    CausalRelation,  // "Rain → higher vegetable prices"
    Custom(String),
}

/// Procedural Memory: How to do things
/// Workflows, strategies, skills, and learned procedures
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProceduralMemory {
    pub id: Uuid,
    pub skill_name: String,
    pub description: String,
    pub steps: Vec<ProcedureStep>,
    pub preconditions: Vec<String>,
    pub postconditions: Vec<String>,
    pub success_rate: f64,
    pub average_duration_ms: Option<u64>,
    pub applicable_contexts: Vec<String>,
    pub learned_from: String, // "explicit_instruction", "observation", "trial_and_error"
    pub embedding: Option<Vec<f64>>,
    pub status: NodeStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcedureStep {
    pub step_number: u32,
    pub action: String,
    pub tool_required: Option<String>,
    pub expected_outcome: String,
    pub failure_mode: Option<String>,
    pub retry_strategy: Option<String>,
}

// ── Memory Edge Types ────────────────────────────────────────────────────────

/// Relationships between memory nodes
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MemoryEdge {
    /// Temporal sequence: A happened before B
    TemporalSequence {
        source_id: Uuid,
        target_id: Uuid,
        time_gap_hours: f64,
    },
    /// Causal: A caused B
    Causal {
        source_id: Uuid,
        target_id: Uuid,
        confidence: f64,
    },
    /// Semantic similarity: A is related to B
    SemanticSimilarity {
        source_id: Uuid,
        target_id: Uuid,
        similarity: f64,
    },
    /// Contextual: A provides context for B
    Contextual {
        source_id: Uuid,
        target_id: Uuid,
        context_type: String,
    },
    /// Contradicts: A contradicts B
    Contradicts {
        source_id: Uuid,
        target_id: Uuid,
        resolution: Option<String>,
    },
    /// Supports: A supports/confirms B
    Supports {
        source_id: Uuid,
        target_id: Uuid,
        strength: f64,
    },
    /// Part-of: A is part of procedure B
    PartOf {
        source_id: Uuid,
        target_id: Uuid,
        step_index: u32,
    },
    /// Involves: Episode A involves entity/concept B
    Involves {
        source_id: Uuid,
        target_id: Uuid,
        role: String,
    },
}

// ── Graph Node/Edge Implementations ──────────────────────────────────────────

impl GraphNode for MemoryNode {
    fn id(&self) -> Uuid {
        match self {
            MemoryNode::Episodic(m) => m.id,
            MemoryNode::Semantic(m) => m.id,
            MemoryNode::Procedural(m) => m.id,
        }
    }

    fn label(&self) -> String {
        match self {
            MemoryNode::Episodic(m) => format!("Episodic: {}", m.description),
            MemoryNode::Semantic(m) => format!("Semantic: {}", m.concept),
            MemoryNode::Procedural(m) => format!("Procedural: {}", m.skill_name),
        }
    }

    fn node_type(&self) -> String {
        match self {
            MemoryNode::Episodic(_) => "episodic".to_string(),
            MemoryNode::Semantic(_) => "semantic".to_string(),
            MemoryNode::Procedural(_) => "procedural".to_string(),
        }
    }

    fn status(&self) -> NodeStatus {
        match self {
            MemoryNode::Episodic(m) => m.status,
            MemoryNode::Semantic(m) => m.status,
            MemoryNode::Procedural(m) => m.status,
        }
    }

    fn embedding(&self) -> Option<&[f64]> {
        match self {
            MemoryNode::Episodic(m) => m.embedding.as_deref(),
            MemoryNode::Semantic(m) => m.embedding.as_deref(),
            MemoryNode::Procedural(m) => m.embedding.as_deref(),
        }
    }
}

impl GraphEdge for MemoryEdge {
    fn source_id(&self) -> Uuid {
        match self {
            MemoryEdge::TemporalSequence { source_id, .. }
            | MemoryEdge::Causal { source_id, .. }
            | MemoryEdge::SemanticSimilarity { source_id, .. }
            | MemoryEdge::Contextual { source_id, .. }
            | MemoryEdge::Contradicts { source_id, .. }
            | MemoryEdge::Supports { source_id, .. }
            | MemoryEdge::PartOf { source_id, .. }
            | MemoryEdge::Involves { source_id, .. } => *source_id,
        }
    }

    fn target_id(&self) -> Uuid {
        match self {
            MemoryEdge::TemporalSequence { target_id, .. }
            | MemoryEdge::Causal { target_id, .. }
            | MemoryEdge::SemanticSimilarity { target_id, .. }
            | MemoryEdge::Contextual { target_id, .. }
            | MemoryEdge::Contradicts { target_id, .. }
            | MemoryEdge::Supports { target_id, .. }
            | MemoryEdge::PartOf { target_id, .. }
            | MemoryEdge::Involves { target_id, .. } => *target_id,
        }
    }

    fn relationship(&self) -> String {
        match self {
            MemoryEdge::TemporalSequence { .. } => "temporal_sequence".to_string(),
            MemoryEdge::Causal { .. } => "causal".to_string(),
            MemoryEdge::SemanticSimilarity { .. } => "semantic_similarity".to_string(),
            MemoryEdge::Contextual { .. } => "contextual".to_string(),
            MemoryEdge::Contradicts { .. } => "contradicts".to_string(),
            MemoryEdge::Supports { .. } => "supports".to_string(),
            MemoryEdge::PartOf { .. } => "part_of".to_string(),
            MemoryEdge::Involves { .. } => "involves".to_string(),
        }
    }

    fn weight(&self) -> f64 {
        match self {
            MemoryEdge::TemporalSequence { time_gap_hours, .. } => {
                1.0 / (1.0 + time_gap_hours / 24.0) // Decay with time
            }
            MemoryEdge::Causal { confidence, .. } => *confidence,
            MemoryEdge::SemanticSimilarity { similarity, .. } => *similarity,
            MemoryEdge::Contextual { .. } => 0.5,
            MemoryEdge::Contradicts { .. } => -1.0, // Negative weight for contradictions
            MemoryEdge::Supports { strength, .. } => *strength,
            MemoryEdge::PartOf { .. } => 1.0,
            MemoryEdge::Involves { .. } => 0.7,
        }
    }
}

// ── Knowledge Graph ──────────────────────────────────────────────────────────

/// In-memory knowledge graph serving as AGI long-term memory
pub struct KnowledgeGraph {
    nodes: HashMap<Uuid, MemoryNode>,
    edges: Vec<MemoryEdge>,
    /// Index: concept → node IDs (for fast semantic lookup)
    concept_index: HashMap<String, Vec<Uuid>>,
    /// Index: entity → node IDs (for fast entity lookup)
    entity_index: HashMap<String, Vec<Uuid>>,
    /// Statistics
    stats: GraphStats,
}

#[derive(Debug, Default, Serialize)]
pub struct GraphStats {
    pub total_nodes: u64,
    pub episodic_count: u64,
    pub semantic_count: u64,
    pub procedural_count: u64,
    pub total_edges: u64,
    pub avg_connections_per_node: f64,
}

impl KnowledgeGraph {
    pub fn new() -> Self {
        Self {
            nodes: HashMap::new(),
            edges: Vec::new(),
            concept_index: HashMap::new(),
            entity_index: HashMap::new(),
            stats: GraphStats::default(),
        }
    }

    /// Add an episodic memory (what happened)
    pub fn add_episodic(&mut self, memory: EpisodicMemory) -> Uuid {
        let id = memory.id;
        let participants = memory.participants.clone();
        let description = memory.description.clone();

        self.nodes.insert(id, MemoryNode::Episodic(memory));
        self.stats.total_nodes += 1;
        self.stats.episodic_count += 1;

        // Index by participants
        for participant in &participants {
            self.entity_index
                .entry(participant.clone())
                .or_default()
                .push(id);
        }

        // Index by keywords in description
        for word in description.split_whitespace().take(5) {
            let word_lower = word.to_lowercase();
            if word_lower.len() > 3 {
                self.concept_index.entry(word_lower).or_default().push(id);
            }
        }

        id
    }

    /// Add a semantic memory (what's known)
    pub fn add_semantic(&mut self, memory: SemanticMemory) -> Uuid {
        let id = memory.id;
        let concept = memory.concept.clone();

        self.nodes.insert(id, MemoryNode::Semantic(memory));
        self.stats.total_nodes += 1;
        self.stats.semantic_count += 1;

        // Index by concept
        self.concept_index
            .entry(concept.to_lowercase())
            .or_default()
            .push(id);

        id
    }

    /// Add a procedural memory (how to do things)
    pub fn add_procedural(&mut self, memory: ProceduralMemory) -> Uuid {
        let id = memory.id;
        let skill_name = memory.skill_name.clone();

        self.nodes.insert(id, MemoryNode::Procedural(memory));
        self.stats.total_nodes += 1;
        self.stats.procedural_count += 1;

        self.concept_index
            .entry(skill_name.to_lowercase())
            .or_default()
            .push(id);

        id
    }

    /// Add an edge between memory nodes
    pub fn add_edge(&mut self, edge: MemoryEdge) {
        self.edges.push(edge);
        self.stats.total_edges += 1;
        if self.stats.total_nodes > 0 {
            self.stats.avg_connections_per_node =
                self.stats.total_edges as f64 / self.stats.total_nodes as f64;
        }
    }

    /// Query: Find all episodic memories involving a participant
    pub fn episodic_by_participant(&self, participant: &str) -> Vec<&EpisodicMemory> {
        self.entity_index
            .get(participant)
            .map(|ids| {
                ids.iter()
                    .filter_map(|id| match self.nodes.get(id) {
                        Some(MemoryNode::Episodic(m)) => Some(m),
                        _ => None,
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Query: Find semantic knowledge about a concept
    pub fn semantic_by_concept(&self, concept: &str) -> Vec<&SemanticMemory> {
        self.concept_index
            .get(&concept.to_lowercase())
            .map(|ids| {
                ids.iter()
                    .filter_map(|id| match self.nodes.get(id) {
                        Some(MemoryNode::Semantic(m)) => Some(m),
                        _ => None,
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Query: Find procedures for a skill
    pub fn procedural_by_skill(&self, skill: &str) -> Vec<&ProceduralMemory> {
        self.concept_index
            .get(&skill.to_lowercase())
            .map(|ids| {
                ids.iter()
                    .filter_map(|id| match self.nodes.get(id) {
                        Some(MemoryNode::Procedural(m)) => Some(m),
                        _ => None,
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Query: Find all memories in a time range
    pub fn episodic_in_range(
        &self,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
    ) -> Vec<&EpisodicMemory> {
        self.nodes
            .values()
            .filter_map(|node| match node {
                MemoryNode::Episodic(m) if m.timestamp >= start && m.timestamp <= end => Some(m),
                _ => None,
            })
            .collect()
    }

    /// Query: Find causal chains (what caused what)
    pub fn causal_chains_from(&self, event_id: Uuid) -> Vec<(&MemoryEdge, &MemoryNode)> {
        self.edges
            .iter()
            .filter_map(|edge| match edge {
                MemoryEdge::Causal { source_id, .. } if *source_id == event_id => {
                    let target = self.nodes.get(&edge.target_id())?;
                    Some((edge, target))
                }
                _ => None,
            })
            .collect()
    }

    /// Query: Find contradictions in knowledge
    pub fn find_contradictions(&self) -> Vec<(&SemanticMemory, &SemanticMemory, &MemoryEdge)> {
        self.edges
            .iter()
            .filter_map(|edge| match edge {
                MemoryEdge::Contradicts {
                    source_id,
                    target_id,
                    ..
                } => {
                    let a = match self.nodes.get(source_id)? {
                        MemoryNode::Semantic(m) => m,
                        _ => return None,
                    };
                    let b = match self.nodes.get(target_id)? {
                        MemoryNode::Semantic(m) => m,
                        _ => return None,
                    };
                    Some((a, b, edge))
                }
                _ => None,
            })
            .collect()
    }

    /// Get graph statistics
    pub fn stats(&self) -> &GraphStats {
        &self.stats
    }

    /// Export the graph as adjacency list (for visualization/analysis)
    pub fn export_adjacency_list(&self) -> serde_json::Value {
        let nodes: Vec<serde_json::Value> = self
            .nodes
            .values()
            .map(|n| {
                serde_json::json!({
                    "id": n.id().to_string(),
                    "label": n.label(),
                    "type": n.node_type(),
                })
            })
            .collect();

        let edges: Vec<serde_json::Value> = self
            .edges
            .iter()
            .map(|e| {
                serde_json::json!({
                    "source": e.source_id().to_string(),
                    "target": e.target_id().to_string(),
                    "relationship": e.relationship(),
                    "weight": e.weight(),
                })
            })
            .collect();

        serde_json::json!({
            "nodes": nodes,
            "edges": edges,
            "stats": self.stats,
        })
    }

    /// Get all nodes
    pub fn nodes(&self) -> &HashMap<Uuid, MemoryNode> {
        &self.nodes
    }

    /// Get all edges
    pub fn edges(&self) -> &[MemoryEdge] {
        &self.edges
    }

    /// Get mutable access to nodes (for confidence decay)
    pub fn nodes_mut(&mut self) -> &mut HashMap<Uuid, MemoryNode> {
        &mut self.nodes
    }

    /// Apply confidence decay to all semantic and procedural memories.
    /// Prevents confidence inflation by reducing confidence of entries
    /// that haven't been reinforced recently.
    ///
    /// - `half_life_days`: confidence halves every N days since last update
    /// - `min_confidence`: floor value to prevent total erasure
    pub fn apply_confidence_decay(&mut self, half_life_days: f64, min_confidence: f64) -> usize {
        let now = Utc::now();
        let mut decayed = 0;

        for node in self.nodes.values_mut() {
            match node {
                MemoryNode::Semantic(ref mut m) => {
                    if let Some(last_verified) = m.last_verified {
                        let days = (now - last_verified).num_days() as f64;
                        if days > 0.0 {
                            let decay_factor = 0.5_f64.powf(days / half_life_days);
                            let new_confidence = (m.confidence * decay_factor).max(min_confidence);
                            if new_confidence < m.confidence {
                                m.confidence = new_confidence;
                                decayed += 1;
                            }
                        }
                    }
                }
                MemoryNode::Procedural(ref mut m) => {
                    // Decay procedural memory success_rate based on staleness
                    // Use average_duration_ms as a proxy for last activity
                    // (in production, add a last_used field)
                    if m.success_rate > min_confidence {
                        // Conservative decay: 2% per day of inactivity
                        // Since we don't have last_used, apply a small fixed decay
                        let new_rate = (m.success_rate * 0.98).max(min_confidence);
                        if new_rate < m.success_rate {
                            m.success_rate = new_rate;
                            decayed += 1;
                        }
                    }
                }
                MemoryNode::Episodic(_) => {
                    // Episodic memories don't decay — they're historical records
                }
            }
        }

        // Update stats
        self.stats.semantic_count = self
            .nodes
            .values()
            .filter(|n| matches!(n, MemoryNode::Semantic(_)))
            .count() as u64;

        decayed
    }

    /// Prune semantic memories that have decayed below a confidence threshold.
    /// Returns the number of pruned nodes.
    pub fn prune_low_confidence(&mut self, threshold: f64) -> usize {
        let pruned_ids: Vec<Uuid> = self
            .nodes
            .iter()
            .filter_map(|(id, node)| match node {
                MemoryNode::Semantic(m) if m.confidence < threshold => Some(*id),
                _ => None,
            })
            .collect();

        let count = pruned_ids.len();
        for id in &pruned_ids {
            self.nodes.remove(id);
            // Remove from indexes
            self.concept_index
                .values_mut()
                .for_each(|ids| ids.retain(|i| i != id));
            self.entity_index
                .values_mut()
                .for_each(|ids| ids.retain(|i| i != id));
        }
        // Remove edges involving pruned nodes
        self.edges.retain(|e| {
            !pruned_ids.contains(&e.source_id()) && !pruned_ids.contains(&e.target_id())
        });

        self.stats.total_nodes = self.nodes.len() as u64;
        self.stats.total_edges = self.edges.len() as u64;
        count
    }
}

// ── Memory Consolidation ─────────────────────────────────────────────────────

/// Consolidates episodic memories into semantic knowledge
/// (Similar to how human sleep consolidates experiences into knowledge)
pub struct MemoryConsolidator;

impl MemoryConsolidator {
    /// Extract semantic knowledge from repeated episodic patterns
    pub fn consolidate_episodes(
        episodes: &[EpisodicMemory],
        min_occurrences: usize,
    ) -> Vec<SemanticMemory> {
        let mut pattern_counts: HashMap<String, (usize, Vec<String>)> = HashMap::new();

        for ep in episodes {
            // Extract pattern from event type + outcome
            let pattern = format!(
                "{:?} → {}",
                ep.event_type,
                ep.outcome.as_deref().unwrap_or("unknown")
            );
            let entry = pattern_counts.entry(pattern).or_insert((0, Vec::new()));
            entry.0 += 1;
            entry.1.push(ep.description.clone());
        }

        pattern_counts
            .into_iter()
            .filter(|(_, (count, _))| *count >= min_occurrences)
            .map(|(pattern, (count, examples))| SemanticMemory {
                id: Uuid::new_v4(),
                concept: pattern.clone(),
                category: SemanticCategory::TemporalPattern,
                statement: format!(
                    "Pattern observed {} times: {}. Examples: {}",
                    count,
                    pattern,
                    examples
                        .iter()
                        .take(3)
                        .cloned()
                        .collect::<Vec<_>>()
                        .join("; ")
                ),
                confidence: (count as f64 / (count as f64 + 10.0)).min(0.95),
                source: "consolidation".to_string(),
                last_verified: Some(Utc::now()),
                contradiction_count: 0,
                embedding: None,
                status: NodeStatus::Completed,
            })
            .collect()
    }

    /// Consolidate with domain-specific category inference.
    /// Examines the content of episodes to assign better semantic categories.
    pub fn consolidate_with_categories(
        episodes: &[EpisodicMemory],
        min_occurrences: usize,
    ) -> Vec<SemanticMemory> {
        let mut by_type: HashMap<String, Vec<&EpisodicMemory>> = HashMap::new();
        for ep in episodes {
            by_type
                .entry(format!("{:?}", ep.event_type))
                .or_default()
                .push(ep);
        }

        let mut results = Vec::new();

        // Consolidate transaction patterns
        if let Some(tx_episodes) = by_type.get("Transaction") {
            let mut outcome_counts: HashMap<String, usize> = HashMap::new();
            for ep in *tx_episodes {
                let outcome = ep.outcome.as_deref().unwrap_or("unknown").to_string();
                *outcome_counts.entry(outcome).or_insert(0) += 1;
            }
            for (outcome, count) in outcome_counts {
                if count >= min_occurrences {
                    results.push(SemanticMemory {
                        id: Uuid::new_v4(),
                        concept: format!("transaction_outcome_{}", outcome.to_lowercase().replace(' ', "_")),
                        category: SemanticCategory::DomainKnowledge,
                        statement: format!(
                            "Transaction pattern: {} occurred {} times out of {} total transactions",
                            outcome, count, tx_episodes.len()
                        ),
                        confidence: (count as f64 / (count as f64 + 10.0)).min(0.95),
                        source: "consolidation".to_string(),
                        last_verified: Some(Utc::now()),
                        contradiction_count: 0,
                        embedding: None,
                        status: NodeStatus::Completed,
                    });
                }
            }
        }

        // Consolidate learning events
        if let Some(learn_episodes) = by_type.get("Learning") {
            if learn_episodes.len() >= min_occurrences {
                let descriptions: Vec<&str> = learn_episodes
                    .iter()
                    .map(|e| e.description.as_str())
                    .collect();
                results.push(SemanticMemory {
                    id: Uuid::new_v4(),
                    concept: "learning_pattern".to_string(),
                    category: SemanticCategory::CausalRelation,
                    statement: format!(
                        "Learning pattern from {} events: {}",
                        learn_episodes.len(),
                        descriptions
                            .iter()
                            .take(3)
                            .cloned()
                            .collect::<Vec<_>>()
                            .join("; ")
                    ),
                    confidence: (learn_episodes.len() as f64
                        / (learn_episodes.len() as f64 + 10.0))
                        .min(0.95),
                    source: "consolidation".to_string(),
                    last_verified: Some(Utc::now()),
                    contradiction_count: 0,
                    embedding: None,
                    status: NodeStatus::Completed,
                });
            }
        }

        // Fall back to generic consolidation for remaining types
        results.extend(Self::consolidate_episodes(episodes, min_occurrences));
        results
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_knowledge_graph_basic() {
        let mut kg = KnowledgeGraph::new();

        let ep = EpisodicMemory {
            id: Uuid::new_v4(),
            event_type: EpisodicEventType::Transaction,
            description: "Sold 10kg tomatoes at Gikomba".to_string(),
            timestamp: Utc::now(),
            participants: vec!["Grace".to_string()],
            location: Some("Gikomba".to_string()),
            emotional_valence: Some(0.7),
            importance: 0.5,
            context: serde_json::json!({}),
            outcome: Some("Profit KES 500".to_string()),
            embedding: None,
            status: NodeStatus::Completed,
        };

        let id = kg.add_episodic(ep);
        assert_eq!(kg.stats().episodic_count, 1);

        let grace_memories = kg.episodic_by_participant("Grace");
        assert_eq!(grace_memories.len(), 1);
    }

    #[test]
    fn test_semantic_query() {
        let mut kg = KnowledgeGraph::new();

        let sem = SemanticMemory {
            id: Uuid::new_v4(),
            concept: "tomato_spoilage".to_string(),
            category: SemanticCategory::DomainKnowledge,
            statement: "Tomatoes spoil in 3-5 days without cold storage".to_string(),
            confidence: 0.95,
            source: "observation".to_string(),
            last_verified: Some(Utc::now()),
            contradiction_count: 0,
            embedding: None,
            status: NodeStatus::Completed,
        };

        kg.add_semantic(sem);

        let results = kg.semantic_by_concept("tomato_spoilage");
        assert_eq!(results.len(), 1);
        assert!(results[0].statement.contains("spoil"));
    }

    #[test]
    fn test_procedural_memory() {
        let mut kg = KnowledgeGraph::new();

        let proc = ProceduralMemory {
            id: Uuid::new_v4(),
            skill_name: "record_sale".to_string(),
            description: "How to record a sale transaction".to_string(),
            steps: vec![
                ProcedureStep {
                    step_number: 1,
                    action: "Ask for item and quantity".to_string(),
                    tool_required: Some("VoiceInput".to_string()),
                    expected_outcome: "Item name and qty captured".to_string(),
                    failure_mode: Some("Unclear audio".to_string()),
                    retry_strategy: Some("Ask to repeat".to_string()),
                },
                ProcedureStep {
                    step_number: 2,
                    action: "Record price".to_string(),
                    tool_required: Some("Calculator".to_string()),
                    expected_outcome: "Total calculated".to_string(),
                    failure_mode: None,
                    retry_strategy: None,
                },
            ],
            preconditions: vec!["User has items to sell".to_string()],
            postconditions: vec!["Sale recorded in system".to_string()],
            success_rate: 0.92,
            average_duration_ms: Some(15000),
            applicable_contexts: vec!["market".to_string(), "shop".to_string()],
            learned_from: "explicit_instruction".to_string(),
            embedding: None,
            status: NodeStatus::Completed,
        };

        kg.add_procedural(proc);
        assert_eq!(kg.stats().procedural_count, 1);

        let results = kg.procedural_by_skill("record_sale");
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].steps.len(), 2);
    }

    #[test]
    fn test_adjacency_list_export() {
        let mut kg = KnowledgeGraph::new();

        let id1 = kg.add_episodic(EpisodicMemory {
            id: Uuid::new_v4(),
            event_type: EpisodicEventType::Transaction,
            description: "Test event".to_string(),
            timestamp: Utc::now(),
            participants: vec![],
            location: None,
            emotional_valence: None,
            importance: 0.5,
            context: serde_json::json!({}),
            outcome: None,
            embedding: None,
            status: NodeStatus::Completed,
        });

        let export = kg.export_adjacency_list();
        assert!(export["nodes"].as_array().unwrap().len() == 1);
    }
}
