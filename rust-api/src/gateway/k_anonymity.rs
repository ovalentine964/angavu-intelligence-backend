// src/gateway/k_anonymity.rs
//
// k-Anonymity enforcement for all data release endpoints.
//
// IC-PRIVACY changes:
// - Added structured logging for ALL k-anonymity decisions (allow + suppress)
// - Added alerting when k < MIN_K (via tracing::warn)
// - Added audit trail via KAnonymityAuditRecord
// - Added enforce_with_audit() for endpoints that need detailed logging

use chrono::{DateTime, Utc};
use dashmap::DashMap;
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

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
    /// Audit log of all k-anonymity decisions (ring buffer, last 1000)
    audit_log: parking_lot::Mutex<Vec<KAnonymityAuditRecord>>,
}

/// Audit record for k-anonymity enforcement decisions.
/// Logged for both allowed and suppressed queries.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KAnonymityAuditRecord {
    pub timestamp: DateTime<Utc>,
    pub cohort_key: String,
    pub sample_size: u32,
    pub threshold: usize,
    pub allowed: bool,
    pub endpoint: String,
    pub reason: Option<String>,
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
            audit_log: parking_lot::Mutex::new(Vec::with_capacity(1000)),
        }
    }

    /// Create enforcer with the standard minimum k=10.
    pub fn standard() -> Self {
        Self::new(MIN_K_ANONYMITY)
    }

    /// Get the configured k threshold.
    pub fn k_threshold(&self) -> usize {
        self.k
    }

    /// Check if a query result meets k-anonymity requirements.
    /// Logs all decisions and alerts when k < threshold.
    pub fn enforce<T>(&self, cohort_key: &str, data: T, sample_size: u32) -> KAnonymityResult<T> {
        self.enforce_with_audit(cohort_key, data, sample_size, "unknown")
    }

    /// Check k-anonymity with full audit logging (endpoint name captured).
    /// This is the preferred method for all data release endpoints.
    pub fn enforce_with_audit<T>(
        &self,
        cohort_key: &str,
        data: T,
        sample_size: u32,
        endpoint: &str,
    ) -> KAnonymityResult<T> {
        let allowed = sample_size >= self.k as u32;
        let reason = if !allowed {
            Some(format!(
                "Cohort size {} below k-anonymity threshold {}",
                sample_size, self.k
            ))
        } else {
            None
        };

        // ── Audit logging ──
        self.log_decision(cohort_key, sample_size, endpoint, allowed, reason.as_deref());

        // ── Alerting: warn loudly when k < MIN_K ──
        if !allowed {
            warn!(
                cohort_key = %cohort_key,
                sample_size = %sample_size,
                threshold = %self.k,
                endpoint = %endpoint,
                "⚠️ k-ANONYMITY VIOLATION: Cohort suppressed (k={} < MIN_K={})",
                sample_size, self.k
            );
        }

        if allowed {
            self.cohort_sizes.insert(cohort_key.to_string(), sample_size);
            KAnonymityResult {
                data: Some(data),
                k_anonymity: self.k,
                suppressed: false,
                reason: None,
            }
        } else {
            KAnonymityResult {
                data: None,
                k_anonymity: self.k,
                suppressed: true,
                reason,
            }
        }
    }

    /// Record a k-anonymity decision in the audit log.
    fn log_decision(&self, cohort_key: &str, sample_size: u32, endpoint: &str, allowed: bool, reason: Option<&str>) {
        let record = KAnonymityAuditRecord {
            timestamp: Utc::now(),
            cohort_key: cohort_key.to_string(),
            sample_size,
            threshold: self.k,
            allowed,
            endpoint: endpoint.to_string(),
            reason: reason.map(String::from),
        };

        if allowed {
            info!(
                cohort_key = %cohort_key,
                sample_size = %sample_size,
                threshold = %self.k,
                endpoint = %endpoint,
                "k-anonymity check PASSED"
            );
        }

        let mut log = self.audit_log.lock();
        if log.len() >= 1000 {
            log.drain(0..500);
        }
        log.push(record);
    }

    /// Get recent audit records (for monitoring dashboards).
    pub fn recent_audit(&self, limit: usize) -> Vec<KAnonymityAuditRecord> {
        let log = self.audit_log.lock();
        let start = log.len().saturating_sub(limit);
        log[start..].to_vec()
    }

    /// Count violations in the audit log.
    pub fn violation_count(&self) -> usize {
        let log = self.audit_log.lock();
        log.iter().filter(|r| !r.allowed).count()
    }

    /// Enforce k-anonymity on a batch of results (with audit logging)
    pub fn enforce_batch<T>(
        &self,
        results: Vec<(String, T, u32)>, // (cohort_key, data, sample_size)
    ) -> Vec<KAnonymityResult<T>> {
        self.enforce_batch_with_audit(results, "batch")
    }

    /// Enforce k-anonymity on a batch with endpoint tracking
    pub fn enforce_batch_with_audit<T>(
        &self,
        results: Vec<(String, T, u32)>,
        endpoint: &str,
    ) -> Vec<KAnonymityResult<T>> {
        results
            .into_iter()
            .map(|(key, data, size)| self.enforce_with_audit(&key, data, size, endpoint))
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
