-- ============================================================================
-- Migration 004: Connection Pooling & Read Replica Configuration
-- ============================================================================
-- Configures PostgreSQL for connection pooling (pgbouncer) and read replicas.
-- These settings optimize the database for horizontal scaling patterns.
-- ============================================================================

-- ============================================================================
-- 1. Create dedicated roles for connection pooling
-- ============================================================================

-- Application role (used by pgbouncer to connect on behalf of the app)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'msaidizi_app') THEN
        CREATE ROLE msaidizi_app WITH LOGIN PASSWORD 'CHANGE_ME_APP_PASSWORD';
    END IF;
END
$$;

-- Read-only role (used by read replicas and pgbouncer read pool)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'msaidizi_readonly') THEN
        CREATE ROLE msaidizi_readonly WITH LOGIN PASSWORD 'CHANGE_ME_READONLY_PASSWORD';
    END IF;
END
$$;

-- Replication role (used by read replicas)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'msaidizi_replication') THEN
        CREATE ROLE msaidizi_replication WITH REPLICATION LOGIN PASSWORD 'CHANGE_ME_REPL_PASSWORD';
    END IF;
END
$$;

-- ============================================================================
-- 2. Grant permissions
-- ============================================================================

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO msaidizi_app;
GRANT USAGE ON SCHEMA public TO msaidizi_readonly;

-- Grant full access to app role (for read-write pool)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO msaidizi_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO msaidizi_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO msaidizi_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO msaidizi_app;

-- Grant read-only access to readonly role (for read pool / replicas)
GRANT SELECT ON ALL TABLES IN SCHEMA public TO msaidizi_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO msaidizi_readonly;

-- ============================================================================
-- 3. Optimized PostgreSQL settings for connection pooling
--    (Applied via ALTER SYSTEM or postgresql.conf — documented here)
-- ============================================================================

-- Connection settings (for pgbouncer compatibility)
-- max_connections = 200           # Higher than default, pgbouncer manages actual
-- superuser_reserved_connections = 3

-- Memory settings (for 2GB allocation)
-- shared_buffers = 512MB          # 25% of memory
-- effective_cache_size = 1536MB   # 75% of memory
-- work_mem = 16MB                 # Per-operation sort memory
-- maintenance_work_mem = 256MB    # VACUUM, CREATE INDEX memory

-- WAL settings (for replication)
-- wal_level = replica             # Required for streaming replication
-- max_wal_senders = 5             # Max concurrent replica connections
-- max_replication_slots = 5       # Max replication slots
-- wal_keep_size = 1024            # MB of WAL to keep for replicas

-- Checkpoint settings
-- checkpoint_completion_target = 0.9
-- max_wal_size = 2GB
-- min_wal_size = 512MB

-- Query optimization
-- random_page_cost = 1.1          # SSD-optimized (default 4.0 for HDD)
-- effective_io_concurrency = 200  # SSD-optimized (default 1 for HDD)
-- default_statistics_target = 100

-- ============================================================================
-- 4. Create replication slots for read replicas
-- ============================================================================

-- Create a replication slot (only works on primary)
-- SELECT pg_create_physical_replication_slot('replica_1', true);
-- (Uncomment when setting up actual replicas)

-- ============================================================================
-- 5. Monitoring views for connection pool health
-- ============================================================================

-- View: Active connections by role
CREATE OR REPLACE VIEW v_connection_stats AS
SELECT
    usename AS role_name,
    datname AS database_name,
    client_addr,
    state,
    COUNT(*) AS connection_count,
    MAX(query_start) AS latest_query
FROM pg_stat_activity
WHERE datname = 'msaidizi'
GROUP BY usename, datname, client_addr, state
ORDER BY connection_count DESC;

-- View: Replication lag (useful when replicas are active)
CREATE OR REPLACE VIEW v_replication_status AS
SELECT
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(sent_lsn, replay_lsn) AS replication_lag_bytes
FROM pg_stat_replication;

COMMENT ON VIEW v_connection_stats IS 'Monitor connection pool health: connections per role and state';
COMMENT ON VIEW v_replication_status IS 'Monitor replication lag between primary and replicas';
