// credit/approval_gate.rs
// Human-in-the-Loop: Credit Decision Approval Gate
//
// Before any credit application is submitted, this gate:
//   1. Evaluates the credit decision confidence
//   2. If confidence < threshold → requires explicit user confirmation
//   3. Logs all decisions for audit trail
//   4. Supports voice confirmation with timeout
//
// This prevents:
//   - Automatic loan applications without user consent
//   - Low-confidence credit recommendations being acted upon
//   - Missing audit trail for credit decisions

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

/// Credit decision types that require human approval
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CreditDecisionType {
    /// Loan eligibility recommendation
    LoanEligibility,
    /// Specific loan application submission
    LoanApplication,
    /// Credit limit increase
    CreditLimitChange,
    /// Debt restructuring recommendation
    DebtRestructuring,
    /// Group (chama) credit decision
    GroupCredit,
}

/// Approval status for a credit decision
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ApprovalStatus {
    /// Awaiting user confirmation
    Pending,
    /// User explicitly approved
    Approved,
    /// User explicitly rejected
    Rejected,
    /// No response within timeout
    Expired,
    /// Auto-approved (high confidence, low risk)
    AutoApproved,
}

/// A credit decision awaiting approval
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditDecision {
    pub decision_id: String,
    pub decision_type: CreditDecisionType,
    pub worker_id: String,
    pub alama_score: u16,
    pub confidence: f64,
    pub recommended_amount: f64,
    pub lender: String,
    pub product_name: String,
    pub effective_apr: f64,
    pub description: String,
    pub description_swahili: String,
    pub created_at: u64,
    pub expires_at: u64,
    pub status: ApprovalStatus,
    pub user_response: Option<String>,
    pub audit_trail: Vec<AuditEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    pub timestamp: u64,
    pub action: String,
    pub actor: String,
    pub details: String,
}

/// Approval gate configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalGateConfig {
    /// Minimum confidence for auto-approval (0.0 - 1.0)
    pub auto_approve_threshold: f64,
    /// Maximum amount for auto-approval (KES)
    pub auto_approve_max_amount: f64,
    /// Decision timeout in seconds
    pub timeout_seconds: u64,
    /// Whether to require voice confirmation for large amounts
    pub require_voice_above: f64,
}

impl Default for ApprovalGateConfig {
    fn default() -> Self {
        Self {
            auto_approve_threshold: 0.95,
            auto_approve_max_amount: 1000.0, // KES 1,000
            timeout_seconds: 30,
            require_voice_above: 5000.0, // KES 5,000
        }
    }
}

/// Result of submitting a credit decision for approval
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalRequest {
    pub decision_id: String,
    pub status: ApprovalStatus,
    /// Prompt to show the user (Swahili/English)
    pub confirmation_prompt: String,
    /// Whether voice confirmation is required
    pub requires_voice: bool,
    /// Timeout in seconds
    pub timeout_seconds: u64,
}

/// Credit Approval Gate
pub struct CreditApprovalGate {
    config: ApprovalGateConfig,
    pending_decisions: Mutex<HashMap<String, CreditDecision>>,
}

impl CreditApprovalGate {
    pub fn new(config: ApprovalGateConfig) -> Self {
        Self {
            config,
            pending_decisions: Mutex::new(HashMap::new()),
        }
    }

