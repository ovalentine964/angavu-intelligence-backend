// Credit Scoring — Worker-Type Feature Extractors Module
//
// Now supports all 12 worker archetypes plus legacy types.

pub mod farmer;
pub mod boda_boda;
pub mod fisherman;
pub mod vendor;
pub mod jua_kali;
pub mod mpesa_agent;
pub mod construction;
pub mod mining;
pub mod food_service;
pub mod artisan;
pub mod service_provider;
pub mod livestock;
pub mod agent_broker;
pub mod digital_worker;
pub mod casual_laborer;
pub mod community_care;

use crate::credit::types::{WorkerType, TypeFeatures};

/// Trait that all worker-type feature extractors implement.
/// Extracts credit signals unique to a worker type from transaction data.
pub trait WorkerTypeFeatureExtractor: Send + Sync {
    /// Extract type-specific features from raw transaction history
    fn extract(&self, transactions: &[Transaction], context: &WorkerContext) -> TypeFeatures;

    /// Worker type this extractor handles
    fn worker_type(&self) -> WorkerType;

    /// Minimum transactions needed for reliable extraction
    fn min_transactions(&self) -> usize;

    /// Feature names this extractor produces
    fn feature_names(&self) -> Vec<&'static str>;
}

/// Raw transaction (simplified — full version in TransactionRecorder)
#[derive(Debug, Clone)]
pub struct Transaction {
    pub id: String,
    pub amount: f64,
    pub product: Option<String>,
    pub quantity: Option<f64>,
    pub payment_method: PaymentMethod,
    pub timestamp: i64, // Unix epoch seconds
    pub category: TransactionCategory,
    pub counterparty_id: Option<String>,
    pub counterparty_name: Option<String>,
    pub reference: Option<String>, // M-Pesa reference
    pub location: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum PaymentMethod {
    Cash,
    MPesa,
    BankTransfer,
    Credit,
    Other,
}

#[derive(Debug, Clone, PartialEq)]
pub enum TransactionCategory {
    Sale,
    Purchase,
    Expense,
    Transfer,
    Savings,
    Loan,
    Repayment,
    Commission,
    Wage,
    Other,
}

/// Worker context (derived from transaction history)
#[derive(Debug, Clone)]
pub struct WorkerContext {
    pub first_transaction_days_ago: u32,
    pub total_transaction_count: u32,
    pub region: String,
    pub primary_language: String,
}

/// Create the appropriate extractor for a worker type
pub fn create_extractor(worker_type: WorkerType) -> Option<Box<dyn WorkerTypeFeatureExtractor>> {
    match worker_type {
        // 12 archetypes
        WorkerType::Vendor => Some(Box::new(vendor::VendorFeatureExtractor::new())),
        WorkerType::FoodService => Some(Box::new(food_service::FoodServiceFeatureExtractor::new())),
        WorkerType::Artisan => Some(Box::new(artisan::ArtisanFeatureExtractor::new())),
        WorkerType::ServiceProvider => Some(Box::new(service_provider::ServiceProviderFeatureExtractor::new())),
        WorkerType::TransportOperator => Some(Box::new(boda_boda::BodaBodaFeatureExtractor::new())),
        WorkerType::CropFarmer => Some(Box::new(farmer::FarmerFeatureExtractor::new())),
        WorkerType::LivestockKeeper => Some(Box::new(livestock::LivestockFeatureExtractor::new())),
        WorkerType::Fisher => Some(Box::new(fisherman::FishermanFeatureExtractor::new())),
        WorkerType::AgentBroker => Some(Box::new(agent_broker::AgentBrokerFeatureExtractor::new())),
        WorkerType::DigitalWorker => Some(Box::new(digital_worker::DigitalWorkerFeatureExtractor::new())),
        WorkerType::CasualLaborer => Some(Box::new(casual_laborer::CasualLaborerFeatureExtractor::new())),
        WorkerType::CommunityCareWorker => Some(Box::new(community_care::CommunityCareFeatureExtractor::new())),
        // Legacy types (backward compatibility)
        WorkerType::Farmer => Some(Box::new(farmer::FarmerFeatureExtractor::new())),
        WorkerType::BodaBodaRider => Some(Box::new(boda_boda::BodaBodaFeatureExtractor::new())),
        WorkerType::Fisherman => Some(Box::new(fisherman::FishermanFeatureExtractor::new())),
        WorkerType::MarketVendor => Some(Box::new(vendor::VendorFeatureExtractor::new())),
        WorkerType::JuaKaliArtisan => Some(Box::new(jua_kali::JuaKaliFeatureExtractor::new())),
        WorkerType::MpesaAgent => Some(Box::new(mpesa_agent::MpesaAgentFeatureExtractor::new())),
        WorkerType::ConstructionWorker => Some(Box::new(construction::ConstructionFeatureExtractor::new())),
        WorkerType::MiningWorker => Some(Box::new(mining::MiningFeatureExtractor::new())),
        WorkerType::Generic => None,
    }
}
