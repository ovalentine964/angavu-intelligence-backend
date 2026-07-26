// credit/types.rs

/// Worker type classification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum WorkerType {
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
            Self::Farmer | Self::Fisherman => 90,  // need seasonal data
            Self::BodaBodaRider => 30,              // daily patterns
            Self::MarketVendor => 60,               // 2 months
            Self::JuaKaliArtisan => 20,             // project-based
            Self::MpesaAgent => 30,                 // daily patterns
            Self::ConstructionWorker => 30,         // wage patterns
            Self::MiningWorker => 60,               // seasonal
            Self::Generic => 30,
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
    Low,      // < 50,000 KES
    Medium,   // 50,000 - 200,000 KES
    High,     // 200,000 - 500,000 KES
    Premium,  // > 500,000 KES
}

/// Type-erased features from any extractor
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeFeatures {
    pub worker_type: WorkerType,
    pub features: serde_json::Value, // type-specific features as JSON
    pub feature_vector: Vec<f64>,     // normalized numeric features for model input
    pub feature_names: Vec<String>,   // feature names for interpretability
}
