//! Simplex Algorithm — Full Linear Programming Solver.
//!
//! Solves problems of the form:
//!   maximize    c^T x
//!   subject to  Ax ≤ b, x ≥ 0
//!
//! Use cases:
//! - Supply chain optimization: minimize cost subject to demand constraints
//! - Resource allocation: distribute limited budget across products
//! - Restock optimization: maximize profit given budget and storage limits

use serde::{Deserialize, Serialize};

/// A linear programming problem.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LpProblem {
    /// Objective function coefficients (maximize c^T x)
    pub objective: Vec<f64>,
    /// Constraint matrix A (each row is a constraint)
    pub constraints: Vec<Vec<f64>>,
    /// Right-hand side vector b
    pub rhs: Vec<f64>,
}

/// Result of solving a linear program.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LpResult {
    /// Optimal objective value
    pub optimal_value: f64,
    /// Optimal solution vector
    pub solution: Vec<f64>,
    /// Number of iterations
    pub iterations: usize,
    /// Whether a feasible solution was found
    pub feasible: bool,
    /// Whether the solution is bounded
    pub bounded: bool,
}

/// Simplex method solver for linear programming problems.
pub struct SimplexSolver {
    max_iterations: usize,
    tolerance: f64,
}

impl Default for SimplexSolver {
    fn default() -> Self {
        Self {
            max_iterations: 1000,
            tolerance: 1e-10,
        }
    }
}

impl SimplexSolver {
    /// Create a new solver with custom parameters.
    pub fn new(max_iterations: usize, tolerance: f64) -> Self {
        Self { max_iterations, tolerance }
    }

    /// Solve a linear programming problem using the revised simplex method.
    ///
    /// # Arguments
    /// * `problem` - The LP problem definition
    ///
    /// # Returns
    /// `LpResult` with optimal value and solution vector.
    pub fn solve(&self, problem: &LpProblem) -> LpResult {
        let m = problem.constraints.len();
        let n = problem.objective.len();

        if m == 0 || n == 0 || problem.rhs.len() != m {
            return LpResult {
                optimal_value: 0.0,
                solution: vec![0.0; n],
                iterations: 0,
                feasible: false,
                bounded: false,
            };
        }

        // Build tableau: (m+1) rows × (n+m+1) columns
        // [A | I | b]
        // [-c | 0 | 0]
        let cols = n + m + 1;
        let rows = m + 1;
        let mut tableau = vec![vec![0.0; cols]; rows];

        // Constraint rows
        for i in 0..m {
            for j in 0..n {
                tableau[i][j] = problem.constraints[i][j];
            }
            tableau[i][n + i] = 1.0; // slack variable
            tableau[i][cols - 1] = problem.rhs[i];
        }

        // Objective row (negated for maximization)
        for j in 0..n {
            tableau[m][j] = -problem.objective[j];
        }

        // Track basic variables in each row
        let mut basic_vars: Vec<usize> = (n..n + m).collect();

        let mut iterations = 0;

        while iterations < self.max_iterations {
            iterations += 1;

            // Find pivot column (most negative in objective row)
            let mut pivot_col: Option<usize> = None;
            let mut min_val = -self.tolerance;
            for j in 0..cols - 1 {
                if tableau[m][j] < min_val {
                    min_val = tableau[m][j];
                    pivot_col = Some(j);
                }
            }

            // If no negative coefficient, we're optimal
            let pivot_col = match pivot_col {
                Some(c) => c,
                None => break,
            };

            // Find pivot row using minimum ratio test
            let mut pivot_row: Option<usize> = None;
            let mut min_ratio = f64::MAX;
            for i in 0..m {
                if tableau[i][pivot_col] > self.tolerance {
                    let ratio = tableau[i][cols - 1] / tableau[i][pivot_col];
                    if ratio < min_ratio {
                        min_ratio = ratio;
                        pivot_row = Some(i);
                    }
                }
            }

            // If no valid pivot row, problem is unbounded
            let pivot_row = match pivot_row {
                Some(r) => r,
                None => {
                    return LpResult {
                        optimal_value: f64::INFINITY,
                        solution: vec![0.0; n],
                        iterations,
                        feasible: true,
                        bounded: false,
                    };
                }
            };

            // Pivot operation
            let pivot_element = tableau[pivot_row][pivot_col];
            for j in 0..cols {
                tableau[pivot_row][j] /= pivot_element;
            }

            for i in 0..rows {
                if i != pivot_row {
                    let factor = tableau[i][pivot_col];
                    for j in 0..cols {
                        tableau[i][j] -= factor * tableau[pivot_row][j];
                    }
                }
            }

            basic_vars[pivot_row] = pivot_col;
        }

        // Extract solution
        let mut solution = vec![0.0; n];
        for i in 0..m {
            if basic_vars[i] < n {
                solution[basic_vars[i]] = tableau[i][cols - 1];
            }
        }

        let optimal_value = tableau[m][cols - 1];

        LpResult {
            optimal_value,
            solution,
            iterations,
            feasible: true,
            bounded: true,
        }
    }