    /// Submit a credit decision for approval.
    /// Returns an ApprovalRequest indicating whether user confirmation is needed.
    pub fn submit_decision(
        &self,
        decision_type: CreditDecisionType,
        worker_id: &str,
        alama_score: u16,
        confidence: f64,
        recommended_amount: f64,
        lender: &str,
        product_name: &str,
        effective_apr: f64,
    ) -> ApprovalRequest {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let decision_id = format!("cd_{}_{}", worker_id, now);

        // Determine if auto-approval is possible
        let can_auto_approve = confidence >= self.config.auto_approve_threshold
            && recommended_amount <= self.config.auto_approve_max_amount
            && !matches!(decision_type, CreditDecisionType::LoanApplication);

        let status = if can_auto_approve {
            ApprovalStatus::AutoApproved
        } else {
            ApprovalStatus::Pending
        };

        let requires_voice = recommended_amount >= self.config.require_voice_above;

        let (description, description_swahili) = build_description(
            decision_type,
            recommended_amount,
            lender,
            product_name,
            effective_apr,
            alama_score,
        );

        let confirmation_prompt = build_confirmation_prompt(
            decision_type,
            recommended_amount,
            lender,
            product_name,
            alama_score,
            requires_voice,
        );

        let decision = CreditDecision {
            decision_id: decision_id.clone(),
            decision_type,
            worker_id: worker_id.to_string(),
            alama_score,
            confidence,
            recommended_amount,
            lender: lender.to_string(),
            product_name: product_name.to_string(),
            effective_apr,
            description,
            description_swahili,
            created_at: now,
            expires_at: now + self.config.timeout_seconds,
            status,
            user_response: None,
            audit_trail: vec![AuditEntry {
                timestamp: now,
                action: "decision_submitted".to_string(),
                actor: "system".to_string(),
                details: format!(
                    "Type: {:?}, Amount: {:.0}, Confidence: {:.2}, Auto: {}",
                    decision_type, recommended_amount, confidence, can_auto_approve
                ),
            }],
        };

        let mut pending = self
            .pending_decisions
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        pending.insert(decision_id.clone(), decision);

        ApprovalRequest {
            decision_id,
            status,
            confirmation_prompt,
            requires_voice,
            timeout_seconds: self.config.timeout_seconds,
        }
    }

    /// Process user's confirmation response.
    pub fn confirm_decision(
        &self,
        decision_id: &str,
        approved: bool,
        user_comment: Option<&str>,
    ) -> Result<ApprovalStatus, String> {
        let mut pending = self
            .pending_decisions
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let decision = pending
            .get_mut(decision_id)
            .ok_or_else(|| "Decision not found".to_string())?;

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        // Check expiry
        if now > decision.expires_at {
            decision.status = ApprovalStatus::Expired;
            decision.audit_trail.push(AuditEntry {
                timestamp: now,
                action: "decision_expired".to_string(),
                actor: "system".to_string(),
                details: "No response within timeout".to_string(),
            });
            return Ok(ApprovalStatus::Expired);
        }

        // Record response
        decision.status = if approved {
            ApprovalStatus::Approved
        } else {
            ApprovalStatus::Rejected
        };
        decision.user_response = user_comment.map(|s| s.to_string());
        decision.audit_trail.push(AuditEntry {
            timestamp: now,
            action: if approved {
                "decision_approved"
            } else {
                "decision_rejected"
            }
            .to_string(),
            actor: "user".to_string(),
            details: user_comment.unwrap_or("").to_string(),
        });

        Ok(decision.status)
    }

    /// Get the status of a pending decision.
    pub fn get_decision(&self, decision_id: &str) -> Option<CreditDecision> {
        let pending = self
            .pending_decisions
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        pending.get(decision_id).cloned()
    }

    /// Get all pending decisions for a worker.
    pub fn get_pending_for_worker(&self, worker_id: &str) -> Vec<CreditDecision> {
        let pending = self
            .pending_decisions
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        pending
            .values()
            .filter(|d| d.worker_id == worker_id && d.status == ApprovalStatus::Pending)
            .cloned()
            .collect()
    }

    /// Expire stale decisions (cleanup).
    pub fn expire_stale(&self) -> usize {
        let mut pending = self
            .pending_decisions
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let mut expired_count = 0;
        for decision in pending.values_mut() {
            if decision.status == ApprovalStatus::Pending && now > decision.expires_at {
                decision.status = ApprovalStatus::Expired;
                decision.audit_trail.push(AuditEntry {
                    timestamp: now,
                    action: "auto_expired".to_string(),
                    actor: "system".to_string(),
                    details: "Stale decision auto-expired".to_string(),
                });
                expired_count += 1;
            }
        }
        expired_count
    }

    /// Get audit trail for a decision.
    pub fn get_audit_trail(&self, decision_id: &str) -> Option<Vec<AuditEntry>> {
        let pending = self
            .pending_decisions
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        pending.get(decision_id).map(|d| d.audit_trail.clone())
    }
}

