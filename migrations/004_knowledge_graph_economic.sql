-- ============================================================
-- Economic Intelligence Knowledge Graph
-- Extends existing knowledge_nodes/knowledge_edges tables
-- with domain-specific node types and relationship constraints
-- ============================================================

-- Enable pgvector if not already enabled
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- NODE TYPE ENUMS
-- ============================================================

CREATE TYPE kg_node_type AS ENUM (
    'worker_cohort',        -- Anonymized worker group (k≥10)
    'product_category',     -- Product category with demand signals
    'regional_market',      -- Geographic market node
    'credit_risk',          -- Credit risk assessment node
    'alama_component',      -- Alama Score component
    'supply_chain_entity',  -- Supplier, distributor, wholesaler
    'economic_indicator',   -- CPI, GDP proxy, employment index
    'financial_product',    -- Loan, insurance, savings product
    'demand_signal',        -- Aggregated demand pattern
    'price_point',          -- Price observation at time+region
    'worker_type',          -- Taxonomy: mama_mboga, boda_boda, etc.
    'payment_channel'       -- M-Pesa, cash, bank transfer
);

CREATE TYPE kg_edge_type AS ENUM (
    'supply_chain',         -- supplier → product → retailer
    'demand_correlation',   -- product A demand correlates with B
    'price_elasticity',     -- price change → demand change relationship
    'serves_region',        -- entity → regional_market
    'has_credit_component', -- credit_risk → alama_component
    'competes_with',        -- product A competes with product B
    'complements',          -- product A complements product B
    'employs_type',         -- worker_cohort → worker_type
    'uses_channel',         -- worker_cohort → payment_channel
    'generates_signal',     -- worker_cohort → demand_signal
    'contributes_to',       -- worker_cohort → economic_indicator
    'associated_risk',      -- worker_cohort → credit_risk
    'available_via',        -- financial_product → payment_channel
    'correlates_with',      -- economic_indicator ↔ economic_indicator
    'substitutes_for',      -- product_category ↔ product_category
    'traded_in'             -- price_point → regional_market
);

-- ============================================================
-- WORKER COHORT NODES (anonymized, k≥10)
-- ============================================================

CREATE TABLE kg_worker_cohorts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cohort_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 of cohort dimensions
    worker_type VARCHAR(50) NOT NULL,          -- mama_mboga, boda_boda, etc.
    region_id VARCHAR(100) NOT NULL,           -- nairobi-eastlands, kisumu-central
    language_primary VARCHAR(20) NOT NULL,     -- sw, en, sh, dholuo
    scale_bucket VARCHAR(20) NOT NULL,         -- solo, micro, small
    member_count INT NOT NULL CHECK (member_count >= 10),  -- k-anonymity
    avg_daily_revenue DOUBLE PRECISION,
    avg_daily_transactions DOUBLE PRECISION,
    revenue_volatility DOUBLE PRECISION,       -- coefficient of variation
    active_days_ratio DOUBLE PRECISION,        -- % of days with transactions
    top_products JSONB NOT NULL DEFAULT '[]',  -- [{category, share_pct}]
    payment_mix JSONB NOT NULL DEFAULT '{}',   -- {mpesa: 0.6, cash: 0.4}
    embedding vector(1536),                    -- for similarity search
    last_aggregated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_cohorts_type ON kg_worker_cohorts(worker_type);
CREATE INDEX idx_kg_cohorts_region ON kg_worker_cohorts(region_id);
CREATE INDEX idx_kg_cohorts_hash ON kg_worker_cohorts(cohort_hash);
CREATE INDEX idx_kg_cohorts_embedding ON kg_worker_cohorts
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================
-- PRODUCT CATEGORY NODES
-- ============================================================

