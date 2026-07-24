-- ============================================================================
-- Migration 002: TimescaleDB & Transaction Events Hypertable
-- ============================================================================
-- Enables TimescaleDB for time-series transaction event data.
-- Creates hypertable with compression and continuous aggregates.
-- ============================================================================

-- 1. Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 2. Transaction Events — high-frequency event stream
CREATE TABLE IF NOT EXISTS transaction_events (
    id              VARCHAR(36) NOT NULL,
    user_id         VARCHAR(36) NOT NULL,
    event_type      VARCHAR(50) NOT NULL,
    -- event_type values: 'created', 'updated', 'cancelled', 'refunded',
    --                    'payment_received', 'payment_sent', 'stock_change',
    --                    'price_change', 'category_change'
    transaction_id  VARCHAR(36),
    amount          DECIMAL(10, 2),
    description     TEXT,
    product_name    VARCHAR(200),
    quantity        INT,
    payment_method  VARCHAR(50),
    metadata        JSONB DEFAULT '{}',
    -- Flexible metadata for event-specific data
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Convert to TimescaleDB hypertable (partitioned by month)
SELECT create_hypertable(
    'transaction_events',
    by_range('created_at', INTERVAL '1 month'),
    if_not_exists => TRUE
);

-- 4. Add indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_te_user_id ON transaction_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_te_transaction_id ON transaction_events(transaction_id);
CREATE INDEX IF NOT EXISTS idx_te_event_type ON transaction_events(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_te_user_type ON transaction_events(user_id, event_type, created_at DESC);

-- 5. Enable compression on older chunks (compresses data > 7 days old)
ALTER TABLE transaction_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'user_id, event_type',
    timescaledb.compress_orderby = 'created_at DESC'
);

-- 6. Add compression policy — automatically compress chunks older than 7 days
SELECT add_compression_policy('transaction_events', INTERVAL '7 days', if_not_exists => TRUE);

-- 7. Continuous Aggregate: Daily transaction event summary per user
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_transaction_event_summary
WITH (timescaledb.continuous) AS
SELECT
    user_id,
    time_bucket('1 day', created_at) AS day,
    event_type,
    COUNT(*) AS event_count,
    SUM(CASE WHEN amount IS NOT NULL THEN amount ELSE 0 END) AS total_amount,
    SUM(CASE WHEN quantity IS NOT NULL THEN quantity ELSE 0 END) AS total_quantity,
    COUNT(DISTINCT transaction_id) AS unique_transactions
FROM transaction_events
GROUP BY user_id, time_bucket('1 day', created_at), event_type
WITH NO DATA;

-- 8. Add refresh policy for the continuous aggregate (refresh every hour)
SELECT add_continuous_aggregate_policy('daily_transaction_event_summary',
    start_offset    => INTERVAL '3 days',
    end_offset      => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists   => TRUE
);

-- 9. Continuous Aggregate: Hourly transaction volume (for real-time dashboards)
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_transaction_volume
WITH (timescaledb.continuous) AS
SELECT
    user_id,
    time_bucket('1 hour', created_at) AS hour,
    COUNT(*) AS event_count,
    SUM(CASE WHEN amount IS NOT NULL THEN amount ELSE 0 END) AS total_amount,
    COUNT(DISTINCT transaction_id) AS unique_transactions
FROM transaction_events
GROUP BY user_id, time_bucket('1 hour', created_at)
WITH NO DATA;

-- 10. Refresh policy for hourly aggregate
SELECT add_continuous_aggregate_policy('hourly_transaction_volume',
    start_offset    => INTERVAL '2 days',
    end_offset      => INTERVAL '10 minutes',
    schedule_interval => INTERVAL '10 minutes',
    if_not_exists   => TRUE
);

-- 11. Retention policy — drop raw data older than 2 years
SELECT add_retention_policy('transaction_events', INTERVAL '2 years', if_not_exists => TRUE);

COMMENT ON TABLE transaction_events IS 'Time-series transaction events managed by TimescaleDB hypertable';
COMMENT ON MATERIALIZED VIEW daily_transaction_event_summary IS 'Continuous aggregate: daily rollup of transaction events per user';
COMMENT ON MATERIALIZED VIEW hourly_transaction_volume IS 'Continuous aggregate: hourly transaction volume for real-time dashboards';
