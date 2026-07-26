//! Worker-type-specific feature extractors for Alama Score calibration

use serde::{Deserialize, Serialize};

// Each worker type implements this trait
pub trait WorkerTypeFeatureExtractor: Send + Sync {
    /// Extract type-specific features from raw transaction history
    fn extract(&self, transactions: &[Transaction], context: &WorkerContext) -> TypeFeatures;

    /// Worker type identifier
    fn worker_type(&self) -> WorkerType;

    /// Minimum transactions needed for reliable extraction
    fn min_transactions(&self) -> usize;

    /// Features this extractor produces (for federated learning gradient shapes)
    fn feature_names(&self) -> Vec<&'static str>;
}

pub struct FarmerFeatures {
    /// Detected primary crop type (categorical → one-hot encoded)
    pub primary_crop: CropType,
    /// Estimated land size bucket: small (<1 acre), medium (1-5), large (>5)
    pub land_size_bucket: LandSizeBucket,
    /// Harvest cycle in days (detected from income periodicity)
    pub harvest_cycle_days: Option<u32>,
    /// Income stability within harvest season (0.0-1.0)
    /// Compares peak month to same-month-historical, NOT overall average
    pub intra_season_stability: f64,
    /// Inter-season income ratio (peak_month / trough_month)
    /// High ratio = highly seasonal (expected for farmers, NOT penalized)
    pub seasonal_ratio: f64,
    /// Input investment as % of total expenses (proxy for farm quality)
    pub input_investment_ratio: f64,
    /// Whether cooperative membership detected (regular named payments)
    pub has_cooperative_membership: bool,
    /// Post-harvest savings behavior (savings deposits after harvest spikes)
    pub post_harvest_savings_ratio: f64,
    /// Number of distinct buyer relationships
    pub buyer_diversity: u8,
    /// Storage duration (days between harvest sale and next income — proxy for storage capacity)
    pub avg_storage_duration_days: u32,
}

pub struct BodaBodaFeatures {
    /// Estimated motorcycle asset value bucket
    pub asset_value_bucket: AssetValueBucket,
    /// Daily fuel cost (median, KES)
    pub daily_fuel_cost_median: f64,
    /// Fuel cost as % of daily revenue
    pub fuel_cost_ratio: f64,
    /// Estimated daily trip count (from individual fare receipts)
    pub daily_trip_count_median: u32,
    /// Revenue consistency (day-to-day coefficient of variation)
    pub daily_revenue_cv: f64,
    /// Peak hours utilization (income during 7-9am, 5-7pm vs rest of day)
    pub peak_hour_income_ratio: f64,
    /// Maintenance/repair spending frequency (days between repairs)
    pub maintenance_frequency_days: u32,
    /// Income growth trajectory (30-day moving average slope)
    pub income_trajectory: f64,
    /// Weekend vs weekday income ratio
    pub weekend_weekday_ratio: f64,
    /// Number of regular payment counterparties (repeat passengers)
    pub regular_passenger_count: u32,
}

pub struct FishermanFeatures {
    /// Estimated boat ownership (inferred from fuel + maintenance patterns)
    pub boat_ownership: BoatOwnership, // Owned, Leased, Shared
    /// Fishing zone (inferred from departure time patterns and catch types)
    pub fishing_zone: FishingZone,     // Nearshore, Offshore, Deep-sea
    /// Catch cycle in days (detected from income periodicity)
    pub catch_cycle_days: Option<u32>,
    /// Seasonal catch pattern (monthly income profile)
    pub monthly_income_profile: [f64; 12],
    /// Landing site diversity (number of distinct sale locations)
    pub landing_site_count: u8,
    /// Cold chain access (inferred from product types — fresh vs dried/frozen)
    pub has_cold_chain_access: bool,
    /// Income stability within fishing season
    pub intra_season_stability: f64,
    /// Weather-related income gaps (consecutive zero-income days)
    pub avg_weather_gap_days: u32,
    /// Post-catch savings behavior
    pub savings_rate: f64,
    /// Buyer relationship count
    pub buyer_diversity: u8,
}