CREATE TABLE kg_product_categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category_code VARCHAR(50) NOT NULL UNIQUE,
    category_name VARCHAR(200) NOT NULL,
    parent_category_id UUID REFERENCES kg_product_categories(id),
    demand_trend VARCHAR(20) DEFAULT 'stable',
    avg_price_kes DOUBLE PRECISION,
    price_volatility DOUBLE PRECISION,
    seasonality_pattern JSONB DEFAULT '{}',
    cross_elasticities JSONB DEFAULT '{}',
    total_market_size_kes DOUBLE PRECISION,
    worker_penetration DOUBLE PRECISION,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_products_code ON kg_product_categories(category_code);
CREATE INDEX idx_kg_products_parent ON kg_product_categories(parent_category_id);
CREATE INDEX idx_kg_products_embedding ON kg_product_categories
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- ============================================================
-- REGIONAL MARKET NODES
-- ============================================================

CREATE TABLE kg_regional_markets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_code VARCHAR(100) NOT NULL UNIQUE,
    region_name VARCHAR(200) NOT NULL,
    region_level VARCHAR(20) NOT NULL,
    parent_region_id UUID REFERENCES kg_regional_markets(id),
    center_lat DOUBLE PRECISION,
    center_lon DOUBLE PRECISION,
    geohash VARCHAR(12),
    population_estimate INT,
    worker_density DOUBLE PRECISION,
    economic_activity_index DOUBLE PRECISION,
    avg_cost_of_living DOUBLE PRECISION,
    dominant_payment_channel VARCHAR(50),
    infrastructure_score DOUBLE PRECISION,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_regions_code ON kg_regional_markets(region_code);
CREATE INDEX idx_kg_regions_level ON kg_regional_markets(region_level);
CREATE INDEX idx_kg_regions_parent ON kg_regional_markets(parent_region_id);
CREATE INDEX idx_kg_regions_geohash ON kg_regional_markets(geohash);
CREATE INDEX idx_kg_regions_embedding ON kg_regional_markets
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- ============================================================
-- CREDIT RISK NODES
-- ============================================================

CREATE TABLE kg_credit_risk_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cohort_id UUID NOT NULL REFERENCES kg_worker_cohorts(id) ON DELETE CASCADE,
    alama_score DOUBLE PRECISION CHECK (alama_score >= 300 AND alama_score <= 850),
    risk_tier VARCHAR(20) NOT NULL,
    default_probability DOUBLE PRECISION,
    components JSONB NOT NULL DEFAULT '{}',
    loan_outcomes JSONB DEFAULT '{}',
    feature_vector DOUBLE PRECISION[],
    last_scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_credit_cohort ON kg_credit_risk_profiles(cohort_id);
CREATE INDEX idx_kg_credit_score ON kg_credit_risk_profiles(alama_score);
CREATE INDEX idx_kg_credit_tier ON kg_credit_risk_profiles(risk_tier);

-- ============================================================
-- SUPPLY CHAIN NODES
-- ============================================================

CREATE TABLE kg_supply_chain_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL,
    entity_name VARCHAR(300) NOT NULL,
    anonymized BOOLEAN NOT NULL DEFAULT true,
    region_id UUID REFERENCES kg_regional_markets(id),
    product_categories UUID[] NOT NULL DEFAULT '{}',
    reliability_score DOUBLE PRECISION,
    avg_lead_time_days DOUBLE PRECISION,
    min_order_size DOUBLE PRECISION,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_supply_type ON kg_supply_chain_entities(entity_type);
CREATE INDEX idx_kg_supply_region ON kg_supply_chain_entities(region_id);

-- ============================================================
-- ECONOMIC INDICATOR NODES
-- ============================================================

CREATE TABLE kg_economic_indicators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    indicator_code VARCHAR(50) NOT NULL UNIQUE,
    indicator_name VARCHAR(200) NOT NULL,
    indicator_type VARCHAR(50) NOT NULL,
    region_id UUID REFERENCES kg_regional_markets(id),
    current_value DOUBLE PRECISION,
    previous_value DOUBLE PRECISION,
    change_pct DOUBLE PRECISION,
    trend VARCHAR(20),
    confidence DOUBLE PRECISION,
    sample_size INT,
    last_calculated_at TIMESTAMPTZ,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_indicators_code ON kg_economic_indicators(indicator_code);
