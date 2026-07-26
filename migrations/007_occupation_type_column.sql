-- Add occupation_type to worker cohorts if not present
ALTER TABLE kg_worker_cohorts
ADD COLUMN IF NOT EXISTS occupation_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS county_code VARCHAR(10);

-- Index for occupation-based queries
CREATE INDEX IF NOT EXISTS idx_worker_cohorts_occupation
ON kg_worker_cohorts(occupation_type);
