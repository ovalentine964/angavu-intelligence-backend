-- migrations/20260727000001_multi_agent_orchestration.sql

-- Audit log for inter-module communication
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trace_id UUID NOT NULL,
    message_type VARCHAR(64) NOT NULL,
    source_module VARCHAR(64) NOT NULL,
    destination_module VARCHAR(64),
    priority VARCHAR(16) NOT NULL,
    payload_size_bytes INTEGER,
    org_id VARCHAR(64),
    endpoint VARCHAR(256),
    status_code INTEGER,
    response_time_ms BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_log_timestamp ON audit_log (timestamp DESC);
CREATE INDEX idx_audit_log_trace ON audit_log (trace_id);
CREATE INDEX idx_audit_log_org ON audit_log (org_id, timestamp DESC);

-- Orchestrator cycle history
CREATE TABLE IF NOT EXISTS orchestrator_cycles (
    id BIGSERIAL PRIMARY KEY,
    cycle_number BIGINT NOT NULL,
    phase VARCHAR(32) NOT NULL,
    messages_processed BIGINT NOT NULL,
    anomalies_detected INTEGER NOT NULL,
    patterns_found INTEGER NOT NULL,
    duration_ms BIGINT NOT NULL,
    actions_taken JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Detected cross-module patterns
CREATE TABLE IF NOT EXISTS emergent_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_type VARCHAR(64) NOT NULL,
    region VARCHAR(128),
    modules_involved VARCHAR(64)[] NOT NULL,
    correlation_strength DOUBLE PRECISION NOT NULL,
    description TEXT NOT NULL,
    actionable BOOLEAN NOT NULL DEFAULT FALSE,
    acted_upon BOOLEAN NOT NULL DEFAULT FALSE,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Worker credit scores (Alama Score)
CREATE TABLE IF NOT EXISTS alama_scores (
    worker_id_hash VARCHAR(64) PRIMARY KEY,
    score INTEGER NOT NULL CHECK (score >= 300 AND score <= 850),
    risk_level VARCHAR(16) NOT NULL,
    factors JSONB NOT NULL DEFAULT '[]',
    confidence DOUBLE PRECISION NOT NULL,
    previous_score INTEGER,
    score_change INTEGER GENERATED ALWAYS AS (score - COALESCE(previous_score, score)) STORED,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alama_scores_risk ON alama_scores (risk_level, score);
