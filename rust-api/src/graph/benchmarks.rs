// rust-api/src/graph/benchmarks.rs

#[cfg(test)]
mod benchmarks {
    use criterion::{black_box, criterion_group, criterion_main, Criterion};
    use crate::graph::pipeline::*;
    use crate::graph::algorithms::*;
    use crate::graph::ooda::*;
    use uuid::Uuid;

    fn bench_topological_sort(c: &mut Criterion) {
        c.bench_function("pipeline_topological_levels", |b| {
            let dag = PipelineDag::standard_intelligence_pipeline();
            b.iter(|| {
                PipelineDag::topological_levels(black_box(&dag.nodes));
            });
        });
    }

    fn bench_ready_nodes(c: &mut Criterion) {
        c.bench_function("pipeline_ready_nodes", |b| {
            let dag = PipelineDag::standard_intelligence_pipeline();
            b.iter(|| {
                black_box(&dag).ready_nodes();
            });
        });
    }

    fn bench_circuit_breaker(c: &mut Criterion) {
        c.bench_function("circuit_breaker_should_allow", |b| {
            let mut cb = make_node_circuit_breaker("bench", 5, 60);
            b.iter(|| {
                black_box(&mut cb).should_allow();
            });
        });
    }

    fn create_bench_graph(node_count: usize) -> AlgorithmGraph {
        let mut graph = AlgorithmGraph::new();
        let nodes: Vec<Uuid> = (0..node_count).map(|_| Uuid::new_v4()).collect();

        // Create a connected graph with random edges
        for i in 0..node_count {
            let num_edges = (i % 5) + 1;
            for j in 0..num_edges {
                let target = (i + j + 1) % node_count;
                graph.add_edge(nodes[i], nodes[target], 1.0);
            }
        }

        graph
    }

    fn bench_pagerank_100(c: &mut Criterion) {
        c.bench_function("pagerank_100_nodes", |b| {
            let graph = create_bench_graph(100);
            b.iter(|| {
                black_box(&graph).pagerank(20, 0.85);
            });
        });
    }

    fn bench_pagerank_1000(c: &mut Criterion) {
        c.bench_function("pagerank_1000_nodes", |b| {
            let graph = create_bench_graph(1000);
            b.iter(|| {
                black_box(&graph).pagerank(20, 0.85);
            });
        });
    }

    fn bench_community_detection(c: &mut Criterion) {
        c.bench_function("community_detection_100", |b| {
            let graph = create_bench_graph(100);
            b.iter(|| {
                black_box(&graph).detect_communities();
            });
        });
    }

    fn bench_degree_centrality(c: &mut Criterion) {
        c.bench_function("degree_centrality_1000", |b| {
            let graph = create_bench_graph(1000);
            b.iter(|| {
                black_box(&graph).degree_centrality(20);
            });
        });
    }

    fn bench_shortest_path(c: &mut Criterion) {
        c.bench_function("shortest_path_1000", |b| {
            let graph = create_bench_graph(1000);
            let nodes = graph.node_ids();
            let from = nodes[0];
            let to = nodes[nodes.len() - 1];
            b.iter(|| {
                black_box(&graph).shortest_path(from, to);
            });
        });
    }

    fn bench_neighborhood(c: &mut Criterion) {
        c.bench_function("neighborhood_2_hops_1000", |b| {
            let graph = create_bench_graph(1000);
            let nodes = graph.node_ids();
            let center = nodes[0];
            b.iter(|| {
                black_box(&graph).neighborhood(center, 2);
            });
        });
    }

    criterion_group!(
        benches,
        bench_topological_sort,
        bench_ready_nodes,
        bench_circuit_breaker,
        bench_pagerank_100,
        bench_pagerank_1000,
        bench_community_detection,
        bench_degree_centrality,
        bench_shortest_path,
        bench_neighborhood,
    );
    criterion_main!(benches);
}
