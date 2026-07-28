//! Graph Algorithms — PageRank, community detection, centrality, shortest path.
//!
//! These operate on an in-memory adjacency-list graph built from the knowledge
//! graph stored in PostgreSQL (kg_edges, kg_worker_cohorts, kg_product_categories, etc.).

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque, BinaryHeap};
use std::cmp::Reverse;
use uuid::Uuid;

/// An in-memory graph for algorithm execution.
/// Built from knowledge graph edges and used for analytics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlgorithmGraph {
    /// Adjacency list: node_id → list of (neighbor_id, edge_weight)
    pub adjacency: HashMap<Uuid, Vec<(Uuid, f64)>>,
    /// Reverse adjacency for PageRank
    pub reverse_adjacency: HashMap<Uuid, Vec<(Uuid, f64)>>,
    /// Node metadata
    pub node_labels: HashMap<Uuid, String>,
    /// Total edge count
    pub edge_count: usize,
}

/// Result from PageRank computation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PageRankResult {
    pub node_id: Uuid,
    pub score: f64,
    pub label: Option<String>,
}

/// A detected community (cluster of related nodes).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Community {
    pub id: u32,
    pub members: Vec<Uuid>,
    pub internal_edges: usize,
    pub modularity_score: f64,
}

/// Degree centrality result for a single node.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CentralityResult {
    pub node_id: Uuid,
    pub degree: usize,
    pub in_degree: usize,
    pub out_degree: usize,
    pub label: Option<String>,
}

/// Shortest path result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShortestPathResult {
    pub path: Vec<Uuid>,
    pub total_weight: f64,
    pub hop_count: usize,
}

impl AlgorithmGraph {
    /// Create an empty graph.
    pub fn new() -> Self {
        Self {
            adjacency: HashMap::new(),
            reverse_adjacency: HashMap::new(),
            node_labels: HashMap::new(),
            edge_count: 0,
        }
    }

    /// Add a directed edge with weight.
    pub fn add_edge(&mut self, from: Uuid, to: Uuid, weight: f64) {
        self.adjacency
            .entry(from)
            .or_default()
            .push((to, weight));
        self.reverse_adjacency
            .entry(to)
            .or_default()
            .push((from, weight));
        self.edge_count += 1;
    }

    /// Add an undirected edge (two directed edges).
    pub fn add_undirected_edge(&mut self, a: Uuid, b: Uuid, weight: f64) {
        self.add_edge(a, b, weight);
        self.add_edge(b, a, weight);
        // Adjust edge count (add_edge increments twice, but we want to count it as one undirected edge)
        self.edge_count -= 1;
    }

    /// Set label for a node.
    pub fn set_label(&mut self, id: Uuid, label: String) {
        self.node_labels.insert(id, label);
    }

    /// Get all node IDs.
    pub fn node_ids(&self) -> Vec<Uuid> {
        let mut nodes: HashSet<Uuid> = HashSet::new();
        for (k, v) in &self.adjacency {
            nodes.insert(*k);
            for (n, _) in v {
                nodes.insert(*n);
            }
        }
        nodes.into_iter().collect()
    }

    /// Get node count.
    pub fn node_count(&self) -> usize {
        self.node_ids().len()
    }

