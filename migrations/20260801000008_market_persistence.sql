-- ============================================================
-- Market Module Persistence — Tables for market intelligence
-- Fixes: MarketAnalyzer, FMCGIntelligence, DistributionAnalyzer
--        lose state on restart. Replaces fragile file-based
--        ModuleStateStore with PostgreSQL.
-- ============================================================

-- 1. Market Windows: Rolling time-window data per (region, product)
-- MarketAnalyzer writes here; survives restarts.
CREATE TABLE IF NOT EXISTS market_windows (
    id              BIGSERIAL PRIMARY KEY,
    region          VARCHAR(100) NOT NULL,
    product_category VARCHAR(100) NOT NULL,
    -- Rolling window data stored as JSONB arrays
    prices          JSONB NOT NULL DEFAULT '[]',      -- f64[]
    volumes         JSONB NOT NULL DEFAULT '[]',      -- f64[]
    timestamps      JSONB NOT NULL DEFAULT '[]',      -- ISO8601[]
    max_size        INT NOT NULL DEFAULT 168,
    min_sample_size INT NOT NULL DEFAULT 10,
    -- Computed aggregates (cached for fast reads)
    mean_price      DOUBLE PRECISION,
    price_stddev    DOUBLE PRECISION,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(region, product_category)
);

CREATE INDEX IF NOT EXISTS idx_market_windows_region ON market_windows(region);
CREATE INDEX IF NOT EXISTS idx_market_windows_updated ON market_windows(last_updated DESC);

-- 2. FMCG Signals: Brand/product tracking data
-- FMCGIntelligence writes brand volumes and elasticity data here.
CREATE TABLE IF NOT EXISTS fmcg_signals (
    id              BIGSERIAL PRIMARY KEY,
    region          VARCHAR(100) NOT NULL,
    product_category VARCHAR(100) NOT NULL,
    -- Brand tracking: {"brand_name": volume, ...}
    brand_volumes   JSONB NOT NULL DEFAULT '{}',
    total_volume    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Price-demand pairs for elasticity: [[price, qty], ...]
    elasticity_data JSONB NOT NULL DEFAULT '[]',
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(region, product_category)
);

CREATE INDEX IF NOT EXISTS idx_fmcg_signals_region ON fmcg_signals(region);
CREATE INDEX IF NOT EXISTS idx_fmcg_signals_category ON fmcg_signals(product_category);
CREATE INDEX IF NOT EXISTS idx_fmcg_signals_updated ON fmcg_signals(last_updated DESC);

-- 3. Distribution Gaps: Supply-demand analysis
-- DistributionAnalyzer writes supply/demand indices and gap history.
CREATE TABLE IF NOT EXISTS distribution_gaps (
    id              BIGSERIAL PRIMARY KEY,
    region          VARCHAR(100) NOT NULL,
    product_category VARCHAR(100) NOT NULL,
    supply_index    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    demand_index    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Gap history as JSONB array of gap ratios
    gap_history     JSONB NOT NULL DEFAULT '[]',
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(region, product_category)
);

CREATE INDEX IF NOT EXISTS idx_dist_gaps_region ON distribution_gaps(region);
CREATE INDEX IF NOT EXISTS idx_dist_gaps_updated ON distribution_gaps(last_updated DESC);

-- 4. Service Prices: Pricing intelligence from ServicePriceBroadcast events
-- ServicePriceDiscoveryEngine processes broadcasts and stores aggregated signals.
CREATE TABLE IF NOT EXISTS service_prices (
    id              BIGSERIAL PRIMARY KEY,
    service_category VARCHAR(50) NOT NULL,   -- Transport, Construction, Beauty, Repair, etc.
    service_type    VARCHAR(100) NOT NULL,    -- boda_boda_ride, hair_braiding, etc.
    region          VARCHAR(100) NOT NULL,
    -- Aggregated price data
    price_avg       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    price_min       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    price_max       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    price_trend     DOUBLE PRECISION NOT NULL DEFAULT 0.0,  -- -1.0 to 1.0
    demand_velocity DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    volatility      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    sample_size     INT NOT NULL DEFAULT 0,
    -- Pricing factors as JSONB
    factors         JSONB NOT NULL DEFAULT '[]',
    -- Raw broadcast count for confidence
    broadcast_count INT NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(service_category, service_type, region)
);