    /// Solve a restock optimization problem.
    ///
    /// Given products with unit costs, expected profits, and storage sizes,
    /// find optimal quantities given budget and storage constraints.
    pub fn optimize_restock(
        &self,
        unit_costs: &[f64],
        profits: &[f64],
        storage_sizes: &[f64],
        budget: f64,
        storage_capacity: f64,
    ) -> LpResult {
        let n = unit_costs.len();
        if n == 0 || n != profits.len() || n != storage_sizes.len() {
            return LpResult {
                optimal_value: 0.0,
                solution: vec![],
                iterations: 0,
                feasible: false,
                bounded: false,
            };
        }

        let problem = LpProblem {
            objective: profits.to_vec(),
            constraints: vec![
                unit_costs.to_vec(),
                storage_sizes.to_vec(),
            ],
            rhs: vec![budget, storage_capacity],
        };

        self.solve(&problem)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simplex_basic() {
        // maximize 3x + 2y
        // subject to: x + y ≤ 4, x ≤ 3, y ≤ 3
        let problem = LpProblem {
            objective: vec![3.0, 2.0],
            constraints: vec![
                vec![1.0, 1.0],
                vec![1.0, 0.0],
                vec![0.0, 1.0],
            ],
            rhs: vec![4.0, 3.0, 3.0],
        };

        let solver = SimplexSolver::default();
        let result = solver.solve(&problem);

        assert!(result.feasible);
        assert!(result.bounded);
        assert!((result.optimal_value - 11.0).abs() < 0.01); // x=3, y=1 → 3*3 + 2*1 = 11
    }

    #[test]
    fn test_simplex_restock() {
        let costs = vec![10.0, 20.0, 15.0];
        let profits = vec![5.0, 8.0, 6.0];
        let storage = vec![1.0, 2.0, 1.5];

        let solver = SimplexSolver::default();
        let result = solver.optimize_restock(&costs, &profits, &storage, 100.0, 20.0);

        assert!(result.feasible);
        assert!(result.optimal_value > 0.0);
    }

    #[test]
    fn test_simplex_empty() {
        let problem = LpProblem {
            objective: vec![],
            constraints: vec![],
            rhs: vec![],
        };

        let solver = SimplexSolver::default();
        let result = solver.solve(&problem);
        assert!(!result.feasible);
    }

    #[test]
    fn test_simplex_single_variable() {
        // maximize 5x subject to x ≤ 10
        let problem = LpProblem {
            objective: vec![5.0],
            constraints: vec![vec![1.0]],
            rhs: vec![10.0],
        };

        let solver = SimplexSolver::default();
        let result = solver.solve(&problem);
        assert!(result.feasible);
        assert!((result.optimal_value - 50.0).abs() < 0.01);
        assert!((result.solution[0] - 10.0).abs() < 0.01);
    }
}
