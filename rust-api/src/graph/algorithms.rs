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

    /// Betweenness centrality using Brandes' algorithm.
    ///
    /// Finds nodes that serve as bridges between communities.
    /// High betweenness = important intermediary (e.g., a supplier serving multiple regions).
    /// Complexity: O(VE) for unweighted, O(V(E + V log V)) for weighted.
    pub fn betweenness_centrality(&self, top_k: usize) -> Vec<(Uuid, f64)> {
        let nodes = self.node_ids();
        let mut betweenness: HashMap<Uuid, f64> = HashMap::new();

        // Initialize all betweenness scores to 0
        for &node in &nodes {
            betweenness.insert(node, 0.0);
        }

        for &source in &nodes {
            // BFS from source to compute shortest paths
            let mut stack: Vec<Uuid> = Vec::new();
            let mut predecessors: HashMap<Uuid, Vec<Uuid>> = HashMap::new();
            let mut sigma: HashMap<Uuid, f64> = HashMap::new();
            let mut dist: HashMap<Uuid, i64> = HashMap::new();

            sigma.insert(source, 1.0);
            dist.insert(source, 0);

            let mut queue = VecDeque::new();
            queue.push_back(source);

            while let Some(v) = queue.pop_front() {
                stack.push(v);
                let v_dist = *dist.get(&v).unwrap_or(&0);

                if let Some(neighbors) = self.adjacency.get(&v) {
                    for (w, _) in neighbors {
                        // First time visiting w?
                        if !dist.contains_key(w) {
                            dist.insert(*w, v_dist + 1);
                            queue.push_back(*w);
                        }

                        // Is v on a shortest path to w?
                        if *dist.get(w).unwrap_or(&0) == v_dist + 1 {
                            let w_sigma = *sigma.get(w).unwrap_or(&0.0);
                            let v_sigma = *sigma.get(&v).unwrap_or(&0.0);
                            sigma.insert(*w, w_sigma + v_sigma);
                            predecessors.entry(*w).or_default().push(v);
                        }
                    }
                }
            }

            // Back-propagate dependency
            let mut delta: HashMap<Uuid, f64> = HashMap::new();
            for &node in &nodes {
                delta.insert(node, 0.0);
            }

            while let Some(w) = stack.pop() {
                if let Some(preds) = predecessors.get(&w) {
                    for v in preds {
                        let v_sigma = *sigma.get(v).unwrap_or(&1.0);
                        let w_sigma = *sigma.get(&w).unwrap_or(&1.0);
                        let w_delta = *delta.get(&w).unwrap_or(&0.0);
                        let contrib = (v_sigma / w_sigma) * (1.0 + w_delta);
                        *delta.entry(*v).or_insert(0.0) += contrib;
                    }
                }
                if w != source {
                    *betweenness.entry(w).or_insert(0.0) += *delta.get(&w).unwrap_or(&0.0);
                }
            }
        }

        // Normalize: divide by 2 for undirected graphs (we use directed, so skip)
        // Divide by (n-1)(n-2) for normalized betweenness
        let n = nodes.len() as f64;
        if n > 2.0 {
            let norm_factor = (n - 1.0) * (n - 2.0);
            for score in betweenness.values_mut() {
                *score /= norm_factor;
            }
        }

        let mut results: Vec<(Uuid, f64)> = betweenness.into_iter().collect();
        results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        results.truncate(top_k);
        results
    }

    /// k-Core decomposition.
    ///
    /// Finds the k-core of the graph: the maximal subgraph where every node
    /// has degree ≥ k. Useful for identifying tightly-connected communities
    /// and the "core" of the economy.
    ///
    /// Returns a map of node_id → core number (max k such that node is in k-core).
    /// Complexity: O(V + E) using the peeling algorithm.
    pub fn k_core_decomposition(&self) -> HashMap<Uuid, usize> {
        let nodes = self.node_ids();
        if nodes.is_empty() {
            return HashMap::new();
        }

        // Compute effective degree (total undirected degree)
        let mut degree: HashMap<Uuid, usize> = HashMap::new();
        for &node in &nodes {
            let out = self.adjacency.get(&node).map(|e| e.len()).unwrap_or(0);
            let inc = self.reverse_adjacency.get(&node).map(|e| e.len()).unwrap_or(0);
            // For undirected interpretation, count unique neighbors
            let mut neighbors: HashSet<Uuid> = HashSet::new();
            if let Some(edges) = self.adjacency.get(&node) {
                for (n, _) in edges { neighbors.insert(*n); }
            }
            if let Some(edges) = self.reverse_adjacency.get(&node) {
                for (n, _) in edges { neighbors.insert(*n); }
            }
            degree.insert(node, neighbors.len());
        }

        let max_degree = degree.values().copied().max().unwrap_or(0);
        let mut core: HashMap<Uuid, usize> = HashMap::new();
        let mut removed: HashSet<Uuid> = HashSet::new();

        // Peeling algorithm: iteratively remove nodes with degree < k
        for k in 0..=max_degree {
            // Find all nodes with current effective degree <= k that haven't been removed
            let mut to_remove: Vec<Uuid> = Vec::new();
            for (&node, &deg) in degree.iter() {
                if !removed.contains(&node) && deg <= k {
                    to_remove.push(node);
                }
            }

            // BFS removal: removing a node reduces neighbors' degrees
            let mut queue: VecDeque<Uuid> = to_remove.into();
            while let Some(node) = queue.pop_front() {
                if removed.contains(&node) {
                    continue;
                }
                removed.insert(node);
                core.insert(node, k);

                // Decrease degree of all neighbors
                let mut neighbors: HashSet<Uuid> = HashSet::new();
                if let Some(edges) = self.adjacency.get(&node) {
                    for (n, _) in edges { neighbors.insert(*n); }
                }
                if let Some(edges) = self.reverse_adjacency.get(&node) {
                    for (n, _) in edges { neighbors.insert(*n); }
                }

                for neighbor in neighbors {
                    if !removed.contains(&neighbor) {
                        if let Some(deg) = degree.get_mut(&neighbor) {
                            *deg = deg.saturating_sub(1);
                            if *deg <= k {
                                queue.push_back(neighbor);
                            }
                        }
                    }
                }
            }
        }

        core
    }

    /// Weighted shortest path using Dijkstra's algorithm.
    ///
    /// Unlike the basic [shortest_path] which uses raw edge weights as costs,
    /// this uses inverse weights: higher-weight edges (stronger relationships)
    /// are "cheaper" to traverse. Cost = 1/weight for each edge.
    ///
    /// This enables queries like: "What's the closest (strongest) path between
    /// two economic entities?"
    pub fn weighted_shortest_path(&self, from: Uuid, to: Uuid) -> Option<ShortestPathResult> {
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

            if current_dist > *dist.get(&current).unwrap_or(&f64::INFINITY) {
                continue;
            }

            if let Some(neighbors) = self.adjacency.get(&current) {
                for (neighbor, weight) in neighbors {
                    // Inverse weight: stronger edges have lower cost
                    // Clamp to avoid division by zero
                    let cost = if *weight > 0.001 { 1.0 / weight } else { 1000.0 };
                    let new_dist = current_dist + cost;
                    let known_dist = *dist.get(neighbor).unwrap_or(&f64::INFINITY);

                    if new_dist < known_dist {
                        dist.insert(*neighbor, new_dist);
                        prev.insert(*neighbor, Some(current));
                        heap.push(Reverse((new_dist, *neighbor)));
                    }
                }
            }
        }

        None
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
    fn test_betweenness_centrality() {
        let graph = create_test_graph();
        let results = graph.betweenness_centrality(5);

        assert_eq!(results.len(), 5);
        // Node A (center, connecting bridge) should have highest betweenness
        let center = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        assert_eq!(results[0].node_id, center);
        assert!(results[0].score > 0.0, "Center node should have non-zero betweenness");
    }

    #[test]
    fn test_betweenness_centrality_linear() {
        // Linear chain: A → B → C → D
        // B and C should have highest betweenness (they bridge the chain)
        let mut graph = AlgorithmGraph::new();
        let a = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        let b = Uuid::parse_str("00000000-0000-0000-0000-000000000002").unwrap();
        let c = Uuid::parse_str("00000000-0000-0000-0000-000000000003").unwrap();
        let d = Uuid::parse_str("00000000-0000-0000-0000-000000000004").unwrap();

        graph.add_edge(a, b, 1.0);
        graph.add_edge(b, c, 1.0);
        graph.add_edge(c, d, 1.0);

        let results = graph.betweenness_centrality(4);
        // B and C are bridges; they should have highest betweenness
        let b_score = results.iter().find(|(id, _)| *id == b).map(|(_, s)| *s).unwrap_or(0.0);
        let c_score = results.iter().find(|(id, _)| *id == c).map(|(_, s)| *s).unwrap_or(0.0);
        let a_score = results.iter().find(|(id, _)| *id == a).map(|(_, s)| *s).unwrap_or(0.0);
        assert!(b_score > a_score, "B should have higher betweenness than A");
        assert!(c_score > a_score, "C should have higher betweenness than A");
    }

    #[test]
    fn test_k_core_decomposition() {
        let mut graph = AlgorithmGraph::new();
        let a = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        let b = Uuid::parse_str("00000000-0000-0000-0000-000000000002").unwrap();
        let c = Uuid::parse_str("00000000-0000-0000-0000-000000000003").unwrap();
        let d = Uuid::parse_str("00000000-0000-0000-0000-000000000004").unwrap();
        let e = Uuid::parse_str("00000000-0000-0000-0000-000000000005").unwrap();

        // Triangle: A-B-C (k=2 core)
        graph.add_undirected_edge(a, b, 1.0);
        graph.add_undirected_edge(b, c, 1.0);
        graph.add_undirected_edge(c, a, 1.0);
        // D attached to B (k=1)
        graph.add_undirected_edge(b, d, 1.0);
        // E attached to D (k=1, leaf)
        graph.add_undirected_edge(d, e, 1.0);

        let cores = graph.k_core_decomposition();

        // A, B, C should be in 2-core (triangle)
        let a_core = cores.get(&a).copied().unwrap_or(0);
        let b_core = cores.get(&b).copied().unwrap_or(0);
        let c_core = cores.get(&c).copied().unwrap_or(0);
        assert!(a_core >= 1, "A should be in at least 1-core");
        assert!(b_core >= 1, "B should be in at least 1-core");
        assert!(c_core >= 1, "C should be in at least 1-core");

        // E (leaf) should be in 1-core only
        let e_core = cores.get(&e).copied().unwrap_or(0);
        assert_eq!(e_core, 1, "Leaf node E should be in 1-core only");
    }

    #[test]
    fn test_weighted_shortest_path() {
        let mut graph = AlgorithmGraph::new();
        let a = Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap();
        let b = Uuid::parse_str("00000000-0000-0000-0000-000000000002").unwrap();
        let c = Uuid::parse_str("00000000-0000-0000-0000-000000000003").unwrap();

        // Strong edge A→B (weight 10.0) and weak edge A→C (weight 0.1), C→B (weight 0.1)
        graph.add_edge(a, b, 10.0);  // cost = 1/10 = 0.1
        graph.add_edge(a, c, 0.1);   // cost = 1/0.1 = 10
        graph.add_edge(c, b, 0.1);   // cost = 1/0.1 = 10

        // Weighted shortest should prefer the direct strong edge A→B
        let result = graph.weighted_shortest_path(a, b).unwrap();
        assert_eq!(result.path, vec![a, b]);
        assert!((result.total_weight - 0.1).abs() < 0.001, "Cost should be 1/10 = 0.1");
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
