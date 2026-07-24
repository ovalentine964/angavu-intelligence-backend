-- ============================================================================
-- Run All Migrations
-- ============================================================================
-- Execute this file to apply all database migrations in order.
-- Safe to run multiple times (all statements use IF NOT EXISTS).
--
-- Usage:
--   psql -U msaidizi -d msaidizi -f database/migrations/run_all.sql
--   OR via docker:
--   docker exec -i msaidizi-postgres psql -U msaidizi -d msaidizi < database/migrations/run_all.sql
-- ============================================================================

\echo '=== Migration 001: pgvector Extension & Agent Memory ==='
\i 001_enable_pgvector.sql

\echo '=== Migration 002: TimescaleDB & Transaction Events ==='
\i 002_enable_timescaledb.sql

\echo '=== Migration 003: Table Partitioning ==='
\i 003_table_partitioning.sql

\echo '=== Migration 004: Connection Pooling & Read Replica Config ==='
\i 004_connection_pooling_and_replicas.sql

\echo '=== All migrations complete ==='
