-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE user_role AS ENUM ('admin', 'analyst', 'viewer', 'api_user');
CREATE TYPE memory_layer AS ENUM ('working', 'short_term', 'long_term', 'episodic', 'semantic');
CREATE TYPE intelligence_module AS ENUM (
    'revenue_forecasting', 'customer_behavior', 'market_analysis',
    'risk_assessment', 'pricing_optimization', 'churn_prediction'
);
CREATE TYPE task_status AS ENUM ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled', 'retrying');
CREATE TYPE ooda_phase AS ENUM ('observe', 'orient', 'decide', 'act');
CREATE TYPE sync_status AS ENUM ('synced', 'pending', 'conflict', 'error');
CREATE TYPE federated_status AS ENUM ('collecting', 'aggregating', 'distributing', 'completed', 'failed');
CREATE TYPE participant_status AS ENUM ('invited', 'training', 'submitted', 'aggregated', 'dropped');

-- ============================================================
-- ORGANIZATIONS
-- ============================================================

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    plan VARCHAR(50) NOT NULL DEFAULT 'free',
    max_users INT NOT NULL DEFAULT 10,
    max_api_calls BIGINT NOT NULL DEFAULT 100000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_organizations_slug ON organizations(slug);
CREATE INDEX idx_organizations_plan ON organizations(plan);

-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role user_role NOT NULL DEFAULT 'viewer',
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_organization ON users(organization_id);
CREATE INDEX idx_users_role ON users(role);

-- ============================================================
-- INTELLIGENCE TASKS
-- ============================================================

CREATE TABLE intelligence_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    module intelligence_module NOT NULL,
    phase ooda_phase NOT NULL DEFAULT 'observe',
    status task_status NOT NULL DEFAULT 'pending',
    input_data JSONB NOT NULL,
    output_data JSONB,
    error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NOT NULL REFERENCES users(id),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_intelligence_tasks_org ON intelligence_tasks(organization_id);
CREATE INDEX idx_intelligence_tasks_status ON intelligence_tasks(status);
CREATE INDEX idx_intelligence_tasks_module ON intelligence_tasks(module);
CREATE INDEX idx_intelligence_tasks_created ON intelligence_tasks(created_at DESC);

-- ============================================================
-- REVENUE FORECASTS
-- ============================================================

CREATE TABLE revenue_forecasts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    forecast_date DATE NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    predicted_revenue DOUBLE PRECISION NOT NULL,
    confidence_lower DOUBLE PRECISION NOT NULL,
    confidence_upper DOUBLE PRECISION NOT NULL,
    confidence_level DOUBLE PRECISION NOT NULL DEFAULT 0.95,
    model_version VARCHAR(50) NOT NULL,
    features_used JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_revenue_forecasts_org ON revenue_forecasts(organization_id);
CREATE INDEX idx_revenue_forecasts_date ON revenue_forecasts(forecast_date);

-- ============================================================
-- CHURN PREDICTIONS
-- ============================================================

CREATE TABLE churn_predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    churn_probability DOUBLE PRECISION NOT NULL,
    churn_risk VARCHAR(20) NOT NULL,
    key_factors JSONB NOT NULL DEFAULT '[]',
    retention_actions TEXT[] NOT NULL DEFAULT '{}',
    predicted_churn_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_churn_predictions_org ON churn_predictions(organization_id);
CREATE INDEX idx_churn_predictions_customer ON churn_predictions(customer_id);
CREATE INDEX idx_churn_predictions_risk ON churn_predictions(churn_risk);

-- ============================================================
-- MEMORY ENTRIES
-- ============================================================

CREATE TABLE memory_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    layer memory_layer NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    importance_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    access_count INT NOT NULL DEFAULT 0,
    last_accessed TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}',
    tags TEXT[] NOT NULL DEFAULT '{}',
    source VARCHAR(255) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_memory_entries_user ON memory_entries(user_id);
CREATE INDEX idx_memory_entries_org ON memory_entries(organization_id);
CREATE INDEX idx_memory_entries_layer ON memory_entries(layer);
CREATE INDEX idx_memory_entries_importance ON memory_entries(importance_score DESC);
CREATE INDEX idx_memory_entries_expires ON memory_entries(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_memory_entries_tags ON memory_entries USING GIN(tags);

-- ============================================================
-- AGENTS
-- ============================================================

CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'idle',
    capabilities TEXT[] NOT NULL DEFAULT '{}',
    config JSONB NOT NULL DEFAULT '{}',
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_agents_type ON agents(agent_type);
CREATE INDEX idx_agents_status ON agents(status);

-- ============================================================
-- AGENT TASKS
-- ============================================================

CREATE TABLE agent_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    task_type VARCHAR(100) NOT NULL,
    priority INT NOT NULL DEFAULT 0,
    status task_status NOT NULL DEFAULT 'pending',
    input JSONB NOT NULL,
    output JSONB,
    error TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NOT NULL REFERENCES users(id)
);

CREATE INDEX idx_agent_tasks_agent ON agent_tasks(agent_id);
CREATE INDEX idx_agent_tasks_status ON agent_tasks(status);
CREATE INDEX idx_agent_tasks_priority ON agent_tasks(priority DESC, created_at);

-- ============================================================
-- CUSTOMER BEHAVIORS
-- ============================================================

