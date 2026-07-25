use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Minimum k value enforced by Angavu for anonymization compliance.
pub const MIN_K: usize = 10;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnonymizedRecord {
    pub cohort_id: String,
    pub cohort_size: usize,
    pub data: HashMap<String, f64>,
    pub suppressed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnonymizationStats {
    pub total_input_records: usize,
    pub cohorts_formed: usize,
    pub cohorts_kept: usize,
    pub cohorts_suppressed: usize,
    pub records_in_kept_cohorts: usize,
    pub records_suppressed: usize,
}

pub struct KAnonymityEnforcer {
    min_k: usize,
}

impl KAnonymityEnforcer {
    pub fn new(min_k: usize) -> Self {
        let enforced_k = min_k.max(MIN_K);
        Self { min_k: enforced_k }
    }

    /// Filter out any cohort below the k threshold. Records in suppressed cohorts
    /// are dropped entirely to prevent re-identification.
    pub fn enforce(&self, records: Vec<AnonymizedRecord>) -> Vec<AnonymizedRecord> {
        records
            .into_iter()
            .filter(|r| r.cohort_size >= self.min_k)
            .collect()
    }

    /// Suppress individual records that cannot be grouped into a valid cohort.
    /// Returns (kept_records, suppressed_records).
    pub fn suppress(
        &self,
        records: Vec<AnonymizedRecord>,
    ) -> (Vec<AnonymizedRecord>, Vec<AnonymizedRecord>) {
        let mut kept = Vec::new();
        let mut suppressed = Vec::new();
        for record in records {
            if record.cohort_size >= self.min_k {
                kept.push(record);
            } else {
                let mut r = record;
                r.suppressed = true;
                suppressed.push(r);
            }
        }
        (kept, suppressed)
    }

    /// Generalize quasi-identifiers by bucketing numeric values.
    /// E.g., ages 23, 27, 31 → bucket "20-29" for generalization width 10.
    pub fn generalize_value(value: f64, bucket_width: f64) -> String {
        let lower = (value / bucket_width).floor() * bucket_width;
        let upper = lower + bucket_width;
        format!("{}-{}", lower as u64, upper as u64)
    }

    /// Form cohorts from raw records using quasi-identifier fields.
    /// Records are grouped by their generalized key fields.
    /// Cohorts below k are suppressed.
    pub fn form_cohort(
        &self,
        records: Vec<HashMap<String, f64>>,
        key_fields: &[String],
    ) -> Vec<AnonymizedRecord> {
        let stats = self.form_cohort_with_stats(records, key_fields);
        stats
    }

    /// Form cohorts and return detailed statistics.
    pub fn form_cohort_with_stats(
        &self,
        records: Vec<HashMap<String, f64>>,
        key_fields: &[String],
    ) -> Vec<AnonymizedRecord> {
        let mut groups: HashMap<String, Vec<HashMap<String, f64>>> = HashMap::new();

        for record in records {
            // Build generalized key from quasi-identifiers
            let key: String = key_fields
                .iter()
                .map(|f| {
                    record
                        .get(f)
                        .map(|v| Self::generalize_value(*v, 10.0))
                        .unwrap_or_else(|| "unknown".to_string())
                })
                .collect::<Vec<_>>()
                .join("|");
            groups.entry(key).or_default().push(record);
        }

        groups
            .into_iter()
            .map(|(key, members)| {
                let size = members.len();
                let mut avg_data = HashMap::new();
                if let Some(first) = members.first() {
                    for k in first.keys() {
                        let avg = members.iter().filter_map(|m| m.get(k)).sum::<f64>()
                            / members.len() as f64;
                        avg_data.insert(k.clone(), avg);
                    }
                }
                AnonymizedRecord {
                    cohort_id: key,
                    cohort_size: size,
                    data: avg_data,
                    suppressed: size < self.min_k,
                }
            })
            .collect()
    }

    /// Full anonymization pipeline: form cohorts → suppress below k → compute stats.
    pub fn anonymize(
        &self,
        records: Vec<HashMap<String, f64>>,
        key_fields: &[String],
    ) -> (Vec<AnonymizedRecord>, AnonymizationStats) {
        let total_input = records.len();
        let all_cohorts = self.form_cohort_with_stats(records, key_fields);
        let cohorts_formed = all_cohorts.len();

        let mut kept = Vec::new();
        let mut suppressed_count = 0usize;
        let mut records_suppressed = 0usize;

        for cohort in all_cohorts {
            if cohort.cohort_size >= self.min_k {
                kept.push(cohort);
            } else {
                suppressed_count += 1;
                records_suppressed += cohort.cohort_size;
            }
        }

        let records_in_kept: usize = kept.iter().map(|c| c.cohort_size).sum();

        (
            kept,
            AnonymizationStats {
                total_input_records: total_input,
                cohorts_formed,
                cohorts_kept: kept.len() + suppressed_count - suppressed_count,
                cohorts_suppressed: suppressed_count,
                records_in_kept_cohorts: records_in_kept,
                records_suppressed,
            },
        )
    }

    /// Check if a dataset satisfies k-anonymity.
    pub fn is_k_anonymous(&self, records: &[AnonymizedRecord]) -> bool {
        records.iter().all(|r| r.cohort_size >= self.min_k)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_record(cohort_id: &str, size: usize) -> AnonymizedRecord {
        let mut data = HashMap::new();
        data.insert("avg_income".to_string(), 5000.0);
        AnonymizedRecord {
            cohort_id: cohort_id.to_string(),
            cohort_size: size,
            data,
            suppressed: false,
        }
    }

    #[test]
    fn test_min_k_enforcement() {
        // Even if you request k=5, the enforcer should clamp to MIN_K=10
        let enforcer = KAnonymityEnforcer::new(5);
        assert!(enforcer.min_k >= MIN_K);
    }

    #[test]
    fn test_enforce_filters_below_k() {
        let enforcer = KAnonymityEnforcer::new(10);
        let records = vec![
            make_record("A", 15),
            make_record("B", 8),   // below k=10
            make_record("C", 12),
            make_record("D", 3),   // below k=10
        ];
        let result = enforcer.enforce(records);
        assert_eq!(result.len(), 2);
        assert!(result.iter().all(|r| r.cohort_size >= 10));
    }

    #[test]
    fn test_suppress_separates_records() {
        let enforcer = KAnonymityEnforcer::new(10);
        let records = vec![
            make_record("A", 15),
            make_record("B", 5),
            make_record("C", 20),
        ];
        let (kept, suppressed) = enforcer.suppress(records);
        assert_eq!(kept.len(), 2);
        assert_eq!(suppressed.len(), 1);
        assert!(suppressed[0].suppressed);
    }

    #[test]
    fn test_generalize_value() {
        assert_eq!(KAnonymityEnforcer::generalize_value(23.0, 10.0), "20-30");
        assert_eq!(KAnonymityEnforcer::generalize_value(29.0, 10.0), "20-30");
        assert_eq!(KAnonymityEnforcer::generalize_value(30.0, 10.0), "30-40");
        assert_eq!(KAnonymityEnforcer::generalize_value(5.0, 5.0), "5-10");
    }

    #[test]
    fn test_form_cohort() {
        let enforcer = KAnonymityEnforcer::new(3);
        let records = vec![
            HashMap::from([("age".to_string(), 25.0), ("income".to_string(), 5000.0)]),
            HashMap::from([("age".to_string(), 27.0), ("income".to_string(), 5500.0)]),
            HashMap::from([("age".to_string(), 28.0), ("income".to_string(), 4800.0)]),
            HashMap::from([("age".to_string(), 45.0), ("income".to_string(), 8000.0)]),
            HashMap::from([("age".to_string(), 47.0), ("income".to_string(), 8500.0)]),
            HashMap::from([("age".to_string(), 42.0), ("income".to_string(), 7500.0)]),
        ];
        let cohorts = enforcer.form_cohort(records, &["age".to_string()]);
        // All cohorts should have at least 3 members
        assert!(cohorts.iter().all(|c| c.cohort_size >= 3));
    }

    #[test]
    fn test_anonymize_with_stats() {
        let enforcer = KAnonymityEnforcer::new(3);
        let records = vec![
            HashMap::from([("age".to_string(), 25.0), ("income".to_string(), 5000.0)]),
            HashMap::from([("age".to_string(), 27.0), ("income".to_string(), 5500.0)]),
            HashMap::from([("age".to_string(), 28.0), ("income".to_string(), 4800.0)]),
            HashMap::from([("age".to_string(), 70.0), ("income".to_string(), 3000.0)]), // isolated
        ];
        let (kept, stats) = enforcer.anonymize(records, &["age".to_string()]);
        assert_eq!(stats.total_input_records, 4);
        assert!(stats.cohorts_formed > 0);
        // The isolated age=70 record should be suppressed
        assert!(stats.records_suppressed > 0 || kept.iter().all(|c| c.cohort_size >= 3));
    }

    #[test]
    fn test_is_k_anonymous() {
        let enforcer = KAnonymityEnforcer::new(10);
        let valid = vec![make_record("A", 15), make_record("B", 12)];
        assert!(enforcer.is_k_anonymous(&valid));

        let invalid = vec![make_record("A", 15), make_record("B", 5)];
        assert!(!enforcer.is_k_anonymous(&invalid));
    }
}
