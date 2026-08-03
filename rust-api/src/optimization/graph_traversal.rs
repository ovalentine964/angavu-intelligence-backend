//! Graph Traversal — BFS and DFS for Knowledge Graph.
//!
//! Breadth-first search and depth-first search algorithms for
//! traversing the knowledge graph structure.
//!
//! Use cases:
//! - Finding all connected entities (BFS for shortest connections)
//! - Exploring deep relationships (DFS for exhaustive search)
//! - Cycle detection in supply chains
//! - Component detection in disconnected graphs

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};

/// Result of a graph traversal.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraversalResult {
    /// Nodes visited in order
    pub visited: Vec<usize>,
    /// Depth/distance from source for each visited node
    pub depths: HashMap<usize, usize>,
    /// Parent of each node in the traversal tree
    pub parent: HashMap<usize, Option<usize>>,
    /// Whether a cycle was detected
    pub has_cycle: bool,
    /// Connected components found
    pub components: Vec<Vec<usize>>,
}

/// Graph traversal algorithms.
pub struct GraphTraversal {
    /// Adjacency list: node → list of neighbors
    pub adjacency: HashMap<usize, Vec<usize>>,
}

impl GraphTraversal {
    /// Create a new graph traversal engine.
    pub fn new() -> Self {
        Self {
            adjacency: HashMap::new(),
        }
    }

    /// Add a directed edge.
    pub fn add_edge(&mut self, from: usize, to: usize) {
        self.adjacency.entry(from).or_default().push(to);
        self.adjacency.entry(to).or_default(); // ensure node exists
    }

    /// Add an undirected edge.
    pub fn add_undirected_edge(&mut self, a: usize, b: usize) {
        self.adjacency.entry(a).or_default().push(b);
        self.adjacency.entry(b).or_default().push(a);
    }

    /// Add a node with no edges.
    pub fn add_node(&mut self, node: usize) {
        self.adjacency.entry(node).or_default();
    }

    /// Breadth-First Search from a source node.
    ///
    /// Explores all neighbors at current depth before moving to next level.
    /// Returns nodes in order of their distance from source.
    pub fn bfs(&self, source: usize) -> TraversalResult {
        let mut visited_order = Vec::new();
        let mut depths = HashMap::new();
        let mut parent = HashMap::new();
        let mut visited_set = HashSet::new();

        let mut queue = VecDeque::new();
        queue.push_back((source, 0usize));
        visited_set.insert(source);
        parent.insert(source, None);
        depths.insert(source, 0);

        while let Some((node, depth)) = queue.pop_front() {
            visited_order.push(node);

            if let Some(neighbors) = self.adjacency.get(&node) {
                for &neighbor in neighbors {
                    if !visited_set.contains(&neighbor) {
                        visited_set.insert(neighbor);
                        depths.insert(neighbor, depth + 1);
                        parent.insert(neighbor, Some(node));
                        queue.push_back((neighbor, depth + 1));
                    }
                }
            }
        }

        TraversalResult {
            visited: visited_order,
            depths,
            parent,
            has_cycle: false,
            components: Vec::new(),
        }
    }

    /// Depth-First Search from a source node.
    ///
    /// Explores as far as possible along each branch before backtracking.
    /// Uses iterative implementation to avoid stack overflow.
    pub fn dfs(&self, source: usize) -> TraversalResult {
        let mut visited_order = Vec::new();
        let mut depths = HashMap::new();
        let mut parent = HashMap::new();
        let mut visited_set = HashSet::new();
        let mut has_cycle = false;

        let mut stack = Vec::new();
        stack.push((source, 0usize, None)); // (node, depth, parent)

        while let Some((node, depth, par)) = stack.pop() {
            if visited_set.contains(&node) {
                // Check for back edge (cycle detection)
                if parent.contains_key(&node) {
                    has_cycle = true;
                }
                continue;
            }

            visited_set.insert(node);
            visited_order.push(node);
            depths.insert(node, depth);
            parent.insert(node, par);

            // Push neighbors in reverse order so we visit them in original order
            if let Some(neighbors) = self.adjacency.get(&node) {
                for &neighbor in neighbors.iter().rev() {
                    if !visited_set.contains(&neighbor) {
                        stack.push((neighbor, depth + 1, Some(node)));
                    }
                }
            }
        }

        TraversalResult {
            visited: visited_order,
            depths,
            parent,
            has_cycle,
            components: Vec::new(),
        }
    }

