// =============================================================================
// Angavu Intelligence — Classical Algorithm Implementations for Quantum Traits
//
// Addresses B12 P1 gaps:
// - Classical implementations of CreditScoringAlgorithm, OptimizationAlgorithm, SearchAlgorithm
// - Simulated Annealing for quantum-inspired optimization
// - Makes the trait system functional (currently all traits are unimplemented interfaces)
//
// These implementations use the quantum_traits interfaces so they can be
// seamlessly swapped for quantum versions when hardware becomes available.
// =============================================================================

use async_trait::async_trait;
use rand::Rng;
use serde::{Deserialize, Serialize};

use super::quantum_traits::*;

// ═══════════════════════════════════════════════════════════
//  Classical Credit Scoring Algorithm (wraps LogisticRegression/IRLS)
// ═══════════════════════════════════════════════════════════

/// Classical credit scoring using logistic regression via IRLS.
/// Implements the CreditScoringAlgorithm trait for the quantum upgrade path.
pub struct ClassicalCreditScorer {
    coefficients: Vec<f64>,
    intercept: f64,
    feature_names: Vec<String>,
    trained: bool,
    metrics: Option<TrainingMetricsSnapshot>,
}

impl ClassicalCreditScorer {
    pub fn new() -> Self {
        Self {
            coefficients: Vec::new(),
            intercept: 0.0,
            feature_names: Vec::new(),
            trained: false,
            metrics: None,
        }
    }

    /// Create with pre-trained coefficients (for loading saved models)
    pub fn with_coefficients(
        coefficients: Vec<f64>,
        intercept: f64,
        feature_names: Vec<String>,
    ) -> Self {
        Self {
            coefficients,
            intercept,
            feature_names,
            trained: true,
            metrics: None,
        }
    }

    /// Sigmoid function
    fn sigmoid(z: f64) -> f64 {
        1.0 / (1.0 + (-z).exp())
    }

    /// Compute log-odds: z = intercept + Σ(coef_i * x_i)
    fn log_odds(&self, features: &[f64]) -> f64 {
        self.intercept + features.iter()
            .zip(self.coefficients.iter())
            .map(|(x, w)| x * w)
            .sum::<f64>()
    }

    /// Map probability to Alama score (300-850 range)
    fn probability_to_alama(p: f64) -> u16 {
        (300.0 + p * 550.0).round().clamp(300.0, 850.0) as u16
    }