pub struct VendorFeatures {
    /// Market location quality tier (inferred from transaction volume + pricing)
    pub market_tier: MarketTier,  // Tier1 (CBD), Tier2 (suburban), Tier3 (rural)
    /// Product category diversity
    pub product_diversity: u8,
    /// Number of supplier relationships
    pub supplier_count: u8,
    /// Years in business (inferred from first transaction date)
    pub years_in_business: f64,
    /// Daily transaction count median
    pub daily_txn_count_median: u32,
    /// Average transaction size (KES)
    pub avg_transaction_size: f64,
    /// Inventory turnover speed (days to sell through stock)
    pub inventory_turnover_days: u32,
    /// Weekend income premium
    pub weekend_premium: f64,
    /// Savings pattern regularity
    pub savings_regularity: f64,
    /// Restock frequency (days between supplier payments)
    pub restock_frequency_days: u32,
}

pub struct JuaKaliFeatures {
    /// Skill type (inferred from material purchases)
    pub skill_type: SkillType, // Welding, Carpentry, Tailoring, Mechanics, etc.
    /// Tools/equipment investment level
    pub equipment_investment_bucket: AssetValueBucket,
    /// Client repeat rate (% of income from returning clients)
    pub client_repeat_rate: f64,
    /// Project completion rate (income patterns suggesting project delivery)
    pub project_completion_signal: f64,
    /// Income irregularity (expected for project-based work — NOT penalized)
    pub income_irregularity_cv: f64,
    /// Material cost ratio (materials / total revenue)
    pub material_cost_ratio: f64,
    /// Pricing tier (average project value)
    pub avg_project_value: f64,
    /// Geographic reach (number of distinct payment locations)
    pub geographic_reach: u8,
    /// Savings between projects
    pub inter_project_savings_rate: f64,
    /// Years of activity
    pub years_active: f64,
}

pub struct MpesaAgentFeatures {
    /// Float turnover ratio (daily float used / total float)
    pub float_turnover_ratio: f64,
    /// Daily transaction count
    pub daily_txn_count_median: u32,
    /// Commission income (inferred from M-Pesa agent payment patterns)
    pub daily_commission_median: f64,
    /// Agent tier (inferred from transaction volume thresholds)
    pub agent_tier: AgentTier, // SuperAgent, Standard, Mini
    /// Location foot traffic score (transaction volume variance by hour)
    pub foot_traffic_score: f64,
    /// Float management efficiency (min idle float time)
    pub float_efficiency: f64,
    /// Transaction type mix (deposits vs withdrawals vs transfers)
    pub deposit_withdrawal_ratio: f64,
    /// Business hours utilization (transactions during operating hours)
    pub operating_hours_utilization: f64,
    /// Revenue growth trajectory
    pub revenue_trajectory: f64,
    /// Cash handling risk (large transaction frequency)
    pub large_txn_frequency: f64,
}

pub struct ConstructionFeatures {
    /// Skill certification level (inferred from wage rates)
    pub skill_level: SkillLevel, // Helper, Fundi, Supervisor, Contractor
    /// Number of contractor relationships (distinct employers)
    pub contractor_count: u8,
    /// Project frequency (days between income gaps)
    pub project_frequency_days: u32,
    /// Wage regularity (payment consistency from same contractor)
    pub wage_regularity: f64,
    /// Income growth trajectory
    pub wage_trajectory: f64,
    /// Geographic mobility (payment locations across regions)
    pub geographic_mobility: u8,
    /// Tool ownership (tool purchase patterns)
    pub tool_investment: f64,
    /// Weekend/holiday work frequency
    pub weekend_work_ratio: f64,
    /// Payment method preference (M-Pesa vs cash)
    pub mpesa_payment_ratio: f64,
    /// Wage level relative to skill type
    pub relative_wage_percentile: f64,
}

pub struct MiningFeatures {
    /// Mine type (inferred from patterns)
    pub mine_type: MineType, // Artisanal, SmallScale, Industrial
    /// Mineral type (inferred from sale patterns)
    pub mineral_type: MineralType, // Gold, Gemstones, Sand, Limestone
    /// Equipment ownership level
    pub equipment_investment: AssetValueBucket,
    /// Seasonal income patterns
    pub seasonal_income_profile: [f64; 12],
    /// Income stability (within active mining periods)
    pub active_period_stability: f64,
    /// Buyer relationships
    pub buyer_diversity: u8,
    /// Savings behavior
    pub savings_rate: f64,
    /// Income growth trajectory
    pub income_trajectory: f64,
    /// Activity gap analysis (consecutive inactive days)
    pub avg_inactive_gap_days: u32,
    /// Safety investment (spending on safety equipment)
    pub safety_investment_ratio: f64,
}