    /// Find all connected components using BFS.
    ///
    /// Useful for identifying disconnected subgraphs in the knowledge graph.
    pub fn connected_components(&self) -> Vec<Vec<usize>> {
        let mut visited = HashSet::new();
        let mut components = Vec::new();

        for &node in self.adjacency.keys() {
            if !visited.contains(&node) {
                let result = self.bfs(node);
                let component: Vec<usize> = result
                    .visited
                    .iter()
                    .filter(|n| !visited.contains(n))
                    .copied()
                    .collect();

                for &n in &component {
                    visited.insert(n);
                }

                if !component.is_empty() {
                    components.push(component);
                }
            }
        }

        components
    }

    /// Detect cycles in a directed graph using DFS.
    pub fn has_cycle(&self) -> bool {
        let mut visited = HashSet::new();
        let mut rec_stack = HashSet::new();

        for &node in self.adjacency.keys() {
            if !visited.contains(&node) {
                if self.dfs_cycle_check(node, &mut visited, &mut rec_stack) {
                    return true;
                }
            }
        }

        false
    }

    fn dfs_cycle_check(
        &self,
        node: usize,
        visited: &mut HashSet<usize>,
        rec_stack: &mut HashSet<usize>,
    ) -> bool {
        visited.insert(node);
        rec_stack.insert(node);

        if let Some(neighbors) = self.adjacency.get(&node) {
            for &neighbor in neighbors {
                if !visited.contains(&neighbor) {
                    if self.dfs_cycle_check(neighbor, visited, rec_stack) {
                        return true;
                    }
                } else if rec_stack.contains(&neighbor) {
                    return true; // Back edge found → cycle
                }
            }
        }

        rec_stack.remove(&node);
        false
    }

    /// Find shortest path (unweighted) using BFS.
    pub fn shortest_path_bfs(&self, source: usize, target: usize) -> Option<Vec<usize>> {
        if source == target {
            return Some(vec![source]);
        }

        let mut visited = HashSet::new();
        let mut parent: HashMap<usize, usize> = HashMap::new();
        let mut queue = VecDeque::new();

        visited.insert(source);
        queue.push_back(source);

        while let Some(node) = queue.pop_front() {
            if node == target {
                // Reconstruct path
                let mut path = vec![target];
                let mut current = target;
                while let Some(&p) = parent.get(&current) {
                    path.push(p);
                    current = p;
                }
                path.reverse();
                return Some(path);
            }

            if let Some(neighbors) = self.adjacency.get(&node) {
                for &neighbor in neighbors {
                    if !visited.contains(&neighbor) {
                        visited.insert(neighbor);
                        parent.insert(neighbor, node);
                        queue.push_back(neighbor);
                    }
                }
            }
        }

        None
    }

    /// Topological sort using DFS (for DAGs only).
    pub fn topological_sort(&self) -> Option<Vec<usize>> {
        let mut visited = HashSet::new();
        let mut stack = Vec::new();
        let mut rec_stack = HashSet::new();

        for &node in self.adjacency.keys() {
            if !visited.contains(&node) {
                if !self.topo_dfs(node, &mut visited, &mut stack, &mut rec_stack) {
                    return None; // Cycle detected, not a DAG
                }
            }
        }

        stack.reverse();
        Some(stack)
    }

    fn topo_dfs(
        &self,
        node: usize,
        visited: &mut HashSet<usize>,
        stack: &mut Vec<usize>,
        rec_stack: &mut HashSet<usize>,
    ) -> bool {
        visited.insert(node);
        rec_stack.insert(node);

        if let Some(neighbors) = self.adjacency.get(&node) {
            for &neighbor in neighbors {
                if !visited.contains(&neighbor) {
                    if !self.topo_dfs(neighbor, visited, stack, rec_stack) {
                        return false;
                    }
                } else if rec_stack.contains(&neighbor) {
                    return false; // Cycle
                }
            }
        }

        rec_stack.remove(&node);
        stack.push(node);
        true
    }

