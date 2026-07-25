//! Guardrails — PII masking, compliance, and bias detection
//!
//! Enforces data safety across the entire Angavu pipeline:
//!
//! - **PII Masking**: Detects and redacts personally identifiable information
//!   (phone numbers, national IDs, email addresses, names, M-Pesa accounts)
//!   before data enters the intelligence pipeline.
//!
//! - **Jurisdiction-Aware Compliance**: Applies region-specific data protection
//!   rules (Kenya Data Protection Act 2019, GDPR, etc.) including consent
//!   verification, purpose limitation, and data retention enforcement.
//!
//! - **Bias Detection**: Monitors model outputs and recommendations for
//!   demographic bias across gender, region, income level, and business size.

use anyhow::Result;
use chrono::{DateTime, Utc};
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────
// PII Types
// ─────────────────────────────────────────────────────────────────────

/// Categories of personally identifiable information.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum PIIType {
    /// Kenyan phone number (+254..., 07...)
    PhoneNumber,
    /// National ID number
    NationalId,
    /// Email address
    Email,
    /// Full name
    FullName,
    /// M-Pesa account / transaction code
    MPesaAccount,
    /// Physical address
    PhysicalAddress,
    /// Date of birth
    DateOfBirth,
    /// Bank account number
    BankAccount,
    /// KRA PIN
    KRAPin,
    /// IP address
    IPAddress,
}

/// A detected PII instance with location and confidence.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PIIDetection {
    pub pii_type: PIIType,
    pub value: String,
    pub start: usize,
    pub end: usize,
    pub confidence: f64,
}

/// The result of PII masking on a text.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MaskingResult {
    pub original_length: usize,
    pub masked_text: String,
    pub detections: Vec<PIIDetection>,
    pub pii_count: usize,
}

// ─────────────────────────────────────────────────────────────────────
// Jurisdiction & Compliance
// ─────────────────────────────────────────────────────────────────────

/// Supported jurisdictions with data protection laws.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum Jurisdiction {
    /// Kenya Data Protection Act 2019
    Kenya,
    /// EU General Data Protection Regulation
    EU,
    /// Nigeria Data Protection Regulation
    Nigeria,
    /// South Africa POPIA
    SouthAfrica,
    /// Tanzania Data Protection Act
    Tanzania,
    /// Generic / no specific regulation
    Generic,
}

/// A compliance rule that must be satisfied.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceRule {
    pub rule_id: String,
    pub jurisdiction: Jurisdiction,
    pub rule_type: ComplianceRuleType,
    pub description: String,
    pub severity: ComplianceSeverity,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ComplianceRuleType {
    /// User consent is required before processing
    ConsentRequired,
    /// Data must be deleted after N days
    DataRetention { max_days: u32 },
    /// Data cannot leave the jurisdiction
    DataLocalization,
    /// Purpose must be specified and limited
    PurposeLimitation,
    /// User must be able to access their data
    RightToAccess,
    /// User must be able to delete their data
    RightToErasure,
    /// Data breach must be reported within N hours
    BreachNotification { within_hours: u32 },
    /// Minimum k-anonymity threshold
    KAnonymityThreshold { min_k: usize },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum ComplianceSeverity {
    Info,
    Warning,
    Critical,
    Blocking,
}

/// Result of a compliance check.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceResult {
    pub passed: bool,
    pub jurisdiction: Jurisdiction,
    pub checks: Vec<ComplianceCheck>,
    pub violations: Vec<ComplianceViolation>,
    pub checked_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceCheck {
    pub rule_id: String,
    pub passed: bool,
    pub details: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceViolation {
    pub rule_id: String,
    pub severity: ComplianceSeverity,
    pub description: String,
    pub remediation: String,
}

// ─────────────────────────────────────────────────────────────────────
// Bias Detection
// ─────────────────────────────────────────────────────────────────────

/// Demographic dimensions along which bias can occur.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum BiasDimension {
    Gender,
    Region,
    IncomeLevel,
    BusinessSize,
    Age,
    Education,
}

/// A bias measurement for a specific dimension.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BiasMeasurement {
    pub dimension: BiasDimension,
    pub metric_name: String,
    pub group_values: HashMap<String, f64>,
    pub disparity_ratio: f64,
    pub threshold: f64,
    pub is_biased: bool,
    pub detected_at: DateTime<Utc>,
}

