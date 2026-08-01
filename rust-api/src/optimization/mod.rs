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

pub mod simplex;
pub mod network_flow;
pub mod queuing;
pub mod numerical;
pub mod dynamic_programming;
pub mod stochastic;
pub mod graph_traversal;

// Re-export key types
pub use simplex::{SimplexSolver, LpProblem, LpResult};
pub use network_flow::{FlowNetwork, MaxFlowResult};
pub use queuing::{MM1Queue, MMcQueue, QueueStats};
pub use numerical::{newton_raphson, simpsons_rule, linear_interpolation, cubic_interpolation};
pub use dynamic_programming::BellmanSolver;
pub use stochastic::StochasticOptimizer;
pub use graph_traversal::{GraphTraversal, TraversalResult};