CREATE INDEX idx_kg_indicators_type ON kg_economic_indicators(indicator_type);
CREATE INDEX idx_kg_indicators_region ON kg_economic_indicators(region_id);

-- ============================================================
-- FINANCIAL PRODUCT NODES
-- ============================================================

CREATE TABLE kg_financial_products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_type VARCHAR(50) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    provider VARCHAR(200) NOT NULL,
    min_amount DOUBLE PRECISION,
    max_amount DOUBLE PRECISION,
    interest_rate DOUBLE PRECISION,
    term_days INT,
    eligibility_criteria JSONB DEFAULT '{}',
    target_worker_types VARCHAR(50)[] DEFAULT '{}',
    target_regions VARCHAR(100)[] DEFAULT '{}',
    approval_rate DOUBLE PRECISION,
    default_rate DOUBLE PRECISION,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_financial_type ON kg_financial_products(product_type);
CREATE INDEX idx_kg_financial_provider ON kg_financial_products(provider);

-- ============================================================
-- DEMAND SIGNAL NODES
-- ============================================================

CREATE TABLE kg_demand_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_category_id UUID NOT NULL REFERENCES kg_product_categories(id),
    region_id UUID NOT NULL REFERENCES kg_regional_markets(id),
    signal_type VARCHAR(50) NOT NULL,
    signal_strength DOUBLE PRECISION NOT NULL,
    direction VARCHAR(20) NOT NULL,
    magnitude_pct DOUBLE PRECISION,
    duration_estimate VARCHAR(50),
    contributing_cohorts UUID[] DEFAULT '{}',
    confidence DOUBLE PRECISION NOT NULL,
    sample_size INT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_signals_product ON kg_demand_signals(product_category_id);
CREATE INDEX idx_kg_signals_region ON kg_demand_signals(region_id);
CREATE INDEX idx_kg_signals_type ON kg_demand_signals(signal_type);
CREATE INDEX idx_kg_signals_detected ON kg_demand_signals(detected_at DESC);

-- ============================================================
-- PRICE POINT NODES
-- ============================================================

CREATE TABLE kg_price_points (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_category_id UUID NOT NULL REFERENCES kg_product_categories(id),
    region_id UUID NOT NULL REFERENCES kg_regional_markets(id),
    price_kes DOUBLE PRECISION NOT NULL,
    unit VARCHAR(20) NOT NULL,
    sample_size INT NOT NULL,
    price_percentile_25 DOUBLE PRECISION,
    price_percentile_75 DOUBLE PRECISION,
    price_change_7d DOUBLE PRECISION,
    price_change_30d DOUBLE PRECISION,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kg_prices_product ON kg_price_points(product_category_id);
CREATE INDEX idx_kg_prices_region ON kg_price_points(region_id);
CREATE INDEX idx_kg_prices_recorded ON kg_price_points(recorded_at DESC);

-- ============================================================
-- GENERIC EDGES TABLE
-- ============================================================

CREATE TABLE kg_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type kg_node_type NOT NULL,
    source_id UUID NOT NULL,
    target_type kg_node_type NOT NULL,
    target_id UUID NOT NULL,
    edge_type kg_edge_type NOT NULL,
    weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    properties JSONB NOT NULL DEFAULT '{}',
    sample_size INT,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (sample_size IS NULL OR sample_size >= 10),
    CHECK (source_id != target_id OR source_type != target_type)
);