    /// IRLS (Iteratively Reweighted Least Squares) training for logistic regression.
    /// This is the classical MLE implementation.
    fn train_irls(&mut self, data: &CreditTrainingData, max_iter: usize, tol: f64) -> Result<(), AlgorithmError> {
        let n = data.features.len();
        let p = data.feature_names.len();

        if n == 0 || p == 0 {
            return Err(AlgorithmError::TrainingFailed("Empty training data".to_string()));
        }

        // Initialize coefficients to zero
        let mut beta = vec![0.0_f64; p + 1]; // +1 for intercept
        let mut prev_ll = f64::NEG_INFINITY;

        for iteration in 0..max_iter {
            // Compute predictions
            let predictions: Vec<f64> = data.features.iter().map(|x| {
                let z = beta[0] + x.iter().zip(beta[1..].iter()).map(|(xi, bi)| xi * bi).sum::<f64>();
                Self::sigmoid(z)
            }).collect();

            // Compute log-likelihood
            let ll: f64 = data.labels.iter().zip(predictions.iter())
                .map(|(&y, &p)| {
                    let y_f = y as f64;
                    (y_f * p.max(1e-15).ln() + (1.0 - y_f) * (1.0 - p).max(1e-15).ln())
                })
                .sum();

            // Check convergence
            if (ll - prev_ll).abs() < tol && iteration > 0 {
                tracing::info!(iterations = iteration, log_likelihood = %ll, "IRLS converged");
                break;
            }
            prev_ll = ll;

            // Compute weights and working response for IRLS
            let mut xt_w_x = vec![vec![0.0_f64; p + 1]; p + 1];
            let mut xt_w_z = vec![0.0_f64; p + 1];

            for i in 0..n {
                let pi = predictions[i];
                let yi = data.labels[i] as f64;
                let wi = pi * (1.0 - pi); // variance
                let zi = (yi - pi) / wi.max(1e-15); // working response

                // Build row [1, x_i]
                let mut row = vec![1.0_f64];
                row.extend_from_slice(&data.features[i]);

                // Accumulate X^T W X and X^T W z
                for j in 0..=p {
                    xt_w_z[j] += wi * row[j] * zi;
                    for k in 0..=p {
                        xt_w_x[j][k] += wi * row[j] * row[k];
                    }
                }
            }

            // Solve normal equations with regularization (Ridge)
            let lambda = 0.01;
            for j in 1..=p {
                xt_w_x[j][j] += lambda;
            }

            // Simple Gauss-Seidel solver
            let delta = gauss_seidel_solve(&xt_w_x, &xt_w_z, 100, 1e-8);

            // Update coefficients
            for j in 0..=p {
                beta[j] += delta[j];
            }
        }

        self.intercept = beta[0];
        self.coefficients = beta[1..].to_vec();
        self.feature_names = data.feature_names.clone();
        self.trained = true;

        // Compute final metrics
        let predictions: Vec<f64> = data.features.iter().map(|x| {
            let z = self.intercept + x.iter().zip(self.coefficients.iter())
                .map(|(xi, bi)| xi * bi).sum::<f64>();
            Self::sigmoid(z)
        }).collect();

        let auc = compute_auc_roc(&predictions, &data.labels);
        let accuracy = compute_accuracy(&predictions, &data.labels, 0.5);

        self.metrics = Some(TrainingMetricsSnapshot {
            auc_roc: auc,
            accuracy,
            precision: 0.0, // Would need confusion matrix
            recall: 0.0,
            f1_score: 0.0,
        });

        Ok(())
    }
}

#[async_trait]
impl CreditScoringAlgorithm for ClassicalCreditScorer {
    fn algorithm_id(&self) -> &str {
        "classical_logistic_regression_irls"
    }

    fn algorithm_tier(&self) -> AlgorithmTier {
        AlgorithmTier::Classical
    }

    async fn train(&mut self, training_data: &CreditTrainingData) -> Result<TrainingResult, AlgorithmError> {
        let start = std::time::Instant::now();
        self.train_irls(training_data, 100, 1e-6)?;
        let duration = start.elapsed().as_millis() as u64;

        Ok(TrainingResult {
            algorithm_id: self.algorithm_id().to_string(),
            tier: self.algorithm_tier(),
            metrics: self.metrics.clone().unwrap_or(TrainingMetricsSnapshot {
                auc_roc: 0.0,
                accuracy: 0.0,
                precision: 0.0,
                recall: 0.0,
                f1_score: 0.0,
            }),
            training_duration_ms: duration,
        })
    }

    async fn predict(&self, features: &[f64]) -> Result<CreditPrediction, AlgorithmError> {
        if !self.trained {
            return Err(AlgorithmError::PredictionFailed("Model not trained".to_string()));
        }
        if features.len() != self.coefficients.len() {
            return Err(AlgorithmError::PredictionFailed(
                format!("Feature count mismatch: expected {}, got {}", self.coefficients.len(), features.len())
            ));
        }

        let z = self.log_odds(features);
        let probability = Self::sigmoid(z);
        let alama_score = Self::probability_to_alama(probability);
        let confidence = (2.0 * (probability - 0.5).abs()).min(1.0);

        let contributing_factors: Vec<(String, f64)> = self.feature_names.iter()
            .zip(features.iter())
            .zip(self.coefficients.iter())
            .map(|((name, &x), &w)| (name.clone(), x * w))
            .collect();

        Ok(CreditPrediction {
            probability,
            alama_score,
            confidence,
            contributing_factors,
        })
    }