CREATE INDEX IF NOT EXISTS idx_service_prices_region ON service_prices(region);
CREATE INDEX IF NOT EXISTS idx_service_prices_category ON service_prices(service_category);
CREATE INDEX IF NOT EXISTS idx_service_prices_updated ON service_prices(last_updated DESC);

-- 5. Service Price Broadcasts (raw incoming data for aggregation)
-- Stores individual broadcasts before aggregation.
CREATE TABLE IF NOT EXISTS service_price_broadcasts (
    id              BIGSERIAL PRIMARY KEY,
    broadcast_id    UUID NOT NULL UNIQUE,
    worker_id_hash  VARCHAR(100) NOT NULL,
    service_category VARCHAR(50) NOT NULL,
    service_type    VARCHAR(100) NOT NULL,
    region          VARCHAR(100) NOT NULL,
    price_bucket    VARCHAR(50) NOT NULL,     -- "100-200"
    price_midpoint  DOUBLE PRECISION NOT NULL, -- computed from bucket
    unit            VARCHAR(50) NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    processed       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spb_region ON service_price_broadcasts(region);
CREATE INDEX IF NOT EXISTS idx_spb_category ON service_price_broadcasts(service_category);
CREATE INDEX IF NOT EXISTS idx_spb_unprocessed ON service_price_broadcasts(processed)
    WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_spb_recorded ON service_price_broadcasts(recorded_at DESC);

-- 6. Data Retention Policy: Auto-cleanup via pg_cron or application-level
-- Partition helper: created_at index for efficient cleanup
CREATE INDEX IF NOT EXISTS idx_spb_created ON service_price_broadcasts(created_at);

COMMENT ON TABLE market_windows IS 'Rolling time-window data for MarketAnalyzer. Survives restarts.';
COMMENT ON TABLE fmcg_signals IS 'Brand tracking and elasticity data for FMCGIntelligence.';
COMMENT ON TABLE distribution_gaps IS 'Supply-demand gap analysis for DistributionAnalyzer.';
COMMENT ON TABLE service_prices IS 'Aggregated service pricing intelligence from broadcasts.';
COMMENT ON TABLE service_price_broadcasts IS 'Raw service price broadcasts before aggregation.';

-- ============================================================
-- Data Retention: Auto-cleanup old data
-- Run periodically via pg_cron or application-level scheduler
-- ============================================================

-- Retention function: cleans up data older than retention period
CREATE OR REPLACE FUNCTION market_retention_cleanup()
RETURNS TABLE(table_name TEXT, rows_deleted BIGINT) AS $$
DECLARE
    deleted BIGINT;
BEGIN
    -- Raw broadcasts: keep 90 days
    DELETE FROM service_price_broadcasts WHERE created_at < NOW() - INTERVAL '90 days';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    table_name := 'service_price_broadcasts';
    rows_deleted := deleted;
    RETURN NEXT;

    -- Market windows: remove stale entries not updated in 30 days
    DELETE FROM market_windows WHERE last_updated < NOW() - INTERVAL '30 days';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    table_name := 'market_windows';
    rows_deleted := deleted;
    RETURN NEXT;

    -- FMCG signals: remove stale entries not updated in 30 days
    DELETE FROM fmcg_signals WHERE last_updated < NOW() - INTERVAL '30 days';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    table_name := 'fmcg_signals';
    rows_deleted := deleted;
    RETURN NEXT;

    -- Distribution gaps: remove stale entries not updated in 30 days
    DELETE FROM distribution_gaps WHERE last_updated < NOW() - INTERVAL '30 days';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    table_name := 'distribution_gaps';
    rows_deleted := deleted;
    RETURN NEXT;

    -- Service prices: keep aggregated signals for 90 days
    DELETE FROM service_prices WHERE last_updated < NOW() - INTERVAL '90 days';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    table_name := 'service_prices';
    rows_deleted := deleted;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- Schedule via pg_cron (if available): SELECT cron.schedule('market-retention', '0 3 * * *', 'SELECT market_retention_cleanup();');
COMMENT ON FUNCTION market_retention_cleanup() IS 'Data retention cleanup for market module tables. Call daily.';
