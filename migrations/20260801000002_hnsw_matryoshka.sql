-- ============================================================
-- G4: Replace IVFFlat indexes with HNSW + Matryoshka truncation
--
-- HNSW advantages over IVFFlat for this workload:
--   - Recall@10: 95-99% (vs 85-95% for IVFFlat)
--   - Query time: 2-6ms (vs 2-10ms for IVFFlat)
--   - Incremental inserts (no rebuild needed)
--
-- Matryoshka truncation to 256 dimensions:
--   - 83% storage savings (256/1536 = 16.7% of original)
--   - <2% recall loss for semantic search tasks
--   - text-embedding-3-small supports native Matryoshka truncation
--
-- Migration strategy:
--   1. Drop old IVFFlat indexes
--   2. Add truncated embedding columns (256 dims)
--   3. Create HNSW indexes on truncated columns
--   4. Keep full 1536-dim columns for knowledge-critical nodes
-- ============================================================

-- ════════════════════════════════════════════════════════════
-- STEP 1: Drop old IVFFlat indexes
-- ════════════════════════════════════════════════════════════

DROP INDEX IF EXISTS idx_kg_cohorts_embedding;
DROP INDEX IF EXISTS idx_kg_products_embedding;
DROP INDEX IF EXISTS idx_kg_regions_embedding;

-- ════════════════════════════════════════════════════════════
-- STEP 2: Add Matryoshka-truncated embedding columns (256 dims)
-- ════════════════════════════════════════════════════════════

-- Worker cohorts: 256-dim for fast similarity search
ALTER TABLE kg_worker_cohorts
    ADD COLUMN IF NOT EXISTS embedding_256 vector(256);

-- Product categories: 256-dim
ALTER TABLE kg_product_categories
    ADD COLUMN IF NOT EXISTS embedding_256 vector(256);

-- Regional markets: 256-dim
ALTER TABLE kg_regional_markets
    ADD COLUMN IF NOT EXISTS embedding_256 vector(256);

-- Supply chain entities: 256-dim
ALTER TABLE kg_supply_chain_entities
    ADD COLUMN IF NOT EXISTS embedding_256 vector(256);

-- Economic indicators: 256-dim
ALTER TABLE kg_economic_indicators
    ADD COLUMN IF NOT EXISTS embedding_256 vector(256);

-- Financial products: 256-dim
ALTER TABLE kg_financial_products
    ADD COLUMN IF NOT EXISTS embedding_256 vector(256);

-- Demand signals: 256-dim
ALTER TABLE kg_demand_signals
    ADD COLUMN IF NOT EXISTS embedding_256 vector(256);

-- ════════════════════════════════════════════════════════════
-- STEP 3: Create HNSW indexes on truncated columns
--
-- Parameters:
--   m = 16 (number of connections per node, default 16)
--   ef_construction = 64 (build-time search width, higher = better recall)
--   ef_search can be tuned at query time (default 40, increase for cold-start)
-- ════════════════════════════════════════════════════════════

-- Worker cohorts — primary similarity target
CREATE INDEX idx_kg_cohorts_emb256_hnsw ON kg_worker_cohorts
    USING hnsw (embedding_256 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Product categories — demand correlation, substitution analysis
CREATE INDEX idx_kg_products_emb256_hnsw ON kg_product_categories
    USING hnsw (embedding_256 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Regional markets — geographic similarity
CREATE INDEX idx_kg_regions_emb256_hnsw ON kg_regional_markets
    USING hnsw (embedding_256 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Supply chain entities — supplier similarity
CREATE INDEX idx_kg_supply_emb256_hnsw ON kg_supply_chain_entities
    USING hnsw (embedding_256 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Economic indicators — indicator correlation
CREATE INDEX idx_kg_indicators_emb256_hnsw ON kg_economic_indicators
    USING hnsw (embedding_256 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Financial products — product matching
CREATE INDEX idx_kg_financial_emb256_hnsw ON kg_financial_products
    USING hnsw (embedding_256 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Demand signals — signal correlation
CREATE INDEX idx_kg_signals_emb256_hnsw ON kg_demand_signals
    USING hnsw (embedding_256 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ════════════════════════════════════════════════════════════
-- STEP 4: Also create HNSW on full 1536-dim columns (replace IVFFlat)
-- These are for knowledge-critical nodes that need maximum precision.
-- ════════════════════════════════════════════════════════════

CREATE INDEX idx_kg_cohorts_emb1536_hnsw ON kg_worker_cohorts
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_kg_products_emb1536_hnsw ON kg_product_categories
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_kg_regions_emb1536_hnsw ON kg_regional_markets
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ════════════════════════════════════════════════════════════
-- STEP 5: Helper function for Matryoshka truncation
-- Truncates a 1536-dim vector to 256 dims (first 256 components).
-- text-embedding-3-small supports this natively; this function
-- handles pre-computed 1536-dim vectors.
-- ════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION matryoshka_truncate_256(embedding_1536 vector(1536))
RETURNS vector(256)
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $$
    SELECT embedding_1536::vector(256);
$$;

-- ════════════════════════════════════════════════════════════
-- STEP 6: Trigger to auto-populate embedding_256 on INSERT/UPDATE
-- ════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION auto_truncate_embedding()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.embedding IS NOT NULL AND (NEW.embedding_256 IS NULL OR TG_OP = 'INSERT') THEN
        NEW.embedding_256 := matryoshka_truncate_256(NEW.embedding);
    END IF;
    RETURN NEW;
END;
$$;

-- Apply trigger to all tables with embeddings
CREATE TRIGGER trg_cohorts_truncate_embedding
    BEFORE INSERT OR UPDATE OF embedding ON kg_worker_cohorts
    FOR EACH ROW EXECUTE FUNCTION auto_truncate_embedding();

CREATE TRIGGER trg_products_truncate_embedding
    BEFORE INSERT OR UPDATE OF embedding ON kg_product_categories
    FOR EACH ROW EXECUTE FUNCTION auto_truncate_embedding();

CREATE TRIGGER trg_regions_truncate_embedding
    BEFORE INSERT OR UPDATE OF embedding ON kg_regional_markets
    FOR EACH ROW EXECUTE FUNCTION auto_truncate_embedding();

CREATE TRIGGER trg_supply_truncate_embedding
    BEFORE INSERT OR UPDATE OF embedding ON kg_supply_chain_entities
    FOR EACH ROW EXECUTE FUNCTION auto_truncate_embedding();

CREATE TRIGGER trg_indicators_truncate_embedding
    BEFORE INSERT OR UPDATE OF embedding ON kg_economic_indicators
    FOR EACH ROW EXECUTE FUNCTION auto_truncate_embedding();

CREATE TRIGGER trg_financial_truncate_embedding
    BEFORE INSERT OR UPDATE OF embedding ON kg_financial_products
    FOR EACH ROW EXECUTE FUNCTION auto_truncate_embedding();

CREATE TRIGGER trg_signals_truncate_embedding
    BEFORE INSERT OR UPDATE OF embedding ON kg_demand_signals
    FOR EACH ROW EXECUTE FUNCTION auto_truncate_embedding();

-- ════════════════════════════════════════════════════════════
-- STEP 7: Materialized view refresh (update kg_graph_stats)
-- ════════════════════════════════════════════════════════════

-- Add HNSW index stats to graph stats
CREATE OR REPLACE VIEW kg_index_stats AS
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS index_size
FROM pg_indexes
WHERE indexname LIKE '%hnsw%'
   OR indexname LIKE '%ivfflat%'
ORDER BY tablename, indexname;
