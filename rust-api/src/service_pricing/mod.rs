// Service Economy Price Intelligence — Backend Module
// Extends MarketAnalyzer to cover SERVICE workers (40%+ of informal economy)
// Transport, Construction/Labor, Beauty/Personal Care, Repair Services

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ═══════════════════════════════════════════════════════════════════════════
// Core Service Pricing Types
// ═══════════════════════════════════════════════════════════════════════════

/// Top-level service category taxonomy
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum ServiceCategory {
    Transport,
    Construction,
    Beauty,
    Repair,
    Entertainment,
    Cleaning,
    Other(String),
}

/// A single service price data point — anonymized and k-anonymous
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServicePriceRecord {
    pub record_id: Uuid,
    pub service_category: ServiceCategory,
    pub service_type: String,           // e.g., "boda_boda_ride", "hair_braiding", "phone_screen_repair"
    pub region: String,                 // e.g., "nairobi-eastlands", "migori-town"
    pub price_bucket: String,           // e.g., "100-200" — never exact price
    pub price_avg: f64,                 // aggregated average (only if k≥10)
    pub unit: String,                   // e.g., "per_trip", "per_hour", "per_piece"
    pub sample_size: u32,              // how many data points (must be ≥10 for k-anonymity)
    pub confidence: f64,               // 0.0-1.0
    pub recorded_at: DateTime<Utc>,
    pub synced_at: DateTime<Utc>,
}

/// Aggregated service market signal — computed from multiple ServicePriceRecords
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceMarketSignal {
    pub signal_id: Uuid,
    pub service_category: ServiceCategory,
    pub service_type: String,
    pub region: String,
    pub price_avg: f64,
    pub price_min: f64,
    pub price_max: f64,
    pub price_trend: f64,              // -1.0 to 1.0 (declining to rising)
    pub demand_velocity: f64,          // relative demand strength
    pub volatility: f64,               // price stability
    pub sample_size: u32,
    pub factors: Vec<PricingFactor>,   // what's influencing the price
    pub updated_at: DateTime<Utc>,
}

