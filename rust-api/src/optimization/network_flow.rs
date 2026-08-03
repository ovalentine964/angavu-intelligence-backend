//! Network Flow — Ford-Fulkerson Algorithm and Max-Flow/Min-Cut.
//!
//! Solves maximum flow problems in directed networks.
//!
//! Use cases:
//! - Supply chain optimization: max throughput from suppliers to consumers
//! - Distribution planning: how much product can flow through a network
//! - Bottleneck identification: min-cut reveals capacity constraints

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};

/// A flow network edge.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlowEdge {
    pub from: usize,
    pub to: usize,
    pub capacity: f64,
    pub flow: f64,
}

/// A flow network (directed graph with capacities).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlowNetwork {
    /// Number of nodes
    pub num_nodes: usize,
    /// Adjacency list: node → list of edge indices
    pub adjacency: HashMap<usize, Vec<usize>>,
    /// All edges (forward and residual)
    pub edges: Vec<FlowEdge>,
}

/// Result of a max-flow computation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MaxFlowResult {
    /// Maximum flow value
    pub max_flow: f64,
    /// Flow on each original edge
    pub edge_flows: Vec<(usize, usize, f64)>,
    /// Min-cut: nodes on source side
    pub min_cut_source: Vec<usize>,
    /// Min-cut: nodes on sink side
    pub min_cut_sink: Vec<usize>,
    /// Min-cut capacity (equals max-flow by max-flow min-cut theorem)
    pub min_cut_capacity: f64,
}

impl FlowNetwork {
    /// Create a new empty flow network.
    pub fn new(num_nodes: usize) -> Self {
        Self {
            num_nodes,
            adjacency: HashMap::new(),
            edges: Vec::new(),
        }
    }

    /// Add a directed edge with capacity.
    pub fn add_edge(&mut self, from: usize, to: usize, capacity: f64) {
        let edge_idx = self.edges.len();

        // Forward edge
        self.edges.push(FlowEdge {
            from,
            to,
            capacity,
            flow: 0.0,
        });
        self.adjacency.entry(from).or_default().push(edge_idx);

        // Backward (residual) edge
        self.edges.push(FlowEdge {
            from: to,
            to: from,
            capacity: 0.0,
            flow: 0.0,
        });
        self.adjacency.entry(to).or_default().push(edge_idx + 1);
    }

    /// Compute maximum flow using Ford-Fulkerson with BFS (Edmonds-Karp).
    ///
    /// Time complexity: O(V * E²)
    pub fn max_flow(&mut self, source: usize, sink: usize) -> MaxFlowResult {
        let mut total_flow = 0.0;

        loop {
            // BFS to find augmenting path
            let (path, bottleneck) = match self.bfs_augmenting_path(source, sink) {
                Some(result) => result,
                None => break,
            };

            // Augment flow along the path
            for &edge_idx in &path {
                self.edges[edge_idx].flow += bottleneck;
                // Residual edge is at odd index if forward is even, and vice versa
                let residual_idx = if edge_idx % 2 == 0 {
                    edge_idx + 1
                } else {
                    edge_idx - 1
                };
                self.edges[residual_idx].flow -= bottleneck;
            }

            total_flow += bottleneck;
        }

        // Find min-cut using BFS from source in residual graph
        let min_cut_source = self.reachable_from(source);
        let min_cut_sink: Vec<usize> = (0..self.num_nodes)
            .filter(|n| !min_cut_source.contains(n))
            .collect();

        let min_cut_capacity = self.compute_min_cut_capacity(&min_cut_source);

        // Collect edge flows for original edges (even indices)
        let edge_flows: Vec<(usize, usize, f64)> = self
            .edges
            .iter()
            .enumerate()
            .filter(|(i, _)| i % 2 == 0)
            .filter(|(_, e)| e.flow > 0.0)
            .map(|(_, e)| (e.from, e.to, e.flow))
            .collect();

        MaxFlowResult {
            max_flow: total_flow,
            edge_flows,
            min_cut_source,
            min_cut_sink,
            min_cut_capacity,
        }
    }

