// =============================================================================
// Angavu Intelligence — Quantum-Upgradeable Algorithm Traits
// Trait interfaces that can be swapped for quantum versions
//
// Design principle: All computationally intensive algorithms expose a trait
// interface. Classical implementations exist today. When quantum hardware
// becomes accessible, quantum implementations of the same traits can be
// swapped in without changing any caller code.
//
// Upgrade path:
// 1. NOW: Classical implementations (this module)
// 2. 2026-2027: Quantum-inspired classical (simulated annealing, tensor networks)
// 3. 2027-2028: Hybrid quantum-classical (VQE, QAOA)
// 4. 2029+: Full quantum (fault-tolerant)
// =============================================================================

use async_trait::async_trait;
use serde::{Deserialize, Serialize};

// ── Credit Scoring Algorithm Trait ───────────────────────────────────────────

/// Quantum-upgradeable credit scoring algorithm
///
/// Classical implementation: Logistic regression via IRLS
/// Quantum upgrade path: Quantum SVM or Variational Quantum Classifier
///
/// The trait signature is designed so that quantum implementations
/// can use the same feature vectors and produce the same output types.
#[async_trait]
pub trait CreditScoringAlgorithm: Send + Sync {
    /// Algorithm identifier
    fn algorithm_id(&self) -> &str;

    /// Algorithm version (classical, quantum-inspired, hybrid, quantum)
    fn algorithm_tier(&self) -> AlgorithmTier;

    /// Train the model on historical data
    async fn train(
        &mut self,
        training_data: &CreditTrainingData,
    ) -> Result<TrainingResult, AlgorithmError>;

    /// Predict credit score for a single observation
    async fn predict(&self, features: &[f64]) -> Result<CreditPrediction, AlgorithmError>;

    /// Batch prediction for efficiency
    async fn predict_batch(
        &self,
        features: &[Vec<f64>],
    ) -> Result<Vec<CreditPrediction>, AlgorithmError>;

    /// Get feature importance (for explainability)
    fn feature_importance(&self) -> Vec<(String, f64)>;

