-- ============================================================
-- Knowledge Graph Memory System
-- Episodic, Semantic, and Procedural memory tables
-- for AGI long-term memory integration
-- ============================================================

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