    /// BFS to find an augmenting path from source to sink.
    fn bfs_augmenting_path(&self, source: usize, sink: usize) -> Option<(Vec<usize>, f64)> {
        let mut visited = vec![false; self.num_nodes];
        let mut parent: Vec<Option<(usize, usize)>> = vec![None; self.num_nodes]; // (parent_node, edge_idx)
        let mut queue = VecDeque::new();

        visited[source] = true;
        queue.push_back(source);

        while let Some(node) = queue.pop_front() {
            if node == sink {
                // Reconstruct path
                let mut path = Vec::new();
                let mut bottleneck = f64::MAX;
                let mut current = sink;

                while let Some((prev, edge_idx)) = parent[current] {
                    let residual = self.edges[edge_idx].capacity - self.edges[edge_idx].flow;
                    bottleneck = bottleneck.min(residual);
                    path.push(edge_idx);
                    current = prev;
                }
                path.reverse();
                return Some((path, bottleneck));
            }

            if let Some(edge_indices) = self.adjacency.get(&node) {
                for &edge_idx in edge_indices {
                    let edge = &self.edges[edge_idx];
                    let residual = edge.capacity - edge.flow;
                    if !visited[edge.to] && residual > 1e-10 {
                        visited[edge.to] = true;
                        parent[edge.to] = Some((node, edge_idx));
                        queue.push_back(edge.to);
                    }
                }
            }
        }

        None
    }

    /// Find all nodes reachable from source in the residual graph.
    fn reachable_from(&self, source: usize) -> Vec<usize> {
        let mut visited = vec![false; self.num_nodes];
        let mut queue = VecDeque::new();

        visited[source] = true;
        queue.push_back(source);

        while let Some(node) = queue.pop_front() {
            if let Some(edge_indices) = self.adjacency.get(&node) {
                for &edge_idx in edge_indices {
                    let edge = &self.edges[edge_idx];
                    if !visited[edge.to] && (edge.capacity - edge.flow) > 1e-10 {
                        visited[edge.to] = true;
                        queue.push_back(edge.to);
                    }
                }
            }
        }

        (0..self.num_nodes).filter(|&n| visited[n]).collect()
    }

    /// Compute the capacity of a cut.
    fn compute_min_cut_capacity(&self, source_side: &[usize]) -> f64 {
        let source_set: std::collections::HashSet<usize> = source_side.iter().copied().collect();
        let mut capacity = 0.0;

        for (i, edge) in self.edges.iter().enumerate() {
            // Only forward edges (even indices)
            if i % 2 == 0 && source_set.contains(&edge.from) && !source_set.contains(&edge.to) {
                capacity += edge.capacity;
            }
        }

        capacity
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_max_flow_basic() {
        //   0 → 1 (capacity 10)
        //   0 → 2 (capacity 10)
        //   1 → 2 (capacity 2)
        //   1 → 3 (capacity 10)
        //   2 → 3 (capacity 10)
        let mut network = FlowNetwork::new(4);
        network.add_edge(0, 1, 10.0);
        network.add_edge(0, 2, 10.0);
        network.add_edge(1, 2, 2.0);
        network.add_edge(1, 3, 10.0);
        network.add_edge(2, 3, 10.0);

        let result = network.max_flow(0, 3);

        assert!((result.max_flow - 20.0).abs() < 0.01);
        assert!((result.min_cut_capacity - 20.0).abs() < 0.01);
    }

    #[test]
    fn test_max_flow_bottleneck() {
        //   0 → 1 (capacity 5)
        //   1 → 2 (capacity 100)
        let mut network = FlowNetwork::new(3);
        network.add_edge(0, 1, 5.0);
        network.add_edge(1, 2, 100.0);

        let result = network.max_flow(0, 2);
        assert!((result.max_flow - 5.0).abs() < 0.01);
    }

    #[test]
    fn test_max_flow_disconnected() {
        let mut network = FlowNetwork::new(3);
        network.add_edge(0, 1, 10.0);
        // No path from 0 to 2

        let result = network.max_flow(0, 2);
        assert!((result.max_flow).abs() < 0.01);
    }

    #[test]
    fn test_min_cut() {
        let mut network = FlowNetwork::new(4);
        network.add_edge(0, 1, 10.0);
        network.add_edge(0, 2, 10.0);
        network.add_edge(1, 3, 5.0);
        network.add_edge(2, 3, 5.0);

        let result = network.max_flow(0, 3);
        assert!((result.max_flow - 10.0).abs() < 0.01);
        assert!(result.min_cut_source.contains(&0));
        assert!(result.min_cut_sink.contains(&3));
    }
}
