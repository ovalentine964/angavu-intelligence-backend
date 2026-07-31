-- ============================================================
-- OODA Loop State Tracking & Pipeline DAG
-- ============================================================

CREATE TYPE ooda_cycle_speed AS ENUM ('fast', 'hourly', 'daily', 'weekly');
CREATE TYPE ooda_node_status AS ENUM ('pending', 'running', 'completed', 'failed', 'skipped', 'circuit_open');
CREATE TYPE pipeline_node_status AS ENUM ('pending', 'running', 'completed', 'failed', 'skipped', 'retrying', 'circuit_open');

-- ============================================================
-- OODA CYCLES
-- ============================================================

CREATE TABLE ooda_cycles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_speed ooda_cycle_speed NOT NULL,
    cycle_number BIGINT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    trigger_source VARCHAR(100),
    trigger_metadata JSONB DEFAULT '{}',
    total_duration_ms BIGINT,
    metadata JSONB NOT NULL DEFAULT '{}',
    UNIQUE (cycle_speed, cycle_number)
);

CREATE INDEX idx_ooda_cycles_speed ON ooda_cycles(cycle_speed);
CREATE INDEX idx_ooda_cycles_status ON ooda_cycles(status);
CREATE INDEX idx_ooda_cycles_started ON ooda_cycles(started_at DESC);

-- ============================================================
-- OODA PHASE EXECUTIONS
-- ============================================================

CREATE TABLE ooda_phase_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID NOT NULL REFERENCES ooda_cycles(id) ON DELETE CASCADE,
    phase ooda_phase NOT NULL,
    status ooda_node_status NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    input_data JSONB DEFAULT '{}',
    output_data JSONB DEFAULT '{}',
    error_message TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    circuit_breaker_state VARCHAR(20) DEFAULT 'closed',
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_ooda_phase_cycle ON ooda_phase_executions(cycle_id);
CREATE INDEX idx_ooda_phase_status ON ooda_phase_executions(status);

-- ============================================================
-- OODA EDGE EXECUTIONS
-- ============================================================

CREATE TABLE ooda_edge_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID NOT NULL REFERENCES ooda_cycles(id) ON DELETE CASCADE,
    source_phase ooda_phase NOT NULL,
    target_phase ooda_phase NOT NULL,
    data_transferred JSONB DEFAULT '{}',
    transfer_ms BIGINT,
    condition_evaluated VARCHAR(100),
    condition_result BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ooda_edge_cycle ON ooda_edge_executions(cycle_id);

-- ============================================================
-- PIPELINE DEFINITIONS
-- ============================================================

CREATE TABLE pipeline_definitions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pipeline_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    dag_definition JSONB NOT NULL,
    version INT NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- PIPELINE EXECUTIONS
-- ============================================================

CREATE TABLE pipeline_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pipeline_id UUID NOT NULL REFERENCES pipeline_definitions(id),
    execution_number BIGINT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    trigger_source VARCHAR(100),
    metadata JSONB NOT NULL DEFAULT '{}',
    UNIQUE (pipeline_id, execution_number)
);

CREATE INDEX idx_pipeline_executions_pipeline ON pipeline_executions(pipeline_id);
CREATE INDEX idx_pipeline_executions_status ON pipeline_executions(status);

-- ============================================================
-- PIPELINE NODE EXECUTIONS
-- ============================================================

CREATE TABLE pipeline_node_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id UUID NOT NULL REFERENCES pipeline_executions(id) ON DELETE CASCADE,
    node_name VARCHAR(100) NOT NULL,
    node_type VARCHAR(50) NOT NULL,
    status pipeline_node_status NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    input_data JSONB DEFAULT '{}',
    output_data JSONB DEFAULT '{}',
    error_message TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    circuit_breaker_state VARCHAR(20) DEFAULT 'closed',
    circuit_breaker_failures INT NOT NULL DEFAULT 0,
    depends_on TEXT[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_pipeline_node_exec ON pipeline_node_executions(execution_id);
CREATE INDEX idx_pipeline_node_status ON pipeline_node_executions(status);

-- ============================================================
-- FEDERATED LEARNING MODEL VERSIONS
-- ============================================================

CREATE TABLE fl_model_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    parent_version_id UUID REFERENCES fl_model_versions(id),
    aggregation_algorithm VARCHAR(50) NOT NULL DEFAULT 'fedprox',
    participant_count INT NOT NULL DEFAULT 0,
    cohort_breakdown JSONB DEFAULT '{}',
    global_metrics JSONB DEFAULT '{}',
    delta_size_bytes BIGINT,
    privacy_epsilon DOUBLE PRECISION,
    privacy_delta DOUBLE PRECISION,
    status VARCHAR(20) NOT NULL DEFAULT 'training',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (model_name, version)
);

CREATE INDEX idx_fl_models_name ON fl_model_versions(model_name);
CREATE INDEX idx_fl_models_status ON fl_model_versions(status);

-- ============================================================
-- FL PARTICIPANT CONTRIBUTIONS
-- ============================================================

CREATE TABLE fl_participant_contributions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_version_id UUID NOT NULL REFERENCES fl_model_versions(id) ON DELETE CASCADE,
    cohort_hash VARCHAR(64) NOT NULL,
    participant_count INT NOT NULL CHECK (participant_count >= 10),
    gradient_norm DOUBLE PRECISION,
    local_loss DOUBLE PRECISION,
    local_accuracy DOUBLE PRECISION,
    data_samples INT NOT NULL,
    contribution_weight DOUBLE PRECISION,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (model_version_id, cohort_hash)
);

CREATE INDEX idx_fl_contributions_model ON fl_participant_contributions(model_version_id);
CREATE INDEX idx_fl_contributions_cohort ON fl_participant_contributions(cohort_hash);

-- ============================================================
-- FL MODEL DISTRIBUTIONS
-- ============================================================

CREATE TABLE fl_model_distributions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_version_id UUID NOT NULL REFERENCES fl_model_versions(id) ON DELETE CASCADE,
    target_cohort_hash VARCHAR(64),
    target_region VARCHAR(100),
    delta_url VARCHAR(500),
    delta_size_bytes BIGINT,
    delivery_method VARCHAR(20) NOT NULL,
    devices_reached INT DEFAULT 0,
    devices_applied INT DEFAULT 0,
    devices_rolled_back INT DEFAULT 0,
    rollback_rate DOUBLE PRECISION,
    distributed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (model_version_id, target_cohort_hash)
);

CREATE INDEX idx_fl_distributions_model ON fl_model_distributions(model_version_id);
