//! Dynamic Programming — Bellman Equation for Sequential Decisions.
//!
//! Solves multi-stage optimization problems where decisions at each stage
//! affect future states and rewards.
//!
//! Use cases:
//! - Inventory management: optimal ordering policy over time
//! - Investment planning: allocate budget across periods
//! - Credit repayment: optimal payment schedule

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// A dynamic programming problem definition.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DpProblem {
    /// Number of stages (time periods)
    pub stages: usize,
    /// Possible states at each stage
    pub states: Vec<usize>,
    /// Possible actions at each state
    pub actions: Vec<usize>,
}

/// Result of solving a DP problem.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DpResult {
    /// Optimal value at each stage and state
    pub value_function: Vec<Vec<f64>>,
    /// Optimal action at each stage and state
    pub policy: Vec<Vec<usize>>,
    /// Optimal total value
    pub optimal_value: f64,
}

/// Bellman equation solver for finite-horizon DP problems.
///
/// Solves: V_t(s) = max_a { R(s,a) + γ * Σ P(s'|s,a) * V_{t+1}(s') }
///
/// Uses backward induction (value iteration from the last stage).
pub struct BellmanSolver {
    /// Discount factor (0 < γ ≤ 1)
    pub discount: f64,
}

impl BellmanSolver {
    pub fn new(discount: f64) -> Self {
        Self {
            discount: discount.clamp(0.0, 1.0),
        }
    }

    /// Solve a finite-horizon DP problem.
    ///
    /// # Arguments
    /// * `reward` - R(s, a): reward for taking action a in state s
    /// * `transition` - P(s'|s,a): probability of transitioning to s' from s with action a
    /// * `num_states` - Number of possible states
    /// * `num_actions` - Number of possible actions
    /// * `num_stages` - Number of time stages
    /// * `terminal_value` - V_T(s): value at the terminal stage
    pub fn solve(
        &self,
        reward: impl Fn(usize, usize) -> f64,
        transition: impl Fn(usize, usize, usize) -> f64,
        num_states: usize,
        num_actions: usize,
        num_stages: usize,
        terminal_value: impl Fn(usize) -> f64,
    ) -> DpResult {
        // Initialize value function with terminal values
        let mut value = vec![vec![0.0; num_states]; num_stages + 1];
        let mut policy = vec![vec![0usize; num_states]; num_stages];

        // Terminal values
        for s in 0..num_states {
            value[num_stages][s] = terminal_value(s);
        }

        // Backward induction
        for t in (0..num_stages).rev() {
            for s in 0..num_states {
                let mut best_value = f64::NEG_INFINITY;
                let mut best_action = 0;

                for a in 0..num_actions {
                    let immediate = reward(s, a);

                    let future: f64 = (0..num_states)
                        .map(|s_next| {
                            let prob = transition(s, a, s_next);
                            prob * value[t + 1][s_next]
                        })
                        .sum();

                    let total = immediate + self.discount * future;

                    if total > best_value {
                        best_value = total;
                        best_action = a;
                    }
                }

                value[t][s] = best_value;
                policy[t][s] = best_action;
            }
        }

        let optimal_value = value[0].iter().cloned().fold(f64::NEG_INFINITY, f64::max);

        DpResult {
            value_function: value,
            policy,
            optimal_value,
        }
    }
}

/// Inventory management using dynamic programming.
///
/// Finds optimal order quantity at each period to minimize
/// holding + shortage + ordering costs.
///
/// # Arguments
/// * `demand_dist` - Probability distribution of demand (P(demand = k))
/// * `holding_cost` - Cost per unit of inventory held
/// * `shortage_cost` - Cost per unit of unmet demand
/// * `ordering_cost` - Fixed cost per order + variable cost per unit
/// * `max_inventory` - Maximum inventory level
/// * `periods` - Number of planning periods
pub fn inventory_dp(
    demand_dist: &[f64],
    holding_cost: f64,
    shortage_cost: f64,
    ordering_cost_fn: impl Fn(f64) -> f64,
    max_inventory: usize,
    periods: usize,
    discount: f64,
) -> DpResult {
    let solver = BellmanSolver::new(discount);
    let max_demand = demand_dist.len().saturating_sub(1);

    // Reward: negative cost (we minimize cost = maximize negative cost)
    let reward = |s: usize, a: usize| {
        let inventory = s as f64;
        let order = a as f64;
        let total = inventory + order;

        // Expected cost from demand
        let mut expected_cost = 0.0;
        for d in 0..=max_demand {
            let demand = d as f64;
            let prob = if d < demand_dist.len() { demand_dist[d] } else { 0.0 };
            let remaining = (total - demand).max(0.0);
            let shortage = (demand - total).max(0.0);
            expected_cost += prob * (holding_cost * remaining + shortage_cost * shortage);
        }

        -(ordering_cost_fn(order) + expected_cost)
    };

    // Transition: next inventory = max(current + order - demand, 0)
    let transition = |s: usize, a: usize, s_next: usize| {
        let total = (s + a).min(max_inventory);
        let demand = total.saturating_sub(s_next);
        if demand < demand_dist.len() {
            demand_dist[demand]
        } else {
            0.0
        }
    };

    solver.solve(
        reward,
        transition,
        max_inventory + 1,
        max_inventory + 1,
        periods,
        |_| 0.0, // Terminal value
    )
}

