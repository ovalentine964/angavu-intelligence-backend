//! Stochastic Optimization — Scenario-Based Optimization Under Uncertainty.
//!
//! Optimizes decisions when outcomes are uncertain by considering
//! multiple scenarios with associated probabilities.
//!
//! Use cases:
//! - Revenue optimization under demand uncertainty
//! - Portfolio optimization with market scenarios
//! - Supply chain planning with disruption scenarios

use serde::{Deserialize, Serialize};

/// A scenario representing a possible future state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Scenario {
    /// Unique identifier
    pub id: String,
    /// Probability of this scenario occurring (0-1)
    pub probability: f64,
    /// Objective value for each decision option
    pub outcomes: Vec<f64>,
    /// Additional context/description
    pub description: String,
}

/// Result of stochastic optimization.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StochasticResult {
    /// Best decision index
    pub best_decision: usize,
    /// Expected value of the best decision
    pub expected_value: f64,
    /// Value at Risk (VaR) at the specified confidence level
    pub value_at_risk: f64,
    /// Conditional Value at Risk (CVaR) — expected loss beyond VaR
    pub conditional_var: f64,
    /// Expected value under each scenario for the best decision
    pub scenario_values: Vec<f64>,
    /// Robustness score (0-1, higher = more robust across scenarios)
    pub robustness: f64,
}

/// Stochastic optimizer using scenario-based approach.
pub struct StochasticOptimizer {
    /// Confidence level for VaR/CVaR (e.g., 0.95)
    pub confidence: f64,
    /// Risk aversion parameter (0 = risk-neutral, higher = more risk-averse)
    pub risk_aversion: f64,
}

impl Default for StochasticOptimizer {
    fn default() -> Self {
        Self {
            confidence: 0.95,
            risk_aversion: 0.0,
        }
    }
}

impl StochasticOptimizer {
    pub fn new(confidence: f64, risk_aversion: f64) -> Self {
        Self {
            confidence: confidence.clamp(0.0, 1.0),
            risk_aversion: risk_aversion.max(0.0),
        }
    }

    /// Find the decision that maximizes expected value.
    pub fn maximize_expected_value(
        &self,
        scenarios: &[Scenario],
        num_decisions: usize,
    ) -> StochasticResult {
        let mut best_decision = 0;
        let mut best_ev = f64::NEG_INFINITY;

        for d in 0..num_decisions {
            let ev: f64 = scenarios
                .iter()
                .map(|s| s.probability * s.outcomes.get(d).copied().unwrap_or(0.0))
                .sum();

            if ev > best_ev {
                best_ev = ev;
                best_decision = d;
            }
        }

        self.build_result(scenarios, num_decisions, best_decision)
    }

    /// Find the decision that maximizes expected utility with risk aversion.
    ///
    /// Uses mean-variance optimization: max E[x] - λ * Var(x)
    pub fn maximize_utility(
        &self,
        scenarios: &[Scenario],
        num_decisions: usize,
    ) -> StochasticResult {
        let mut best_decision = 0;
        let mut best_utility = f64::NEG_INFINITY;

        for d in 0..num_decisions {
            let values: Vec<f64> = scenarios
                .iter()
                .map(|s| s.outcomes.get(d).copied().unwrap_or(0.0))
                .collect();

            let ev: f64 = scenarios
                .iter()
                .zip(values.iter())
                .map(|(s, v)| s.probability * v)
                .sum();

            let variance: f64 = scenarios
                .iter()
                .zip(values.iter())
                .map(|(s, v)| s.probability * (v - ev).powi(2))
                .sum();

            let utility = ev - self.risk_aversion * variance;

            if utility > best_utility {
                best_utility = utility;
                best_decision = d;
            }
        }

        self.build_result(scenarios, num_decisions, best_decision)
    }

    /// Minimax regret: minimize the maximum regret across all scenarios.
    ///
    /// Regret = best possible outcome - actual outcome for each scenario.
    pub fn minimize_regret(
        &self,
        scenarios: &[Scenario],
        num_decisions: usize,
    ) -> StochasticResult {
        // Compute regret matrix
        let mut max_regret_per_decision = vec![f64::NEG_INFINITY; num_decisions];

        for s in scenarios {
            let best_outcome = s
                .outcomes
                .iter()
                .take(num_decisions)
                .cloned()
                .fold(f64::NEG_INFINITY, f64::max);

            for d in 0..num_decisions {
                let outcome = s.outcomes.get(d).copied().unwrap_or(0.0);
                let regret = best_outcome - outcome;
                max_regret_per_decision[d] = max_regret_per_decision[d].max(regret);
            }
        }

        let best_decision = max_regret_per_decision
            .iter()
            .enumerate()
            .min_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i)
            .unwrap_or(0);