/// Factors that influence service pricing
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PricingFactor {
    TimeOfDay { hour: u8, multiplier: f64 },
    DayOfWeek { day: String, multiplier: f64 },
    Weather { condition: String, multiplier: f64 },
    Season { season: String, multiplier: f64 },
    Event { event_type: String, multiplier: f64 },
    FuelCost { price_per_litre: f64 },
    DemandSurge { reason: String, multiplier: f64 },
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. Transport Pricing (Boda Boda, Tuk-Tuk, Matatu)
// ═══════════════════════════════════════════════════════════════════════════

/// Route-based transport pricing model
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransportRoute {
    pub route_id: Uuid,
    pub origin: GeoPoint,
    pub destination: GeoPoint,
    pub origin_name: String,           // "CBD", "Westlands", "Kawangware"
    pub destination_name: String,
    pub distance_km: f64,
    pub transport_type: TransportType,
    pub base_fare: f64,                // KES
    pub per_km_rate: f64,             // KES per km
    pub region: String,
    pub sample_size: u32,
    pub last_updated: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum TransportType {
    BodaBoda,
    TukTuk,
    Matatu,
    Taxi,
    Bus,
}

/// Geographic point for route calculations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeoPoint {
    pub latitude: f64,
    pub longitude: f64,
}

/// Surge pricing detection state
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SurgeState {
    pub region: String,
    pub transport_type: TransportType,
    pub is_surge: bool,
    pub surge_multiplier: f64,         // 1.0 = normal, 1.5 = 50% surge
    pub reason: SurgeReason,
    pub detected_at: DateTime<Utc>,
    pub expected_duration_mins: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SurgeReason {
    Rain,
    RushHour,
    Event { event_name: String },
    FuelPriceHike,
    RoadClosure { location: String },
    Holiday,
    NightTime,
}

/// Fuel cost integration for transport pricing
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FuelCostModel {
    pub region: String,
    pub fuel_price_per_litre: f64,     // KES
    pub consumption_per_km: f64,       // litres per km
    pub cost_per_km: f64,              // derived: fuel_price * consumption
    pub last_updated: DateTime<Utc>,
}

impl FuelCostModel {
    pub fn compute_cost_per_km(&self) -> f64 {
        self.fuel_price_per_litre * self.consumption_per_km
    }
}

/// Transport competitor rate snapshot
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransportCompetitorRate {
    pub rate_id: Uuid,
    pub route_id: Uuid,
    pub transport_type: TransportType,
    pub competitor_count: u32,         // how many riders at this stage
    pub avg_fare: f64,
    pub min_fare: f64,
    pub max_fare: f64,
    pub idle_time_pct: f64,            // % of time riders are idle
    pub region: String,
    pub recorded_at: DateTime<Utc>,
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. Construction/Labor Pricing (Fundis, Masons, Laborers)
// ═══════════════════════════════════════════════════════════════════════════

/// Skill-based rate card for construction workers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LaborRateCard {
    pub rate_id: Uuid,
    pub skill_type: SkillType,
    pub experience_level: ExperienceLevel,
    pub region: String,
    pub daily_rate: f64,               // KES per day
    pub hourly_rate: f64,              // KES per hour
    pub project_rate: Option<f64>,     // KES per project (if applicable)
    pub unit: String,                  // "per_day", "per_hour", "per_project"
    pub sample_size: u32,
    pub last_updated: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum SkillType {
    Mason,
    Plumber,
    Electrician,
    Carpenter,
    Painter,
    Welder,
    Roofer,
    Tiler,
    GeneralLaborer,
    Fundi,  // generic skilled artisan
    Other(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum ExperienceLevel {
    Apprentice,     // < 1 year
    Junior,         // 1-3 years
    Intermediate,   // 3-7 years
    Senior,         // 7-15 years
    Master,         // 15+ years
}

/// Project type pricing model
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectPricing {
    pub pricing_id: Uuid,
    pub project_type: ProjectType,
    pub skill_required: SkillType,
    pub region: String,
    pub material_cost_estimate: f64,   // KES
    pub labor_cost_estimate: f64,      // KES
    pub total_estimate: f64,           // KES
    pub duration_days: u32,
    pub workers_needed: u32,
    pub sample_size: u32,
    pub last_updated: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum ProjectType {
    Foundation,
    Walling,
    Roofing,
    Plumbing,
    Electrical,
    Painting,
    Tiling,
    Fencing,
    Renovation,
    FullConstruction,
    Other(String),
}

/// Material cost integration for construction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConstructionMaterial {
    pub material_id: Uuid,
    pub name: String,                  // "cement", "sand", "ballast", "timber"
    pub unit: String,                  // "bag", "tonne", "piece", "metre"
    pub region: String,
    pub price_avg: f64,
    pub price_min: f64,
    pub price_max: f64,
    pub supplier_count: u32,
    pub last_updated: DateTime<Utc>,
}

/// Regional wage index — compares wages across regions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionalWageIndex {
    pub index_id: Uuid,
    pub skill_type: SkillType,
    pub region: String,
    pub daily_wage_avg: f64,
    pub daily_wage_median: f64,
    pub daily_wage_p25: f64,           // 25th percentile
    pub daily_wage_p75: f64,           // 75th percentile
    pub worker_count: u32,             // must be ≥10 for k-anonymity
    pub cost_of_living_index: f64,     // relative to national average (1.0)
    pub updated_at: DateTime<Utc>,
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. Beauty/Personal Care Pricing (Salon, Barbershop)
// ═══════════════════════════════════════════════════════════════════════════

/// Service type pricing for beauty/personal care
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BeautyServicePrice {
    pub price_id: Uuid,
    pub service_type: BeautyServiceType,
    pub establishment_type: EstablishmentType,
    pub region: String,
    pub price_avg: f64,
    pub price_min: f64,
    pub price_max: f64,
    pub duration_mins: u32,
    pub sample_size: u32,
    pub last_updated: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum BeautyServiceType {
    // Hair services
    Haircut,
    HairBraiding,
    HairWeaving,
    HairColoring,
    HairRelaxing,
    Dreadlocks,
    // Skin/beauty
    Manicure,
    Pedicure,
    Facial,
    Makeup,
    // Barbering
    BeardTrim,
    Shave,
    LineUp,
    // Other
    Massage,
    Other(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum EstablishmentType {
    Salon,
    Barbershop,
    Spa,
    HomeService,      // mobile service provider
    StreetSide,
}

/// Time-based pricing for beauty services
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BeautyTimePricing {
    pub service_type: BeautyServiceType,
    pub region: String,
    pub peak_hours: Vec<u8>,           // hours with highest demand (0-23)
    pub peak_multiplier: f64,          // price multiplier during peak
    pub off_peak_multiplier: f64,      // price multiplier during off-peak
    pub weekend_multiplier: f64,
}

/// Product cost integration for beauty services
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BeautyProduct {
    pub product_id: Uuid,
    pub name: String,                  // "hair gel", "relaxer", "hair dye"
    pub unit: String,                  // "bottle", "tube", "packet"
    pub region: String,
    pub price_avg: f64,
    pub usage_per_service: f64,        // how much product per service
    pub cost_per_service: f64,         // derived
    pub last_updated: DateTime<Utc>,
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. Repair Services Pricing (Phone, Electronics, Mechanics)
// ═══════════════════════════════════════════════════════════════════════════

/// Device/equipment type pricing for repairs
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RepairServicePrice {
    pub price_id: Uuid,
    pub repair_category: RepairCategory,
    pub device_type: String,           // "Samsung Galaxy", "iPhone", "TV", "motorcycle"
    pub repair_type: String,           // "screen replacement", "battery", "engine overhaul"
    pub complexity: RepairComplexity,
    pub region: String,
    pub labor_cost_avg: f64,
    pub parts_cost_avg: f64,
    pub total_cost_avg: f64,
    pub duration_hours: f64,
    pub sample_size: u32,
    pub warranty_days: u32,            // typical warranty offered
    pub last_updated: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum RepairCategory {
    PhoneRepair,
    ElectronicsRepair,    // TV, radio, sound systems
    ApplianceRepair,      // fridge, washing machine
    MotorcycleRepair,     // boda boda, tuk-tuk
    VehicleRepair,        // car, matatu
    BicycleRepair,
    Other(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum RepairComplexity {
    Simple,       // < 1 hour, basic tools
    Moderate,     // 1-3 hours, specialized tools
    Complex,      // 3-8 hours, expert knowledge
    Expert,       // 8+ hours, rare skills/parts
}

/// Parts cost integration for repair services
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RepairPart {
    pub part_id: Uuid,
    pub name: String,                  // "screen", "battery", "brake pad"
    pub compatible_devices: Vec<String>,
    pub region: String,
    pub price_avg: f64,
    pub price_min: f64,
    pub price_max: f64,
    pub is_genuine: bool,              // genuine vs aftermarket
    pub availability: PartAvailability,
    pub last_updated: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum PartAvailability {
    InStock,
    LimitedStock,
    OrderRequired,      // 1-3 days
    ImportRequired,     // 1-4 weeks
    Discontinued,
}

// ═══════════════════════════════════════════════════════════════════════════
// 5. Entertainment Services Pricing
// ═══════════════════════════════════════════════════════════════════════════

/// Entertainment service pricing
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EntertainmentServicePrice {
    pub price_id: Uuid,
    pub service_type: EntertainmentType,
    pub region: String,
    pub price_avg: f64,
    pub price_min: f64,
    pub price_max: f64,
    pub unit: String,                  // "per_hour", "per_event", "per_song"
    pub equipment_included: bool,
    pub sample_size: u32,
    pub last_updated: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum EntertainmentType {
    DJ,
    MC,
    LiveBand,
    SoloMusician,
    Dancer,
    Comedian,
    Photographer,
    Videographer,
    SoundSystemRental,
    Other(String),
}

// ═══════════════════════════════════════════════════════════════════════════
// 6. Service Price Discovery API (for MarketAnalyzer integration)
// ═══════════════════════════════════════════════════════════════════════════

/// Request to query service prices
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServicePriceQuery {
    pub service_category: ServiceCategory,
    pub service_type: Option<String>,
    pub region: String,
    pub date: Option<DateTime<Utc>>,
    pub include_factors: bool,         // include pricing factors in response
}

/// Response with service price intelligence
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServicePriceResponse {
    pub query: ServicePriceQuery,
    pub market_signal: Option<ServiceMarketSignal>,
    pub price_range: Option<PriceRange>,
    pub factors: Vec<PricingFactor>,
    pub comparable_regions: Vec<RegionComparison>,
    pub cache_hit: bool,               // was this served from offline cache?
    pub k_anonymity_met: bool,         // was k≥10 satisfied?
    pub generated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceRange {
    pub min: f64,
    pub max: f64,
    pub avg: f64,
    pub recommended: f64,              // suggested price for the worker
    pub unit: String,
}

/// Compare pricing across regions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionComparison {
    pub region: String,
    pub price_avg: f64,
    pub price_diff_pct: f64,           // % difference from queried region
    pub sample_size: u32,
}

/// Service price broadcast from device to backend
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServicePriceBroadcast {
    pub broadcast_id: Uuid,
    pub worker_id: String,             // anonymized
    pub service_category: ServiceCategory,
    pub service_type: String,
    pub region: String,
    pub price_bucket: String,          // "100-200" — never exact
    pub unit: String,
    pub timestamp: DateTime<Utc>,
}

// ═══════════════════════════════════════════════════════════════════════════
// 7. Wage Calculator Types
// ═══════════════════════════════════════════════════════════════════════════

/// Wage calculation request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WageCalculationRequest {
    pub skill_type: SkillType,
    pub experience_level: ExperienceLevel,
    pub region: String,
    pub project_type: Option<ProjectType>,
    pub duration_days: Option<u32>,
    pub include_materials: bool,
}

/// Wage calculation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WageCalculationResult {
    pub request: WageCalculationRequest,
    pub fair_daily_wage: f64,
    pub fair_hourly_wage: f64,
    pub fair_project_wage: Option<f64>,
    pub material_cost_estimate: Option<f64>,
    pub total_estimate: Option<f64>,
    pub regional_comparison: RegionalWageIndex,
    pub percentile_rank: f64,          // where this wage falls (0-100)
    pub k_anonymity_met: bool,
    pub generated_at: DateTime<Utc>,
}

// ═══════════════════════════════════════════════════════════════════════════
// 8. Offline Cache Structure
// ═══════════════════════════════════════════════════════════════════════════

/// Cached service price data for offline use
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServicePriceCache {
    pub cache_id: Uuid,
    pub region: String,
    pub service_category: ServiceCategory,
    pub prices: Vec<ServicePriceRecord>,
    pub market_signals: Vec<ServiceMarketSignal>,
    pub cached_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,     // cache TTL
    pub version: u64,                  // for conflict resolution on sync
}

impl ServicePriceCache {
    pub fn is_expired(&self) -> bool {
        Utc::now() > self.expires_at
    }

    pub fn is_stale(&self) -> bool {
        // Stale if older than 24 hours
        let staleness = Utc::now().signed_duration_since(self.cached_at);
        staleness.num_hours() > 24
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// 9. K-Anonymity Enforcement for Service Data
// ═══════════════════════════════════════════════════════════════════════════

/// Privacy enforcement for service pricing queries
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KAnonymityCheck {
    pub min_cohort_size: u32,          // must be ≥10
    pub actual_cohort_size: u32,
    pub is_anonymous: bool,
    pub suppression_applied: bool,     // true if data was suppressed
    pub generalization_level: u8,      // 0=exact, 1=city, 2=county, 3=country
}

impl KAnonymityCheck {
    pub fn new(actual_size: u32) -> Self {
        Self {
            min_cohort_size: 10,
            actual_cohort_size: actual_size,
            is_anonymous: actual_size >= 10,
            suppression_applied: actual_size < 10,
            generalization_level: 0,
        }
    }

    /// Returns the appropriate geographic generalization level
    /// to achieve k≥10 anonymity
    pub fn required_generalization(&self) -> u8 {
        match self.actual_cohort_size {
            0..=9 => 3,    // must generalize to country level
            10..=24 => 2,  // county level
            25..=99 => 1,  // city level
            _ => 0,        // exact region is fine
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_k_anonymity_enforcement() {
        let check = KAnonymityCheck::new(5);
        assert!(!check.is_anonymous);
        assert!(check.suppression_applied);
        assert_eq!(check.required_generalization(), 3);

        let check = KAnonymityCheck::new(15);
        assert!(check.is_anonymous);
        assert!(!check.suppression_applied);
        assert_eq!(check.required_generalization(), 2);

        let check = KAnonymityCheck::new(100);
        assert!(check.is_anonymous);
        assert_eq!(check.required_generalization(), 0);
    }

    #[test]
    fn test_fuel_cost_model() {
        let model = FuelCostModel {
            region: "nairobi".to_string(),
            fuel_price_per_litre: 185.0,
            consumption_per_km: 0.03,  // boda boda: ~30km/litre
            cost_per_km: 0.0,
            last_updated: Utc::now(),
        };
        let cost = model.compute_cost_per_km();
        assert!((cost - 5.55).abs() < 0.01); // 185 * 0.03 = 5.55
    }

    #[test]
    fn test_service_price_cache_expiry() {
        let cache = ServicePriceCache {
            cache_id: Uuid::new_v4(),
            region: "migori".to_string(),
            service_category: ServiceCategory::Transport,
            prices: vec![],
            market_signals: vec![],
            cached_at: Utc::now() - chrono::Duration::hours(2),
            expires_at: Utc::now() - chrono::Duration::hours(1),
            version: 1,
        };
        assert!(cache.is_expired());
        assert!(!cache.is_stale()); // 2 hours < 24 hours
    }

    #[test]
    fn test_service_categories() {
        let categories = vec![
            ServiceCategory::Transport,
            ServiceCategory::Construction,
            ServiceCategory::Beauty,
            ServiceCategory::Repair,
            ServiceCategory::Entertainment,
        ];
        assert_eq!(categories.len(), 5);
    }

    #[test]
    fn test_repair_complexity_ordering() {
        // Verify complexity levels exist and are distinct
        let complexities = vec![
            RepairComplexity::Simple,
            RepairComplexity::Moderate,
            RepairComplexity::Complex,
            RepairComplexity::Expert,
        ];
        assert_eq!(complexities.len(), 4);
    }
}