/// Investment allocation using dynamic programming.
///
/// Allocates budget across investment options over multiple periods
/// to maximize expected return.
pub fn investment_dp(
    returns: &[Vec<f64>],    // returns[option][period]
    probabilities: &[Vec<f64>], // probabilities[option][period]
    budget_levels: usize,
    periods: usize,
    discount: f64,
) -> DpResult {
    let num_options = returns.len();
    let solver = BellmanSolver::new(discount);

    let reward = |s: usize, a: usize| {
        let budget = s as f64;
        let allocation = (a % num_options) as f64 / num_options as f64 * budget;
        let option = a % num_options;
        let period = a / num_options;

        if option < returns.len() && period < returns[option].len() {
            allocation * returns[option][period]
        } else {
            0.0
        }
    };

    let transition = |s: usize, a: usize, s_next: usize| {
        // Deterministic transition for simplicity
        if s_next == s { 1.0 } else { 0.0 }
    };

    solver.solve(
        reward,
        transition,
        budget_levels,
        num_options * periods,
        periods,
        |s| s as f64, // Terminal value = remaining budget
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bellman_basic() {
        // Simple 2-state, 2-action, 3-stage problem
        let solver = BellmanSolver::new(0.9);

        let reward = |s: usize, a: usize| -> f64 {
            match (s, a) {
                (0, 0) => 1.0,
                (0, 1) => 2.0,
                (1, 0) => 3.0,
                (1, 1) => 1.5,
                _ => 0.0,
            }
        };

        let transition = |s: usize, a: usize, s_next: usize| -> f64 {
            match (s, a, s_next) {
                (0, 0, 0) => 0.7,
                (0, 0, 1) => 0.3,
                (0, 1, 0) => 0.5,
                (0, 1, 1) => 0.5,
                (1, 0, 0) => 0.4,
                (1, 0, 1) => 0.6,
                (1, 1, 0) => 0.2,
                (1, 1, 1) => 0.8,
                _ => 0.0,
            }
        };

        let result = solver.solve(reward, transition, 2, 2, 3, |_| 0.0);

        assert!(result.optimal_value > 0.0);
        assert_eq!(result.policy.len(), 3);
        assert_eq!(result.policy[0].len(), 2);
    }

    #[test]
    fn test_inventory_dp() {
        let demand_dist = vec![0.1, 0.3, 0.4, 0.2]; // demand 0,1,2,3
        let result = inventory_dp(
            &demand_dist,
            1.0,  // holding cost
            5.0,  // shortage cost
            |order| if order > 0.0 { 10.0 + order * 2.0 } else { 0.0 },
            10,   // max inventory
            5,    // periods
            0.95,
        );

        assert!(result.optimal_value < 0.0); // Negative because we're maximizing negative cost
        assert_eq!(result.policy.len(), 5);
    }

    #[test]
    fn test_bellman_deterministic() {
        // Walk right (reward 1) or stay (reward 0) on a line
        let solver = BellmanSolver::new(1.0);

        let reward = |_s: usize, a: usize| -> f64 {
            if a == 1 { 1.0 } else { 0.0 }
        };

        let transition = |s: usize, a: usize, s_next: usize| -> f64 {
            let next = (s + a).min(4);
            if s_next == next { 1.0 } else { 0.0 }
        };

        let result = solver.solve(reward, transition, 5, 2, 4, |_| 0.0);

        // Optimal: always move right = 4.0 total reward
        assert!((result.optimal_value - 4.0).abs() < 0.01);
    }
}