/// Build human-readable description of the credit decision.
fn build_description(
    decision_type: CreditDecisionType,
    amount: f64,
    lender: &str,
    product: &str,
    apr: f64,
    score: u16,
) -> (String, String) {
    let en = match decision_type {
        CreditDecisionType::LoanEligibility => {
            format!(
                "Based on your Alama Score of {}, you may qualify for a {} loan of KES {:,.0} from {} at {:.1}% APR.",
                score, product, amount, lender, apr * 100.0
            )
        }
        CreditDecisionType::LoanApplication => {
            format!(
                "Submit loan application for KES {:,.0} from {} ({}) at {:.1}% APR. Alama Score: {}.",
                amount, lender, product, apr * 100.0, score
            )
        }
        CreditDecisionType::CreditLimitChange => {
            format!(
                "Credit limit change to KES {:,.0} for {} ({}). Current Alama Score: {}.",
                amount, lender, product, score
            )
        }
        CreditDecisionType::DebtRestructuring => {
            format!(
                "Debt restructuring recommendation: KES {:,.0} via {} at {:.1}% APR.",
                amount,
                product,
                apr * 100.0
            )
        }
        CreditDecisionType::GroupCredit => {
            format!(
                "Group credit decision: KES {:,.0} from {} for your chama. Alama Score: {}.",
                amount, lender, score
            )
        }
    };

    let sw = match decision_type {
        CreditDecisionType::LoanEligibility => {
            format!(
                "Kulingana na Alama Score yako ya {}, unaweza kupata mkopo wa KES {:,.0} kutoka {} kwa riba ya {:.1}% APR. Unataka kuendelea?",
                score, amount, lender, apr * 100.0
            )
        }
        CreditDecisionType::LoanApplication => {
            format!(
                "Unataka kuomba mkopo wa KES {:,.0} kutoka {} ({}) kwa riba ya {:.1}% APR. Alama Score: {}. Unakubali?",
                amount, lender, product, apr * 100.0, score
            )
        }
        CreditDecisionType::CreditLimitChange => {
            format!(
                "Kikomo cha mkopo kimebadilishwa kuwa KES {:,.0} kwa {} ({}). Alama Score ya sasa: {}.",
                amount, lender, product, score
            )
        }
        CreditDecisionType::DebtRestructuring => {
            format!(
                "Pendekezo la kubadilisha deni: KES {:,.0} kupitia {} kwa riba ya {:.1}% APR.",
                amount,
                product,
                apr * 100.0
            )
        }
        CreditDecisionType::GroupCredit => {
            format!(
                "Uamuzi wa mkopo wa kikundi: KES {:,.0} kutoka {} kwa chama yako. Alama Score: {}.",
                amount, lender, score
            )
        }
    };

    (en, sw)
}