    async fn predict_batch(&self, features: &[Vec<f64>]) -> Result<Vec<CreditPrediction>, AlgorithmError> {
        let mut results = Vec::with_capacity(features.len());
        for f in features {
            results.push(self.predict(f).await?);
        }
        Ok(results)
    }

    fn feature_importance(&self) -> Vec<(String, f64)> {
        self.feature_names.iter()
            .zip(self.coefficients.iter())
            .map(|(name, &coef)| (name.clone(), coef.abs()))
            .collect()
    }
}

// ═══════════════════════════════════════════════════════════
//  Simulated Annealing — Quantum-Inspired Optimization
// ═══════════════════════════════════════════════════════════

/// Simulated Annealing optimizer for combinatorial optimization problems.
/// This is the quantum-inspired classical step in the upgrade path.
///
/// Simulates the physical annealing process: start at high temperature,
/// gradually cool, accept worse solutions with decreasing probability.
/// This enables escaping local optima, similar to quantum tunneling.
pub struct SimulatedAnnealingOptimizer {
    /// Initial temperature
    initial_temp: f64,
    /// Cooling rate (0 < α < 1)
    cooling_rate: f64,
    /// Minimum temperature (stopping criterion)
    min_temp: f64,
    /// Maximum iterations per temperature
    iterations_per_temp: usize,
    /// Total iterations cap
    max_total_iterations: usize,
}

impl SimulatedAnnealingOptimizer {
    pub fn new() -> Self {
        Self {
            initial_temp: 100.0,
            cooling_rate: 0.995,
            min_temp: 0.001,
            iterations_per_temp: 100,
            max_total_iterations: 100_000,
        }
    }

    pub fn with_config(initial_temp: f64, cooling_rate: f64, min_temp: f64) -> Self {
        Self {
            initial_temp,
            cooling_rate,
            min_temp,
            iterations_per_temp: 100,
            max_total_iterations: 100_000,
        }
    }

    /// Acceptance probability for a worse solution.
    /// P(accept) = exp(-ΔE / T)
    fn acceptance_probability(delta: f64, temperature: f64) -> f64 {
        if delta <= 0.0 {
            return 1.0; // Always accept better solutions
        }
        if temperature <= 0.0 {
            return 0.0;
        }
        (-delta / temperature).exp()
    }

    /// Solve a combinatorial optimization problem using simulated annealing.
    /// Works with QUBO-formatted problems for quantum annealing compatibility.
    pub fn solve_qubo(&self, problem: &OptimizationProblem) -> Result<OptimizationSolution, AlgorithmError> {
        let n = problem.variables.len();
        if n == 0 {
            return Err(AlgorithmError::Internal("No variables in problem".to_string()));
        }

        let mut rng = rand::thread_rng();

        // Initialize random solution
        let mut current_solution: Vec<f64> = problem.variables.iter().map(|v| {
            match v.var_type {
                VariableType::Binary => if rng.gen_bool(0.5) { 1.0 } else { 0.0 },
                VariableType::Integer => rng.gen_range(v.lower_bound as i64..=v.upper_bound as i64) as f64,
                VariableType::Continuous => rng.gen_range(v.lower_bound..=v.upper_bound),
            }
        }).collect();

        let mut current_cost = self.evaluate_cost(problem, &current_solution);
        let mut best_solution = current_solution.clone();
        let mut best_cost = current_cost;

        let mut temp = self.initial_temp;
        let mut total_iterations = 0;

        while temp > self.min_temp && total_iterations < self.max_total_iterations {
            for _ in 0..self.iterations_per_temp {
                total_iterations += 1;

                // Generate neighbor by perturbing one variable
                let idx = rng.gen_range(0..n);
                let var = &problem.variables[idx];
                let neighbor_value = match var.var_type {
                    VariableType::Binary => if current_solution[idx] > 0.5 { 0.0 } else { 1.0 },
                    VariableType::Integer => {
                        let delta = rng.gen_range(-2..=2);
                        ((current_solution[idx] as i64) + delta)
                            .clamp(var.lower_bound as i64, var.upper_bound as i64) as f64
                    }
                    VariableType::Continuous => {
                        let range = var.upper_bound - var.lower_bound;
                        let step = range * 0.1 * rng.gen_range(-1.0..1.0);
                        (current_solution[idx] + step).clamp(var.lower_bound, var.upper_bound)
                    }
                };

                let mut neighbor = current_solution.clone();
                neighbor[idx] = neighbor_value;
                let neighbor_cost = self.evaluate_cost(problem, &neighbor);

                let delta = neighbor_cost - current_cost;
                if Self::acceptance_probability(delta, temp) > rng.gen() {
                    current_solution = neighbor;
                    current_cost = neighbor_cost;

                    if current_cost < best_cost {
                        best_solution = current_solution.clone();
                        best_cost = current_cost;
                    }
                }
            }

            temp *= self.cooling_rate;
        }

        let variable_values: Vec<(String, f64)> = problem.variables.iter()
            .zip(best_solution.iter())
            .map(|(v, &val)| (v.name.clone(), val))
            .collect();

        Ok(OptimizationSolution {
            problem_id: problem.problem_id.clone(),
            algorithm_id: self.algorithm_id().to_string(),
            tier: self.algorithm_tier(),
            objective_value: best_cost,
            variable_values,
            is_optimal: false, // SA doesn't guarantee optimality
            solver_time_ms: 0, // Caller should measure
            iterations: total_iterations as u64,
        })
    }