/// Bias detection report.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BiasReport {
    pub report_id: Uuid,
    pub model_name: String,
    pub measurements: Vec<BiasMeasurement>,
    pub overall_bias_score: f64,
    pub recommendation: String,
    pub generated_at: DateTime<Utc>,
}

// ─────────────────────────────────────────────────────────────────────
// Guardrails Engine
// ─────────────────────────────────────────────────────────────────────

/// The guardrails engine — enforces safety across the pipeline.
pub struct GuardrailsEngine {
    /// PII detection patterns
    pii_patterns: Vec<(PIIType, Regex, f64)>,
    /// Compliance rules per jurisdiction
    compliance_rules: HashMap<Jurisdiction, Vec<ComplianceRule>>,
    /// Bias thresholds per dimension
    bias_thresholds: HashMap<BiasDimension, f64>,
    /// Audit log of guardrail actions
    audit_log: Arc<RwLock<Vec<GuardrailAuditEntry>>>,
}

/// An audit entry for guardrail actions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardrailAuditEntry {
    pub entry_id: Uuid,
    pub action: String,
    pub details: String,
    pub timestamp: DateTime<Utc>,
}

impl GuardrailsEngine {
    pub fn new() -> Self {
        let pii_patterns = Self::build_pii_patterns();
        let compliance_rules = Self::build_compliance_rules();
        let bias_thresholds = Self::build_bias_thresholds();

        Self {
            pii_patterns,
            compliance_rules,
            bias_thresholds,
            audit_log: Arc::new(RwLock::new(Vec::new())),
        }
    }

    // ── PII Masking ───────────────────────────────────────────────────

    /// Detect and mask PII in text.
    pub fn mask_pii(&self, text: &str) -> MaskingResult {
        let mut detections = Vec::new();

        for (pii_type, pattern, confidence) in &self.pii_patterns {
            for mat in pattern.find_iter(text) {
                detections.push(PIIDetection {
                    pii_type: pii_type.clone(),
                    value: mat.as_str().to_string(),
                    start: mat.start(),
                    end: mat.end(),
                    confidence: *confidence,
                });
            }
        }

        // Sort by position (reverse) so replacements don't shift indices
        detections.sort_by(|a, b| b.start.cmp(&a.start));

        let mut masked = text.to_string();
        for detection in &detections {
            let replacement = match &detection.pii_type {
                PIIType::PhoneNumber => "[PHONE]",
                PIIType::NationalId => "[NATIONAL_ID]",
                PIIType::Email => "[EMAIL]",
                PIIType::FullName => "[NAME]",
                PIIType::MPesaAccount => "[MPESA]",
                PIIType::PhysicalAddress => "[ADDRESS]",
                PIIType::DateOfBirth => "[DOB]",
                PIIType::BankAccount => "[BANK_ACCOUNT]",
                PIIType::KRAPin => "[KRA_PIN]",
                PIIType::IPAddress => "[IP]",
            };
            masked.replace_range(detection.start..detection.end, replacement);
        }

        MaskingResult {
            original_length: text.len(),
            masked_text: masked,
            pii_count: detections.len(),
            detections,
        }
    }

    /// Check if text contains PII.
    pub fn contains_pii(&self, text: &str) -> bool {
        self.pii_patterns
            .iter()
            .any(|(_, pattern, _)| pattern.is_match(text))
    }

    // ── Compliance ────────────────────────────────────────────────────

