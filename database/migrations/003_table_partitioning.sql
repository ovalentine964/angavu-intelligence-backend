-- ============================================================================
-- Migration 003: Table Partitioning Strategy for Large Tables
-- ============================================================================
-- Adds declarative partitioning to large, high-growth tables.
-- Reduces index bloat, speeds up vacuum, enables partition pruning.
-- ============================================================================

-- ============================================================================
-- 1. Partition whatsapp_messages by month (high-volume, append-only)
--    Strategy: Create partitioned table, migrate data, rename.
-- ============================================================================

-- Create new partitioned table
CREATE TABLE IF NOT EXISTS whatsapp_messages_partitioned (
    id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text',
    content TEXT,
    openwa_message_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'sent',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (created_at);

-- Create partitions for current year + next year (extend as needed)
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m01 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m02 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m03 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m04 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m05 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m06 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m07 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m08 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m09 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m10 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m11 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2025m12 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m01 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m02 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m03 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m04 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m05 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m06 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m07 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m08 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m09 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m10 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m11 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE IF NOT EXISTS whatsapp_messages_y2026m12 PARTITION OF whatsapp_messages_partitioned
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

-- Default partition for data outside defined ranges
CREATE TABLE IF NOT EXISTS whatsapp_messages_default PARTITION OF whatsapp_messages_partitioned DEFAULT;

-- Add indexes to partitioned table
CREATE INDEX IF NOT EXISTS idx_wmp_user_id ON whatsapp_messages_partitioned(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wmp_phone ON whatsapp_messages_partitioned(phone, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wmp_openwa_id ON whatsapp_messages_partitioned(openwa_message_id);

-- ============================================================================
-- 2. Partition transactions by month (high-volume, append-heavy)
-- ============================================================================

CREATE TABLE IF NOT EXISTS transactions_partitioned (
    id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    type VARCHAR(20) NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    description TEXT,
    product_name VARCHAR(200),
    quantity INT DEFAULT 1,
    payment_method VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (created_at);

-- Create partitions for 2025-2026
CREATE TABLE IF NOT EXISTS transactions_y2025m01 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m02 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m03 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m04 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m05 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m06 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m07 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m08 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m09 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m10 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m11 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
CREATE TABLE IF NOT EXISTS transactions_y2025m12 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m01 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m02 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m03 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m04 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m05 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m06 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m07 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m08 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m09 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m10 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m11 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE IF NOT EXISTS transactions_y2026m12 PARTITION OF transactions_partitioned
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

-- Default partition
CREATE TABLE IF NOT EXISTS transactions_default PARTITION OF transactions_partitioned DEFAULT;

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_tp_user_id ON transactions_partitioned(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tp_type ON transactions_partitioned(type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tp_product ON transactions_partitioned(product_name, created_at DESC);

-- ============================================================================
-- 3. Partition auto-creation function (for ongoing maintenance)
--    Run monthly via pg_cron or a scheduled job to create future partitions.
-- ============================================================================

CREATE OR REPLACE FUNCTION create_monthly_partitions(
    p_table_name TEXT,
    p_months_ahead INT DEFAULT 3
)
RETURNS VOID AS $$
DECLARE
    v_start DATE;
    v_end DATE;
    v_partition_name TEXT;
    v_month TEXT;
    v_year TEXT;
BEGIN
    FOR i IN 0..p_months_ahead LOOP
        v_start := date_trunc('month', CURRENT_DATE + (i || ' months')::INTERVAL);
        v_end := v_start + INTERVAL '1 month';
        v_year := to_char(v_start, 'YYYY');
        v_month := to_char(v_start, 'MM');
        v_partition_name := p_table_name || '_y' || v_year || 'm' || v_month;

        -- Only create if it doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM pg_class WHERE relname = v_partition_name
        ) THEN
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                v_partition_name, p_table_name || '_partitioned', v_start, v_end
            );
            RAISE NOTICE 'Created partition: %', v_partition_name;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_monthly_partitions IS 'Creates future monthly partitions for partitioned tables. Run via pg_cron or scheduled job.';
