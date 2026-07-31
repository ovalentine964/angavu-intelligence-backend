// src/gateway/k_anonymity.rs

use dashmap::DashMap;
use serde::{Deserialize, Serialize};

/// Standard minimum k-anonymity threshold across the entire system.
/// All cohort queries, FL aggregation, and market intelligence must
/// represent at least this many individuals before results are shown.
pub const MIN_K_ANONYMITY: usize = 10;

/// Enforces k-anonymity on all query results
///
/// Any aggregate result must represent at least k individuals.
/// If a query result has fewer than k contributors, it is suppressed.
pub struct KAnonymityEnforcer {
    /// Minimum cohort size (always >= MIN_K_ANONYMITY)
    k: usize,
    /// Per-query cohort tracking
    cohort_sizes: DashMap<String, u32>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct KAnonymityResult<T> {
    pub data: Option<T>,
    pub k_anonymity: usize,
    pub suppressed: bool,
    pub reason: Option<String>,
}

impl KAnonymityEnforcer {
    pub fn new(k: usize) -> Self {
        Self {
            k: k.max(MIN_K_ANONYMITY), // Enforce system-wide minimum
            cohort_sizes: DashMap::new(),
        }
    }

    /// Create enforcer with the standard minimum k=10.
    pub fn standard() -> Self {
        Self::new(MIN_K_ANONYMITY)
    }

    /// Check if a query result meets k-anonymity requirements
    pub fn enforce<T>(&self, cohort_key: &str, data: T, sample_size: u32) -> KAnonymityResult<T> {
        if sample_size < self.k as u32 {
            KAnonymityResult {
                data: None,
                k_anonymity: self.k,
                suppressed: true,
                reason: Some(format!(
                    "Cohort size {} below k-anonymity threshold {}",
                    sample_size, self.k
                )),
            }
        } else {
            // Track cohort
            self.cohort_sizes.insert(cohort_key.to_string(), sample_size);

            KAnonymityResult {
                data: Some(data),
                k_anonymity: self.k,
                suppressed: false,
                reason: None,
            }
        }
    }

    /// Enforce k-anonymity on a batch of results
    pub fn enforce_batch<T>(
        &self,
        results: Vec<(String, T, u32)>, // (cohort_key, data, sample_size)
    ) -> Vec<KAnonymityResult<T>> {
        results.into_iter()
            .map(|(key, data, size)| self.enforce(&key, data, size))
            .collect()
    }

    /// Merge small cohorts with nearest neighbors
    pub fn merge_small_cohorts(
        &self,
        cohorts: &mut std::collections::HashMap<String, Vec<String>>,
    ) {
        let small_cohorts: Vec<String> = cohorts.iter()
            .filter(|(_, members)| members.len() < self.k)
            .map(|(key, _)| key.clone())
            .collect();

        for small_key in small_cohorts {
            if let Some((_, members)) = cohorts.remove_entry(&small_key) {
                // Find nearest existing cohort
                let nearest = cohorts.keys()
                    .min_by_key(|k| cohort_distance(&small_key, k))
                    .cloned();

                if let Some(target) = nearest.clone() {
                    cohorts.entry(target.clone()).or_default().extend(members);
                    tracing::info!(
                        merged = %small_key,
                        into = %target,
                        "Merged small cohort for k-anonymity"
                    );
                }
            }
        }
    }
}

/// Simple string-based cohort distance (region > business > language priority)
fn cohort_distance(a: &str, b: &str) -> usize {
    let parts_a: Vec<&str> = a.split('|').collect();
    let parts_b: Vec<&str> = b.split('|').collect();

    let mut distance = 0;
    for (pa, pb) in parts_a.iter().zip(parts_b.iter()) {
        if pa != pb {
            distance += 1;
        }
    }
    distance + parts_a.len().abs_diff(parts_b.len())
}
