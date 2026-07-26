// rust-api/src/graph/benchmarks.rs

#[cfg(test)]
mod benchmarks {
    use criterion::{black_box, criterion_group, criterion_main, Criterion};
    use super::pipeline::*;

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
            let mut cb = CircuitBreaker::new(5, 60);
            b.iter(|| {
                black_box(&mut cb).should_allow();
            });
        });
    }

    criterion_group!(benches, bench_topological_sort, bench_ready_nodes, bench_circuit_breaker);
    criterion_main!(benches);
}