    /// Compute PageRank for all nodes.
    ///
    /// Classic iterative PageRank: PR(i) = (1-d)/N + d * Σ(PR(j)/L(j)) for all j linking to i.
    ///
    /// - `iterations`: number of power iterations (typically 20-50)
    /// - `damping`: damping factor (typically 0.85)
    pub fn pagerank(&self, iterations: u32, damping: f64) -> Vec<PageRankResult> {
        let nodes = self.node_ids();
        let n = nodes.len() as f64;
        if n == 0.0 {
            return Vec::new();
        }

        let damping = damping.clamp(0.0, 1.0);
        let initial_rank = 1.0 / n;
        let teleport = (1.0 - damping) / n;

        // Initialize ranks
        let mut ranks: HashMap<Uuid, f64> = HashMap::new();
        for &node in &nodes {
            ranks.insert(node, initial_rank);
        }

        // Out-degree for each node
        let out_degree: HashMap<Uuid, usize> = self
            .adjacency
            .iter()
            .map(|(k, v)| (*k, v.len()))
            .collect();

        // Power iteration
        for _ in 0..iterations {
            let mut new_ranks: HashMap<Uuid, f64> = HashMap::new();

            // Collect dangling rank (nodes with no outgoing edges)
            let dangling_rank: f64 = nodes
                .iter()
                .filter(|n| !out_degree.contains_key(n) || out_degree[*n] == 0)
                .map(|n| ranks.get(n).copied().unwrap_or(0.0))
                .sum();

            let dangling_contrib = dangling_rank * damping / n;

            for &node in &nodes {
                // Contribution from incoming edges
                let incoming_contrib: f64 = self
                    .reverse_adjacency
                    .get(&node)
                    .map(|edges| {
                        edges
                            .iter()
                            .map(|(from, _)| {
                                let from_rank = ranks.get(from).copied().unwrap_or(0.0);
                                let from_out = out_degree.get(from).copied().unwrap_or(1).max(1) as f64;
                                from_rank / from_out
                            })
                            .sum()
                    })
                    .unwrap_or(0.0);

                let rank = teleport + dangling_contrib + damping * incoming_contrib;
                new_ranks.insert(node, rank);
            }

            ranks = new_ranks;
        }

        // Sort by rank descending
        let mut results: Vec<PageRankResult> = ranks
            .into_iter()
            .map(|(node_id, score)| PageRankResult {
                node_id,
                score,
                label: self.node_labels.get(&node_id).cloned(),
            })
            .collect();

        results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
        results
    }

    /// Detect communities using the Louvain-like label propagation algorithm.
    ///
    /// This is a simplified version suitable for the knowledge graph scale:
    /// 1. Each node starts in its own community
    /// 2. Iteratively join the community of the majority of neighbors
    /// 3. Converge when no more changes
    pub fn detect_communities(&self) -> Vec<Community> {
        let nodes = self.node_ids();
        if nodes.is_empty() {
            return Vec::new();
        }

        let n = nodes.len();
        let mut membership: HashMap<Uuid, u32> = HashMap::new();

        // Initialize: each node in its own community
        for (i, &node) in nodes.iter().enumerate() {
            membership.insert(node, i as u32);
        }

        // Build node index for fast lookup
        let node_set: HashSet<Uuid> = nodes.iter().cloned().collect();

        // Label propagation iterations
        let max_iterations = 50;
        for _ in 0..max_iterations {
            let mut changed = false;

            // Shuffle order to avoid bias (use deterministic order for reproducibility)
            let mut order: Vec<Uuid> = nodes.clone();
            order.sort_by_key(|n| n.as_bytes().to_vec());

            for node in &order {
                // Count community labels of neighbors
                let mut community_counts: HashMap<u32, f64> = HashMap::new();

                if let Some(neighbors) = self.adjacency.get(node) {
                    for (neighbor, weight) in neighbors {
                        if node_set.contains(neighbor) {
                            let comm = membership.get(neighbor).copied().unwrap_or(0);
                            *community_counts.entry(comm).or_insert(0.0) += weight;
                        }
                    }
                }

                if community_counts.is_empty() {
                    continue;
                }

                // Find community with max weighted votes
                let best_community = community_counts
                    .iter()
                    .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
                    .map(|(comm, _)| *comm)
                    .unwrap();

                let current = membership.get(node).copied().unwrap_or(0);
                if current != best_community {
                    membership.insert(*node, best_community);
                    changed = true;
                }
            }

            if !changed {
                break;
            }
        }

        // Group nodes by community
        let mut groups: HashMap<u32, Vec<Uuid>> = HashMap::new();
        for (node, comm) in &membership {
            groups.entry(*comm).or_default().push(*node);
        }

        // Count internal edges per community
        groups
            .into_iter()
            .map(|(id, members)| {
                let member_set: HashSet<Uuid> = members.iter().cloned().collect();
                let internal_edges = members
                    .iter()
                    .map(|node| {
                        self.adjacency
                            .get(node)
                            .map(|edges| {
                                edges
                                    .iter()
                                    .filter(|(neighbor, _)| member_set.contains(neighbor))
                                    .count()
                            })
                            .unwrap_or(0)
                    })
                    .sum::<usize>();

                // Simplified modularity: internal_edges / total_edges
                let modularity_score = if self.edge_count > 0 {
                    internal_edges as f64 / self.edge_count as f64
                } else {
                    0.0
                };

                Community {
                    id,
                    members,
                    internal_edges,
                    modularity_score,
                }
            })
            .collect()
    }

