// Angavu Intelligence Backend — Credit Scoring Module
// Worker-Type-Calibrated Alama Score with Seasonality Awareness

pub mod approval_gate; // Human-in-the-Loop: Credit Decision Approval
pub mod base_features;
pub mod classical_algorithms;
pub mod extractors;
pub mod fairness; // Fairness testing: demographic parity, equalized odds, predictive parity
pub mod federated;
pub mod logistic_regression;
pub mod model_registry; // Model versioning, A/B testing, champion/challenger framework
pub mod privacy_budget; // Privacy budget tracker with RDP composition (IC-PRIVACY)
pub mod quantum_traits; // Quantum-upgradeable algorithm trait interfaces
pub mod score_fusion;
pub mod score_verification;
pub mod seasonality;
pub mod seasonality_enhanced;
pub mod shap_explainer; // KernelSHAP explainability (EU AI Act compliance)
pub mod type_features;
pub mod types;
pub mod worker_type_detector; // Classical implementations of quantum_traits (simulated annealing, etc.)