    /// Evaluate the objective function + constraint penalties
    fn evaluate_cost(&self, problem: &OptimizationProblem, solution: &[f64]) -> f64 {
        let mut cost = 0.0;

        // Objective function
        for (var_name, &coeff) in &problem.objective.coefficients {
            if let Some(idx) = problem.variables.iter().position(|v| &v.name == var_name) {
                match problem.objective.direction {
                    ObjectiveDirection::Minimize => cost += coeff * solution[idx],
                    ObjectiveDirection::Maximize => cost -= coeff * solution[idx],
                }
            }
        }

        // Constraint penalties (quadratic penalty method)
        let penalty_weight = 1000.0;
        for constraint in &problem.constraints {
            let lhs: f64 = constraint.coefficients.iter()
                .filter_map(|(name, coeff)| {
                    problem.variables.iter().position(|v| &v.name == name)
                        .map(|idx| coeff * solution[idx])
                })
                .sum();

            let violation = match constraint.sense {
                ConstraintSense::LessEqual => (lhs - constraint.rhs).max(0.0),
                ConstraintSense::Equal => (lhs - constraint.rhs).abs(),
                ConstraintSense::GreaterEqual => (constraint.rhs - lhs).max(0.0),
            };

            cost += penalty_weight * violation * violation;
        }

        cost
    }
}

#[async_trait]
impl OptimizationAlgorithm for SimulatedAnnealingOptimizer {
    fn algorithm_id(&self) -> &str {
        "simulated_annealing_classical"
    }

    fn algorithm_tier(&self) -> AlgorithmTier {
        AlgorithmTier::QuantumInspired
    }

    async fn solve(&self, problem: &OptimizationProblem) -> Result<OptimizationSolution, AlgorithmError> {
        self.solve_qubo(problem)
    }

    fn can_handle(&self, problem_size: usize) -> bool {
        problem_size <= 10_000 // SA handles up to 10k variables efficiently
    }

    fn max_problem_size(&self) -> usize {
        10_000
    }
}

// ═══════════════════════════════════════════════════════════
//  Classical Search Algorithm — Bipartite Matching
// ═══════════════════════════════════════════════════════════

/// Classical search using cosine similarity + greedy matching.
/// Implements the SearchAlgorithm trait for the quantum upgrade path.
pub struct ClassicalSearchEngine {
    /// Minimum similarity score for a match
    min_similarity: f64,
}

impl ClassicalSearchEngine {
    pub fn new() -> Self {
        Self { min_similarity: 0.3 }
    }