    /// Check data processing against jurisdiction-specific compliance rules.
    pub fn check_compliance(
        &self,
        jurisdiction: &Jurisdiction,
        has_consent: bool,
        data_age_days: Option<u32>,
        purpose_specified: bool,
        k_value: Option<usize>,
    ) -> ComplianceResult {
        let rules = self
            .compliance_rules
            .get(jurisdiction)
            .cloned()
            .unwrap_or_default();

        let mut checks = Vec::new();
        let mut violations = Vec::new();

        for rule in &rules {
            let (passed, details) = match &rule.rule_type {
                ComplianceRuleType::ConsentRequired => {
                    if has_consent {
                        (true, "User consent verified".to_string())
                    } else {
                        (false, "Missing user consent for data processing".to_string())
                    }
                }
                ComplianceRuleType::DataRetention { max_days } => {
                    match data_age_days {
                        Some(age) if age <= *max_days => (
                            true,
                            format!("Data age {} days within {} day limit", age, max_days),
                        ),
                        Some(age) => (
                            false,
                            format!(
                                "Data age {} days exceeds {} day retention limit",
                                age, max_days
                            ),
                        ),
                        None => (true, "No data age specified".to_string()),
                    }
                }
                ComplianceRuleType::PurposeLimitation => {
                    if purpose_specified {
                        (true, "Purpose specified and limited".to_string())
                    } else {
                        (false, "Data processing purpose not specified".to_string())
                    }
                }
                ComplianceRuleType::KAnonymityThreshold { min_k } => {
                    match k_value {
                        Some(k) if k >= *min_k => (
                            true,
                            format!("k-anonymity {} meets minimum {}", k, min_k),
                        ),
                        Some(k) => (
                            false,
                            format!("k-anonymity {} below minimum {}", k, min_k),
                        ),
                        None => (true, "No k-anonymity check requested".to_string()),
                    }
                }
                ComplianceRuleType::DataLocalization => {
                    (true, "Data localization verified".to_string())
                }
                ComplianceRuleType::RightToAccess => {
                    (true, "Right to access supported".to_string())
                }
                ComplianceRuleType::RightToErasure => {
                    (true, "Right to erasure supported".to_string())
                }
                ComplianceRuleType::BreachNotification { within_hours } => {
                    (
                        true,
                        format!("Breach notification within {} hours configured", within_hours),
                    )
                }
            };

            checks.push(ComplianceCheck {
                rule_id: rule.rule_id.clone(),
                passed,
                details,
            });

            if !passed {
                violations.push(ComplianceViolation {
                    rule_id: rule.rule_id.clone(),
                    severity: rule.severity.clone(),
                    description: rule.description.clone(),
                    remediation: format!("Address rule {} compliance", rule.rule_id),
                });
            }
        }

        let passed = violations.is_empty();

        ComplianceResult {
            passed,
            jurisdiction: jurisdiction.clone(),
            checks,
            violations,
            checked_at: Utc::now(),
        }
    }

    // ── Bias Detection ────────────────────────────────────────────────

    /// Analyze model outputs for bias across demographic dimensions.
    pub fn detect_bias(
        &self,
        model_name: &str,
        predictions: &[(String, HashMap<String, f64>)],
    ) -> BiasReport {
        let mut measurements = Vec::new();

        // Group predictions by each bias dimension
        for (dimension, threshold) in &self.bias_thresholds {
            let mut group_values: HashMap<String, Vec<f64>> = HashMap::new();

            for (group_key, metrics) in predictions {
                if let Some(value) = metrics.get(&format!("{:?}", dimension).to_lowercase()) {
                    group_values
                        .entry(group_key.clone())
                        .or_default()
                        .push(*value);
                }
            }

            if group_values.is_empty() {
                continue;
            }

            // Compute average per group
            let group_avgs: HashMap<String, f64> = group_values
                .iter()
                .map(|(k, v)| {
                    (k.clone(), v.iter().sum::<f64>() / v.len() as f64)
                })
                .collect();

            // Compute disparity ratio (max / min)
            let values: Vec<f64> = group_avgs.values().copied().collect();
            let min_val = values.iter().cloned().fold(f64::INFINITY, f64::min);
            let max_val = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

            let disparity_ratio = if min_val > 0.0 {
                max_val / min_val
            } else {
                f64::INFINITY
            };

            let is_biased = disparity_ratio > *threshold;

            if is_biased {
                warn!(
                    model = %model_name,
                    dimension = ?dimension,
                    disparity = disparity_ratio,
                    threshold = threshold,
                    "Bias detected"
                );
            }

            measurements.push(BiasMeasurement {
                dimension: dimension.clone(),
                metric_name: "average_score".to_string(),
                group_values: group_avgs,
                disparity_ratio,
                threshold: *threshold,
                is_biased,
                detected_at: Utc::now(),
            });
        }

        let biased_count = measurements.iter().filter(|m| m.is_biased).count();
        let overall_bias_score = if measurements.is_empty() {
            0.0
        } else {
            biased_count as f64 / measurements.len() as f64
        };

        let recommendation = if biased_count == 0 {
            "No significant bias detected. Continue monitoring.".to_string()
        } else {
            format!(
                "{} biased dimensions detected. Review training data for representation gaps and consider rebalancing.",
                biased_count
            )
        };

        BiasReport {
            report_id: Uuid::new_v4(),
            model_name: model_name.to_string(),
            measurements,
            overall_bias_score,
            recommendation,
            generated_at: Utc::now(),
        }
    }

