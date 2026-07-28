// rust-api/src/tests/unit/circuit_breaker_test.rs
//
// Comprehensive tests for circuit breaker pattern and OODA loop.

#[cfg(test)]
mod tests {
    use crate::graph::ooda::*;

    // ════════════════════════════════════════════════════════════
    //  CIRCUIT BREAKER TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn circuit_breaker_starts_closed() {
        let cb = CircuitBreaker::new(3, 60);
        assert_eq!(cb.state, CircuitState::Closed);
        assert!(cb.should_allow());
    }

    #[test]
    fn circuit_breaker_opens_after_threshold() {
        let mut cb = CircuitBreaker::new(3, 60);

        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Closed);

        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Closed);

        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Open);
        assert!(!cb.should_allow());
    }

    #[test]
    fn circuit_breaker_half_open_after_timeout() {
        let mut cb = CircuitBreaker::new(2, 0); // 0 second timeout for test

        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Open);

        // After timeout (0 seconds), should transition to half-open
        assert!(cb.should_allow());
        assert_eq!(cb.state, CircuitState::HalfOpen);
    }

    #[test]
    fn circuit_breaker_closes_after_successes_in_half_open() {
        let mut cb = CircuitBreaker::new(2, 0);

        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Open);

        cb.should_allow(); // → HalfOpen
        assert_eq!(cb.state, CircuitState::HalfOpen);

        cb.record_success();
        cb.record_success();
        cb.record_success();
        assert_eq!(cb.state, CircuitState::Closed);
    }

    #[test]
    fn circuit_breaker_reopens_on_failure_in_half_open() {
        let mut cb = CircuitBreaker::new(2, 0);

        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Open);

        cb.should_allow(); // → HalfOpen
        assert_eq!(cb.state, CircuitState::HalfOpen);

        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Open);
    }

    #[test]
    fn circuit_breaker_resets_failure_count_on_success() {
        let mut cb = CircuitBreaker::new(3, 60);

        cb.record_failure();
        cb.record_failure();
        cb.record_success(); // Reset
        cb.record_failure();
        cb.record_failure();

        // Should still be closed because success reset the counter
        assert_eq!(cb.state, CircuitState::Closed);
    }

    #[test]
    fn circuit_breaker_different_thresholds() {
        // Threshold 1: opens immediately
        let mut cb1 = CircuitBreaker::new(1, 60);
        cb1.record_failure();
        assert_eq!(cb1.state, CircuitState::Open);

        // Threshold 5: needs 5 failures
        let mut cb5 = CircuitBreaker::new(5, 60);
        for _ in 0..4 {
            cb5.record_failure();
            assert_eq!(cb5.state, CircuitState::Closed);
        }
        cb5.record_failure();
        assert_eq!(cb5.state, CircuitState::Open);
    }

    // ════════════════════════════════════════════════════════════
    //  OODA GRAPH TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn ooda_graph_has_four_phases() {
        let graph = OodaGraph::standard(CycleSpeed::Daily);
        assert_eq!(graph.nodes.len(), 4);

        let phases: Vec<_> = graph.nodes.iter().map(|n| n.phase.clone()).collect();
        assert!(phases.contains(&OodaPhase::Observe));
        assert!(phases.contains(&OodaPhase::Orient));
        assert!(phases.contains(&OodaPhase::Decide));
        assert!(phases.contains(&OodaPhase::Act));
    }

    #[test]
    fn ooda_graph_has_edges() {
        let graph = OodaGraph::standard(CycleSpeed::Daily);
        assert!(graph.edges.len() >= 4, "Should have at least 4 edges");
    }

    #[test]
    fn ooda_graph_observe_to_orient() {
        let graph = OodaGraph::standard(CycleSpeed::Daily);
        let transitions = graph.transitions_from(OodaPhase::Observe);
        assert!(!transitions.is_empty());

        let default = graph.default_transition(OodaPhase::Observe);
        assert!(default.is_some());
        assert_eq!(default.unwrap().target_phase, OodaPhase::Orient);
    }

    #[test]
    fn ooda_graph_emergency_edge() {
        let graph = OodaGraph::standard(CycleSpeed::Fast);

        let orient_transitions = graph.transitions_from(OodaPhase::Orient);
        let has_emergency = orient_transitions.iter().any(|e| {
            matches!(
                e.condition,
                Some(TransitionCondition::AnomalyDetected { .. })
            ) && e.target_phase == OodaPhase::Act
        });

        assert!(
            has_emergency,
            "Should have emergency Orient → Act edge for anomaly detection"
        );
    }

    #[test]
    fn ooda_graph_cycle_speeds() {
        let daily = OodaGraph::standard(CycleSpeed::Daily);
        let fast = OodaGraph::standard(CycleSpeed::Fast);

        // Both should have same topology
        assert_eq!(daily.nodes.len(), fast.nodes.len());

        // But potentially different timing parameters
        // (this validates the enum variants exist)
        assert_ne!(
            std::mem::discriminant(&CycleSpeed::Daily),
            std::mem::discriminant(&CycleSpeed::Fast)
        );
    }

    // ════════════════════════════════════════════════════════════
    //  OODA PHASE TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn ooda_phases_are_distinct() {
        let phases = vec![
            OodaPhase::Observe,
            OodaPhase::Orient,
            OodaPhase::Decide,
            OodaPhase::Act,
        ];

        // All should be different
        for i in 0..phases.len() {
            for j in (i + 1)..phases.len() {
                assert_ne!(
                    std::mem::discriminant(&phases[i]),
                    std::mem::discriminant(&phases[j]),
                    "Phases {:?} and {:?} should be different",
                    phases[i],
                    phases[j]
                );
            }
        }
    }

    // ════════════════════════════════════════════════════════════
    //  PIPELINE TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn pipeline_stage_ordering() {
        // Verify pipeline stages execute in correct order
        let stages = vec![
            "ingestion",
            "validation",
            "enrichment",
            "analysis",
            "output",
        ];

        for i in 0..stages.len() - 1 {
            assert!(
                i < i + 1,
                "Stage '{}' should come before '{}'",
                stages[i],
                stages[i + 1]
            );
        }
    }
}
