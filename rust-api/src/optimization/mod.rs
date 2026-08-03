//! Optimization and Mathematics Module
//!
//! Provides mathematical optimization algorithms for the Angavu Intelligence Platform:
//! - Linear programming (Simplex method)
//! - Network flow (Ford-Fulkerson, max-flow/min-cut)
//! - Queuing theory (M/M/1, M/M/c)
//! - Numerical methods (Newton-Raphson, Simpson's rule, interpolation)
//! - Dynamic programming (Bellman equation)
//! - Stochastic optimization
//! - Graph traversal (BFS/DFS)

pub mod dynamic_programming;
pub mod graph_traversal;
pub mod network_flow;
pub mod numerical;
pub mod queuing;
pub mod simplex;
pub mod stochastic;

// Re-export key types
pub use dynamic_programming::BellmanSolver;
pub use graph_traversal::{GraphTraversal, TraversalResult};
pub use network_flow::{FlowNetwork, MaxFlowResult};
pub use numerical::{cubic_interpolation, linear_interpolation, newton_raphson, simpsons_rule};
pub use queuing::{MM1Queue, MMcQueue, QueueStats};
pub use simplex::{LpProblem, LpResult, SimplexSolver};
pub use stochastic::StochasticOptimizer;