        self.build_result(scenarios, num_decisions, best_decision)
    }

    /// Expected value of perfect information (EVPI).
    ///
    /// How much would perfect knowledge of the future be worth?
    /// EVPI = E[best decision with perfect info] - E[best decision without info]
    pub fn evpi(&self, scenarios: &[Scenario], num_decisions: usize) -> f64 {
        // Expected value with perfect info: choose best decision per scenario
        let ev_perfect: f64 = scenarios
            .iter()
            .map(|s| {
                let best = s
                    .outcomes
                    .iter()
                    .take(num_decisions)
                    .cloned()
                    .fold(f64::NEG_INFINITY, f64::max);
                s.probability * best
            })
            .sum();

        // Expected value without perfect info
        let ev_best = self
            .maximize_expected_value(scenarios, num_decisions)
            .expected_value;

        ev_perfect - ev_best
    }

    /// Build result with VaR, CVaR, and robustness metrics.
    fn build_result(
        &self,
        scenarios: &[Scenario],
        num_decisions: usize,
        best_decision: usize,
    ) -> StochasticResult {
        let mut scenario_values: Vec<f64> = scenarios
            .iter()
            .map(|s| s.outcomes.get(best_decision).copied().unwrap_or(0.0))
            .collect();

        let expected_value: f64 = scenarios
            .iter()
            .map(|s| s.probability * s.outcomes.get(best_decision).copied().unwrap_or(0.0))
            .sum();

        // Sort for VaR computation
        let mut sorted_values = scenario_values.clone();
        sorted_values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        // VaR: the loss at the confidence percentile
        let var_idx = ((1.0 - self.confidence) * sorted_values.len() as f64) as usize;
        let value_at_risk = expected_value - sorted_values[var_idx.min(sorted_values.len() - 1)];

        // CVaR: expected loss beyond VaR
        let cvar_values: Vec<f64> = sorted_values[..=var_idx.min(sorted_values.len() - 1)].to_vec();
        let cvar_mean = if cvar_values.is_empty() {
            0.0
        } else {
            cvar_values.iter().sum::<f64>() / cvar_values.len() as f64
        };
        let conditional_var = expected_value - cvar_mean;

        // Robustness: coefficient of variation (lower = more robust)
        let variance: f64 = scenarios
            .iter()
            .map(|s| {
                let v = s.outcomes.get(best_decision).copied().unwrap_or(0.0);
                s.probability * (v - expected_value).powi(2)
            })
            .sum();

        let std_dev = variance.sqrt();
        let robustness = if expected_value.abs() > 1e-10 {
            1.0 - (std_dev / expected_value.abs()).min(1.0)
        } else {
            0.0
        };

        StochasticResult {
            best_decision,
            expected_value,
            value_at_risk,
            conditional_var,
            scenario_values,
            robustness,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_scenarios() -> Vec<Scenario> {
        vec![
            Scenario {
                id: "boom".into(),
                probability: 0.3,
                outcomes: vec![100.0, 80.0, 120.0],
                description: "Economic boom".into(),
            },
            Scenario {
                id: "normal".into(),
                probability: 0.5,
                outcomes: vec![50.0, 60.0, 40.0],
                description: "Normal conditions".into(),
            },
            Scenario {
                id: "recession".into(),
                probability: 0.2,
                outcomes: vec![-20.0, 10.0, -50.0],
                description: "Economic recession".into(),
            },
        ]
    }

    #[test]
    fn test_maximize_expected_value() {
        let optimizer = StochasticOptimizer::default();
        let scenarios = test_scenarios();

        let result = optimizer.maximize_expected_value(&scenarios, 3);

        // EV of option 0: 0.3*100 + 0.5*50 + 0.2*(-20) = 30 + 25 - 4 = 51
        // EV of option 1: 0.3*80 + 0.5*60 + 0.2*10 = 24 + 30 + 2 = 56
        // EV of option 2: 0.3*120 + 0.5*40 + 0.2*(-50) = 36 + 20 - 10 = 46
        assert_eq!(result.best_decision, 1);
        assert!((result.expected_value - 56.0).abs() < 0.01);
    }

    #[test]
    fn test_minimize_regret() {
        let optimizer = StochasticOptimizer::default();
        let scenarios = test_scenarios();

        let result = optimizer.minimize_regret(&scenarios, 3);
        // Option 1 has the least maximum regret
        assert_eq!(result.best_decision, 1);
    }

    #[test]
    fn test_evpi() {
        let optimizer = StochasticOptimizer::default();
        let scenarios = test_scenarios();

        let evpi = optimizer.evpi(&scenarios, 3);
        // EVPI should be positive (perfect info has value)
        assert!(evpi > 0.0);
    }

    #[test]
    fn test_risk_averse() {
        let optimizer = StochasticOptimizer::new(0.95, 2.0);
        let scenarios = test_scenarios();

        let result = optimizer.maximize_utility(&scenarios, 3);
        // With high risk aversion, should prefer the safer option (option 1)
        assert_eq!(result.best_decision, 1);
    }
}
