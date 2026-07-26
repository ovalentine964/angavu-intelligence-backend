-- Occupation hazard definitions
CREATE TABLE kg_occupation_hazards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occupation_type VARCHAR(50) NOT NULL,
    hazard_id VARCHAR(100) NOT NULL,
    hazard_category VARCHAR(50) NOT NULL,
    hazard_name VARCHAR(200) NOT NULL,
    hazard_description TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    base_risk_multiplier DECIMAL(3,1) NOT NULL,
    prevalence DECIMAL(4,3) NOT NULL,
    who_reference VARCHAR(100),
    recommended_insurance JSONB NOT NULL,
    data_signals JSONB NOT NULL,
    mitigation_factors JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(occupation_type, hazard_id)
);

-- Regional disease and health facility data
CREATE TABLE kg_location_health_risk (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    county_code VARCHAR(10) NOT NULL,
    sub_county VARCHAR(100),
    malaria_risk VARCHAR(20),
    tuberculosis_risk VARCHAR(20),
    hiv_prevalence VARCHAR(20),
    waterborne_disease_risk VARCHAR(20),
    rift_valley_fever_risk VARCHAR(20),
    schistosomiasis_risk VARCHAR(20),
    nearest_health_center_km DECIMAL(6,1),
    nearest_hospital_km DECIMAL(6,1),
    has_emergency_services BOOLEAN,
    ambulance_availability VARCHAR(30),
    water_source VARCHAR(30),
    sanitation_level VARCHAR(30),
    pm25_level DECIMAL(6,1),
    overall_location_multiplier DECIMAL(3,2),
    data_source VARCHAR(100),
    data_year INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(county_code, sub_county)
);

-- Insurance product catalog
CREATE TABLE kg_insurance_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_type VARCHAR(50) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    provider VARCHAR(200) NOT NULL,
    monthly_premium_base DECIMAL(10,2) NOT NULL,
    coverage_amount DECIMAL(12,2) NOT NULL,
    coverage_description TEXT,
    eligibility_criteria JSONB NOT NULL,
    risk_loadings JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Worker health risk assessments (computed, anonymized)
CREATE TABLE kg_health_risk_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_cohort_id UUID NOT NULL REFERENCES kg_worker_cohorts(id),
    assessment_date DATE NOT NULL,
    occupation_type VARCHAR(50) NOT NULL,
    county_code VARCHAR(10) NOT NULL,
    overall_risk_score DECIMAL(3,1) NOT NULL,
    risk_tier VARCHAR(20) NOT NULL,
    occupation_risk_score DECIMAL(3,1) NOT NULL,
    location_multiplier DECIMAL(3,2) NOT NULL,
    exposure_adjustment DECIMAL(3,2) NOT NULL,
    income_stability_factor DECIMAL(3,2) NOT NULL,
    protective_adjustment DECIMAL(3,2) NOT NULL,
    top_hazards JSONB NOT NULL,
    risk_explanation JSONB NOT NULL,
    insurance_eligibility JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- k-anonymity: only store if cohort has ≥10 workers
    CHECK (true)  -- Enforced at application layer via kAnonymityEnforcer
);

-- Indexes
CREATE INDEX idx_occupation_hazards_type ON kg_occupation_hazards(occupation_type);
CREATE INDEX idx_location_health_risk_county ON kg_location_health_risk(county_code);
CREATE INDEX idx_health_risk_cohort ON kg_health_risk_assessments(worker_cohort_id);
CREATE INDEX idx_health_risk_date ON kg_health_risk_assessments(assessment_date);
CREATE INDEX idx_health_risk_tier ON kg_health_risk_assessments(risk_tier);
