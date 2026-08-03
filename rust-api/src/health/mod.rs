//! Health Metrics module — occupation-hazard risk assessment
//!
//! Multi-dimensional health risk scoring using:
//! - Occupation-specific hazard profiles (10 worker types)
//! - Location-based risk adjustments (county-level disease burden)
//! - Exposure signals derived from transaction patterns
//! - Insurance eligibility engine
//! - Differential privacy on all outputs

pub mod insurance;
pub mod location_risk;
pub mod occupation_hazards;
pub mod types;

// Re-export key types for convenience
pub use insurance::{InsuranceEligibility, InsuranceEligibilityEngine};
pub use location_risk::LocationRiskAdjustment;
pub use types::*;
