// rust-api/src/graph/ooda_tests.rs

#[cfg(test)]
mod tests {
    use super::ooda::*;

    #[test]
    fn test_circuit_breaker_transitions() {
        let mut cb = CircuitBreaker::new(3, 60);

        // Closed state: allow requests
        assert!(cb.should_allow());
        assert_eq!(cb.state, CircuitState::Closed);

        // Fail 3 times → open
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Closed);
        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Open);
        assert!(!cb.should_allow());
    }

    #[test]
    fn test_circuit_breaker_recovery() {
        let mut cb = CircuitBreaker::new(2, 0);  // 0 second open duration for test

        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state, CircuitState::Open);

        // After open duration, should transition to half-open
        // (In test, duration is 0 so it happens immediately)
        assert!(cb.should_allow());
        assert_eq!(cb.state, CircuitState::HalfOpen);

        // 3 successes in half-open → closed
        cb.record_success();
        cb.record_success();
        cb.record_success();
        assert_eq!(cb.state, CircuitState::Closed);
    }

    #[test]
    fn test_ooda_graph_standard_topology() {
        let graph = OodaGraph::standard(CycleSpeed::Daily);

        // Should have 4 nodes
        assert_eq!(graph.nodes.len(), 4);

        // Should have edges (primary flow + conditional)
        assert!(graph.edges.len() >= 4);

        // Observe should have transitions to Orient
        let observe_transitions = graph.transitions_from(OodaPhase::Observe);
        assert!(!observe_transitions.is_empty());

        // Default transition from Observe should go to Orient
        let default = graph.default_transition(OodaPhase::Observe);
        assert!(default.is_some());
        assert_eq!(default.unwrap().target_phase, OodaPhase::Orient);
    }

    #[test]
    fn test_ooda_graph_conditional_transitions() {
        let graph = OodaGraph::standard(CycleSpeed::Fast);

        // Orient should have both a default (→ Decide) and an emergency (→ Act)
        let orient_transitions = graph.transitions_from(OodaPhase::Orient);
        assert!(orient_transitions.len() >= 2);

        let has_emergency = orient_transitions.iter().any(|e| {
            matches!(
                e.condition,
                Some(TransitionCondition::AnomalyDetected { .. })
            ) && e.target_phase == OodaPhase::Act
        });
        assert!(has_emergency, "Should have emergency Orient → Act edge");
    }
}
