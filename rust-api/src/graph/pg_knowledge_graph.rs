// Knowledge Graph — PostgreSQL-backed implementation
// Connects the in-memory graph model to the kg_* tables in PostgreSQL.
// This replaces the pure in-memory KnowledgeGraph with a persistent one.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use super::{GraphEdge, GraphNode, GraphTraversal, NodeStatus};

// ── Re-export memory types from the existing knowledge_graph module ──
pub use super::knowledge_graph::*;

/// PostgreSQL-backed Knowledge Graph.
/// Wraps a connection pool and delegates to kg_* tables.
pub struct PgKnowledgeGraph {
    pool: sqlx::PgPool,
}

impl PgKnowledgeGraph {
    pub fn new(pool: sqlx::PgPool) -> Self {
        Self { pool }
    }

    /// Insert an episodic memory into kg_episodic_memories
    pub async fn add_episodic(&self, memory: &EpisodicMemory) -> Result<(), String> {
        sqlx::query!(
            r#"
            INSERT INTO kg_episodic_memories (id, event_type, description, timestamp, participants, location, emotional_valence, importance, context, outcome, embedding, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (id) DO UPDATE SET
                description = EXCLUDED.description,
                context = EXCLUDED.context,
                outcome = EXCLUDED.outcome
            "#,
            memory.id,
            serde_json::to_string(&memory.event_type).unwrap_or_default(),
            memory.description,
            memory.timestamp,
            &memory.participants,
            memory.location,
            memory.emotional_valence,
            memory.importance,
            memory.context,
            memory.outcome,
            memory.embedding.as_deref().map(|e| e.to_vec()),
            serde_json::to_string(&memory.status).unwrap_or_default(),
        )
        .execute(&self.pool)
        .await
        .map_err(|e| format!("Failed to insert episodic memory: {}", e))?;

        Ok(())
    }

    /// Insert a semantic memory into kg_semantic_memories
    pub async fn add_semantic(&self, memory: &SemanticMemory) -> Result<(), String> {
        sqlx::query!(
            r#"
            INSERT INTO kg_semantic_memories (id, concept, category, statement, confidence, source, last_verified, contradiction_count, embedding, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (id) DO UPDATE SET
                statement = EXCLUDED.statement,
                confidence = EXCLUDED.confidence,
                last_verified = EXCLUDED.last_verified
            "#,
            memory.id,
            memory.concept,
            serde_json::to_string(&memory.category).unwrap_or_default(),
            memory.statement,
            memory.confidence,
            memory.source,
            memory.last_verified,
            memory.contradiction_count as i32,
            memory.embedding.as_deref().map(|e| e.to_vec()),
            serde_json::to_string(&memory.status).unwrap_or_default(),
        )
        .execute(&self.pool)
        .await
        .map_err(|e| format!("Failed to insert semantic memory: {}", e))?;

        Ok(())
    }

    /// Insert a procedural memory into kg_procedural_memories
    pub async fn add_procedural(&self, memory: &ProceduralMemory) -> Result<(), String> {
        let steps_json = serde_json::to_value(&memory.steps).unwrap_or_default();
        sqlx::query!(
            r#"
            INSERT INTO kg_procedural_memories (id, skill_name, description, steps, preconditions, postconditions, success_rate, average_duration_ms, applicable_contexts, learned_from, embedding, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (id) DO UPDATE SET
                steps = EXCLUDED.steps,
                success_rate = EXCLUDED.success_rate,
                average_duration_ms = EXCLUDED.average_duration_ms
            "#,
            memory.id,
            memory.skill_name,
            memory.description,
            steps_json,
            &memory.preconditions,
            &memory.postconditions,
            memory.success_rate,
            memory.average_duration_ms.map(|d| d as i64),
            &memory.applicable_contexts,
            memory.learned_from,
            memory.embedding.as_deref().map(|e| e.to_vec()),
            serde_json::to_string(&memory.status).unwrap_or_default(),
        )
        .execute(&self.pool)
        .await
        .map_err(|e| format!("Failed to insert procedural memory: {}", e))?;

        Ok(())
    }

    /// Insert an edge into kg_memory_edges
    pub async fn add_edge(&self, edge: &MemoryEdge) -> Result<(), String> {
        let (source_id, target_id, edge_type, weight, properties) = match edge {
            MemoryEdge::TemporalSequence { source_id, target_id, time_gap_hours } =>
                (*source_id, *target_id, "temporal_sequence", 1.0 / (1.0 + time_gap_hours / 24.0), serde_json::json!({"time_gap_hours": time_gap_hours})),
            MemoryEdge::Causal { source_id, target_id, confidence } =>
                (*source_id, *target_id, "causal", *confidence, serde_json::json!({})),
            MemoryEdge::SemanticSimilarity { source_id, target_id, similarity } =>
                (*source_id, *target_id, "semantic_similarity", *similarity, serde_json::json!({})),
            MemoryEdge::Contextual { source_id, target_id, context_type } =>
                (*source_id, *target_id, "contextual", 0.5, serde_json::json!({"context_type": context_type})),
            MemoryEdge::Contradicts { source_id, target_id, resolution } =>
                (*source_id, *target_id, "contradicts", -1.0, serde_json::json!({"resolution": resolution})),
            MemoryEdge::Supports { source_id, target_id, strength } =>
                (*source_id, *target_id, "supports", *strength, serde_json::json!({})),
            MemoryEdge::PartOf { source_id, target_id, step_index } =>
                (*source_id, *target_id, "part_of", 1.0, serde_json::json!({"step_index": step_index})),
            MemoryEdge::Involves { source_id, target_id, role } =>
                (*source_id, *target_id, "involves", 0.7, serde_json::json!({"role": role})),
        };

        sqlx::query!(
            r#"
            INSERT INTO kg_memory_edges (source_id, target_id, edge_type, weight, properties)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (source_id, target_id, edge_type) DO UPDATE SET
                weight = EXCLUDED.weight,
                properties = EXCLUDED.properties
            "#,
            source_id,
            target_id,
            edge_type,
            weight,
            properties,
        )
        .execute(&self.pool)
        .await
        .map_err(|e| format!("Failed to insert memory edge: {}", e))?;

        Ok(())
    }

    /// Query episodic memories by participant
    pub async fn episodic_by_participant(&self, participant: &str) -> Result<Vec<EpisodicMemory>, String> {
        let rows = sqlx::query!(
            r#"
            SELECT id, event_type, description, timestamp, participants, location, emotional_valence, importance, context, outcome, embedding, status
            FROM kg_episodic_memories
            WHERE $1 = ANY(participants)
            ORDER BY timestamp DESC
            LIMIT 50
            "#,
            participant,
        )
        .fetch_all(&self.pool)
        .await
        .map_err(|e| format!("Failed to query episodic memories: {}", e))?;

        Ok(rows.into_iter().map(|r| EpisodicMemory {
            id: r.id,
            event_type: serde_json::from_str(&r.event_type).unwrap_or(EpisodicEventType::Custom("unknown".to_string())),
            description: r.description,
            timestamp: r.timestamp,
            participants: r.participants,
            location: r.location,
            emotional_valence: r.emotional_valence,
            importance: r.importance,
            context: r.context.unwrap_or_default(),
            outcome: r.outcome,
            embedding: r.embedding,
            status: serde_json::from_str(&r.status).unwrap_or(NodeStatus::Completed),
        }).collect())
    }

    /// Query semantic memories by concept
    pub async fn semantic_by_concept(&self, concept: &str) -> Result<Vec<SemanticMemory>, String> {
        let rows = sqlx::query!(
            r#"
            SELECT id, concept, category, statement, confidence, source, last_verified, contradiction_count, embedding, status
            FROM kg_semantic_memories
            WHERE LOWER(concept) = LOWER($1)
            ORDER BY confidence DESC
            LIMIT 20
            "#,
            concept,
        )
        .fetch_all(&self.pool)
        .await
        .map_err(|e| format!("Failed to query semantic memories: {}", e))?;

        Ok(rows.into_iter().map(|r| SemanticMemory {
            id: r.id,
            concept: r.concept,
            category: serde_json::from_str(&r.category).unwrap_or(SemanticCategory::Custom("unknown".to_string())),
            statement: r.statement,
            confidence: r.confidence,
            source: r.source,
            last_verified: r.last_verified,
            contradiction_count: r.contradiction_count.unwrap_or(0) as u32,
            embedding: r.embedding,
            status: serde_json::from_str(&r.status).unwrap_or(NodeStatus::Completed),
        }).collect())
    }

    /// Get graph statistics from PostgreSQL
    pub async fn stats(&self) -> Result<GraphStats, String> {
        let episodic = sqlx::query_scalar!("SELECT COUNT(*) FROM kg_episodic_memories")
            .fetch_one(&self.pool).await.unwrap_or(0);
        let semantic = sqlx::query_scalar!("SELECT COUNT(*) FROM kg_semantic_memories")
            .fetch_one(&self.pool).await.unwrap_or(0);
        let procedural = sqlx::query_scalar!("SELECT COUNT(*) FROM kg_procedural_memories")
            .fetch_one(&self.pool).await.unwrap_or(0);
        let edges = sqlx::query_scalar!("SELECT COUNT(*) FROM kg_memory_edges")
            .fetch_one(&self.pool).await.unwrap_or(0);

        let total = episodic + semantic + procedural;
        Ok(GraphStats {
            total_nodes: total as u64,
            episodic_count: episodic as u64,
            semantic_count: semantic as u64,
            procedural_count: procedural as u64,
            total_edges: edges as u64,
            avg_connections_per_node: if total > 0 { edges as f64 / total as f64 } else { 0.0 },
        })
    }
}

/// SQL migration to create the PostgreSQL tables for the knowledge graph memory system.
pub const KG_MEMORY_MIGRATION: &str = r#"
-- Episodic Memory table
CREATE TABLE IF NOT EXISTS kg_episodic_memories (
    id UUID PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    participants TEXT[] NOT NULL DEFAULT '{}',
    location TEXT,
    emotional_valence DOUBLE PRECISION,
    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    context JSONB NOT NULL DEFAULT '{}',
    outcome TEXT,
    embedding DOUBLE PRECISION[],
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_episodic_timestamp ON kg_episodic_memories(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_kg_episodic_participants ON kg_episodic_memories USING GIN(participants);
CREATE INDEX IF NOT EXISTS idx_kg_episodic_type ON kg_episodic_memories(event_type);

-- Semantic Memory table
CREATE TABLE IF NOT EXISTS kg_semantic_memories (
    id UUID PRIMARY KEY,
    concept VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    statement TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    source VARCHAR(200) NOT NULL DEFAULT 'unknown',
    last_verified TIMESTAMPTZ,
    contradiction_count INT NOT NULL DEFAULT 0,
    embedding DOUBLE PRECISION[],
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_semantic_concept ON kg_semantic_memories(LOWER(concept));
CREATE INDEX IF NOT EXISTS idx_kg_semantic_category ON kg_semantic_memories(category);
CREATE INDEX IF NOT EXISTS idx_kg_semantic_confidence ON kg_semantic_memories(confidence DESC);

-- Procedural Memory table
CREATE TABLE IF NOT EXISTS kg_procedural_memories (
    id UUID PRIMARY KEY,
    skill_name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    steps JSONB NOT NULL DEFAULT '[]',
    preconditions TEXT[] NOT NULL DEFAULT '{}',
    postconditions TEXT[] NOT NULL DEFAULT '{}',
    success_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    average_duration_ms BIGINT,
    applicable_contexts TEXT[] NOT NULL DEFAULT '{}',
    learned_from VARCHAR(100) NOT NULL DEFAULT 'unknown',
    embedding DOUBLE PRECISION[],
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_procedural_skill ON kg_procedural_memories(LOWER(skill_name));
CREATE INDEX IF NOT EXISTS idx_kg_procedural_success ON kg_procedural_memories(success_rate DESC);

-- Memory Edges table
CREATE TABLE IF NOT EXISTS kg_memory_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL,
    target_id UUID NOT NULL,
    edge_type VARCHAR(50) NOT NULL,
    weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    properties JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, target_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_kg_mem_edges_source ON kg_memory_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_kg_mem_edges_target ON kg_memory_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_kg_mem_edges_type ON kg_memory_edges(edge_type);
"#;