    /// BFS within a distance limit (k-hop neighborhood).
    pub fn k_hop_neighborhood(&self, source: usize, k: usize) -> Vec<usize> {
        let result = self.bfs(source);
        result
            .visited
            .into_iter()
            .filter(|n| result.depths.get(n).copied().unwrap_or(usize::MAX) <= k)
            .collect()
    }
}

impl Default for GraphTraversal {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bfs_basic() {
        let mut graph = GraphTraversal::new();
        graph.add_undirected_edge(0, 1);
        graph.add_undirected_edge(0, 2);
        graph.add_undirected_edge(1, 3);
        graph.add_undirected_edge(2, 4);

        let result = graph.bfs(0);

        assert_eq!(result.visited[0], 0);
        assert_eq!(result.depths[&0], 0);
        assert_eq!(result.depths[&1], 1);
        assert_eq!(result.depths[&3], 2);
    }

    #[test]
    fn test_dfs_basic() {
        let mut graph = GraphTraversal::new();
        graph.add_edge(0, 1);
        graph.add_edge(0, 2);
        graph.add_edge(1, 3);
        graph.add_edge(2, 4);

        let result = graph.dfs(0);

        assert_eq!(result.visited[0], 0);
        assert!(result.visited.contains(&4));
    }

    #[test]
    fn test_cycle_detection() {
        let mut graph = GraphTraversal::new();
        graph.add_edge(0, 1);
        graph.add_edge(1, 2);
        graph.add_edge(2, 0); // cycle

        assert!(graph.has_cycle());
    }

    #[test]
    fn test_no_cycle() {
        let mut graph = GraphTraversal::new();
        graph.add_edge(0, 1);
        graph.add_edge(1, 2);
        graph.add_edge(0, 2);

        assert!(!graph.has_cycle());
    }

    #[test]
    fn test_connected_components() {
        let mut graph = GraphTraversal::new();
        graph.add_undirected_edge(0, 1);
        graph.add_undirected_edge(1, 2);
        graph.add_undirected_edge(3, 4);

        let components = graph.connected_components();
        assert_eq!(components.len(), 2);
    }

    #[test]
    fn test_shortest_path_bfs() {
        let mut graph = GraphTraversal::new();
        graph.add_undirected_edge(0, 1);
        graph.add_undirected_edge(1, 2);
        graph.add_undirected_edge(0, 3);
        graph.add_undirected_edge(3, 2);

        let path = graph.shortest_path_bfs(0, 2).unwrap();
        assert_eq!(path.len(), 3); // 0 → 1 → 2 or 0 → 3 → 2
        assert_eq!(path[0], 0);
        assert_eq!(path[2], 2);
    }

    #[test]
    fn test_topological_sort() {
        let mut graph = GraphTraversal::new();
        graph.add_edge(0, 1);
        graph.add_edge(0, 2);
        graph.add_edge(1, 3);
        graph.add_edge(2, 3);

        let topo = graph.topological_sort().unwrap();
        let pos_0 = topo.iter().position(|&n| n == 0).unwrap();
        let pos_1 = topo.iter().position(|&n| n == 1).unwrap();
        let pos_3 = topo.iter().position(|&n| n == 3).unwrap();

        assert!(pos_0 < pos_1);
        assert!(pos_0 < pos_3);
        assert!(pos_1 < pos_3);
    }

    #[test]
    fn test_k_hop_neighborhood() {
        let mut graph = GraphTraversal::new();
        graph.add_undirected_edge(0, 1);
        graph.add_undirected_edge(1, 2);
        graph.add_undirected_edge(2, 3);

        let one_hop = graph.k_hop_neighborhood(0, 1);
        assert!(one_hop.contains(&0));
        assert!(one_hop.contains(&1));
        assert!(!one_hop.contains(&2));

        let two_hop = graph.k_hop_neighborhood(0, 2);
        assert!(two_hop.contains(&2));
        assert!(!two_hop.contains(&3));
    }
}