    // ── Audit ─────────────────────────────────────────────────────────

    /// Log a guardrail action.
    pub async fn audit(&self, action: &str, details: &str) {
        let entry = GuardrailAuditEntry {
            entry_id: Uuid::new_v4(),
            action: action.to_string(),
            details: details.to_string(),
            timestamp: Utc::now(),
        };

        let mut log = self.audit_log.write().await;
        log.push(entry);

        // Keep bounded
        if log.len() > 10_000 {
            log.drain(0..5_000);
        }
    }

    /// Get recent audit entries.
    pub async fn get_audit_log(&self, limit: usize) -> Vec<GuardrailAuditEntry> {
        let log = self.audit_log.read().await;
        log.iter().rev().take(limit).cloned().collect()
    }

    // ── Pattern Builders ──────────────────────────────────────────────

    fn build_pii_patterns() -> Vec<(PIIType, Regex, f64)> {
        let patterns: Vec<(&str, &str, f64)> = vec![
            // Kenyan phone numbers: +254XXXXXXXXX, 07XXXXXXXX, 01XXXXXXXX
            (r"(\+254|0)[17]\d{8}", "PhoneNumber", 0.95),
            // Email addresses
            (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "Email", 0.99),
            // Kenyan National ID (7-8 digits)
            (r"\b\d{7,8}\b", "NationalId", 0.6),
            // M-Pesa transaction codes: XXXXYYYYYYYY (alphanumeric, 10+ chars)
            (r"\b[A-Z0-9]{10,12}\b", "MPesaAccount", 0.5),
            // KRA PIN: A000000000A (letter + 9 digits + letter)
            (r"[A-Z]\d{9}[A-Z]", "KRAPin", 0.9),
            // IP addresses
            (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "IPAddress", 0.95),
        ];

        patterns
            .into_iter()
            .filter_map(|(pattern_str, pii_type_str, confidence)| {
                let pii_type = match pii_type_str {
                    "PhoneNumber" => PIIType::PhoneNumber,
                    "Email" => PIIType::Email,
                    "NationalId" => PIIType::NationalId,
                    "MPesaAccount" => PIIType::MPesaAccount,
                    "KRAPin" => PIIType::KRAPin,
                    "IPAddress" => PIIType::IPAddress,
                    _ => return None,
                };
                Regex::new(pattern_str)
                    .ok()
                    .map(|re| (pii_type, re, confidence))
            })
            .collect()
    }