CREATE INDEX idx_kg_edges_source ON kg_edges(source_type, source_id);
CREATE INDEX idx_kg_edges_target ON kg_edges(target_type, target_id);
CREATE INDEX idx_kg_edges_type ON kg_edges(edge_type);
CREATE INDEX idx_kg_edges_valid ON kg_edges(valid_from, valid_until)
    WHERE valid_until IS NULL;
CREATE INDEX idx_kg_edges_traversal ON kg_edges(source_type, source_id, edge_type, target_type);

-- ============================================================
-- VIEWS
-- ============================================================

CREATE VIEW kg_supply_chain_graph AS
SELECT
    wc.id AS cohort_id,
    wc.worker_type,
    wc.region_id AS cohort_region,
    e.edge_type,
    e.weight,
    pc.category_code,
    pc.category_name,
    rm.region_code AS market_region,
    dp.price_kes AS current_avg_price
FROM kg_worker_cohorts wc
JOIN kg_edges e ON e.source_id = wc.id AND e.source_type = 'worker_cohort'
JOIN kg_product_categories pc ON pc.id = e.target_id AND e.target_type = 'product_category'
LEFT JOIN kg_edges e2 ON e2.source_id = pc.id AND e2.edge_type = 'traded_in'
LEFT JOIN kg_regional_markets rm ON rm.id = e2.target_id
LEFT JOIN kg_price_points dp ON dp.product_category_id = pc.id
    AND dp.region_id = rm.id
    AND dp.recorded_at > NOW() - INTERVAL '24 hours';

CREATE VIEW kg_credit_graph AS
SELECT
    wc.id AS cohort_id,
    wc.worker_type,
    wc.region_id,
    cr.alama_score,
    cr.risk_tier,
    cr.components,
    cr.default_probability,
    e.weight AS risk_weight,
    fp.product_name AS eligible_product,
    fp.max_amount AS max_loan_amount
FROM kg_worker_cohorts wc
JOIN kg_edges e ON e.source_id = wc.id AND e.edge_type = 'associated_risk'
JOIN kg_credit_risk_profiles cr ON cr.id = e.target_id
LEFT JOIN kg_financial_products fp ON
    cr.alama_score >= (fp.eligibility_criteria->>'min_alama_score')::DOUBLE PRECISION
    AND wc.worker_type = ANY(fp.target_worker_types);

CREATE VIEW kg_demand_intelligence AS
SELECT
    pc.category_code,
    pc.category_name,
    rm.region_code,
    rm.region_name,
    ds.signal_type,
    ds.signal_strength,
    ds.direction,
    ds.magnitude_pct,
    ds.confidence,
    ds.sample_size,
    ds.detected_at,
    ds.expires_at
FROM kg_demand_signals ds
JOIN kg_product_categories pc ON pc.id = ds.product_category_id
JOIN kg_regional_markets rm ON rm.id = ds.region_id
WHERE ds.expires_at IS NULL OR ds.expires_at > NOW()
ORDER BY ds.signal_strength DESC;

CREATE MATERIALIZED VIEW kg_graph_stats AS
SELECT
    'worker_cohort' AS node_type,
    COUNT(*) AS node_count,
    SUM(member_count) AS represented_workers,
    AVG(member_count) AS avg_cohort_size
FROM kg_worker_cohorts
UNION ALL
SELECT 'product_category', COUNT(*), NULL, NULL FROM kg_product_categories
UNION ALL
SELECT 'regional_market', COUNT(*), NULL, NULL FROM kg_regional_markets
UNION ALL
SELECT 'credit_risk', COUNT(*), NULL, NULL FROM kg_credit_risk_profiles
UNION ALL
SELECT 'demand_signal', COUNT(*), NULL, NULL FROM kg_demand_signals
WHERE expires_at IS NULL OR expires_at > NOW()
UNION ALL
SELECT 'total_edges', COUNT(*), NULL, NULL FROM kg_edges
WHERE valid_until IS NULL;

CREATE UNIQUE INDEX idx_kg_graph_stats_type ON kg_graph_stats(node_type);