CREATE TABLE customer_behaviors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    behavior_type VARCHAR(100) NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    features JSONB NOT NULL DEFAULT '{}',
    segments TEXT[] NOT NULL DEFAULT '{}',
    risk_level VARCHAR(20) NOT NULL DEFAULT 'low',
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_customer_behaviors_org ON customer_behaviors(organization_id);
CREATE INDEX idx_customer_behaviors_customer ON customer_behaviors(customer_id);

-- ============================================================
-- MARKET ANALYSES
-- ============================================================

CREATE TABLE market_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    market_segment VARCHAR(255) NOT NULL,
    analysis_type VARCHAR(100) NOT NULL,
    metrics JSONB NOT NULL DEFAULT '{}',
    insights TEXT[] NOT NULL DEFAULT '{}',
    recommendations TEXT[] NOT NULL DEFAULT '{}',
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    period VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_analyses_org ON market_analyses(organization_id);

-- ============================================================
-- RISK ASSESSMENTS
-- ============================================================

CREATE TABLE risk_assessments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    risk_score DOUBLE PRECISION NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    risk_factors JSONB NOT NULL DEFAULT '{}',
    mitigation_strategies TEXT[] NOT NULL DEFAULT '{}',
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_risk_assessments_org ON risk_assessments(organization_id);
CREATE INDEX idx_risk_assessments_entity ON risk_assessments(entity_type, entity_id);

-- ============================================================
-- PRICING OPTIMIZATIONS
-- ============================================================

CREATE TABLE pricing_optimizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    product_id UUID NOT NULL,
    current_price DOUBLE PRECISION NOT NULL,
    recommended_price DOUBLE PRECISION NOT NULL,
    expected_revenue_impact DOUBLE PRECISION NOT NULL,
    elasticity DOUBLE PRECISION NOT NULL,
    competitive_position VARCHAR(50) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pricing_optimizations_org ON pricing_optimizations(organization_id);

-- ============================================================
-- INTELLIGENCE INSIGHTS
-- ============================================================

CREATE TABLE intelligence_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    module intelligence_module NOT NULL,
    insight_type VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    data JSONB NOT NULL DEFAULT '{}',
    actionable BOOLEAN NOT NULL DEFAULT false,
    acknowledged BOOLEAN NOT NULL DEFAULT false,
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_intelligence_insights_org ON intelligence_insights(organization_id);
CREATE INDEX idx_intelligence_insights_module ON intelligence_insights(module);
CREATE INDEX idx_intelligence_insights_severity ON intelligence_insights(severity);

-- ============================================================
-- CONVERSATION CONTEXTS
-- ============================================================

CREATE TABLE conversation_contexts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]',
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversation_contexts_user ON conversation_contexts(user_id);
CREATE INDEX idx_conversation_contexts_session ON conversation_contexts(session_id);

-- ============================================================
-- KNOWLEDGE GRAPH NODES
-- ============================================================

CREATE TABLE knowledge_nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    node_type VARCHAR(100) NOT NULL,
    label VARCHAR(500) NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_knowledge_nodes_org ON knowledge_nodes(organization_id);
CREATE INDEX idx_knowledge_nodes_type ON knowledge_nodes(node_type);

-- ============================================================
-- KNOWLEDGE GRAPH EDGES
-- ============================================================

CREATE TABLE knowledge_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_node_id UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    relationship VARCHAR(255) NOT NULL,
    weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    properties JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_knowledge_edges_source ON knowledge_edges(source_node_id);
CREATE INDEX idx_knowledge_edges_target ON knowledge_edges(target_node_id);
CREATE INDEX idx_knowledge_edges_relationship ON knowledge_edges(relationship);

-- ============================================================
-- DEVICE SYNC
-- ============================================================

CREATE TABLE device_syncs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id VARCHAR(255) NOT NULL,
    device_type VARCHAR(50) NOT NULL,
    device_name VARCHAR(255) NOT NULL,
    last_sync TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sync_version BIGINT NOT NULL DEFAULT 0,
    status sync_status NOT NULL DEFAULT 'pending',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, device_id)
);

CREATE INDEX idx_device_syncs_user ON device_syncs(user_id);
CREATE INDEX idx_device_syncs_device ON device_syncs(device_id);

-- ============================================================
-- FEDERATED MODELS
-- ============================================================

CREATE TABLE federated_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name VARCHAR(255) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    global_weights FLOAT[] NOT NULL DEFAULT '{}',
    participants UUID[] NOT NULL DEFAULT '{}',
    round_number INT NOT NULL DEFAULT 0,
    status federated_status NOT NULL DEFAULT 'collecting',
    metrics JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_federated_models_name ON federated_models(model_name);
CREATE INDEX idx_federated_models_status ON federated_models(status);

-- ============================================================
-- FEDERATED PARTICIPANTS
-- ============================================================

CREATE TABLE federated_participants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_id UUID NOT NULL REFERENCES federated_models(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    device_id VARCHAR(255) NOT NULL,
    local_weights FLOAT[],
    gradient_norm DOUBLE PRECISION,
    data_samples INT NOT NULL DEFAULT 0,
    status participant_status NOT NULL DEFAULT 'invited',
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_federated_participants_model ON federated_participants(model_id);
CREATE INDEX idx_federated_participants_user ON federated_participants(user_id);