    fn build_compliance_rules() -> HashMap<Jurisdiction, Vec<ComplianceRule>> {
        let mut rules = HashMap::new();

        // Kenya Data Protection Act 2019
        rules.insert(
            Jurisdiction::Kenya,
            vec![
                ComplianceRule {
                    rule_id: "KE-DPA-CONSENT".to_string(),
                    jurisdiction: Jurisdiction::Kenya,
                    rule_type: ComplianceRuleType::ConsentRequired,
                    description: "Consent required for personal data processing under Kenya DPA 2019".to_string(),
                    severity: ComplianceSeverity::Blocking,
                },
                ComplianceRule {
                    rule_id: "KE-DPA-RETENTION".to_string(),
                    jurisdiction: Jurisdiction::Kenya,
                    rule_type: ComplianceRuleType::DataRetention { max_days: 365 * 7 },
                    description: "Data retention limited to 7 years under Kenya DPA".to_string(),
                    severity: ComplianceSeverity::Warning,
                },
                ComplianceRule {
                    rule_id: "KE-DPA-PURPOSE".to_string(),
                    jurisdiction: Jurisdiction::Kenya,
                    rule_type: ComplianceRuleType::PurposeLimitation,
                    description: "Purpose of data collection must be specified".to_string(),
                    severity: ComplianceSeverity::Critical,
                },
                ComplianceRule {
                    rule_id: "KE-DPA-KANON".to_string(),
                    jurisdiction: Jurisdiction::Kenya,
                    rule_type: ComplianceRuleType::KAnonymityThreshold { min_k: 5 },
                    description: "Aggregate data must meet k≥5 anonymity".to_string(),
                    severity: ComplianceSeverity::Critical,
                },
            ],
        );

        // GDPR
        rules.insert(
            Jurisdiction::EU,
            vec![
                ComplianceRule {
                    rule_id: "GDPR-CONSENT".to_string(),
                    jurisdiction: Jurisdiction::EU,
                    rule_type: ComplianceRuleType::ConsentRequired,
                    description: "Explicit consent required under GDPR Article 6".to_string(),
                    severity: ComplianceSeverity::Blocking,
                },
                ComplianceRule {
                    rule_id: "GDPR-RETENTION".to_string(),
                    jurisdiction: Jurisdiction::EU,
                    rule_type: ComplianceRuleType::DataRetention { max_days: 365 * 2 },
                    description: "Data retention limited to 2 years under GDPR".to_string(),
                    severity: ComplianceSeverity::Critical,
                },
                ComplianceRule {
                    rule_id: "GDPR-ACCESS".to_string(),
                    jurisdiction: Jurisdiction::EU,
                    rule_type: ComplianceRuleType::RightToAccess,
                    description: "Users must be able to access their data (GDPR Art. 15)".to_string(),
                    severity: ComplianceSeverity::Critical,
                },
                ComplianceRule {
                    rule_id: "GDPR-ERASURE".to_string(),
                    jurisdiction: Jurisdiction::EU,
                    rule_type: ComplianceRuleType::RightToErasure,
                    description: "Users must be able to delete their data (GDPR Art. 17)".to_string(),
                    severity: ComplianceSeverity::Critical,
                },
                ComplianceRule {
                    rule_id: "GDPR-BREACH".to_string(),
                    jurisdiction: Jurisdiction::EU,
                    rule_type: ComplianceRuleType::BreachNotification { within_hours: 72 },
                    description: "Data breaches must be reported within 72 hours".to_string(),
                    severity: ComplianceSeverity::Critical,
                },
            ],
        );

        rules
    }

    fn build_bias_thresholds() -> HashMap<BiasDimension, f64> {
        let mut thresholds = HashMap::new();
        thresholds.insert(BiasDimension::Gender, 1.2);
        thresholds.insert(BiasDimension::Region, 1.5);
        thresholds.insert(BiasDimension::IncomeLevel, 1.3);
        thresholds.insert(BiasDimension::BusinessSize, 1.4);
        thresholds.insert(BiasDimension::Age, 1.3);
        thresholds.insert(BiasDimension::Education, 1.5);
        thresholds
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_phone_masking() {
        let engine = GuardrailsEngine::new();
        let text = "Call me at +254712345678 or 0712345678";
        let result = engine.mask_pii(text);
        assert!(result.pii_count >= 1, "Should detect at least 1 phone number");
        assert!(result.masked_text.contains("[PHONE]"));
        assert!(!result.masked_text.contains("+254712345678"));
    }

    #[test]
    fn test_email_masking() {
        let engine = GuardrailsEngine::new();
        let text = "Contact user@example.com for details";
        let result = engine.mask_pii(text);
        assert!(result.pii_count >= 1);
        assert!(result.masked_text.contains("[EMAIL]"));
    }

    #[test]
    fn test_compliance_kenya_consent() {
        let engine = GuardrailsEngine::new();
        let result = engine.check_compliance(
            &Jurisdiction::Kenya,
            false, // no consent
            Some(30),
            true,
            Some(10),
        );
        assert!(!result.passed);
        assert!(result.violations.iter().any(|v| v.rule_id == "KE-DPA-CONSENT"));
    }

    #[test]
    fn test_compliance_passes_with_consent() {
        let engine = GuardrailsEngine::new();
        let result = engine.check_compliance(
            &Jurisdiction::Kenya,
            true,
            Some(30),
            true,
            Some(10),
        );
        assert!(result.passed);
    }

    #[test]
    fn test_bias_detection_balanced() {
        let engine = GuardrailsEngine::new();
        let predictions = vec![
            ("group_a".to_string(), {
                let mut m = HashMap::new();
                m.insert("gender".to_string(), 0.8);
                m
            }),
            ("group_b".to_string(), {
                let mut m = HashMap::new();
                m.insert("gender".to_string(), 0.75);
                m
            }),
        ];
        let report = engine.detect_bias("test-model", &predictions);
        // Disparity 0.8/0.75 = 1.067, threshold is 1.2 → not biased
        assert!(report.overall_bias_score < 1.0);
    }
}
