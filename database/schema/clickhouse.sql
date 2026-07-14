-- ============================================================================
-- Angavu Intelligence — ClickHouse Schema
-- ============================================================================
-- Analytics tables for 600M+ records. Designed for:
--   - Time-series queries (prices, transactions over time)
--   - Aggregate analytics (GDP, inflation, employment)
--   - Dashboard queries (real-time metrics)
--   - Report generation (historical analysis)
--
-- ClickHouse is 30-200x faster than PostgreSQL for these workloads.
-- ============================================================================

-- Ensure database exists (created by CLICKHOUSE_DB env var, but safe to repeat)
CREATE DATABASE IF NOT EXISTS biashara;

-- ============================================================================
-- 1. transactions_analytics
-- Denormalized transaction facts for fast aggregation.
-- Partitioned by month on `date` for efficient range scans.
-- Ordered by (region, product_category, date) for common GROUP BY patterns.
-- ============================================================================
CREATE TABLE IF NOT EXISTS biashara.transactions_analytics
(
    date                Date,
    region              LowCardinality(String),
    sub_county          LowCardinality(String)     DEFAULT '',
    product_category    LowCardinality(String),
    product_name        String                      DEFAULT '',
    payment_method      LowCardinality(String)      DEFAULT 'cash',
    volume              UInt64,                     -- number of transactions
    amount              Decimal128(2),              -- total monetary value (KES)
    quantity            UInt64                      DEFAULT 0,  -- items sold
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (region, product_category, date)
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 2. economic_indicators
-- Regional economic estimates derived from transaction data + external sources.
-- Partitioned by month, ordered by (region, date) for geo-temporal queries.
-- ============================================================================
CREATE TABLE IF NOT EXISTS biashara.economic_indicators
(
    date                Date,
    region              LowCardinality(String),
    sub_county          LowCardinality(String)     DEFAULT '',
    gdp_estimate        Decimal128(2),              -- estimated regional GDP (KES millions)
    inflation_estimate  Decimal128(4),              -- estimated inflation rate (percent)
    employment_rate     Decimal128(4),              -- estimated employment rate (percent, 0-100)
    informal_sector_pct Decimal128(4)    DEFAULT 0, -- informal economy share (percent)
    confidence_score    Float32           DEFAULT 0 -- 0-1 confidence in the estimate
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (region, date)
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 3. market_data
-- Product-level market intelligence: supply, demand, pricing trends.
-- Partitioned by month, ordered by (product, region, date) for product analytics.
-- ============================================================================
CREATE TABLE IF NOT EXISTS biashara.market_data
(
    date                Date,
    product             LowCardinality(String),
    product_category    LowCardinality(String)     DEFAULT '',
    region              LowCardinality(String),
    sub_county          LowCardinality(String)     DEFAULT '',
    supply_index        Decimal128(4),              -- relative supply score (0-100)
    demand_index        Decimal128(4),              -- relative demand score (0-100)
    price               Decimal128(2),              -- average observed price (KES)
    price_change_pct    Decimal128(4)    DEFAULT 0, -- day-over-day price change (percent)
    transaction_count   UInt64           DEFAULT 0, -- underlying transaction count
    vendor_count        UInt32           DEFAULT 0  -- unique vendors in sample
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (product, region, date)
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 4. worker_activity
-- Worker/economic-participant metrics by region and time.
-- Partitioned by month, ordered by (region, date) for regional dashboards.
-- ============================================================================
CREATE TABLE IF NOT EXISTS biashara.worker_activity
(
    date                    Date,
    region                  LowCardinality(String),
    sub_county              LowCardinality(String)     DEFAULT '',
    active_workers          UInt32,                     -- workers with ≥1 transaction
    new_workers             UInt32          DEFAULT 0,  -- first-time workers
    returning_workers       UInt32          DEFAULT 0,  -- workers active this period & prior
    transactions_per_worker Decimal128(4)   DEFAULT 0,  -- avg transactions per active worker
    avg_income              Decimal128(2)   DEFAULT 0,  -- avg daily income per worker (KES)
    total_income            Decimal128(2)   DEFAULT 0,  -- total worker income (KES)
    top_category            LowCardinality(String) DEFAULT '' -- most common product category
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (region, date)
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 5. Materialized Views — real-time incremental aggregation
-- ============================================================================

-- Daily transaction totals (auto-populated from inserts into transactions_analytics)
CREATE MATERIALIZED VIEW IF NOT EXISTS biashara.mv_daily_transaction_totals
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (region, date)
AS
SELECT
    date,
    region,
    sum(volume)     AS total_volume,
    sum(amount)     AS total_amount,
    sum(quantity)    AS total_quantity,
    count()          AS row_count
FROM biashara.transactions_analytics
GROUP BY date, region;

-- Weekly economic indicator averages (auto-aggregated)
CREATE MATERIALIZED VIEW IF NOT EXISTS biashara.mv_weekly_economic_summary
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(week_start)
ORDER BY (region, week_start)
AS
SELECT
    toMonday(date)                              AS week_start,
    region,
    avgState(gdp_estimate)                      AS avg_gdp,
    avgState(inflation_estimate)                AS avg_inflation,
    avgState(employment_rate)                   AS avg_employment,
    avgState(confidence_score)                  AS avg_confidence
FROM biashara.economic_indicators
GROUP BY week_start, region;

-- Daily market price summary (auto-aggregated)
CREATE MATERIALIZED VIEW IF NOT EXISTS biashara.mv_daily_market_summary
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (product, region, date)
AS
SELECT
    date,
    product,
    region,
    avgState(price)                 AS avg_price,
    avgState(supply_index)          AS avg_supply,
    avgState(demand_index)          AS avg_demand,
    sumState(transaction_count)     AS total_transactions,
    maxState(vendor_count)          AS max_vendors
FROM biashara.market_data
GROUP BY date, product, region;

-- ============================================================================
-- 6. TTL — auto-expire raw data after 2 years to manage storage
--    (materialized views retain aggregated data indefinitely)
-- ============================================================================
ALTER TABLE biashara.transactions_analytics  MODIFY TTL date + INTERVAL 2 YEAR;
ALTER TABLE biashara.market_data             MODIFY TTL date + INTERVAL 2 YEAR;
ALTER TABLE biashara.worker_activity         MODIFY TTL date + INTERVAL 2 YEAR;
-- economic_indicators kept indefinitely (low volume, high analytical value)