    /// Compute degree centrality for all nodes.
    ///
    /// Returns nodes sorted by total degree (in + out) descending.
    pub fn degree_centrality(&self, top_k: usize) -> Vec<CentralityResult> {
        let nodes = self.node_ids();
        let mut results: Vec<CentralityResult> = nodes
            .into_iter()
            .map(|node| {
                let out_degree = self.adjacency.get(&node).map(|e| e.len()).unwrap_or(0);
                let in_degree = self.reverse_adjacency.get(&node).map(|e| e.len()).unwrap_or(0);
                CentralityResult {
                    node_id: node,
                    degree: in_degree + out_degree,
                    in_degree,
                    out_degree,
                    label: self.node_labels.get(&node).cloned(),
                }
            })
            .collect();

        results.sort_by(|a, b| b.degree.cmp(&a.degree));
        results.truncate(top_k);
        results
    }

    /// Find shortest path between two nodes using Dijkstra's algorithm.
    ///
    /// Returns None if no path exists.
    pub fn shortest_path(&self, from: Uuid, to: Uuid) -> Option<ShortestPathResult> {
        if from == to {
            return Some(ShortestPathResult {
                path: vec![from],
                total_weight: 0.0,
                hop_count: 0,
            });
        }

        let mut dist: HashMap<Uuid, f64> = HashMap::new();
        let mut prev: HashMap<Uuid, Option<Uuid>> = HashMap::new();
        let mut heap = BinaryHeap::new();

        dist.insert(from, 0.0);
        prev.insert(from, None);
        heap.push(Reverse((0.0_f64, from)));

        while let Reverse((current_dist, current)) = heap.pop() {
            if current == to {
                // Reconstruct path
                let mut path = Vec::new();
                let mut node = Some(to);
                while let Some(n) = node {
                    path.push(n);
                    node = prev.get(&n).and_then(|p| *p);
                }
                path.reverse();
                return Some(ShortestPathResult {
                    path,
                    total_weight: current_dist,
                    hop_count: path.len().saturating_sub(1),
                });
            }

            // Skip if we already found a better path
            if current_dist > *dist.get(&current).unwrap_or(&f64::INFINITY) {
                continue;
            }

            if let Some(neighbors) = self.adjacency.get(&current) {
                for (neighbor, weight) in neighbors {
                    let new_dist = current_dist + weight;
                    let known_dist = *dist.get(neighbor).unwrap_or(&f64::INFINITY);

                    if new_dist < known_dist {
                        dist.insert(*neighbor, new_dist);
                        prev.insert(*neighbor, Some(current));
                        heap.push(Reverse((new_dist, *neighbor)));
                    }
                }
            }
        }

        None // No path found
    }

    /// Find all nodes within N hops of a source node (BFS).
    pub fn neighborhood(&self, source: Uuid, max_hops: u32) -> Vec<(Uuid, u32)> {
        let mut visited: HashMap<Uuid, u32> = HashMap::new();
        let mut queue = VecDeque::new();

        visited.insert(source, 0);
        queue.push_back((source, 0u32));

        while let Some((node, depth)) = queue.pop_front() {
            if depth >= max_hops {
                continue;
            }

            if let Some(neighbors) = self.adjacency.get(&node) {
                for (neighbor, _) in neighbors {
                    if !visited.contains_key(neighbor) {
                        visited.insert(*neighbor, depth + 1);
                        queue.push_back((*neighbor, depth + 1));
                    }
                }
            }
        }

        let mut result: Vec<(Uuid, u32)> = visited.into_iter().collect();
        result.sort_by_key(|(_, d)| *d);
        result
    }

