use serde::{Deserialize, Serialize};
// credit/types.rs

/// Worker type classification — 12 archetypes + legacy types
///
/// The 12 archetypes cover 123 worker types from the taxonomy.
/// Legacy types are kept for backward compatibility with existing
/// credit scoring extractors.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum WorkerType {
    // ── 12 Archetypes ──
    /// Buys goods wholesale and resells retail (T-001–T-024)
    Vendor,
    /// Prepares and sells cooked food/beverages (F-001–F-019)
    FoodService,
    /// Transforms raw materials into finished products (M-001–M-028)
    Artisan,
    /// Provides skill-based services without physical product (S-001–S-034)
    ServiceProvider,
    /// Transports people or goods using a vehicle (TR-001–TR-017)
    TransportOperator,
    /// Grows crops for food or sale (A-001–A-006)
    CropFarmer,
    /// Raises animals for income (A-007–A-014)
    LivestockKeeper,
    /// Catches or raises fish (A-015–A-018)
    Fisher,
    /// Facilitates transactions between parties (D-001–D-004, T-023)
    AgentBroker,
    /// Earns income through digital platforms (D-005–D-013)
    DigitalWorker,
    /// Sells labor by the day/hour/task (A-019–A-023, M-009–M-015, O-001–O-004)
    CasualLaborer,
    /// Entertainment, education, community services (O-005–O-030)
    CommunityCareWorker,

    // ── Legacy types (backward compatibility) ──
    MarketVendor,
    BodaBodaRider,
    Farmer,
    Fisherman,
    JuaKaliArtisan,
    MpesaAgent,
    ConstructionWorker,
    MiningWorker,
    Generic, // unknown / fallback
}

impl WorkerType {
    /// Get the type head weight (β) for score fusion
    pub fn type_weight(&self) -> f64 {
        match self {
            // 12 archetypes
            Self::Vendor => 0.3,
            Self::FoodService => 0.4,
            Self::Artisan => 0.4,
            Self::ServiceProvider => 0.4,
            Self::TransportOperator => 0.5,
            Self::CropFarmer => 0.6,
            Self::LivestockKeeper => 0.5,
            Self::Fisher => 0.6,
            Self::AgentBroker => 0.4,
            Self::DigitalWorker => 0.3,
            Self::CasualLaborer => 0.5,
            Self::CommunityCareWorker => 0.3,
            // Legacy
            Self::MarketVendor => 0.3,
            Self::BodaBodaRider => 0.5,
            Self::Farmer => 0.6,
            Self::Fisherman => 0.6,
            Self::JuaKaliArtisan => 0.4,
            Self::MpesaAgent => 0.4,
            Self::ConstructionWorker => 0.5,
            Self::MiningWorker => 0.5,
            Self::Generic => 0.0,
        }
    }

    /// Minimum transactions needed for type-specific scoring
    pub fn min_transactions(&self) -> usize {
        match self {
            // 12 archetypes
            Self::CropFarmer | Self::Fisher => 90,
            Self::TransportOperator => 30,
            Self::Vendor | Self::FoodService => 60,
            Self::Artisan | Self::ServiceProvider => 20,
            Self::AgentBroker => 30,
            Self::LivestockKeeper => 60,
            Self::DigitalWorker => 30,
            Self::CasualLaborer => 15,
            Self::CommunityCareWorker => 20,
            // Legacy
            Self::Farmer | Self::Fisherman => 90,
            Self::BodaBodaRider => 30,
            Self::MarketVendor => 60,
            Self::JuaKaliArtisan => 20,
            Self::MpesaAgent => 30,
            Self::ConstructionWorker => 30,
            Self::MiningWorker => 60,
            Self::Generic => 30,
        }
    }

    /// Map legacy types to their corresponding archetype
    pub fn to_archetype(&self) -> WorkerType {
        match self {
            Self::MarketVendor | Self::Vendor => Self::Vendor,
            Self::BodaBodaRider | Self::TransportOperator => Self::TransportOperator,
            Self::Farmer | Self::CropFarmer => Self::CropFarmer,
            Self::Fisherman | Self::Fisher => Self::Fisher,
            Self::JuaKaliArtisan | Self::Artisan => Self::Artisan,
            Self::MpesaAgent | Self::AgentBroker => Self::AgentBroker,
            Self::ConstructionWorker | Self::CasualLaborer => Self::CasualLaborer,
            Self::MiningWorker => Self::Artisan, // Mining maps to artisan
            _ => *self,
        }
    }
}

/// Worker type detection result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerTypeDetection {
    pub worker_type: WorkerType,
    pub confidence: f64,
    pub signals: Vec<DetectionSignal>,
}

/// Signal that contributed to type detection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectionSignal {
    pub signal_name: String,
    pub weight: f64,
    pub value: String,
}

/// Asset value bucket (used across multiple extractors)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AssetValueBucket {
    Low,     // < 50,000 KES
    Medium,  // 50,000 - 200,000 KES
    High,    // 200,000 - 500,000 KES
    Premium, // > 500,000 KES
}

/// Type-erased features from any extractor
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeFeatures {
    pub worker_type: WorkerType,
    pub features: serde_json::Value, // type-specific features as JSON
    pub feature_vector: Vec<f64>,    // normalized numeric features for model input
    pub feature_names: Vec<String>,  // feature names for interpretability
}

// Worker-type specific enums
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SkillLevel {
    Beginner,
    Intermediate,
    Advanced,
    Expert,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CropType {
    Cereals,
    Vegetables,
    Fruits,
    CashCrops,
    Legumes,
    Other,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LandSizeBucket {
    Small,
    Medium,
    Large,
    ExtraLarge,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BoatOwnership {
    Own,
    Leased,
    Shared,
    None,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum FishingZone {
    Shore,
    NearShore,
    DeepSea,
    Lake,
    River,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MineType {
    Surface,
    Underground,
    Alluvial,
    Other,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MineralType {
    Gold,
    Gemstones,
    Sand,
    Limestone,
    Other,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AgentTier {
    Tier1,
    Tier2,
    Tier3,
    TopAgent,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MarketTier {
    Informal,
    SemiFormal,
    Formal,
    Premium,
}
