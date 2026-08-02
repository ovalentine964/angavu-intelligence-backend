-- ============================================================
-- FIX: sync_events table + missing HNSW indexes on 1536-dim columns
--
-- Problem 1: Migration 20260801000007 creates indexes on sync_events
--            but the table was never created. This migration adds it.
--
-- Problem 2: Migration 20260801000005 creates HNSW indexes on
--            embedding_256 for all 7 KG tables, but only creates
--            HNSW on the full 1536-dim embedding for 3 tables.
--            The remaining 4 tables have vector(1536) columns
--            with NO index, causing sequential scans on similarity
--            queries against the full embedding.
-- ============================================================

-- ════════════════════════════════════════════════════════════
-- PART 1: Create sync_events table
-- Referenced by 20260801000007_performance_indices migration
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sync_events (
    id              BIGSERIAL PRIMARY KEY,
    device_id       VARCHAR(64) NOT NULL,
    event_type      VARCHAR(50) NOT NULL DEFAULT 'graph_sync',
    region          VARCHAR(100),
    business_type   VARCHAR(50),
    cohort_hash     VARCHAR(64),
    deltas_applied  INT NOT NULL DEFAULT 0,
    status          VARCHAR(20) NOT NULL DEFAULT 'success',
    error_message   TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes (matching what 20260801000007 expects)
CREATE INDEX IF NOT EXISTS idx_sync_device_timestamp ON sync_events(device_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sync_region ON sync_events(region);
CREATE INDEX IF NOT EXISTS idx_sync_business_type ON sync_events(business_type);

-- Additional useful indexes
CREATE INDEX IF NOT EXISTS idx_sync_events_cohort ON sync_events(cohort_hash);
CREATE INDEX IF NOT EXISTS idx_sync_events_status ON sync_events(status);

-- ════════════════════════════════════════════════════════════
-- PART 2: Add missing HNSW indexes on full 1536-dim embeddings
--
-- These 4 tables have embedding vector(1536) columns (from
-- migration 20240101000004) but were never indexed. Migration
-- 20260801000005 added embedding_256 + HNSW but only added
-- 1536-dim HNSW for cohorts, products, and regions.
-- ════════════════════════════════════════════════════════════

-- Supply chain entities — supplier similarity at full precision
CREATE INDEX IF NOT EXISTS idx_kg_supply_emb1536_hnsw ON kg_supply_chain_entities
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Economic indicators — indicator correlation at full precision
CREATE INDEX IF NOT EXISTS idx_kg_indicators_emb1536_hnsw ON kg_economic_indicators
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Financial products — product matching at full precision
CREATE INDEX IF NOT EXISTS idx_kg_financial_emb1536_hnsw ON kg_financial_products
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Demand signals — signal correlation at full precision
CREATE INDEX IF NOT EXISTS idx_kg_signals_emb1536_hnsw ON kg_demand_signals
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
