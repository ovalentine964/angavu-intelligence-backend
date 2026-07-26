//! Health Metrics module — occupation-hazard risk assessment
//!
//! Multi-dimensional health risk scoring using:
//! - Occupation-specific hazard profiles (10 worker types)
//! - Location-based risk adjustments (county-level disease burden)
//! - Exposure signals derived from transaction patterns
//! - Insurance eligibility engine
//! - Differential privacy on all outputs

pub mod types;
pub mod occupation_hazards;
pub mod location_risk;
pub mod insurance;

// Re-export key types for convenience
pub use types::*;
pub use location_risk::LocationRiskAdjustment;
pub use insurance::{InsuranceEligibility, InsuranceEligibilityEngine};
