// =============================================================================
// Angavu Intelligence — AGI Training Data Collection
// Structured traces for future model fine-tuning and AGI training
//
// Extends the existing AgentTrace system with:
// - Decision outcomes (what was decided, what happened as a result)
// - Social context data (chama dynamics, supplier relationships)
// - Environmental context (market conditions, weather, events)
// - Goal tracking (user goals, progress, obstacles)
// - Causal chains (what led to what)
//
// All data is stored in a format suitable for future model fine-tuning:
// JSON-lines compatible, with input/output pairs and rich metadata.
// =============================================================================

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ── Decision Outcome Tracking ────────────────────────────────────────────────

/// Records the outcome of a decision for learning
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionOutcome {
    pub decision_id: String,
    pub trace_id: String,
    pub session_id: String,
    pub worker_id: String,
    pub decision_type: DecisionType,
    pub context: DecisionContext,
    pub recommendation: String,
    pub action_taken: Option<String>,
    pub outcome: Option<OutcomeRecord>,
    pub confidence_at_decision: f64,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DecisionType {
    CreditApproval,
    CreditRejection,
    ProductRecommendation,
    PricingAdvice,
    MarketEntry,
    SupplierSelection,
    InventoryManagement,
    ChamaContribution,
    SavingsGoal,
    InvestmentDecision,
    RiskAssessment,
    Custom(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionContext {
    /// Features/inputs that informed the decision
    pub input_features: serde_json::Value,
    /// Market conditions at decision time
    pub market_snapshot: Option<MarketSnapshot>,
    /// Worker's financial state at decision time
    pub financial_state: Option<FinancialSnapshot>,
    /// Social context
    pub social_context: Option<SocialContext>,
}

/// Snapshot of market conditions (for causal analysis)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketSnapshot {
    pub date: DateTime<Utc>,
    pub region: String,
    pub commodity_prices: std::collections::HashMap<String, f64>,
    pub demand_level: DemandLevel,
    pub supply_level: SupplyLevel,
    pub notable_events: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DemandLevel {
    VeryLow,
    Low,
    Normal,
    High,
    VeryHigh,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SupplyLevel {
    Scarce,
    Tight,
    Normal,
    Abundant,
    Oversupply,
}

/// Worker's financial snapshot at decision time
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FinancialSnapshot {
    pub cash_on_hand: f64,
    pub daily_revenue_avg: f64,
    pub daily_expense_avg: f64,
    pub outstanding_debt: f64,
    pub savings: f64,
    pub alama_score: Option<u16>,
}

/// Social context relevant to the decision
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SocialContext {
    pub chama_membership: Option<ChamaContext>,
    pub supplier_relationships: Vec<SupplierRelationship>,
    pub customer_base_size: Option<u32>,
    pub community_standing: CommunityStanding,
    pub family_dependents: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChamaContext {
    pub chama_id: String,
    pub role: String,
    pub contribution_frequency: String,
    pub trust_score: f64,
    pub active_members: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupplierRelationship {
    pub supplier_id: String,
    pub relationship_duration_months: u32,
    pub trust_level: TrustLevel,
    pub average_order_value: f64,
    pub payment_reliability: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TrustLevel {
    New,
    Developing,
    Established,
    Trusted,
    Preferred,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum CommunityStanding {
    Newcomer,
    Known,
    Respected,
    Leader,
}

/// Record of what actually happened after a decision
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutcomeRecord {
    pub recorded_at: DateTime<Utc>,
    pub outcome_type: OutcomeType,
    pub financial_impact: Option<FinancialImpact>,
    pub time_to_outcome_days: Option<u32>,
    pub unexpected_factors: Vec<String>,
    /// Would the user make the same decision again?
    pub user_satisfaction: Option<f64>, // 0.0 - 1.0
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OutcomeType {
    Success,
    PartialSuccess,
    Neutral,
    PartialFailure,
    Failure,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FinancialImpact {
    pub revenue_change: f64,
    pub cost_change: f64,
    pub net_impact: f64,
    pub impact_duration_days: u32,
}

// ── Goal Tracking ────────────────────────────────────────────────────────────

/// Tracks user goals and progress for AGI planning capability
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GoalRecord {
    pub goal_id: String,
    pub worker_id: String,
    pub goal_type: GoalType,
    pub description: String,
    pub target_value: f64,
    pub current_value: f64,
    pub unit: String,
    pub deadline: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub milestones: Vec<Milestone>,
    pub obstacles: Vec<Obstacle>,
    pub status: GoalStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GoalType {
    SavingsTarget,
    RevenueGrowth,
    DebtReduction,
    AssetAcquisition,
    BusinessExpansion,
    SkillDevelopment,
    MarketEntry,
    Custom(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Milestone {
    pub name: String,
    pub target_value: f64,
    pub achieved: bool,
    pub achieved_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Obstacle {
    pub description: String,
    pub severity: f64, // 0.0 - 1.0
    pub identified_at: DateTime<Utc>,
    pub resolved: bool,
    pub resolution: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GoalStatus {
    Active,
    Paused,
    Achieved,
    Abandoned,
    Revised,
}

// ── Environmental Context ────────────────────────────────────────────────────

/// Environmental context for richer training data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvironmentalContext {
    pub timestamp: DateTime<Utc>,
    pub region: String,
    pub weather: Option<WeatherContext>,
    pub economic_indicators: Option<EconomicContext>,
    pub infrastructure: Option<InfrastructureContext>,
    pub regulatory: Option<RegulatoryContext>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WeatherContext {
    pub condition: String,
    pub temperature_celsius: f64,
    pub rainfall_mm: Option<f64>,
    pub season: String,
    pub agricultural_impact: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EconomicContext {
    pub inflation_rate: Option<f64>,
    pub exchange_rate_usd: Option<f64>,
    pub fuel_price_per_liter: Option<f64>,
    pub mobile_money_transaction_volume: Option<f64>,
    pub market_confidence_index: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InfrastructureContext {
    pub internet_quality: String,
    pub power_reliability: String,
    pub road_accessibility: String,
    pub mobile_network_quality: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegulatoryContext {
    pub recent_policy_changes: Vec<String>,
    pub tax_changes: Vec<String>,
    pub trade_restrictions: Vec<String>,
}

// ── Causal Chain ─────────────────────────────────────────────────────────────

/// Records causal chains for AGI reasoning training
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CausalChain {
    pub chain_id: String,
    pub root_event: String,
    pub events: Vec<CausalEvent>,
    pub final_outcome: String,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CausalEvent {
    pub event_id: String,
    pub description: String,
    pub timestamp: DateTime<Utc>,
    pub event_type: String,
    pub caused_by: Option<String>, // previous event_id
    pub led_to: Option<String>,    // next event_id
}

// ── Training Data Export ─────────────────────────────────────────────────────

/// Format for exporting training data (input-output pairs for fine-tuning)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrainingExample {
    /// Unique example ID
    pub example_id: String,
    /// Source trace/decision ID
    pub source_id: String,
    /// Training format
    pub format: TrainingFormat,
    /// System prompt (instruction context)
    pub system: String,
    /// User input (the situation/question)
    pub input: String,
    /// Expected output (the expert decision/reasoning)
    pub output: String,
    /// Metadata for filtering/curation
    pub metadata: TrainingMetadata,
    /// Quality score (0.0 - 1.0) for data curation
    pub quality_score: f64,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TrainingFormat {
    /// Standard instruction-following format
    Instruction,
    /// Multi-turn conversation format
    Conversation,
    /// Chain-of-thought reasoning format
    ChainOfThought,
    /// Decision-making with context format
    DecisionMaking,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrainingMetadata {
    pub worker_type: Option<String>,
    pub decision_type: Option<String>,
    pub region: Option<String>,
    pub outcome_quality: Option<OutcomeType>,
    pub has_social_context: bool,
    pub has_market_context: bool,
    pub has_causal_chain: bool,
    pub tags: Vec<String>,
}

// ── Export Utilities ─────────────────────────────────────────────────────────

/// Export a decision outcome as a training example
pub fn export_decision_as_training(
    decision: &DecisionOutcome,
    system_prompt: &str,
) -> TrainingExample {
    let input = format!(
        "Worker type: {:?}\nContext: {}\nMarket: {}\nFinancial state: {}\nQuestion: What should the worker do?",
        decision.decision_type,
        serde_json::to_string(&decision.context.input_features).unwrap_or_default(),
        decision
            .context
            .market_snapshot
            .as_ref()
            .map(|m| serde_json::to_string(m).unwrap_or_default())
            .unwrap_or_else(|| "N/A".to_string()),
        decision
            .context
            .financial_state
            .as_ref()
            .map(|f| serde_json::to_string(f).unwrap_or_default())
            .unwrap_or_else(|| "N/A".to_string()),
    );

    let output = format!(
        "Recommendation: {}\nConfidence: {}\nOutcome: {}",
        decision.recommendation,
        decision.confidence_at_decision,
        decision
            .outcome
            .as_ref()
            .map(|o| serde_json::to_string(&o.outcome_type).unwrap_or_default())
            .unwrap_or_else(|| "Pending".to_string()),
    );

    let quality = if decision.outcome.is_some() {
        match &decision.outcome.as_ref().unwrap().outcome_type {
            OutcomeType::Success => 0.95,
            OutcomeType::PartialSuccess => 0.8,
            OutcomeType::Neutral => 0.6,
            OutcomeType::PartialFailure => 0.4,
            OutcomeType::Failure => 0.2,
            OutcomeType::Unknown => 0.5,
        }
    } else {
        0.5
    };

    TrainingExample {
        example_id: Uuid::new_v4().to_string(),
        source_id: decision.decision_id.clone(),
        format: TrainingFormat::DecisionMaking,
        system: system_prompt.to_string(),
        input,
        output,
        metadata: TrainingMetadata {
            worker_type: None,
            decision_type: Some(format!("{:?}", decision.decision_type)),
            region: decision
                .context
                .market_snapshot
                .as_ref()
                .map(|m| m.region.clone()),
            outcome_quality: decision.outcome.as_ref().map(|o| o.outcome_type.clone()),
            has_social_context: decision.context.social_context.is_some(),
            has_market_context: decision.context.market_snapshot.is_some(),
            has_causal_chain: false,
            tags: vec![],
        },
        quality_score: quality,
        created_at: Utc::now(),
    }
}

/// Export training data as JSONL format (one JSON object per line)
pub fn export_training_jsonl(examples: &[TrainingExample]) -> String {
    examples
        .iter()
        .filter_map(|ex| serde_json::to_string(ex).ok())
        .collect::<Vec<_>>()
        .join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decision_outcome_serialization() {
        let decision = DecisionOutcome {
            decision_id: "d-001".to_string(),
            trace_id: "t-001".to_string(),
            session_id: "s-001".to_string(),
            worker_id: "w-001".to_string(),
            decision_type: DecisionType::CreditApproval,
            context: DecisionContext {
                input_features: serde_json::json!({"income": 15000, "months_active": 6}),
                market_snapshot: None,
                financial_state: None,
                social_context: None,
            },
            recommendation: "Approve KES 10,000 loan".to_string(),
            action_taken: None,
            outcome: None,
            confidence_at_decision: 0.82,
            timestamp: Utc::now(),
        };

        let json = serde_json::to_string(&decision).unwrap();
        assert!(json.contains("CreditApproval"));
        assert!(json.contains("d-001"));
    }

    #[test]
    fn test_goal_record_serialization() {
        let goal = GoalRecord {
            goal_id: "g-001".to_string(),
            worker_id: "w-001".to_string(),
            goal_type: GoalType::SavingsTarget,
            description: "Save for motorcycle".to_string(),
            target_value: 80000.0,
            current_value: 25000.0,
            unit: "KES".to_string(),
            deadline: None,
            created_at: Utc::now(),
            milestones: vec![Milestone {
                name: "25% saved".to_string(),
                target_value: 20000.0,
                achieved: true,
                achieved_at: None,
            }],
            obstacles: vec![],
            status: GoalStatus::Active,
        };

        let json = serde_json::to_string(&goal).unwrap();
        assert!(json.contains("SavingsTarget"));
    }

    #[test]
    fn test_training_export() {
        let decision = DecisionOutcome {
            decision_id: "d-002".to_string(),
            trace_id: "t-002".to_string(),
            session_id: "s-002".to_string(),
            worker_id: "w-002".to_string(),
            decision_type: DecisionType::ProductRecommendation,
            context: DecisionContext {
                input_features: serde_json::json!({"product": "tomatoes", "demand": "high"}),
                market_snapshot: None,
                financial_state: None,
                social_context: None,
            },
            recommendation: "Increase tomato stock by 30%".to_string(),
            action_taken: Some("Increased stock".to_string()),
            outcome: Some(OutcomeRecord {
                recorded_at: Utc::now(),
                outcome_type: OutcomeType::Success,
                financial_impact: Some(FinancialImpact {
                    revenue_change: 500.0,
                    cost_change: 200.0,
                    net_impact: 300.0,
                    impact_duration_days: 7,
                }),
                time_to_outcome_days: Some(7),
                unexpected_factors: vec![],
                user_satisfaction: Some(0.9),
            }),
            confidence_at_decision: 0.75,
            timestamp: Utc::now(),
        };

        let example = export_decision_as_training(&decision, "You are a business advisor.");
        assert_eq!(example.format as u8, TrainingFormat::DecisionMaking as u8);
        assert!(example.quality_score > 0.8); // Success outcome
    }
}