    /// Check if quantum acceleration is available
    fn quantum_available(&self) -> bool {
        false
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AlgorithmTier {
    /// Standard classical algorithm
    Classical,
    /// Classical algorithm using quantum-inspired techniques
    QuantumInspired,
    /// Hybrid quantum-classical (runs partially on quantum hardware)
    HybridQuantum,
    /// Full quantum algorithm
    Quantum,
    /// AGI-class model (neural network, transformer, etc.)
    AgiModel,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditTrainingData {
    pub features: Vec<Vec<f64>>,
    pub labels: Vec<u8>,
    pub feature_names: Vec<String>,
    pub worker_types: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrainingResult {
    pub algorithm_id: String,
    pub tier: AlgorithmTier,
    pub metrics: TrainingMetricsSnapshot,
    pub training_duration_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrainingMetricsSnapshot {
    pub auc_roc: f64,
    pub accuracy: f64,
    pub precision: f64,
    pub recall: f64,
    pub f1_score: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditPrediction {
    pub probability: f64,
    pub alama_score: u16,
    pub confidence: f64,
    pub contributing_factors: Vec<(String, f64)>,
}

// ── Optimization Algorithm Trait ─────────────────────────────────────────────

/// Quantum-upgradeable optimization algorithm
///
/// Classical implementation: Linear programming, gradient descent
/// Quantum upgrade path: QAOA, Quantum Annealing, VQE
///
/// Used for: supply chain optimization, pricing, portfolio optimization
#[async_trait]
pub trait OptimizationAlgorithm: Send + Sync {
    fn algorithm_id(&self) -> &str;
    fn algorithm_tier(&self) -> AlgorithmTier;

    /// Solve an optimization problem
    async fn solve(
        &self,
        problem: &OptimizationProblem,
    ) -> Result<OptimizationSolution, AlgorithmError>;

    /// Check if the problem size is within this algorithm's capacity
    fn can_handle(&self, problem_size: usize) -> bool;

    /// Maximum problem size this algorithm can handle
    fn max_problem_size(&self) -> usize;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OptimizationProblem {
    pub problem_id: String,
    pub problem_type: OptimizationType,
    pub variables: Vec<Variable>,
    pub constraints: Vec<Constraint>,
    pub objective: Objective,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OptimizationType {
    /// Minimize cost (supply chain, routing)
    MinimizeCost,
    /// Maximize revenue (pricing, product mix)
    MaximizeRevenue,
    /// Minimize risk (portfolio, credit)
    MinimizeRisk,
    /// Multi-objective (trade-off between multiple goals)
    MultiObjective(Vec<Objective>),
    /// Quadratic Unconstrained Binary Optimization (for quantum annealing)
    QUBO,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Variable {
    pub name: String,
    pub var_type: VariableType,
    pub lower_bound: f64,
    pub upper_bound: f64,
    pub coefficient: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum VariableType {
    Continuous,
    Integer,
    Binary,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Constraint {
    pub name: String,
    pub coefficients: Vec<(String, f64)>, // (variable_name, coefficient)
    pub sense: ConstraintSense,
    pub rhs: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ConstraintSense {
    LessEqual,
    Equal,
    GreaterEqual,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Objective {
    pub direction: ObjectiveDirection,
    pub coefficients: Vec<(String, f64)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ObjectiveDirection {
    Minimize,
    Maximize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OptimizationSolution {
    pub problem_id: String,
    pub algorithm_id: String,
    pub tier: AlgorithmTier,
    pub objective_value: f64,
    pub variable_values: Vec<(String, f64)>,
    pub is_optimal: bool,
    pub solver_time_ms: u64,
    pub iterations: u64,
}

// ── Search Algorithm Trait ───────────────────────────────────────────────────

/// Quantum-upgradeable search/matching algorithm
///
/// Classical implementation: Bipartite matching, Hungarian algorithm
/// Quantum upgrade path: Grover's search, Quantum walk
///
/// Used for: worker-job matching, supplier-buyer matching
#[async_trait]
pub trait SearchAlgorithm: Send + Sync {
    fn algorithm_id(&self) -> &str;
    fn algorithm_tier(&self) -> AlgorithmTier;

    /// Find best matches for a query
    async fn search(&self, query: &SearchQuery) -> Result<SearchResults, AlgorithmError>;

    /// Find optimal assignment between two sets (bipartite matching)
    async fn optimal_assignment(
        &self,
        workers: &[WorkerProfile],
        jobs: &[JobProfile],
    ) -> Result<Vec<(usize, usize, f64)>, AlgorithmError>; // (worker_idx, job_idx, score)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchQuery {
    pub query_type: SearchType,
    pub filters: Vec<SearchFilter>,
    pub embedding: Option<Vec<f64>>,
    pub max_results: usize,
    pub min_score: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SearchType {
    WorkerJobMatch,
    SupplierBuyerMatch,
    MarketPriceSearch,
    SimilarWorkerSearch,
    ProductSearch,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchFilter {
    pub field: String,
    pub filter_type: FilterType,
    pub value: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FilterType {
    Equals,
    Range,
    Contains,
    GreaterThan,
    LessThan,
    In,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResults {
    pub results: Vec<SearchResult>,
    pub total_candidates: usize,
    pub search_time_ms: u64,
    pub algorithm_id: String,
    pub tier: AlgorithmTier,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub id: String,
    pub score: f64,
    pub explanation: Option<String>,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerProfile {
    pub worker_id: String,
    pub skills: Vec<String>,
    pub location: (f64, f64), // lat, lon
    pub availability: Vec<String>,
    pub experience_years: f64,
    pub rating: f64,
    pub embedding: Option<Vec<f64>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JobProfile {
    pub job_id: String,
    pub required_skills: Vec<String>,
    pub location: (f64, f64),
    pub pay_range: (f64, f64),
    pub duration: String,
    pub urgency: f64,
    pub embedding: Option<Vec<f64>>,
}

// ── Algorithm Error ──────────────────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum AlgorithmError {
    #[error("Training failed: {0}")]
    TrainingFailed(String),
    #[error("Prediction failed: {0}")]
    PredictionFailed(String),
    #[error("Problem too large: {0} variables exceeds limit of {1}")]
    ProblemTooLarge(usize, usize),
    #[error("Convergence failed after {0} iterations")]
    ConvergenceFailed(u64),
    #[error("Quantum backend unavailable: {0}")]
    QuantumUnavailable(String),
    #[error("Internal error: {0}")]
    Internal(String),
}

// ── Algorithm Registry ───────────────────────────────────────────────────────

/// Registry that manages algorithm implementations and enables swapping
pub struct AlgorithmRegistry {
    credit_scorers: Vec<Box<dyn CreditScoringAlgorithm>>,
    optimizers: Vec<Box<dyn OptimizationAlgorithm>>,
    searchers: Vec<Box<dyn SearchAlgorithm>>,
}

impl AlgorithmRegistry {
    pub fn new() -> Self {
        Self {
            credit_scorers: Vec::new(),
            optimizers: Vec::new(),
            searchers: Vec::new(),
        }
    }

    /// Register a credit scoring algorithm
    pub fn register_credit_scorer(&mut self, algo: Box<dyn CreditScoringAlgorithm>) {
        tracing::info!(
            "Registered credit scorer: {} (tier: {:?})",
            algo.algorithm_id(),
            algo.algorithm_tier()
        );
        self.credit_scorers.push(algo);
    }

    /// Register an optimization algorithm
    pub fn register_optimizer(&mut self, algo: Box<dyn OptimizationAlgorithm>) {
        tracing::info!(
            "Registered optimizer: {} (tier: {:?})",
            algo.algorithm_id(),
            algo.algorithm_tier()
        );
        self.optimizers.push(algo);
    }

    /// Register a search algorithm
    pub fn register_searcher(&mut self, algo: Box<dyn SearchAlgorithm>) {
        tracing::info!(
            "Registered searcher: {} (tier: {:?})",
            algo.algorithm_id(),
            algo.algorithm_tier()
        );
        self.searchers.push(algo);
    }

    /// Get the best available credit scorer (preferring quantum if available)
    pub fn best_credit_scorer(&self) -> Option<&dyn CreditScoringAlgorithm> {
        // Prefer quantum > hybrid > quantum-inspired > classical
        let tier_order = [
            AlgorithmTier::AgiModel,
            AlgorithmTier::Quantum,
            AlgorithmTier::HybridQuantum,
            AlgorithmTier::QuantumInspired,
            AlgorithmTier::Classical,
        ];

        for tier in &tier_order {
            for algo in &self.credit_scorers {
                if algo.algorithm_tier() == *tier {
                    return Some(algo.as_ref());
                }
            }
        }
        None
    }

    /// Get an optimizer that can handle the given problem size
    pub fn optimizer_for_size(&self, problem_size: usize) -> Option<&dyn OptimizationAlgorithm> {
        let tier_order = [
            AlgorithmTier::Quantum,
            AlgorithmTier::HybridQuantum,
            AlgorithmTier::QuantumInspired,
            AlgorithmTier::Classical,
        ];

        for tier in &tier_order {
            for algo in &self.optimizers {
                if algo.algorithm_tier() == *tier && algo.can_handle(problem_size) {
                    return Some(algo.as_ref());
                }
            }
        }
        None
    }

    /// List all registered algorithms
    pub fn list_algorithms(&self) -> AlgorithmInventory {
        AlgorithmInventory {
            credit_scorers: self
                .credit_scorers
                .iter()
                .map(|a| AlgorithmInfo {
                    id: a.algorithm_id().to_string(),
                    tier: a.algorithm_tier(),
                    category: "credit_scoring".to_string(),
                })
                .collect(),
            optimizers: self
                .optimizers
                .iter()
                .map(|a| AlgorithmInfo {
                    id: a.algorithm_id().to_string(),
                    tier: a.algorithm_tier(),
                    category: "optimization".to_string(),
                })
                .collect(),
            searchers: self
                .searchers
                .iter()
                .map(|a| AlgorithmInfo {
                    id: a.algorithm_id().to_string(),
                    tier: a.algorithm_tier(),
                    category: "search".to_string(),
                })
                .collect(),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct AlgorithmInventory {
    pub credit_scorers: Vec<AlgorithmInfo>,
    pub optimizers: Vec<AlgorithmInfo>,
    pub searchers: Vec<AlgorithmInfo>,
}

#[derive(Debug, Serialize)]
pub struct AlgorithmInfo {
    pub id: String,
    pub tier: AlgorithmTier,
    pub category: String,
}

// ── Quantum Upgrade Path Documentation ───────────────────────────────────────

/// Documents the upgrade path for each algorithm category
pub const QUANTUM_UPGRADE_PATH: &str = r#"
# Quantum Upgrade Path for Angavu Intelligence Algorithms

## Credit Scoring
- **NOW (Classical):** Logistic Regression via IRLS (implemented in credit/logistic_regression.rs)
- **2026-2027 (Quantum-Inspired):** Quantum Kernel Methods — compute kernel matrices classically
  using quantum-inspired tensor decomposition. Provides better feature interaction capture.
- **2027-2028 (Hybrid):** Variational Quantum Classifier (VQC) — parameterized quantum circuit
  trained classically. Runs on IBM Quantum / Amazon Braket.
- **2029+ (Quantum):** Quantum SVM in Hilbert space — exponential speedup for kernel computation.
  Requires fault-tolerant quantum hardware.

## Supply Chain Optimization
- **NOW (Classical):** Linear programming / mixed-integer programming
- **2026-2027 (Quantum-Inspired):** Toshiba Simulated Bifurcation Machine / Fujitsu Digital Annealer
- **2027-2028 (Hybrid):** QAOA on gate-based quantum (IBM, Google)
- **2028+ (Quantum):** D-Wave quantum annealing for QUBO formulations

## Worker-Job Matching
- **NOW (Classical):** Hungarian algorithm for bipartite matching
- **2026-2027 (Quantum-Inspired):** Quantum-inspired simulated annealing for large-scale matching
- **2027-2028 (Hybrid):** Grover's search for unstructured search components
- **2029+ (Quantum):** Quantum walk algorithms for graph-based matching

## Market Price Optimization
- **NOW (Classical):** Gradient descent, game-theoretic solvers
- **2026-2027 (Quantum-Inspired):** Tensor network methods for Nash Equilibrium approximation
- **2027-2028 (Hybrid):** VQE for pricing Hamiltonians
- **2029+ (Quantum):** Quantum game theory for multi-agent pricing equilibria

## Implementation Notes
1. All quantum upgrades implement the same trait interface — no caller code changes needed
2. AlgorithmTier enum allows runtime selection of best available algorithm
3. AlgorithmRegistry handles fallback chain: quantum → hybrid → quantum-inspired → classical
4. Feature vectors are designed to be compatible across all tiers
5. QUBO formulations are used where possible for direct quantum annealing compatibility
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_algorithm_tier_ordering() {
        assert_ne!(AlgorithmTier::Classical, AlgorithmTier::Quantum);
        assert_ne!(AlgorithmTier::HybridQuantum, AlgorithmTier::QuantumInspired);
    }

    #[test]
    fn test_optimization_problem_types() {
        let types = vec![
            OptimizationType::MinimizeCost,
            OptimizationType::MaximizeRevenue,
            OptimizationType::MinimizeRisk,
            OptimizationType::QUBO,
        ];
        assert_eq!(types.len(), 4);
    }

    #[test]
    fn test_algorithm_registry_empty() {
        let registry = AlgorithmRegistry::new();
        let inventory = registry.list_algorithms();
        assert!(inventory.credit_scorers.is_empty());
        assert!(inventory.optimizers.is_empty());
        assert!(inventory.searchers.is_empty());
    }

    #[test]
    fn test_quantum_upgrade_path_exists() {
        assert!(QUANTUM_UPGRADE_PATH.contains("Credit Scoring"));
        assert!(QUANTUM_UPGRADE_PATH.contains("QUBO"));
        assert!(QUANTUM_UPGRADE_PATH.contains("QAOA"));
    }
}
