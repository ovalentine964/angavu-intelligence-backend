-- ============================================================================
-- Migration 001: pgvector Extension & Agent Memory
-- ============================================================================
-- Enables pgvector for vector similarity search (AI agent memory).
-- Creates agent_memory table with HNSW index for fast cosine similarity.
-- ============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Agent Memory table — stores embeddings for RAG / long-term agent memory
CREATE TABLE IF NOT EXISTS agent_memory (
    id              VARCHAR(36) PRIMARY KEY,
    user_id         VARCHAR(36) NOT NULL,
    agent_id        VARCHAR(100) NOT NULL DEFAULT 'default',
    memory_type     VARCHAR(50) NOT NULL DEFAULT 'general',
    -- memory_type values: 'conversation', 'fact', 'preference', 'skill', 'general'
    content         TEXT NOT NULL,
    embedding       vector(1536) NOT NULL,
    -- 1536 dims matches OpenAI text-embedding-3-small / ada-002
    metadata        JSONB DEFAULT '{}',
    importance      FLOAT DEFAULT 0.5,
    -- 0.0 = low importance, 1.0 = critical
    access_count    INT DEFAULT 0,
    last_accessed   TIMESTAMP,
    expires_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 3. HNSW index for fast approximate nearest-neighbor search
--    m=16: connections per node (good balance of speed/accuracy)
--    ef_construction=64: build-time search depth
CREATE INDEX IF NOT EXISTS idx_agent_memory_embedding
    ON agent_memory USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 4. Additional indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_agent_memory_user_id ON agent_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_memory_agent_id ON agent_memory(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_memory_user_agent ON agent_memory(user_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_memory_type ON agent_memory(memory_type);
CREATE INDEX IF NOT EXISTS idx_agent_memory_user_type ON agent_memory(user_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_agent_memory_importance ON agent_memory(importance DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memory_created ON agent_memory(created_at DESC);

-- 5. Updated-at trigger
CREATE OR REPLACE FUNCTION update_agent_memory_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_agent_memory_updated_at
    BEFORE UPDATE ON agent_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_agent_memory_updated_at();

-- 6. Helper function: similarity search for agent memory
CREATE OR REPLACE FUNCTION search_agent_memory(
    p_user_id VARCHAR(36),
    p_agent_id VARCHAR(100),
    p_query_embedding vector(1536),
    p_memory_type VARCHAR(50) DEFAULT NULL,
    p_limit INT DEFAULT 10,
    p_min_similarity FLOAT DEFAULT 0.5
)
RETURNS TABLE (
    id VARCHAR(36),
    content TEXT,
    memory_type VARCHAR(50),
    metadata JSONB,
    importance FLOAT,
    similarity FLOAT,
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        am.id,
        am.content,
        am.memory_type,
        am.metadata,
        am.importance,
        1 - (am.embedding <=> p_query_embedding) AS similarity,
        am.created_at
    FROM agent_memory am
    WHERE am.user_id = p_user_id
      AND am.agent_id = p_agent_id
      AND (p_memory_type IS NULL OR am.memory_type = p_memory_type)
      AND (am.expires_at IS NULL OR am.expires_at > CURRENT_TIMESTAMP)
      AND 1 - (am.embedding <=> p_query_embedding) >= p_min_similarity
    ORDER BY am.embedding <=> p_query_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE agent_memory IS 'AI agent long-term memory with vector embeddings for semantic search';
COMMENT ON COLUMN agent_memory.embedding IS 'Vector embedding (1536-dim) for cosine similarity search via pgvector HNSW';
COMMENT ON COLUMN agent_memory.importance IS 'Memory importance score 0-1, used for retention prioritization';
