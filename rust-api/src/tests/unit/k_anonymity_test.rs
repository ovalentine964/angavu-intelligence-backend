// rust-api/src/tests/unit/k_anonymity_test.rs
//
// Tests for k-anonymity enforcement in the API gateway.

#[cfg(test)]
mod tests {
    use crate::gateway::k_anonymity::*;

    #[test]
    fn k_anonymity_large_cohort_passes() {
        let enforcer = KAnonymityEnforcer::new(10);

        let result = enforcer.enforce("nairobi-vegetables", "market_data", 100);
        assert!(!result.suppressed);
        assert!(result.data.is_some());
        assert_eq!(result.k_anonymity, 10);
    }

    #[test]
    fn k_anonymity_exact_threshold_passes() {
        let enforcer = KAnonymityEnforcer::new(10);

        let result = enforcer.enforce("test-cohort", "data", 10);
        assert!(!result.suppressed);
        assert!(result.data.is_some());
    }

    #[test]
    fn k_anonymity_small_cohort_suppressed() {
        let enforcer = KAnonymityEnforcer::new(10);

        let result = enforcer.enforce("rare-cohort", "sensitive_data", 5);
        assert!(result.suppressed);
        assert!(result.data.is_none());
        assert!(result.reason.is_some());
        assert!(
            result.reason.unwrap().contains("below k-anonymity threshold"),
            "Reason should explain suppression"
        );
    }

    #[test]
    fn k_anonymity_single_individual_suppressed() {
        let enforcer = KAnonymityEnforcer::new(5);

        let result = enforcer.enforce("unique-user", "personal_data", 1);
        assert!(result.suppressed);
        assert!(result.data.is_none());
    }

    #[test]
    fn k_anonymity_batch_enforcement() {
        let enforcer = KAnonymityEnforcer::new(10);

        let batch = vec![
            ("cohort-a".to_string(), "data_a", 50),
            ("cohort-b".to_string(), "data_b", 3),   // below threshold
            ("cohort-c".to_string(), "data_c", 15),
            ("cohort-d".to_string(), "data_d", 8),   // below threshold
        ];

        let results = enforcer.enforce_batch(batch);
        assert_eq!(results.len(), 4);

        assert!(!results[0].suppressed);  // 50 >= 10
        assert!(results[1].suppressed);   // 3 < 10
        assert!(!results[2].suppressed);  // 15 >= 10
        assert!(results[3].suppressed);   // 8 < 10
    }

    #[test]
    fn k_anonymity_different_k_values() {
        // Stricter k = 50
        let strict = KAnonymityEnforcer::new(50);
        assert!(!strict.enforce("a", "data", 50).suppressed);
        assert!(strict.enforce("b", "data", 49).suppressed);

        // Relaxed k = 3
        let relaxed = KAnonymityEnforcer::new(3);
        assert!(!relaxed.enforce("a", "data", 3).suppressed);
        assert!(relaxed.enforce("b", "data", 2).suppressed);
    }

    #[test]
    fn k_anonymity_tracks_cohort_sizes() {
        let enforcer = KAnonymityEnforcer::new(5);

        enforcer.enforce("cohort-1", "data", 100);
        enforcer.enforce("cohort-2", "data", 200);

        // Verify cohorts are tracked (cohort_sizes should have entries)
        assert_eq!(enforcer.cohort_sizes.len(), 2);
    }

    #[test]
    fn k_anonymity_suppressed_does_not_track() {
        let enforcer = KAnonymityEnforcer::new(10);

        enforcer.enforce("small-cohort", "data", 3);
        // Suppressed cohorts should not be tracked
        assert_eq!(enforcer.cohort_sizes.len(), 0);
    }
}