    /// Cosine similarity between two vectors
    fn cosine_similarity(a: &[f64], b: &[f64]) -> f64 {
        if a.len() != b.len() || a.is_empty() {
            return 0.0;
        }
        let dot: f64 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
        let norm_a: f64 = a.iter().map(|x| x * x).sum::<f64>().sqrt();
        let norm_b: f64 = b.iter().map(|x| x * x).sum::<f64>().sqrt();
        if norm_a == 0.0 || norm_b == 0.0 {
            return 0.0;
        }
        dot / (norm_a * norm_b)
    }

    /// Skill overlap score between worker and job
    fn skill_overlap(worker_skills: &[String], job_skills: &[String]) -> f64 {
        if job_skills.is_empty() {
            return 1.0;
        }
        let matches = worker_skills.iter()
            .filter(|s| job_skills.contains(s))
            .count();
        matches as f64 / job_skills.len() as f64
    }
}

#[async_trait]
impl SearchAlgorithm for ClassicalSearchEngine {
    fn algorithm_id(&self) -> &str {
        "classical_cosine_similarity"
    }

    fn algorithm_tier(&self) -> AlgorithmTier {
        AlgorithmTier::Classical
    }

    async fn search(&self, query: &SearchQuery) -> Result<SearchResults, AlgorithmError> {
        // Placeholder: in production, this queries the database
        Ok(SearchResults {
            results: Vec::new(),
            total_candidates: 0,
            search_time_ms: 0,
            algorithm_id: self.algorithm_id().to_string(),
            tier: self.algorithm_tier(),
        })
    }

    async fn optimal_assignment(
        &self,
        workers: &[WorkerProfile],
        jobs: &[JobProfile],
    ) -> Result<Vec<(usize, usize, f64)>, AlgorithmError> {
        let n_workers = workers.len();
        let n_jobs = jobs.len();

        if n_workers == 0 || n_jobs == 0 {
            return Ok(Vec::new());
        }

        // Compute score matrix
        let mut scores: Vec<Vec<f64>> = vec![vec![0.0; n_jobs]; n_workers];
        for (i, worker) in workers.iter().enumerate() {
            for (j, job) in jobs.iter().enumerate() {
                let skill_score = Self::skill_overlap(&worker.skills, &job.required_skills);
                let embed_score = match (&worker.embedding, &job.embedding) {
                    (Some(we), Some(je)) => Self::cosine_similarity(we, je),
                    _ => 0.0,
                };
                // Combine skill match (70%) and embedding similarity (30%)
                scores[i][j] = 0.7 * skill_score + 0.3 * embed_score;
            }
        }

        // Greedy matching (optimal for bipartite matching would use Hungarian algorithm)
        let mut assignments = Vec::new();
        let mut used_workers = std::collections::HashSet::new();
        let mut used_jobs = std::collections::HashSet::new();

        // Sort all possible matches by score descending
        let mut all_matches: Vec<(usize, usize, f64)> = Vec::new();
        for i in 0..n_workers {
            for j in 0..n_jobs {
                if scores[i][j] >= self.min_similarity {
                    all_matches.push((i, j, scores[i][j]));
                }
            }
        }
        all_matches.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));

        for (worker_idx, job_idx, score) in all_matches {
            if !used_workers.contains(&worker_idx) && !used_jobs.contains(&job_idx) {
                assignments.push((worker_idx, job_idx, score));
                used_workers.insert(worker_idx);
                used_jobs.insert(job_idx);
            }
        }

        Ok(assignments)
    }
}

// ═══════════════════════════════════════════════════════════
//  Helper Functions
// ═══════════════════════════════════════════════════════════

