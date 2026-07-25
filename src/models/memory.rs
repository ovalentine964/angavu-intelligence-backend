use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Memory layer types (5-layer hierarchy)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash, sqlx::Type)]
#[sqlx(type_name = "memory_layer", rename_all = "snake_case")]
pub enum MemoryLayer {
    /// Working memory (current context, < 1 hour)
    Working,
    /// Short-term memory (recent interactions, < 24 hours)
    ShortTerm,
    /// Long-term memory (persistent knowledge)
    LongTerm,
    /// Episodic memory (specific events/conversations)
    Episodic,
    /// Semantic memory (facts, concepts, relationships)
    Semantic,
}

/// Memory entry
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct MemoryEntry {
    pub id: Uuid,
    pub user_id: Uuid,
    pub organization_id: Uuid,
    pub layer: MemoryLayer,
    pub content: String,
    pub embedding: Option<Vec<f32>>,
    pub importance_score: f64,
    pub access_count: i32,
    pub last_accessed: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
    pub metadata: serde_json::Value,
    pub tags: Vec<String>,
    pub source: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Memory query
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryQuery {
    pub query: String,
    pub layers: Option<Vec<MemoryLayer>>,
    pub limit: Option<i32>,
    pub min_importance: Option<f64>,
    pub tags: Option<Vec<String>>,
    pub time_range: Option<TimeRange>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimeRange {
    pub start: DateTime<Utc>,
    pub end: DateTime<Utc>,
}

/// Memory search result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemorySearchResult {
    pub entry: MemoryEntry,
    pub relevance_score: f64,
    pub context: String,
}

/// Memory consolidation request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsolidationRequest {
    pub source_layer: MemoryLayer,
    pub target_layer: MemoryLayer,
    pub strategy: ConsolidationStrategy,
    pub max_entries: Option<i32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ConsolidationStrategy {
    Importance,
    Recency,
    Frequency,
    Combined,
}

/// Conversation context
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct ConversationContext {
    pub id: Uuid,
    pub user_id: Uuid,
    pub session_id: Uuid,
    pub messages: Vec<ConversationMessage>,
    pub summary: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationMessage {
    pub role: String,
    pub content: String,
    pub timestamp: DateTime<Utc>,
    pub metadata: Option<serde_json::Value>,
}

/// Knowledge graph node
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct KnowledgeNode {
    pub id: Uuid,
    pub organization_id: Uuid,
    pub node_type: String,
    pub label: String,
    pub properties: serde_json::Value,
    pub embedding: Option<Vec<f32>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Knowledge graph edge
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct KnowledgeEdge {
    pub id: Uuid,
    pub source_node_id: Uuid,
    pub target_node_id: Uuid,
    pub relationship: String,
    pub weight: f64,
    pub properties: serde_json::Value,
    pub created_at: DateTime<Utc>,
}

/// Memory statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryStats {
    pub total_entries: i64,
    pub entries_by_layer: std::collections::HashMap<MemoryLayer, i64>,
    pub total_size_bytes: i64,
    pub avg_importance: f64,
    pub consolidation_pending: i32,
}
