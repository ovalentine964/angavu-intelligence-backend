-- Migration: Cross-repo sync support
-- Tables for tracking device sync state, dedup keys, and model versions

CREATE TABLE IF NOT EXISTS device_sync_state (
    device_id VARCHAR(64) PRIMARY KEY,
    last_sync_timestamp BIGINT NOT NULL DEFAULT 0,
    model_version VARCHAR(32),
    last_alama_score SMALLINT,
    total_syncs BIGINT NOT NULL DEFAULT 0,
    total_transactions_synced BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sync_dedup_keys (
    device_id VARCHAR(64) NOT NULL,
    dedup_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (device_id, dedup_key)
);

-- Index for cleanup of old dedup keys
CREATE INDEX IF NOT EXISTS idx_sync_dedup_keys_created_at
    ON sync_dedup_keys (created_at);

-- Table for pending alerts to devices
CREATE TABLE IF NOT EXISTS device_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id VARCHAR(64) NOT NULL,
    alert_type VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    title VARCHAR(256) NOT NULL,
    body TEXT NOT NULL,
    action_url VARCHAR(512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_device_alerts_device_id
    ON device_alerts (device_id)
    WHERE delivered_at IS NULL;

-- Table for market data freshness tracking
CREATE TABLE IF NOT EXISTS market_data_cache (
    ward VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL,
    data_json JSONB NOT NULL,
    data_timestamp BIGINT NOT NULL,
    ttl_seconds BIGINT NOT NULL DEFAULT 3600,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ward, category)
);

CREATE INDEX IF NOT EXISTS idx_market_data_cache_timestamp
    ON market_data_cache (data_timestamp);