/// Build confirmation prompt for the user.
fn build_confirmation_prompt(
    decision_type: CreditDecisionType,
    amount: f64,
    lender: &str,
    product: &str,
    score: u16,
    requires_voice: bool,
) -> String {
    let voice_note = if requires_voice {
        "\n🎤 Tafadhali thibitisha kwa sauti."
    } else {
        ""
    };

    match decision_type {
        CreditDecisionType::LoanEligibility => {
            format!(
                "📋 CREDIT DECISION\n━━━━━━━━━━━━━━━━━━━━\n\nKulingana na data ya biashara yako (Alama Score: {}), unaweza kupata mkopo wa KES {:,.0} kutoka {}.\n\nBidhaa: {}\n\nUnataka kuomba mkopo huu?\n\n✅ Jibu: Ndio / Hapana{}",
                score, amount, lender, product, voice_note
            )
        }
        CreditDecisionType::LoanApplication => {
            format!(
                "📋 OMBI LA MKOPO\n━━━━━━━━━━━━━━━━━━━━\n\nMkopo: KES {:,.0}\nWakopeshaji: {}\nBidhaa: {}\nAlama Score: {}\n\n⚠️ Unakubali kuomba mkopo huu?\n\n✅ Jibu: Ndio / Hapana{}",
                amount, lender, product, score, voice_note
            )
        }
        CreditDecisionType::CreditLimitChange => {
            format!(
                "📋 KIKOMO CHA MKOPO\n━━━━━━━━━━━━━━━━━━━━\n\nKikomo kipya: KES {:,.0}\nWakopeshaji: {}\n\nUnakubali?\n\n✅ Jibu: Ndio / Hapana{}",
                amount, lender, voice_note
            )
        }
        CreditDecisionType::DebtRestructuring => {
            format!(
                "📋 KUBADILISHA DENI\n━━━━━━━━━━━━━━━━━━━━\n\nKiasi: KES {:,.0}\nBidhaa: {}\n\nUnakubali kubadilisha deni lako?\n\n✅ Jibu: Ndio / Hapana{}",
                amount, product, voice_note
            )
        }
        CreditDecisionType::GroupCredit => {
            format!(
                "📋 MKOPO WA KIKUNDI\n━━━━━━━━━━━━━━━━━━━━\n\nKiasi: KES {:,.0}\nWakopeshaji: {}\n\nUnakubali kwa niaba ya chama yako?\n\n✅ Jibu: Ndio / Hapana{}",
                amount, lender, voice_note
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn high_confidence_low_amount_auto_approves() {
        let gate = CreditApprovalGate::new(ApprovalGateConfig::default());
        let result = gate.submit_decision(
            CreditDecisionType::LoanEligibility,
            "worker_123",
            650,
            0.96,
            500.0,
            "M-Shwari",
            "M-Shwari Loan",
            0.90,
        );
        assert_eq!(result.status, ApprovalStatus::AutoApproved);
    }

    #[test]
    fn loan_application_always_requires_approval() {
        let gate = CreditApprovalGate::new(ApprovalGateConfig::default());
        let result = gate.submit_decision(
            CreditDecisionType::LoanApplication,
            "worker_123",
            650,
            0.99,
            500.0,
            "M-Shwari",
            "M-Shwari Loan",
            0.90,
        );
        assert_eq!(result.status, ApprovalStatus::Pending);
    }

    #[test]
    fn large_amount_requires_voice() {
        let gate = CreditApprovalGate::new(ApprovalGateConfig::default());
        let result = gate.submit_decision(
            CreditDecisionType::LoanEligibility,
            "worker_123",
            650,
            0.8,
            10_000.0,
            "SACCO",
            "SACCO Development Loan",
            0.15,
        );
        assert!(result.requires_voice);
        assert_eq!(result.status, ApprovalStatus::Pending);
    }

    #[test]
    fn confirm_approve_works() {
        let gate = CreditApprovalGate::new(ApprovalGateConfig::default());
        let req = gate.submit_decision(
            CreditDecisionType::LoanEligibility,
            "worker_123",
            650,
            0.8,
            10_000.0,
            "SACCO",
            "SACCO Loan",
            0.15,
        );
        let status = gate
            .confirm_decision(&req.decision_id, true, Some("Nataka mkopo"))
            .unwrap();
        assert_eq!(status, ApprovalStatus::Approved);
    }

    #[test]
    fn confirm_reject_works() {
        let gate = CreditApprovalGate::new(ApprovalGateConfig::default());
        let req = gate.submit_decision(
            CreditDecisionType::LoanEligibility,
            "worker_123",
            650,
            0.8,
            10_000.0,
            "SACCO",
            "SACCO Loan",
            0.15,
        );
        let status = gate
            .confirm_decision(&req.decision_id, false, None)
            .unwrap();
        assert_eq!(status, ApprovalStatus::Rejected);
    }

    #[test]
    fn audit_trail_recorded() {
        let gate = CreditApprovalGate::new(ApprovalGateConfig::default());
        let req = gate.submit_decision(
            CreditDecisionType::LoanEligibility,
            "worker_123",
            650,
            0.8,
            10_000.0,
            "SACCO",
            "SACCO Loan",
            0.15,
        );
        gate.confirm_decision(&req.decision_id, true, Some("Approved"))
            .unwrap();

        let trail = gate.get_audit_trail(&req.decision_id).unwrap();
        assert_eq!(trail.len(), 2); // submit + confirm
        assert_eq!(trail[0].action, "decision_submitted");
        assert_eq!(trail[1].action, "decision_approved");
    }

    #[test]
    fn swahili_prompt_generated() {
        let gate = CreditApprovalGate::new(ApprovalGateConfig::default());
        let req = gate.submit_decision(
            CreditDecisionType::LoanEligibility,
            "worker_123",
            650,
            0.8,
            10_000.0,
            "SACCO",
            "SACCO Loan",
            0.15,
        );
        assert!(req.confirmation_prompt.contains("Alama Score"));
        assert!(req.confirmation_prompt.contains("KES"));
    }
}
