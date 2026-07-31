-- ============================================================
-- Economic Analyzer State Persistence
-- Stores regional economic state across process restarts
-- ============================================================

CREATE TABLE IF NOT EXISTS economic_analyzer_state (
    region VARCHAR(100) PRIMARY KEY,
    state_json JSONB NOT NULL DEFAULT '{}',
    baseline_cpi_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_economic_state_updated ON economic_analyzer_state(updated_at DESC);