/// Simple Gauss-Seidel solver for linear systems
fn gauss_seidel_solve(a: &[Vec<f64>], b: &[f64], max_iter: usize, tol: f64) -> Vec<f64> {
    let n = b.len();
    let mut x = vec![0.0_f64; n];

    for _ in 0..max_iter {
        let mut max_diff = 0.0;
        for i in 0..n {
            let old = x[i];
            if a[i][i].abs() < 1e-15 {
                continue;
            }
            let sum: f64 = (0..n).filter(|&j| j != i).map(|j| a[i][j] * x[j]).sum();
            x[i] = (b[i] - sum) / a[i][i];
            max_diff = max_diff.max((x[i] - old).abs());
        }
        if max_diff < tol {
            break;
        }
    }
    x
}

/// Compute AUC-ROC (area under receiver operating characteristic curve)
fn compute_auc_roc(predictions: &[f64], labels: &[u8]) -> f64 {
    let n = predictions.len();
    if n == 0 { return 0.0; }

    let mut pairs: Vec<(f64, u8)> = predictions.iter().zip(labels.iter())
        .map(|(&p, &l)| (p, l))
        .collect();
    pairs.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));

    let positives = labels.iter().filter(|&&l| l == 1).count() as f64;
    let negatives = labels.iter().filter(|&&l| l == 0).count() as f64;

    if positives == 0.0 || negatives == 0.0 {
        return 0.5;
    }

    let mut tp = 0.0;
    let mut fp = 0.0;
    let mut auc = 0.0;
    let mut prev_fpr = 0.0;

    for (_, label) in &pairs {
        if *label == 1 {
            tp += 1.0;
        } else {
            fp += 1.0;
            let fpr = fp / negatives;
            let tpr = tp / positives;
            auc += (fpr - prev_fpr) * tpr;
            prev_fpr = fpr;
        }
    }

    auc
}

/// Compute accuracy at a given threshold
fn compute_accuracy(predictions: &[f64], labels: &[u8], threshold: f64) -> f64 {
    let correct = predictions.iter().zip(labels.iter())
        .filter(|(&p, &l)| (p >= threshold && l == 1) || (p < threshold && l == 0))
        .count();
    correct as f64 / predictions.len().max(1) as f64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sigmoid() {
        assert!((ClassicalCreditScorer::sigmoid(0.0) - 0.5).abs() < 1e-10);
        assert!(ClassicalCreditScorer::sigmoid(10.0) > 0.99);
        assert!(ClassicalCreditScorer::sigmoid(-10.0) < 0.01);
    }

    #[test]
    fn test_probability_to_alama() {
        assert_eq!(ClassicalCreditScorer::probability_to_alama(0.0), 300);
        assert_eq!(ClassicalCreditScorer::probability_to_alama(1.0), 850);
        assert_eq!(ClassicalCreditScorer::probability_to_alama(0.5), 575);
    }

    #[test]
    fn test_simulated_annealing_acceptance() {
        // Better solution always accepted
        assert_eq!(SimulatedAnnealingOptimizer::acceptance_probability(-1.0, 1.0), 1.0);
        // Worse solution at high temp: ~37% chance
        let prob = SimulatedAnnealingOptimizer::acceptance_probability(1.0, 1.0);
        assert!((prob - 0.368).abs() < 0.01);
        // Worse solution at zero temp: 0% chance
        assert_eq!(SimulatedAnnealingOptimizer::acceptance_probability(1.0, 0.0), 0.0);
    }

    #[test]
    fn test_cosine_similarity() {
        let a = vec![1.0, 0.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        assert!((ClassicalSearchEngine::cosine_similarity(&a, &b) - 1.0).abs() < 1e-10);

        let c = vec![0.0, 1.0, 0.0];
        assert!((ClassicalSearchEngine::cosine_similarity(&a, &c) - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_skill_overlap() {
        let worker = vec!["welding".to_string(), "carpentry".to_string()];
        let job = vec!["welding".to_string()];
        assert!((ClassicalSearchEngine::skill_overlap(&worker, &job) - 1.0).abs() < 1e-10);

        let job2 = vec!["welding".to_string(), "plumbing".to_string()];
        assert!((ClassicalSearchEngine::skill_overlap(&worker, &job2) - 0.5).abs() < 1e-10);
    }
}
