-- ============================================================
-- Performance Indices for frequently queried columns
-- Adds composite and single-column indices for sync, OODA,
-- FL, and knowledge graph tables
-- ============================================================

-- Sync events performance
CREATE INDEX IF NOT EXISTS idx_sync_device_timestamp ON sync_events(device_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sync_region ON sync_events(region);
CREATE INDEX IF NOT EXISTS idx_sync_business_type ON sync_events(business_type);

-- OODA cycles performance
CREATE INDEX IF NOT EXISTS idx_ooda_cycles_speed_status ON ooda_cycles(cycle_speed, status);
CREATE INDEX IF NOT EXISTS idx_ooda_cycles_started_speed ON ooda_cycles(started_at DESC, cycle_speed);

-- FL model versions performance
CREATE INDEX IF NOT EXISTS idx_fl_models_name_version ON fl_model_versions(model_name, version);
CREATE INDEX IF NOT EXISTS idx_fl_models_created ON fl_model_versions(created_at DESC);

-- FL participant contributions performance
CREATE INDEX IF NOT EXISTS idx_fl_contributions_submitted ON fl_participant_contributions(submitted_at DESC);

-- Worker cohorts performance (for k-anonymity queries)
CREATE INDEX IF NOT EXISTS idx_kg_cohorts_type_region ON kg_worker_cohorts(worker_type, region_id);
CREATE INDEX IF NOT EXISTS idx_kg_cohorts_member_count ON kg_worker_cohorts(member_count);

-- Price points performance
CREATE INDEX IF NOT EXISTS idx_kg_prices_product_region ON kg_price_points(product_category_id, region_id);

-- Demand signals performance
CREATE INDEX IF NOT EXISTS idx_kg_signals_product_region ON kg_demand_signals(product_category_id, region_id);

-- Knowledge graph memory edges performance
CREATE INDEX IF NOT EXISTS idx_kg_mem_edges_source_type ON kg_memory_edges(source_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_kg_mem_edges_target_type ON kg_memory_edges(target_id, edge_type);
