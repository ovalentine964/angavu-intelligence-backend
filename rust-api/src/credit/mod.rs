// Angavu Intelligence Backend — Credit Scoring Module
// Worker-Type-Calibrated Alama Score with Seasonality Awareness

pub mod types;
pub mod base_features;
pub mod worker_type_detector;
pub mod seasonality;
pub mod score_fusion;
pub mod extractors;
pub mod type_features;
pub mod seasonality_enhanced;
pub mod federated;
pub mod score_verification;
pub mod logistic_regression;
pub mod approval_gate; // Human-in-the-Loop: Credit Decision Approval
pub mod quantum_traits; // Quantum-upgradeable algorithm trait interfaces
pub mod shap_explainer; // KernelSHAP explainability (EU AI Act compliance)
pub mod fairness; // Fairness testing: demographic parity, equalized odds, predictive parity
pub mod privacy_budget; // Privacy budget tracker with RDP composition (IC-PRIVACY)
pub mod model_registry; // Model versioning, A/B testing, champion/challenger framework
pub mod classical_algorithms; // Classical implementations of quantum_traits (simulated annealing, etc.)