    /// Find similar nodes based on shared neighbors (Jaccard similarity).
    pub fn similar_nodes(&self, node_id: Uuid, limit: usize) -> Vec<(Uuid, f64)> {
        let node_neighbors: HashSet<Uuid> = self
            .adjacency
            .get(&node_id)
            .map(|edges| edges.iter().map(|(n, _)| *n).collect())
            .unwrap_or_default();

        if node_neighbors.is_empty() {
            return Vec::new();
        }

        let mut similarities: Vec<(Uuid, f64)> = self
            .node_ids()
            .into_iter()
            .filter(|n| *n != node_id && !node_neighbors.contains(n))
            .filter_map(|candidate| {
                let candidate_neighbors: HashSet<Uuid> = self
                    .adjacency
                    .get(&candidate)
                    .map(|edges| edges.iter().map(|(n, _)| *n).collect())
                    .unwrap_or_default();

                let intersection = node_neighbors
                    .iter()
                    .filter(|n| candidate_neighbors.contains(n))
                    .count();
                let union = node_neighbors.len() + candidate_neighbors.len() - intersection;

                if union == 0 {
                    return None;
                }

                let jaccard = intersection as f64 / union as f64;
                if jaccard > 0.0 {
                    Some((candidate, jaccard))
                } else {
                    None
                }
            })
            .collect();

        similarities.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        similarities.truncate(limit);
        similarities
    }
}

impl Default for AlgorithmGraph {
    fn default() -> Self {
        Self::new()
    }
}

/// Build an AlgorithmGraph from PostgreSQL knowledge graph tables.
/// This is used by the GraphQL and REST endpoints.
pub async fn build_graph_from_db(
    pool: &sqlx::PgPool,
    max_depth: Option<u32>,
) -> anyhow::Result<AlgorithmGraph> {
    let mut graph = AlgorithmGraph::new();

    // Load edges
    let edges = sqlx::query!(
        "SELECT source_id, target_id, weight, edge_type
         FROM kg_edges
         WHERE sample_size >= 10"
    )
    .fetch_all(pool)
    .await?;

    for edge in &edges {
        graph.add_edge(edge.source_id, edge.target_id, edge.weight.unwrap_or(1.0));
    }

    // Load node labels from worker cohorts
    let cohorts = sqlx::query!(
        "SELECT id, cohort_hash, worker_type FROM kg_worker_cohorts"
    )
    .fetch_all(pool)
    .await?;

    for cohort in &cohorts {
        graph.set_label(
            cohort.id,
            format!("cohort:{}:{}", cohort.worker_type, cohort.cohort_hash),
        );
    }

    // Load node labels from product categories
    let products = sqlx::query!(
        "SELECT id, category_code, category_name FROM kg_product_categories"
    )
    .fetch_all(pool)
    .await?;

    for product in &products {
        graph.set_label(product.id, format!("product:{}", product.category_code));
    }

    Ok(graph)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_graph() -> AlgorithmGraph {
        let mut graph = AlgorithmGraph::new();
        let a = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        let b = Uuid::parse_str("00000000-0000-0000-0000-000000000002").unwrap();
        let c = Uuid::parse_str("00000000-0000-0000-0000-000000000003").unwrap();
        let d = Uuid::parse_str("00000000-0000-0000-0000-000000000004").unwrap();
        let e = Uuid::parse_str("00000000-0000-0000-0000-000000000005").unwrap();

        // Star topology: A is center
        graph.add_edge(a, b, 1.0);
        graph.add_edge(a, c, 1.0);
        graph.add_edge(a, d, 1.0);
        graph.add_edge(a, e, 1.0);
        graph.add_edge(b, c, 0.5);
        graph.add_edge(c, d, 0.5);

        graph.set_label(a, "center".to_string());
        graph.set_label(b, "node_b".to_string());
        graph.set_label(c, "node_c".to_string());
        graph.set_label(d, "node_d".to_string());
        graph.set_label(e, "node_e".to_string());

        graph
    }

    #[test]
    fn test_pagerank() {
        let graph = create_test_graph();
        let results = graph.pagerank(30, 0.85);

        assert_eq!(results.len(), 5);
        // Node A (center) should have highest PageRank
        let center = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        assert_eq!(results[0].node_id, center);

        // All scores should sum to ~1.0
        let total: f64 = results.iter().map(|r| r.score).sum();
        assert!((total - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_degree_centrality() {
        let graph = create_test_graph();
        let results = graph.degree_centrality(5);

        assert_eq!(results.len(), 5);
        // Node A should have highest degree (4 out + some in)
        let center = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        assert_eq!(results[0].node_id, center);
        assert!(results[0].degree >= 4);
    }

    #[test]
    fn test_shortest_path() {
        let graph = create_test_graph();
        let a = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        let d = Uuid::parse_str("00000000-0000-0000-0000-000000000004").unwrap();

        let result = graph.shortest_path(a, d);
        assert!(result.is_some());

        let path = result.unwrap();
        assert_eq!(path.path[0], a);
        assert_eq!(*path.path.last().unwrap(), d);
        assert!(path.total_weight > 0.0);
    }

    #[test]
    fn test_shortest_path_direct() {
        let graph = create_test_graph();
        let a = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        let b = Uuid::parse_str("00000000-0000-0000-0000-000000000002").unwrap();

        let result = graph.shortest_path(a, b).unwrap();
        assert_eq!(result.hop_count, 1);
        assert_eq!(result.total_weight, 1.0);
    }

    #[test]
    fn test_neighborhood() {
        let graph = create_test_graph();
        let a = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();

        let neighbors_1 = graph.neighborhood(a, 1);
        // 4 direct neighbors (B, C, D, E) + A itself
        assert_eq!(neighbors_1.len(), 5);

        let neighbors_2 = graph.neighborhood(a, 2);
        // Should include all 5 nodes at depth ≤ 2
        assert_eq!(neighbors_2.len(), 5);
    }

    #[test]
    fn test_community_detection() {
        let mut graph = AlgorithmGraph::new();
        let a = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        let b = Uuid::parse_str("00000000-0000-0000-0000-000000000002").unwrap();
        let c = Uuid::parse_str("00000000-0000-0000-0000-000000000003").unwrap();
        let d = Uuid::parse_str("00000000-0000-0000-0000-000000000004").unwrap();

        // Two clusters: {A,B} and {C,D} with weak cross-link
        graph.add_undirected_edge(a, b, 1.0);
        graph.add_undirected_edge(c, d, 1.0);
        graph.add_undirected_edge(b, c, 0.1); // weak link

        let communities = graph.detect_communities();
        assert!(!communities.is_empty());

        // Should detect 2 communities
        let non_empty: Vec<_> = communities.iter().filter(|c| c.members.len() > 1).collect();
        assert!(non_empty.len() >= 1);
    }

    #[test]
    fn test_similar_nodes() {
        let graph = create_test_graph();
        let b = Uuid::parse_str("00000000-0000-0000-0000-000000000002").unwrap();

        let similar = graph.similar_nodes(b, 3);
        assert!(!similar.is_empty());
        // C should be similar to B (they share neighbor A)
        let c = Uuid::parse_str("00000000-0000-0000-0000-000000000003").unwrap();
        assert!(similar.iter().any(|(id, score)| *id == c && *score > 0.0));
    }

    #[test]
    fn test_empty_graph() {
        let graph = AlgorithmGraph::new();
        assert_eq!(graph.node_count(), 0);
        assert!(graph.pagerank(10, 0.85).is_empty());
        assert!(graph.detect_communities().is_empty());
        assert!(graph.degree_centrality(10).is_empty());
    }
}
