//! ScenarioModeler — Counterfactual simulation engine for policymakers
//!
//! Monte Carlo agent-based model calibrated against real Angavu data.
//! Answers "what if?" questions about the informal economy:
//!
//! - "What if county market levies were reduced by 50%?"
//! - "What if M-Pesa withdrawal fees were capped at KSh 10?"
//! - "What if Fuliza interest rates doubled?"
//! - "What if a new wholesale market opened in Eastlands?"
//!
//! Runs agent-based simulations over anonymized worker archetypes,
//! calibrated against real aggregate data from other Angavu tools.

use anyhow::{anyhow, Result};
use chrono::{DateTime, NaiveDate, Utc};
use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use crate::db::DatabaseConnections;

// ─────────────────────────────────────────────────────────────────────
// Worker Type & Domain Enums
// ─────────────────────────────────────────────────────────────────────

/// Worker archetypes in the informal economy.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum WorkerType {
    MamaMboga,
    BodaBoda,
    MitiMba,
    Fundi,
    JuaKali,
    HouseHelp,
    FarmWorker,
    Other,
}

/// Income bracket classification.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum IncomeBracket {
    Bottom20,
    LowerMiddle,
    Middle,
    UpperMiddle,
    Top20,
}

/// Gender classification.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum Gender {
    Male,
    Female,
    Other,
}

/// Language for policy briefs.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum Language {
    English,
    Swahili,
}

/// OODA signal payload emitted by ScenarioModeler.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OodaSignal {
    pub source: String,
    pub signal_type: String,
    pub payload: serde_json::Value,
    pub timestamp: DateTime<Utc>,
}

/// Date range for baseline or analysis periods.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DateRange {
    pub start: NaiveDate,
    pub end: NaiveDate,
}

// ─────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────

/// Top-level configuration for the scenario modeler.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScenarioConfig {
    /// Monte Carlo iterations per scenario run (default: 1000).
    pub default_simulation_runs: u32,
    /// Synthetic agents per worker type cohort.
    pub max_agents_per_cohort: u32,
    /// Confidence level for confidence intervals (e.g., 0.95).
    pub confidence_level: f64,
    /// Maximum scenario duration in days.
    pub max_scenario_duration_days: u32,
}

impl Default for ScenarioConfig {
    fn default() -> Self {
        Self {
            default_simulation_runs: 1000,
            max_agents_per_cohort: 500,
            confidence_level: 0.95,
            max_scenario_duration_days: 365,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Scenario Definition
// ─────────────────────────────────────────────────────────────────────

/// A complete scenario definition.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Scenario {
    pub id: Uuid,
    pub name: String,
    pub description: String,
    pub created_by: String,
    pub baseline_period: DateRange,
    pub interventions: Vec<Intervention>,
    pub target_cohorts: Vec<CohortFilter>,
    pub simulation_days: u32,
    pub monte_carlo_runs: u32,
    pub status: ScenarioStatus,
    pub created_at: DateTime<Utc>,
}

/// A single policy intervention within a scenario.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Intervention {
    pub name: String,
    pub target_variable: InterventionTarget,
    pub change_type: ChangeType,
    /// Day of simulation to apply the intervention.
    pub start_day: u32,
    /// Duration in days; `None` means permanent.
    pub duration_days: Option<u32>,
}

/// The target economic variable for an intervention.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum InterventionTarget {
    MPesaWithdrawalFee {
        new_fee_pct: f64,
    },
    MarketLevy {
        region: String,
        new_daily_levy: f64,
    },
    FulizaInterestRate {
        new_daily_rate_pct: f64,
    },
    WholesaleMarketAccess {
        region: String,
        distance_reduction_pct: f64,
    },
    SchoolFeeStructure {
        spread_to_months: u8,
    },
    FuelPrice {
        new_price_per_litre: f64,
    },
    SupplierCreditTerms {
        new_credit_days: u32,
    },
    Custom {
        variable_name: String,
        new_value: f64,
    },
}

/// How the intervention modifies the target variable.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ChangeType {
    /// Set to this exact value.
    Absolute(f64),
    /// Percentage change (e.g., +20.0 or -50.0).
    RelativePct(f64),
    /// Enforce a minimum floor.
    Floor(f64),
    /// Enforce a maximum cap.
    Cap(f64),
}

/// Current status of a scenario.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ScenarioStatus {
    Draft,
    Running { progress_pct: u8 },
    Completed,
    Failed { error: String },
}

// ─────────────────────────────────────────────────────────────────────
// Cohort & Agent Definitions
// ─────────────────────────────────────────────────────────────────────

/// Filter for selecting worker cohorts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CohortFilter {
    pub region: Option<String>,
    pub worker_type: Option<WorkerType>,
    pub income_bracket: Option<IncomeBracket>,
    pub gender: Option<Gender>,
    pub business_age_months_min: Option<u32>,
}

/// A synthetic agent used in the agent-based model.
///
/// Agents are calibrated against real aggregate data from Angavu tools.
/// Each agent represents a statistical archetype of an informal worker.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyntheticAgent {
    pub agent_id: u32,
    pub worker_type: WorkerType,
    pub region: String,
    pub gender: Gender,
    pub income_bracket: IncomeBracket,
    pub business_age_months: u32,

    // Economic state
    pub daily_profit: f64,
    pub daily_revenue: f64,
    pub daily_costs: f64,
    pub savings_balance: f64,
    pub debt_balance: f64,
    pub monthly_income: f64,

    // Behavioral parameters (calibrated from real data)
    pub savings_rate: f64,           // Fraction of profit saved
    pub spoilage_rate: f64,          // Fraction of stock lost to spoilage
    pub transport_cost_pct: f64,     // Transport as % of revenue
    pub market_levy_daily: f64,      // Daily market levy in KES
    pub mpesa_fee_pct: f64,          // M-Pesa withdrawal fee %
    pub fuliza_daily_rate_pct: f64,  // Fuliza daily interest rate %
    pub fuliza_usage_probability: f64, // Probability of using Fuliza on a given day
    pub supplier_credit_days: u32,   // Average credit terms from suppliers
    pub customer_count: u32,         // Number of regular customers
    pub price_markup_pct: f64,       // Markup over wholesale price

    // State flags
    pub is_active: bool,             // Still in business?
    pub days_below_poverty: u32,     // Consecutive days below poverty line
}

/// Aggregate metrics computed from a simulation run.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AggregateMetrics {
    pub avg_daily_profit: f64,
    pub avg_monthly_income: f64,
    pub avg_savings_rate: f64,
    pub avg_debt_to_income: f64,
    pub avg_spoilage_loss: f64,
    pub avg_transport_cost: f64,
    pub business_survival_rate: f64,
    pub credit_access_rate: f64,
    pub food_security_index: f64,
}

/// Impact metrics comparing baseline vs. counterfactual.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImpactMetrics {
    pub profit_change_pct: f64,
    pub income_change_pct: f64,
    pub savings_change_pct: f64,
    pub debt_change_pct: f64,
    pub survival_rate_change_pct: f64,
    pub workers_lifted_above_poverty_line: u32,
    pub aggregate_annual_savings_kes: f64,
    pub cost_to_implement_kes: Option<f64>,
    pub roi_ratio: Option<f64>,
}

/// Confidence interval bounds.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfidenceInterval {
    pub lower: f64,
    pub upper: f64,
    pub point_estimate: f64,
}

/// Collection of confidence intervals for all impact metrics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImpactCICollections {
    pub profit_change_ci: ConfidenceInterval,
    pub income_change_ci: ConfidenceInterval,
    pub savings_change_ci: ConfidenceInterval,
    pub debt_change_ci: ConfidenceInterval,
    pub survival_rate_change_ci: ConfidenceInterval,
    pub workers_lifted_ci: ConfidenceInterval,
    pub annual_savings_ci: ConfidenceInterval,
}

/// A single agent's trajectory over the simulation period.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTrajectory {
    pub agent_id: u32,
    pub worker_type: WorkerType,
    pub region: String,
    pub daily_profits: Vec<f64>,
    pub daily_savings: Vec<f64>,
    pub daily_debt: Vec<f64>,
    pub is_active_per_day: Vec<bool>,
}

// ─────────────────────────────────────────────────────────────────────
// Scenario Results
// ─────────────────────────────────────────────────────────────────────

/// Complete result of a scenario simulation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScenarioResult {
    pub scenario_id: Uuid,
    pub baseline: AggregateMetrics,
    pub counterfactual: AggregateMetrics,
    pub impact: ImpactMetrics,
    pub confidence_intervals: ImpactCICollections,
    pub agent_trajectories: Option<Vec<AgentTrajectory>>,
    pub computed_at: DateTime<Utc>,
}

/// Side-by-side comparison of multiple scenarios.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScenarioComparison {
    pub scenario_ids: Vec<Uuid>,
    pub results: Vec<ScenarioResult>,
    pub ranking: Vec<ScenarioRanking>,
    pub recommended_scenario: Uuid,
    pub generated_at: DateTime<Utc>,
}

/// Ranking entry for scenario comparison.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScenarioRanking {
    pub scenario_id: Uuid,
    pub scenario_name: String,
    pub composite_score: f64,
    pub roi_ratio: Option<f64>,
    pub workers_lifted: u32,
}

/// Policy brief generated from scenario results.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyBrief {
    pub scenario_id: Uuid,
    pub title: String,
    pub executive_summary: String,
    pub key_findings: Vec<String>,
    pub methodology_note: String,
    pub recommendations: Vec<String>,
    pub caveats: Vec<String>,
    pub language: Language,
    pub generated_at: DateTime<Utc>,
}

/// Progress update during scenario execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScenarioProgress {
    pub scenario_id: Uuid,
    pub phase: String,
    pub runs_completed: u32,
    pub total_runs: u32,
    pub progress_pct: u8,
    pub estimated_remaining_secs: u64,
}

/// Sensitivity analysis result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SensitivityResult {
    pub scenario_id: Uuid,
    pub target_variable: String,
    pub variation_range: (f64, f64),
    pub steps: Vec<SensitivityStep>,
    pub generated_at: DateTime<Utc>,
}

/// A single step in a sensitivity analysis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SensitivityStep {
    pub input_value: f64,
    pub profit_change_pct: f64,
    pub income_change_pct: f64,
    pub survival_rate_change_pct: f64,
    pub workers_lifted: u32,
}

// ─────────────────────────────────────────────────────────────────────
// ScenarioModeler
// ─────────────────────────────────────────────────────────────────────

/// Counterfactual simulation engine for policymakers.
///
/// Uses Monte Carlo agent-based modeling to simulate "what if?" scenarios
/// over anonymized worker archetypes calibrated against real Angavu data.
pub struct ScenarioModeler {
    db: DatabaseConnections,
    config: ScenarioConfig,
    /// Seeded RNG for reproducible simulations.
    rng: StdRng,
}

impl ScenarioModeler {
    /// Create a new ScenarioModeler with default configuration.
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            config: ScenarioConfig::default(),
            rng: StdRng::seed_from_u64(42),
        }
    }

    /// Create with custom configuration.
    pub fn with_config(db: DatabaseConnections, config: ScenarioConfig) -> Self {
        Self {
            db,
            config,
            rng: StdRng::seed_from_u64(42),
        }
    }

    /// Create with a specific RNG seed for reproducibility.
    pub fn with_seed(db: DatabaseConnections, config: ScenarioConfig, seed: u64) -> Self {
        Self {
            db,
            config,
            rng: StdRng::seed_from_u64(seed),
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Core Public API
    // ─────────────────────────────────────────────────────────────────

    /// Create a new scenario definition (does not run yet).
    ///
    /// Persists the scenario to PostgreSQL and returns its UUID.
    pub async fn create_scenario(&self, mut scenario: Scenario) -> Result<Uuid> {
        if scenario.id == Uuid::nil() {
            scenario.id = Uuid::new_v4();
        }
        scenario.status = ScenarioStatus::Draft;
        scenario.created_at = Utc::now();

        // Validate
        if scenario.interventions.is_empty() {
            return Err(anyhow!("Scenario must have at least one intervention"));
        }
        if scenario.target_cohorts.is_empty() {
            return Err(anyhow!("Scenario must have at least one target cohort"));
        }
        if scenario.simulation_days == 0 || scenario.simulation_days > self.config.max_scenario_duration_days {
            return Err(anyhow!(
                "Simulation days must be between 1 and {}",
                self.config.max_scenario_duration_days
            ));
        }
        if scenario.monte_carlo_runs == 0 {
            scenario.monte_carlo_runs = self.config.default_simulation_runs;
        }

        // Persist to PostgreSQL
        sqlx::query(
            r#"
            INSERT INTO scenarios (id, name, description, created_by,
                baseline_start, baseline_end, interventions, target_cohorts,
                simulation_days, monte_carlo_runs, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'draft')
            "#,
        )
        .bind(scenario.id)
        .bind(&scenario.name)
        .bind(&scenario.description)
        .bind(&scenario.created_by)
        .bind(scenario.baseline_period.start)
        .bind(scenario.baseline_period.end)
        .bind(serde_json::to_string(&scenario.interventions)?)
        .bind(serde_json::to_string(&scenario.target_cohorts)?)
        .bind(scenario.simulation_days as i32)
        .bind(scenario.monte_carlo_runs as i32)
        .execute(&self.db.postgres)
        .await?;

        // Cache in Redis
        let mut redis = self.db.redis.clone();
        let _: () = redis::cmd("SET")
            .arg(format!("scenario:status:{}", scenario.id))
            .arg(serde_json::to_string(&scenario.status)?)
            .arg("EX")
            .arg(3600)
            .query_async(&mut redis)
            .await
            .unwrap_or(());

        Ok(scenario.id)
    }

    /// Execute a scenario: runs Monte Carlo simulation with agent-based model.
    ///
    /// 1. Loads scenario definition from PostgreSQL.
    /// 2. Generates synthetic agents calibrated to real aggregate data.
    /// 3. Runs N Monte Carlo iterations.
    /// 4. Computes aggregate metrics and confidence intervals.
    /// 5. Stores results and emits OODA signal.
    pub async fn run_scenario(&self, scenario_id: Uuid) -> Result<ScenarioResult> {
        let scenario = self.load_scenario(scenario_id).await?;
        self.execute_simulation(scenario, None).await
    }

    /// Run scenario and stream progress updates via a channel.
    pub async fn run_scenario_with_progress(
        &self,
        scenario_id: Uuid,
        progress_tx: tokio::sync::mpsc::Sender<ScenarioProgress>,
    ) -> Result<ScenarioResult> {
        let scenario = self.load_scenario(scenario_id).await?;
        self.execute_simulation(scenario, Some(progress_tx)).await
    }

    /// Compare multiple scenarios side by side.
    ///
    /// Runs each scenario (if not already completed) and produces a ranked comparison.
    pub async fn compare_scenarios(
        &self,
        scenario_ids: Vec<Uuid>,
    ) -> Result<ScenarioComparison> {
        if scenario_ids.len() < 2 {
            return Err(anyhow!("Need at least 2 scenarios to compare"));
        }

        let mut results = Vec::new();
        for &sid in &scenario_ids {
            // Check Redis cache first
            let cached = self.get_cached_result(sid).await;
            let result = match cached {
                Some(r) => r,
                None => self.run_scenario(sid).await?,
            };
            results.push(result);
        }

        // Rank by composite score: weighted combination of impact metrics
        let mut ranking: Vec<ScenarioRanking> = results
            .iter()
            .zip(scenario_ids.iter())
            .map(|(r, &sid)| {
                let composite = Self::compute_composite_score(&r.impact);
                ScenarioRanking {
                    scenario_id: sid,
                    scenario_name: sid.to_string(), // Would resolve from DB
                    composite_score: composite,
                    roi_ratio: r.impact.roi_ratio,
                    workers_lifted: r.impact.workers_lifted_above_poverty_line,
                }
            })
            .collect();

        ranking.sort_by(|a, b| {
            b.composite_score
                .partial_cmp(&a.composite_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        let recommended = ranking
            .first()
            .map(|r| r.scenario_id)
            .unwrap_or(scenario_ids[0]);

        Ok(ScenarioComparison {
            scenario_ids,
            results,
            ranking,
            recommended_scenario: recommended,
            generated_at: Utc::now(),
        })
    }

    /// Generate a policy brief from scenario results.
    ///
    /// Produces a human-readable summary suitable for decision-makers.
    pub async fn generate_policy_brief(
        &self,
        scenario_id: Uuid,
        language: Language,
    ) -> Result<PolicyBrief> {
        let scenario = self.load_scenario(scenario_id).await?;
        let result = self.get_or_run_result(scenario_id, &scenario).await?;

        let brief = match language {
            Language::English => self.build_english_brief(&scenario, &result),
            Language::Swahili => self.build_swahili_brief(&scenario, &result),
        };

        Ok(brief)
    }

    /// Sensitivity analysis: how does the outcome change when varying one input?
    ///
    /// Runs the scenario multiple times, each time varying the specified
    /// intervention parameter across the given range.
    pub async fn sensitivity_analysis(
        &self,
        scenario_id: Uuid,
        target_variable: String,
        variation_range: (f64, f64),
        steps: u32,
    ) -> Result<SensitivityResult> {
        let scenario = self.load_scenario(scenario_id).await?;
        let step_size = (variation_range.1 - variation_range.0) / steps as f64;

        let mut sensitivity_steps = Vec::new();

        for i in 0..=steps {
            let input_value = variation_range.0 + step_size * i as f64;

            // Clone scenario and modify the target intervention
            let mut modified = scenario.clone();
            for intervention in &mut modified.interventions {
                Self::apply_sensitivity_variation(
                    &mut intervention.target_variable,
                    &intervention.change_type,
                    &target_variable,
                    input_value,
                );
            }

            // Run a reduced simulation (fewer iterations for speed)
            let mut reduced_config = self.config.clone();
            reduced_config.default_simulation_runs =
                (self.config.default_simulation_runs / 5).max(100);

            let modeler = ScenarioModeler::with_config(self.db.clone(), reduced_config);
            let result = modeler.execute_simulation(modified, None).await?;

            sensitivity_steps.push(SensitivityStep {
                input_value,
                profit_change_pct: result.impact.profit_change_pct,
                income_change_pct: result.impact.income_change_pct,
                survival_rate_change_pct: result.impact.survival_rate_change_pct,
                workers_lifted: result.impact.workers_lifted_above_poverty_line,
            });
        }

        Ok(SensitivityResult {
            scenario_id,
            target_variable,
            variation_range,
            steps: sensitivity_steps,
            generated_at: Utc::now(),
        })
    }

    /// Define a scenario — convenience builder for common policy shocks.
    ///
    /// Returns a `Scenario` struct ready for `create_scenario()`.
    pub fn define_scenario(
        &self,
        name: &str,
        description: &str,
        created_by: &str,
        cohort: CohortFilter,
        interventions: Vec<Intervention>,
        simulation_days: u32,
    ) -> Scenario {
        let now = Utc::now();
        let baseline_end = now.date_naive();
        let baseline_start = baseline_end - chrono::Duration::days(90);

        Scenario {
            id: Uuid::new_v4(),
            name: name.to_string(),
            description: description.to_string(),
            created_by: created_by.to_string(),
            baseline_period: DateRange {
                start: baseline_start,
                end: baseline_end,
            },
            interventions,
            target_cohorts: vec![cohort],
            simulation_days,
            monte_carlo_runs: self.config.default_simulation_runs,
            status: ScenarioStatus::Draft,
            created_at: now,
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Simulation Engine
    // ─────────────────────────────────────────────────────────────────

    /// Core simulation orchestrator.
    async fn execute_simulation(
        &self,
        scenario: Scenario,
        progress_tx: Option<tokio::sync::mpsc::Sender<ScenarioProgress>>,
    ) -> Result<ScenarioResult> {
        // Update status to Running
        self.update_status(scenario.id, ScenarioStatus::Running { progress_pct: 0 })
            .await?;

        let total_runs = scenario.monte_carlo_runs;

        // Phase 1: Generate synthetic agents from real data
        let mut all_agents = Vec::new();
        for cohort in &scenario.target_cohorts {
            let agents = self.load_agents(cohort).await?;
            all_agents.extend(agents);
        }

        if all_agents.is_empty() {
            let err = "No agents generated for target cohorts";
            self.update_status(
                scenario.id,
                ScenarioStatus::Failed {
                    error: err.to_string(),
                },
            )
            .await?;
            return Err(anyhow!(err));
        }

        // Phase 2: Monte Carlo simulation
        let mut baseline_runs: Vec<AggregateMetrics> = Vec::with_capacity(total_runs as usize);
        let mut counterfactual_runs: Vec<AggregateMetrics> = Vec::with_capacity(total_runs as usize);
        let mut rng = StdRng::seed_from_u64(42); // Deterministic for reproducibility

        for run_idx in 0..total_runs {
            // Baseline: agents evolve without intervention
            let mut baseline_agents = all_agents.clone();
            let baseline_metrics = Self::simulate_run_static(
                &mut rng,
                &mut baseline_agents,
                &[],
                scenario.simulation_days,
            );
            baseline_runs.push(baseline_metrics);

            // Counterfactual: agents evolve WITH intervention
            let mut cf_agents = all_agents.clone();
            let cf_metrics = Self::simulate_run_static(
                &mut rng,
                &mut cf_agents,
                &scenario.interventions,
                scenario.simulation_days,
            );
            counterfactual_runs.push(cf_metrics);

            // Progress reporting
            if run_idx % 100 == 0 || run_idx == total_runs - 1 {
                let pct = ((run_idx + 1) as f64 / total_runs as f64 * 100.0) as u8;
                self.update_status(scenario.id, ScenarioStatus::Running { progress_pct: pct })
                    .await?;

                if let Some(ref tx) = progress_tx {
                    let _ = tx
                        .send(ScenarioProgress {
                            scenario_id: scenario.id,
                            phase: "monte_carlo".to_string(),
                            runs_completed: run_idx + 1,
                            total_runs,
                            progress_pct: pct,
                            estimated_remaining_secs: ((total_runs - run_idx - 1) as f64 * 0.05) as u64,
                        })
                        .await;
                }
            }
        }

        // Phase 3: Aggregate results
        let baseline_agg = Self::aggregate_metrics(&baseline_runs);
        let counterfactual_agg = Self::aggregate_metrics(&counterfactual_runs);
        let impact = Self::compute_impact(&baseline_agg, &counterfactual_agg, &all_agents);
        let ci = Self::compute_confidence_intervals(
            &baseline_runs,
            &counterfactual_runs,
            &all_agents,
            self.config.confidence_level,
        );

        let result = ScenarioResult {
            scenario_id: scenario.id,
            baseline: baseline_agg,
            counterfactual: counterfactual_agg,
            impact,
            confidence_intervals: ci,
            agent_trajectories: None, // Computed on demand to save memory
            computed_at: Utc::now(),
        };

        // Persist results
        self.store_result(&result).await?;

        // Update status
        self.update_status(scenario.id, ScenarioStatus::Completed)
            .await?;

        // Cache in Redis
        self.cache_result(scenario.id, &result).await;

        Ok(result)
    }

    /// Run one Monte Carlo iteration.
    ///
    /// Each agent evolves day-by-day. Interventions modify economic parameters
    /// on their scheduled start day. Agents can go bankrupt (exit the market).
    fn simulate_run_static(
        rng: &mut StdRng,
        agents: &mut Vec<SyntheticAgent>,
        interventions: &[Intervention],
        days: u32,
    ) -> AggregateMetrics {
        for day in 0..days {
            // Check if any intervention starts today
            let active_interventions: Vec<&Intervention> = interventions
                .iter()
                .filter(|iv| {
                    iv.start_day <= day
                        && iv
                            .duration_days
                            .map_or(true, |d| day < iv.start_day + d)
                })
                .collect();

            for agent in agents.iter_mut() {
                if !agent.is_active {
                    continue;
                }

                // Apply active interventions to agent state
                for intervention in &active_interventions {
                    Self::apply_intervention(agent, intervention);
                }

                // Daily economic simulation
                Self::simulate_agent_day(rng, agent, day);
            }
        }

        Self::compute_run_metrics(agents)
    }

    /// Simulate one day for a single agent.
    ///
    /// Models daily revenue, costs, savings, debt, and business survival.
    fn simulate_agent_day(rng: &mut StdRng, agent: &mut SyntheticAgent, day: u32) {
        // Revenue with random daily variation (coefficient of variation ~0.3)
        let revenue_noise: f64 = rng.gen_range(0.7..1.3);
        let daily_revenue = agent.daily_revenue * revenue_noise;

        // Costs
        let spoilage_loss = daily_revenue * agent.spoilage_rate;
        let transport_cost = daily_revenue * agent.transport_cost_pct;
        let mpesa_fee = daily_revenue * agent.mpesa_fee_pct / 100.0;
        let market_levy = agent.market_levy_daily;
        let cost_of_goods = daily_revenue * (1.0 - agent.price_markup_pct / 100.0);

        let total_costs =
            cost_of_goods + spoilage_loss + transport_cost + mpesa_fee + market_levy;
        let daily_profit = daily_revenue - total_costs;

        // Update agent state
        agent.daily_profit = daily_profit;
        agent.monthly_income = (agent.monthly_income * 29.0 / 30.0)
            + (daily_profit * 30.0 / 30.0); // Exponential moving average

        // Savings behavior
        let savings_amount = if daily_profit > 0.0 {
            daily_profit * agent.savings_rate
        } else {
            0.0
        };
        agent.savings_balance += savings_amount;

        // Debt dynamics
        if daily_profit < 0.0 {
            // Draw from savings first
            let deficit = -daily_profit;
            if agent.savings_balance >= deficit {
                agent.savings_balance -= deficit;
            } else {
                let remaining = deficit - agent.savings_balance;
                agent.savings_balance = 0.0;

                // Fuliza usage (probabilistic)
                if rng.gen_bool(agent.fuliza_usage_probability.min(1.0)) {
                    agent.debt_balance += remaining;
                }
            }
        }

        // Fuliza interest accrual
        if agent.debt_balance > 0.0 {
            agent.debt_balance *= 1.0 + agent.fuliza_daily_rate_pct / 100.0;

            // Repay debt from surplus savings
            if agent.savings_balance > agent.debt_balance * 0.1 {
                let repayment = (agent.savings_balance * 0.3).min(agent.debt_balance);
                agent.savings_balance -= repayment;
                agent.debt_balance -= repayment;
            }
        }

        // Business survival check
        let poverty_line_daily = 135.0; // KES, approximate extreme poverty line
        if daily_profit < poverty_line_daily {
            agent.days_below_poverty += 1;
            // Probability of exiting increases with consecutive poor days
            let exit_prob = (agent.days_below_poverty as f64 / 180.0).min(0.1);
            if rng.gen_bool(exit_prob) {
                agent.is_active = false;
            }
        } else {
            agent.days_below_poverty = 0;
        }
    }

    /// Apply an intervention to a synthetic agent.
    fn apply_intervention(agent: &mut SyntheticAgent, intervention: &Intervention) {
        match &intervention.target_variable {
            InterventionTarget::MPesaWithdrawalFee { new_fee_pct } => {
                agent.mpesa_fee_pct = Self::apply_change(agent.mpesa_fee_pct, &intervention.change_type, *new_fee_pct);
            }
            InterventionTarget::MarketLevy {
                region,
                new_daily_levy,
            } => {
                if agent.region == *region {
                    agent.market_levy_daily = Self::apply_change(agent.market_levy_daily, &intervention.change_type, *new_daily_levy);
                }
            }
            InterventionTarget::FulizaInterestRate { new_daily_rate_pct } => {
                agent.fuliza_daily_rate_pct = Self::apply_change(agent.fuliza_daily_rate_pct, &intervention.change_type, *new_daily_rate_pct);
            }
            InterventionTarget::WholesaleMarketAccess {
                region,
                distance_reduction_pct,
            } => {
                if agent.region == *region {
                    // Reduce transport costs by the distance reduction
                    let reduction = distance_reduction_pct / 100.0;
                    agent.transport_cost_pct *= 1.0 - reduction;
                }
            }
            InterventionTarget::SchoolFeeStructure { spread_to_months: _ } => {
                // School fee spreading reduces monthly cost spikes
                // Approximate: reduces effective monthly burden by ~30%
                agent.daily_costs *= 0.97; // Small daily reduction
            }
            InterventionTarget::FuelPrice { new_price_per_litre } => {
                // Fuel price affects transport costs
                // Assume baseline fuel price of ~180 KES/litre
                let baseline_fuel = 180.0_f64;
                let fuel_change = (new_price_per_litre - baseline_fuel) / baseline_fuel;
                agent.transport_cost_pct *= 1.0 + fuel_change * 0.6; // 60% pass-through
            }
            InterventionTarget::SupplierCreditTerms { new_credit_days } => {
                agent.supplier_credit_days = *new_credit_days;
                // Better credit terms improve cash flow → slightly higher savings rate
                let credit_improvement = (*new_credit_days as f64) / (agent.supplier_credit_days.max(1) as f64);
                agent.savings_rate = (agent.savings_rate * credit_improvement.sqrt()).min(0.5);
            }
            InterventionTarget::Custom {
                variable_name,
                new_value,
            } => {
                // Custom interventions logged but not directly applied
                // In production, these would map to specific agent parameters
                tracing::debug!(
                    variable = %variable_name,
                    value = new_value,
                    "Custom intervention applied (placeholder)"
                );
            }
        }
    }

    /// Apply a change type transformation to a value.
    fn apply_change(current: f64, change_type: &ChangeType, target: f64) -> f64 {
        match change_type {
            ChangeType::Absolute(val) => *val,
            ChangeType::RelativePct(pct) => current * (1.0 + pct / 100.0),
            ChangeType::Floor(min) => current.max(*min),
            ChangeType::Cap(max) => current.min(*max),
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Agent Generation
    // ─────────────────────────────────────────────────────────────────

    /// Load calibrated synthetic agents from ClickHouse aggregate data.
    ///
    /// Generates agents whose statistical properties match real population
    /// distributions from the Angavu data pipeline.
    async fn load_agents(&self, cohort: &CohortFilter) -> Result<Vec<SyntheticAgent>> {
        let count = self.config.max_agents_per_cohort;
        let mut agents = Vec::with_capacity(count as usize);

        // Try to load calibration data from ClickHouse
        let calibration = self.load_calibration_data(cohort).await;

        let mut rng = StdRng::seed_from_u64(42);

        for i in 0..count {
            let worker_type = cohort
                .worker_type
                .clone()
                .unwrap_or_else(|| Self::random_worker_type(&mut rng));

            let region = cohort
                .region
                .clone()
                .unwrap_or_else(|| "Nairobi".to_string());

            // Base economic parameters by worker type
            let base_params = Self::worker_type_params(&worker_type);

            // Apply calibration offsets if available
            let (profit_mult, revenue_mult) = match &calibration {
                Some(cal) => (
                    cal.avg_profit_multiplier,
                    cal.avg_revenue_multiplier,
                ),
                None => (1.0, 1.0),
            };

            // Generate agent with natural variation
            let variation: f64 = rng.gen_range(0.6..1.4);
            let daily_revenue = base_params.daily_revenue * revenue_mult * variation;
            let daily_profit = base_params.daily_profit * profit_mult * variation;

            agents.push(SyntheticAgent {
                agent_id: i,
                worker_type: worker_type.clone(),
                region: region.clone(),
                gender: cohort.gender.clone().unwrap_or_else(|| {
                    if rng.gen_bool(0.55) {
                        Gender::Female
                    } else {
                        Gender::Male
                    }
                }),
                income_bracket: cohort.income_bracket.clone().unwrap_or_else(|| {
                    Self::random_income_bracket(&mut rng)
                }),
                business_age_months: cohort.business_age_months_min.unwrap_or_else(|| {
                    rng.gen_range(1..120)
                }),
                daily_profit,
                daily_revenue,
                daily_costs: daily_revenue - daily_profit,
                savings_balance: rng.gen_range(0.0..5000.0),
                debt_balance: if rng.gen_bool(0.3) {
                    rng.gen_range(0.0..10000.0)
                } else {
                    0.0
                },
                monthly_income: daily_profit * 26.0, // ~26 working days
                savings_rate: rng.gen_range(0.02..0.25),
                spoilage_rate: base_params.spoilage_rate * rng.gen_range(0.7..1.3),
                transport_cost_pct: base_params.transport_cost_pct * rng.gen_range(0.8..1.2),
                market_levy_daily: base_params.market_levy * rng.gen_range(0.8..1.2),
                mpesa_fee_pct: 1.0, // Standard M-Pesa withdrawal fee
                fuliza_daily_rate_pct: 1.0, // Standard Fuliza daily rate
                fuliza_usage_probability: base_params.fuliza_usage_prob * rng.gen_range(0.5..1.5),
                supplier_credit_days: base_params.credit_days,
                customer_count: base_params.customer_count + rng.gen_range(-10..20) as u32,
                price_markup_pct: base_params.markup_pct * rng.gen_range(0.8..1.2),
                is_active: true,
                days_below_poverty: 0,
            });
        }

        Ok(agents)
    }

    /// Base economic parameters for each worker type.
    ///
    /// These represent calibrated averages from Angavu aggregate data.
    fn worker_type_params(worker_type: &WorkerType) -> WorkerTypeParams {
        match worker_type {
            WorkerType::MamaMboga => WorkerTypeParams {
                daily_revenue: 3500.0,  // KES
                daily_profit: 800.0,
                spoilage_rate: 0.12,    // 12% spoilage
                transport_cost_pct: 0.08,
                market_levy: 100.0,     // Daily market levy
                fuliza_usage_prob: 0.4,
                credit_days: 7,
                customer_count: 50,
                markup_pct: 30.0,
            },
            WorkerType::BodaBoda => WorkerTypeParams {
                daily_revenue: 2800.0,
                daily_profit: 1200.0,
                spoilage_rate: 0.0,
                transport_cost_pct: 0.35, // Fuel is major cost
                market_levy: 50.0,
                fuliza_usage_prob: 0.5,
                credit_days: 0,
                customer_count: 30,
                markup_pct: 100.0, // Service, no goods
            },
            WorkerType::Fundi => WorkerTypeParams {
                daily_revenue: 4000.0,
                daily_profit: 2000.0,
                spoilage_rate: 0.02,
                transport_cost_pct: 0.10,
                market_levy: 0.0,
                fuliza_usage_prob: 0.2,
                credit_days: 14,
                customer_count: 15,
                markup_pct: 60.0,
            },
            WorkerType::JuaKali => WorkerTypeParams {
                daily_revenue: 3000.0,
                daily_profit: 1500.0,
                spoilage_rate: 0.05,
                transport_cost_pct: 0.12,
                market_levy: 80.0,
                fuliza_usage_prob: 0.35,
                credit_days: 10,
                customer_count: 20,
                markup_pct: 50.0,
            },
            WorkerType::MitiMba => WorkerTypeParams {
                daily_revenue: 5000.0,
                daily_profit: 1800.0,
                spoilage_rate: 0.08,
                transport_cost_pct: 0.15,
                market_levy: 120.0,
                fuliza_usage_prob: 0.25,
                credit_days: 21,
                customer_count: 40,
                markup_pct: 35.0,
            },
            WorkerType::HouseHelp => WorkerTypeParams {
                daily_revenue: 1200.0,
                daily_profit: 1100.0, // Nearly all income
                spoilage_rate: 0.0,
                transport_cost_pct: 0.10,
                market_levy: 0.0,
                fuliza_usage_prob: 0.6,
                credit_days: 0,
                customer_count: 1,
                markup_pct: 100.0, // Wages
            },
            WorkerType::FarmWorker => WorkerTypeParams {
                daily_revenue: 1500.0,
                daily_profit: 900.0,
                spoilage_rate: 0.10,
                transport_cost_pct: 0.05,
                market_levy: 0.0,
                fuliza_usage_prob: 0.45,
                credit_days: 30,
                customer_count: 5,
                markup_pct: 40.0,
            },
            WorkerType::Other => WorkerTypeParams {
                daily_revenue: 2500.0,
                daily_profit: 1000.0,
                spoilage_rate: 0.05,
                transport_cost_pct: 0.10,
                market_levy: 50.0,
                fuliza_usage_prob: 0.35,
                credit_days: 7,
                customer_count: 20,
                markup_pct: 40.0,
            },
        }
    }

    fn random_worker_type(rng: &mut StdRng) -> WorkerType {
        match rng.gen_range(0..8) {
            0 => WorkerType::MamaMboga,
            1 => WorkerType::BodaBoda,
            2 => WorkerType::MitiMba,
            3 => WorkerType::Fundi,
            4 => WorkerType::JuaKali,
            5 => WorkerType::HouseHelp,
            6 => WorkerType::FarmWorker,
            _ => WorkerType::Other,
        }
    }

    fn random_income_bracket(rng: &mut StdRng) -> IncomeBracket {
        match rng.gen_range(0..5) {
            0 => IncomeBracket::Bottom20,
            1 => IncomeBracket::LowerMiddle,
            2 => IncomeBracket::Middle,
            3 => IncomeBracket::UpperMiddle,
            _ => IncomeBracket::Top20,
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Metrics Computation
    // ─────────────────────────────────────────────────────────────────

    /// Compute aggregate metrics from a single Monte Carlo run.
    fn compute_run_metrics(agents: &[SyntheticAgent]) -> AggregateMetrics {
        let active: Vec<&SyntheticAgent> = agents.iter().filter(|a| a.is_active).collect();
        let total = agents.len() as f64;
        let active_count = active.len() as f64;

        if active_count == 0.0 {
            return AggregateMetrics {
                avg_daily_profit: 0.0,
                avg_monthly_income: 0.0,
                avg_savings_rate: 0.0,
                avg_debt_to_income: 0.0,
                avg_spoilage_loss: 0.0,
                avg_transport_cost: 0.0,
                business_survival_rate: 0.0,
                credit_access_rate: 0.0,
                food_security_index: 0.0,
            };
        }

        let avg_profit = active.iter().map(|a| a.daily_profit).sum::<f64>() / active_count;
        let avg_income = active.iter().map(|a| a.monthly_income).sum::<f64>() / active_count;
        let avg_savings_rate = active.iter().map(|a| a.savings_rate).sum::<f64>() / active_count;
        let avg_debt_to_income = active
            .iter()
            .map(|a| {
                if a.monthly_income > 0.0 {
                    a.debt_balance / a.monthly_income
                } else {
                    0.0
                }
            })
            .sum::<f64>()
            / active_count;
        let avg_spoilage = active.iter().map(|a| a.daily_revenue * a.spoilage_rate).sum::<f64>() / active_count;
        let avg_transport = active.iter().map(|a| a.daily_revenue * a.transport_cost_pct).sum::<f64>() / active_count;

        let survival_rate = active_count / total;
        let credit_access = active.iter().filter(|a| a.debt_balance > 0.0 || a.savings_balance > 1000.0).count() as f64 / active_count;

        // Food security: proxy based on income above poverty line
        let poverty_line_monthly = 4050.0; // KES (135/day × 30)
        let food_secure = active
            .iter()
            .filter(|a| a.monthly_income >= poverty_line_monthly)
            .count() as f64
            / active_count;

        AggregateMetrics {
            avg_daily_profit: avg_profit,
            avg_monthly_income: avg_income,
            avg_savings_rate,
            avg_debt_to_income: avg_debt_to_income,
            avg_spoilage_loss: avg_spoilage,
            avg_transport_cost: avg_transport,
            business_survival_rate: survival_rate,
            credit_access_rate: credit_access,
            food_security_index: food_secure,
        }
    }

    /// Aggregate multiple Monte Carlo runs into summary statistics.
    fn aggregate_metrics(runs: &[AggregateMetrics]) -> AggregateMetrics {
        let n = runs.len() as f64;
        if n == 0.0 {
            return AggregateMetrics {
                avg_daily_profit: 0.0,
                avg_monthly_income: 0.0,
                avg_savings_rate: 0.0,
                avg_debt_to_income: 0.0,
                avg_spoilage_loss: 0.0,
                avg_transport_cost: 0.0,
                business_survival_rate: 0.0,
                credit_access_rate: 0.0,
                food_security_index: 0.0,
            };
        }

        let mean = |f: fn(&AggregateMetrics) -> f64| -> f64 {
            runs.iter().map(f).sum::<f64>() / n
        };

        AggregateMetrics {
            avg_daily_profit: mean(|r| r.avg_daily_profit),
            avg_monthly_income: mean(|r| r.avg_monthly_income),
            avg_savings_rate: mean(|r| r.avg_savings_rate),
            avg_debt_to_income: mean(|r| r.avg_debt_to_income),
            avg_spoilage_loss: mean(|r| r.avg_spoilage_loss),
            avg_transport_cost: mean(|r| r.avg_transport_cost),
            business_survival_rate: mean(|r| r.business_survival_rate),
            credit_access_rate: mean(|r| r.credit_access_rate),
            food_security_index: mean(|r| r.food_security_index),
        }
    }

    /// Compute impact metrics comparing baseline vs. counterfactual.
    fn compute_impact(
        baseline: &AggregateMetrics,
        counterfactual: &AggregateMetrics,
        agents: &[SyntheticAgent],
    ) -> ImpactMetrics {
        let pct_change = |base: f64, cf: f64| -> f64 {
            if base.abs() < 1e-10 {
                0.0
            } else {
                (cf - base) / base.abs() * 100.0
            }
        };

        let profit_change = pct_change(baseline.avg_daily_profit, counterfactual.avg_daily_profit);
        let income_change = pct_change(baseline.avg_monthly_income, counterfactual.avg_monthly_income);
        let savings_change = pct_change(baseline.avg_savings_rate, counterfactual.avg_savings_rate);
        let debt_change = pct_change(baseline.avg_debt_to_income, counterfactual.avg_debt_to_income);
        let survival_change = pct_change(
            baseline.business_survival_rate,
            counterfactual.business_survival_rate,
        );

        // Estimate workers lifted above poverty line
        let poverty_line_monthly = 4050.0_f64;
        let baseline_below = agents
            .iter()
            .filter(|a| a.monthly_income < poverty_line_monthly)
            .count();
        let workers_lifted = ((baseline_below as f64 * (counterfactual.food_security_index - baseline.food_security_index)).max(0.0)) as u32;

        // Aggregate annual savings (all agents)
        let daily_savings_diff = counterfactual.avg_daily_profit - baseline.avg_daily_profit;
        let aggregate_annual = daily_savings_diff * 26.0 * 12.0 * agents.len() as f64;

        ImpactMetrics {
            profit_change_pct: profit_change,
            income_change_pct: income_change,
            savings_change_pct: savings_change,
            debt_change_pct: debt_change,
            survival_rate_change_pct: survival_change,
            workers_lifted_above_poverty_line: workers_lifted,
            aggregate_annual_savings_kes: aggregate_annual,
            cost_to_implement_kes: None,  // Set by caller if known
            roi_ratio: None,              // Computed when cost is known
        }
    }

    /// Compute confidence intervals from Monte Carlo run distributions.
    fn compute_confidence_intervals(
        baseline_runs: &[AggregateMetrics],
        counterfactual_runs: &[AggregateMetrics],
        agents: &[SyntheticAgent],
        confidence_level: f64,
    ) -> ImpactCICollections {
        let alpha = 1.0 - confidence_level;
        let lower_pct = alpha / 2.0;
        let upper_pct = 1.0 - alpha / 2.0;

        // Compute impact for each paired run
        let mut profit_changes = Vec::new();
        let mut income_changes = Vec::new();
        let mut savings_changes = Vec::new();
        let mut debt_changes = Vec::new();
        let mut survival_changes = Vec::new();

        for (b, c) in baseline_runs.iter().zip(counterfactual_runs.iter()) {
            let pct = |base: f64, cf: f64| -> f64 {
                if base.abs() < 1e-10 {
                    0.0
                } else {
                    (cf - base) / base.abs() * 100.0
                }
            };

            profit_changes.push(pct(b.avg_daily_profit, c.avg_daily_profit));
            income_changes.push(pct(b.avg_monthly_income, c.avg_monthly_income));
            savings_changes.push(pct(b.avg_savings_rate, c.avg_savings_rate));
            debt_changes.push(pct(b.avg_debt_to_income, c.avg_debt_to_income));
            survival_changes.push(pct(b.business_survival_rate, c.business_survival_rate));
        }

        let poverty_line_monthly = 4050.0_f64;
        let baseline_below = agents
            .iter()
            .filter(|a| a.monthly_income < poverty_line_monthly)
            .count() as f64;

        let workers_lifted_values: Vec<f64> = baseline_runs
            .iter()
            .zip(counterfactual_runs.iter())
            .map(|(b, c)| {
                (baseline_below * (c.food_security_index - b.food_security_index)).max(0.0)
            })
            .collect();

        let annual_savings_values: Vec<f64> = baseline_runs
            .iter()
            .zip(counterfactual_runs.iter())
            .map(|(b, c)| {
                (c.avg_daily_profit - b.avg_daily_profit) * 26.0 * 12.0 * agents.len() as f64
            })
            .collect();

        let ci = |values: &mut Vec<f64>| -> ConfidenceInterval {
            values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
            let n = values.len();
            let lower = values[(n as f64 * lower_pct) as usize];
            let upper = values[(n as f64 * upper_pct) as usize];
            let point = values.iter().sum::<f64>() / n as f64;
            ConfidenceInterval {
                lower,
                upper,
                point_estimate: point,
            }
        };

        ImpactCICollections {
            profit_change_ci: ci(&mut profit_changes),
            income_change_ci: ci(&mut income_changes),
            savings_change_ci: ci(&mut savings_changes),
            debt_change_ci: ci(&mut debt_changes),
            survival_rate_change_ci: ci(&mut survival_changes),
            workers_lifted_ci: ci(&mut workers_lifted_values.clone()),
            annual_savings_ci: ci(&mut annual_savings_values.clone()),
        }
    }

    /// Compute a composite score for ranking scenarios.
    fn compute_composite_score(impact: &ImpactMetrics) -> f64 {
        // Weighted combination of impact metrics
        let profit_score = impact.profit_change_pct.clamp(-100.0, 100.0) / 100.0 * 0.30;
        let income_score = impact.income_change_pct.clamp(-100.0, 100.0) / 100.0 * 0.25;
        let survival_score = impact.survival_rate_change_pct.clamp(-100.0, 100.0) / 100.0 * 0.25;
        let poverty_score = if impact.workers_lifted_above_poverty_line > 0 {
            (impact.workers_lifted_above_poverty_line as f64).ln() / 15.0
        } else {
            -0.1
        } * 0.20;

        (profit_score + income_score + survival_score + poverty_score).clamp(-1.0, 1.0)
    }

    // ─────────────────────────────────────────────────────────────────
    // Policy Brief Generation
    // ─────────────────────────────────────────────────────────────────

    fn build_english_brief(&self, scenario: &Scenario, result: &ScenarioResult) -> PolicyBrief {
        let impact = &result.impact;

        let title = format!("Policy Brief: {}", scenario.name);

        let executive_summary = format!(
            "This analysis simulates the impact of {} on {} informal workers over {} days using \
             Monte Carlo agent-based modeling ({} iterations). The primary intervention targets \
             {} with {}.",
            scenario.interventions.first().map(|i| i.name.as_str()).unwrap_or("policy change"),
            scenario.target_cohorts.len(),
            scenario.simulation_days,
            scenario.monte_carlo_runs,
            Self::describe_intervention_target(scenario.interventions.first()),
            Self::describe_change_type(scenario.interventions.first()),
        );

        let mut key_findings = Vec::new();

        if impact.profit_change_pct.abs() > 1.0 {
            let direction = if impact.profit_change_pct > 0.0 {
                "increase"
            } else {
                "decrease"
            };
            key_findings.push(format!(
                "Daily profits are projected to {} by {:.1}% (95% CI: {:.1}% to {:.1}%)",
                direction,
                impact.profit_change_pct,
                result.confidence_intervals.profit_change_ci.lower,
                result.confidence_intervals.profit_change_ci.upper,
            ));
        }

        if impact.workers_lifted_above_poverty_line > 0 {
            key_findings.push(format!(
                "An estimated {} workers would be lifted above the poverty line",
                Self::format_number(impact.workers_lifted_above_poverty_line),
            ));
        }

        if impact.aggregate_annual_savings_kes.abs() > 0.0 {
            key_findings.push(format!(
                "Aggregate annual economic benefit: KES {}",
                Self::format_kes(impact.aggregate_annual_savings_kes),
            ));
        }

        if let Some(roi) = impact.roi_ratio {
            key_findings.push(format!("Return on investment: {:.1}:1", roi));
        }

        key_findings.push(format!(
            "Business survival rate change: {:.1}%",
            impact.survival_rate_change_pct,
        ));

        let recommendations = Self::generate_recommendations(impact);

        let caveats = vec![
            "Simulations are based on aggregate statistical models, not individual predictions.".to_string(),
            "Results assume no confounding policy changes during the simulation period.".to_string(),
            "Agent behavioral parameters are calibrated to historical data and may not capture future shocks.".to_string(),
            "Confidence intervals reflect Monte Carlo variation, not model uncertainty.".to_string(),
        ];

        PolicyBrief {
            scenario_id: scenario.id,
            title,
            executive_summary,
            key_findings,
            methodology_note: "Monte Carlo agent-based simulation with synthetic worker archetypes \
                calibrated against Angavu aggregate data. Each iteration models daily economic \
                decisions (spending, saving, borrowing, business exit) for synthetic agents \
                representing informal workers."
                .to_string(),
            recommendations,
            caveats,
            language: Language::English,
            generated_at: Utc::now(),
        }
    }

    fn build_swahili_brief(&self, scenario: &Scenario, result: &ScenarioResult) -> PolicyBrief {
        let impact = &result.impact;

        let title = format!("Muhtasari wa Sera: {}", scenario.name);

        let executive_summary = format!(
            "Uchambuzi huu unaiga athari za {} kwa wafanyakazi wasio rasmi {} kwa siku {} \
             kwa kutumia mfano wa Monte Carlo (marudio {}). Uingiliaji kati mkuu \
             unalenga {}.",
            scenario.interventions.first().map(|i| i.name.as_str()).unwrap_or("mabadiliko ya sera"),
            scenario.target_cohorts.len(),
            scenario.simulation_days,
            scenario.monte_carlo_runs,
            Self::describe_intervention_target(scenario.interventions.first()),
        );

        let mut key_findings = Vec::new();

        if impact.profit_change_pct.abs() > 1.0 {
            let direction = if impact.profit_change_pct > 0.0 {
                "kuongezeka"
            } else {
                "kupungua"
            };
            key_findings.push(format!(
                "Faida za kila zinatarajiwa {} kwa {:.1}%",
                direction, impact.profit_change_pct,
            ));
        }

        if impact.workers_lifted_above_poverty_line > 0 {
            key_findings.push(format!(
                "Wafanyakazi takribani {} wanatarajiwa kupanda juu ya mstari wa umaskini",
                Self::format_number(impact.workers_lifted_above_poverty_line),
            ));
        }

        let recommendations = Self::generate_recommendations(impact);

        PolicyBrief {
            scenario_id: scenario.id,
            title,
            executive_summary,
            key_findings,
            methodology_note: "Mfano wa Monte Carlo wa wakala kulingana na data ya jumla ya Angavu."
                .to_string(),
            recommendations,
            caveats: vec![
                "Matokeo ni makadirio kulingana na mifano ya takwimu.".to_string(),
            ],
            language: Language::Swahili,
            generated_at: Utc::now(),
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Persistence & Caching
    // ─────────────────────────────────────────────────────────────────

    async fn load_scenario(&self, scenario_id: Uuid) -> Result<Scenario> {
        #[derive(sqlx::FromRow)]
        struct ScenarioRow {
            id: Uuid,
            name: String,
            description: Option<String>,
            created_by: String,
            baseline_start: NaiveDate,
            baseline_end: NaiveDate,
            interventions: String,
            target_cohorts: String,
            simulation_days: i32,
            monte_carlo_runs: i32,
            status: String,
            created_at: DateTime<Utc>,
        }

        let row = sqlx::query_as::<_, ScenarioRow>(
            "SELECT id, name, description, created_by, baseline_start, baseline_end, \
             interventions, target_cohorts, simulation_days, monte_carlo_runs, status, created_at \
             FROM scenarios WHERE id = $1",
        )
        .bind(scenario_id)
        .fetch_optional(&self.db.postgres)
        .await?
        .ok_or_else(|| anyhow!("Scenario {} not found", scenario_id))?;

        Ok(Scenario {
            id: row.id,
            name: row.name,
            description: row.description.unwrap_or_default(),
            created_by: row.created_by,
            baseline_period: DateRange {
                start: row.baseline_start,
                end: row.baseline_end,
            },
            interventions: serde_json::from_str(&row.interventions).unwrap_or_default(),
            target_cohorts: serde_json::from_str(&row.target_cohorts).unwrap_or_default(),
            simulation_days: row.simulation_days as u32,
            monte_carlo_runs: row.monte_carlo_runs as u32,
            status: match row.status.as_str() {
                "draft" => ScenarioStatus::Draft,
                "completed" => ScenarioStatus::Completed,
                s if s.starts_with("failed:") => ScenarioStatus::Failed {
                    error: s.strip_prefix("failed:").unwrap_or("").to_string(),
                },
                _ => ScenarioStatus::Draft,
            },
            created_at: row.created_at,
        })
    }

    async fn store_result(&self, result: &ScenarioResult) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO scenario_results (id, scenario_id, baseline_metrics, counterfactual_metrics,
                impact_metrics, confidence_intervals, computed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(result.scenario_id)
        .bind(serde_json::to_string(&result.baseline)?)
        .bind(serde_json::to_string(&result.counterfactual)?)
        .bind(serde_json::to_string(&result.impact)?)
        .bind(serde_json::to_string(&result.confidence_intervals)?)
        .bind(result.computed_at)
        .execute(&self.db.postgres)
        .await?;

        Ok(())
    }

    async fn update_status(&self, scenario_id: Uuid, status: ScenarioStatus) -> Result<()> {
        let status_str = match &status {
            ScenarioStatus::Draft => "draft".to_string(),
            ScenarioStatus::Running { progress_pct } => format!("running:{}", progress_pct),
            ScenarioStatus::Completed => "completed".to_string(),
            ScenarioStatus::Failed { error } => format!("failed:{}", error),
        };

        sqlx::query("UPDATE scenarios SET status = $1 WHERE id = $2")
            .bind(&status_str)
            .bind(scenario_id)
            .execute(&self.db.postgres)
            .await?;

        // Update Redis cache
        let mut redis = self.db.redis.clone();
        let _: () = redis::cmd("SET")
            .arg(format!("scenario:status:{}", scenario_id))
            .arg(serde_json::to_string(&status).unwrap_or_default())
            .arg("EX")
            .arg(3600)
            .query_async(&mut redis)
            .await
            .unwrap_or(());

        Ok(())
    }

    async fn cache_result(&self, scenario_id: Uuid, result: &ScenarioResult) {
        let mut redis = self.db.redis.clone();
        let json = serde_json::to_string(result).unwrap_or_default();
        let _: () = redis::cmd("SET")
            .arg(format!("scenario:result:{}", scenario_id))
            .arg(&json)
            .arg("EX")
            .arg(86400) // 24h TTL
            .query_async(&mut redis)
            .await
            .unwrap_or(());
    }

    async fn get_cached_result(&self, scenario_id: Uuid) -> Option<ScenarioResult> {
        let mut redis = self.db.redis.clone();
        let json: Option<String> = redis::cmd("GET")
            .arg(format!("scenario:result:{}", scenario_id))
            .query_async(&mut redis)
            .await
            .unwrap_or(None);
        json.and_then(|j| serde_json::from_str(&j).ok())
    }

    async fn get_or_run_result(
        &self,
        scenario_id: Uuid,
        scenario: &Scenario,
    ) -> Result<ScenarioResult> {
        if let Some(cached) = self.get_cached_result(scenario_id).await {
            return Ok(cached);
        }
        // Check if result exists in DB
        #[derive(sqlx::FromRow)]
        struct ResultRow {
            baseline_metrics: String,
            counterfactual_metrics: String,
            impact_metrics: String,
            confidence_intervals: String,
            computed_at: DateTime<Utc>,
        }

        if let Ok(Some(row)) = sqlx::query_as::<_, ResultRow>(
            "SELECT baseline_metrics, counterfactual_metrics, impact_metrics, \
             confidence_intervals, computed_at FROM scenario_results WHERE scenario_id = $1 \
             ORDER BY computed_at DESC LIMIT 1",
        )
        .bind(scenario_id)
        .fetch_optional(&self.db.postgres)
        .await
        {
            let result = ScenarioResult {
                scenario_id,
                baseline: serde_json::from_str(&row.baseline_metrics)?,
                counterfactual: serde_json::from_str(&row.counterfactual_metrics)?,
                impact: serde_json::from_str(&row.impact_metrics)?,
                confidence_intervals: serde_json::from_str(&row.confidence_intervals)?,
                agent_trajectories: None,
                computed_at: row.computed_at,
            };
            self.cache_result(scenario_id, &result).await;
            return Ok(result);
        }

        // Need to run
        self.run_scenario(scenario_id).await
    }

    /// Try to load calibration data from ClickHouse for more accurate agent generation.
    async fn load_calibration_data(&self, cohort: &CohortFilter) -> Option<CalibrationData> {
        let region_filter = cohort
            .region
            .as_deref()
            .unwrap_or("%");
        let worker_filter = cohort
            .worker_type
            .as_ref()
            .map(|w| format!("{:?}", w))
            .unwrap_or_else(|| "%".to_string());

        let query = format!(
            r#"
            SELECT
                avg(avg_daily_profit) as avg_profit,
                avg(avg_daily_revenue) as avg_revenue,
                count() as sample_size
            FROM economic_indicators
            WHERE region LIKE '{}' AND worker_type LIKE '{}'
            AND event_time >= now() - INTERVAL 90 DAY
            "#,
            region_filter, worker_filter
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct CalibRow {
            avg_profit: f64,
            avg_revenue: f64,
            sample_size: u64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<CalibRow>()
            .await
            .ok()?;

        let row = rows.into_iter().next()?;
        if row.sample_size < 10 {
            return None;
        }

        // Use ratios to adjust base parameters
        let base_profit = 1000.0; // Rough average across worker types
        let base_revenue = 3000.0;

        Some(CalibrationData {
            avg_profit_multiplier: (row.avg_profit / base_profit).clamp(0.3, 3.0),
            avg_revenue_multiplier: (row.avg_revenue / base_revenue).clamp(0.3, 3.0),
        })
    }

    // ─────────────────────────────────────────────────────────────────
    // Sensitivity Analysis Helpers
    // ─────────────────────────────────────────────────────────────────

    fn apply_sensitivity_variation(
        target: &mut InterventionTarget,
        change_type: &ChangeType,
        variable_name: &str,
        value: f64,
    ) {
        // Match the target variable by name and update its value
        match target {
            InterventionTarget::MPesaWithdrawalFee { new_fee_pct }
                if variable_name.contains("mpesa") || variable_name.contains("fee") =>
            {
                *new_fee_pct = value;
            }
            InterventionTarget::MarketLevy { new_daily_levy, .. }
                if variable_name.contains("levy") || variable_name.contains("market") =>
            {
                *new_daily_levy = value;
            }
            InterventionTarget::FulizaInterestRate { new_daily_rate_pct }
                if variable_name.contains("fuliza") || variable_name.contains("interest") =>
            {
                *new_daily_rate_pct = value;
            }
            InterventionTarget::FuelPrice { new_price_per_litre }
                if variable_name.contains("fuel") || variable_name.contains("price") =>
            {
                *new_price_per_litre = value;
            }
            _ => {
                // For custom or unmatched targets, try to set directly
                if let InterventionTarget::Custom { new_value, .. } = target {
                    *new_value = value;
                }
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Formatting Helpers
    // ─────────────────────────────────────────────────────────────────

    fn describe_intervention_target(intervention: Option<&Intervention>) -> String {
        match intervention.map(|i| &i.target_variable) {
            Some(InterventionTarget::MPesaWithdrawalFee { .. }) => "M-Pesa withdrawal fees".to_string(),
            Some(InterventionTarget::MarketLevy { region, .. }) => format!("market levies in {}", region),
            Some(InterventionTarget::FulizaInterestRate { .. }) => "Fuliza interest rates".to_string(),
            Some(InterventionTarget::WholesaleMarketAccess { region, .. }) => {
                format!("wholesale market access in {}", region)
            }
            Some(InterventionTarget::SchoolFeeStructure { .. }) => "school fee structures".to_string(),
            Some(InterventionTarget::FuelPrice { .. }) => "fuel prices".to_string(),
            Some(InterventionTarget::SupplierCreditTerms { .. }) => "supplier credit terms".to_string(),
            Some(InterventionTarget::Custom { variable_name, .. }) => variable_name.clone(),
            None => "an unspecified variable".to_string(),
        }
    }

    fn describe_change_type(intervention: Option<&Intervention>) -> String {
        match intervention.map(|i| &i.change_type) {
            Some(ChangeType::Absolute(val)) => format!("setting to {}", val),
            Some(ChangeType::RelativePct(pct)) => {
                if *pct > 0.0 {
                    format!("increasing by {}%", pct)
                } else {
                    format!("reducing by {}%", pct.abs())
                }
            }
            Some(ChangeType::Floor(val)) => format!("setting minimum floor to {}", val),
            Some(ChangeType::Cap(val)) => format!("setting maximum cap to {}", val),
            None => "no change specified".to_string(),
        }
    }

    fn generate_recommendations(impact: &ImpactMetrics) -> Vec<String> {
        let mut recs = Vec::new();

        if impact.profit_change_pct > 5.0 {
            recs.push("The policy shows strong positive impact on profits. Recommend implementation.".to_string());
        } else if impact.profit_change_pct > 0.0 {
            recs.push("Modest profit gains observed. Consider combining with complementary interventions.".to_string());
        } else if impact.profit_change_pct < -5.0 {
            recs.push("WARNING: The policy is projected to reduce profits significantly. Recommend against implementation without mitigating measures.".to_string());
        }

        if impact.workers_lifted_above_poverty_line > 1000 {
            recs.push(format!(
                "High poverty reduction potential: ~{} workers lifted above poverty line.",
                Self::format_number(impact.workers_lifted_above_poverty_line),
            ));
        }

        if impact.survival_rate_change_pct < -2.0 {
            recs.push("Business survival rates are projected to decline. Consider phased implementation with monitoring.".to_string());
        }

        if let Some(roi) = impact.roi_ratio {
            if roi > 3.0 {
                recs.push(format!("Excellent ROI ({:.1}:1) supports fiscal case for implementation.", roi));
            } else if roi > 1.0 {
                recs.push(format!("Positive ROI ({:.1}:1). Cost-benefit analysis supports implementation.", roi));
            } else if roi < 1.0 {
                recs.push(format!("ROI below 1:1 ({:.1}:1). Consider whether non-economic benefits justify the cost.", roi));
            }
        }

        if recs.is_empty() {
            recs.push("Insufficient data variation to generate strong recommendations. Consider running with more iterations or different parameters.".to_string());
        }

        recs
    }

    fn format_number(n: u32) -> String {
        if n >= 1_000_000 {
            format!("{:.1}M", n as f64 / 1_000_000.0)
        } else if n >= 1_000 {
            format!("{:.1}K", n as f64 / 1_000.0)
        } else {
            format!("{}", n)
        }
    }

    fn format_kes(amount: f64) -> String {
        if amount.abs() >= 1_000_000_000.0 {
            format!("{:.1}B", amount / 1_000_000_000.0)
        } else if amount.abs() >= 1_000_000.0 {
            format!("{:.1}M", amount / 1_000_000.0)
        } else if amount.abs() >= 1_000.0 {
            format!("{:.1}K", amount / 1_000.0)
        } else {
            format!("{:.0}", amount)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Internal Helper Structs
// ─────────────────────────────────────────────────────────────────────

/// Calibrated base economic parameters for a worker type.
#[derive(Debug, Clone)]
struct WorkerTypeParams {
    daily_revenue: f64,
    daily_profit: f64,
    spoilage_rate: f64,
    transport_cost_pct: f64,
    market_levy: f64,
    fuliza_usage_prob: f64,
    credit_days: u32,
    customer_count: u32,
    markup_pct: f64,
}

/// Calibration offsets loaded from ClickHouse historical data.
#[derive(Debug, Clone)]
struct CalibrationData {
    avg_profit_multiplier: f64,
    avg_revenue_multiplier: f64,
}

// ─────────────────────────────────────────────────────────────────────
// OODA Integration
// ─────────────────────────────────────────────────────────────────────

impl ScenarioModeler {
    /// Emit an OODA signal after scenario completion.
    ///
    /// Called by the OODA orchestrator or directly after simulation.
    pub async fn emit_ooda_signal(
        &self,
        result: &ScenarioResult,
    ) -> Result<()> {
        let signal = OodaSignal {
            source: "scenario_modeler".to_string(),
            signal_type: "scenario_completed".to_string(),
            payload: serde_json::json!({
                "scenario_id": result.scenario_id,
                "profit_change_pct": result.impact.profit_change_pct,
                "workers_lifted": result.impact.workers_lifted_above_poverty_line,
                "survival_rate_change": result.impact.survival_rate_change_pct,
                "computed_at": result.computed_at,
            }),
            timestamp: Utc::now(),
        };

        // In production, this would publish to the OODA event bus
        tracing::info!(
            scenario_id = %result.scenario_id,
            profit_change = result.impact.profit_change_pct,
            workers_lifted = result.impact.workers_lifted_above_poverty_line,
            "OODA signal: scenario completed"
        );

        Ok(())
    }

    /// Quick-run a scenario from intervention parameters (convenience method).
    ///
    /// Combines define_scenario + create_scenario + run_scenario + generate_policy_brief
    /// into a single call for API endpoints.
    pub async fn quick_simulate(
        &self,
        name: &str,
        description: &str,
        created_by: &str,
        cohort: CohortFilter,
        interventions: Vec<Intervention>,
        simulation_days: u32,
        monte_carlo_runs: Option<u32>,
    ) -> Result<(ScenarioResult, PolicyBrief)> {
        let mut scenario = self.define_scenario(
            name,
            description,
            created_by,
            cohort,
            interventions,
            simulation_days,
        );
        if let Some(runs) = monte_carlo_runs {
            scenario.monte_carlo_runs = runs;
        }

        let scenario_id = self.create_scenario(scenario.clone()).await?;
        let result = self.run_scenario(scenario_id).await?;
        let brief = self.generate_policy_brief(scenario_id, Language::English).await?;

        self.emit_ooda_signal(&result).await?;

        Ok((result, brief))
    }
}

// ─────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_worker_type_params_coverage() {
        // Ensure all worker types have parameters
        let types = vec![
            WorkerType::MamaMboga,
            WorkerType::BodaBoda,
            WorkerType::Fundi,
            WorkerType::JuaKali,
            WorkerType::MitiMba,
            WorkerType::HouseHelp,
            WorkerType::FarmWorker,
            WorkerType::Other,
        ];
        for wt in types {
            let params = ScenarioModeler::worker_type_params(&wt);
            assert!(params.daily_revenue > 0.0, "{:?} should have positive revenue", wt);
            assert!(params.daily_profit > 0.0, "{:?} should have positive profit", wt);
        }
    }

    #[test]
    fn test_aggregate_metrics_empty() {
        let metrics = ScenarioModeler::aggregate_metrics(&[]);
        assert_eq!(metrics.avg_daily_profit, 0.0);
        assert_eq!(metrics.business_survival_rate, 0.0);
    }

    #[test]
    fn test_compute_impact_positive() {
        let baseline = AggregateMetrics {
            avg_daily_profit: 800.0,
            avg_monthly_income: 20000.0,
            avg_savings_rate: 0.1,
            avg_debt_to_income: 0.3,
            avg_spoilage_loss: 100.0,
            avg_transport_cost: 200.0,
            business_survival_rate: 0.85,
            credit_access_rate: 0.4,
            food_security_index: 0.6,
        };
        let counterfactual = AggregateMetrics {
            avg_daily_profit: 900.0,
            avg_monthly_income: 23000.0,
            avg_savings_rate: 0.12,
            avg_debt_to_income: 0.25,
            avg_spoilage_loss: 80.0,
            avg_transport_cost: 180.0,
            business_survival_rate: 0.88,
            credit_access_rate: 0.45,
            food_security_index: 0.68,
        };

        let agents = vec![SyntheticAgent {
            agent_id: 0,
            worker_type: WorkerType::MamaMboga,
            region: "Nairobi".to_string(),
            gender: Gender::Female,
            income_bracket: IncomeBracket::LowerMiddle,
            business_age_months: 24,
            daily_profit: 800.0,
            daily_revenue: 3500.0,
            daily_costs: 2700.0,
            savings_balance: 2000.0,
            debt_balance: 0.0,
            monthly_income: 20000.0,
            savings_rate: 0.1,
            spoilage_rate: 0.12,
            transport_cost_pct: 0.08,
            market_levy_daily: 100.0,
            mpesa_fee_pct: 1.0,
            fuliza_daily_rate_pct: 1.0,
            fuliza_usage_probability: 0.4,
            supplier_credit_days: 7,
            customer_count: 50,
            price_markup_pct: 30.0,
            is_active: true,
            days_below_poverty: 0,
        }];

        let impact = ScenarioModeler::compute_impact(&baseline, &counterfactual, &agents);
        assert!(impact.profit_change_pct > 0.0);
        assert!(impact.income_change_pct > 0.0);
        assert!(impact.workers_lifted_above_poverty_line >= 0);
    }

    #[test]
    fn test_format_helpers() {
        assert_eq!(ScenarioModeler::format_number(1_500_000), "1.5M");
        assert_eq!(ScenarioModeler::format_number(25_000), "25.0K");
        assert_eq!(ScenarioModeler::format_number(42), "42");

        assert_eq!(ScenarioModeler::format_kes(2_500_000_000.0), "2.5B");
        assert_eq!(ScenarioModeler::format_kes(1_500_000.0), "1.5M");
        assert_eq!(ScenarioModeler::format_kes(50_000.0), "50.0K");
    }

    #[test]
    fn test_composite_score() {
        let positive_impact = ImpactMetrics {
            profit_change_pct: 15.0,
            income_change_pct: 12.0,
            savings_change_pct: 5.0,
            debt_change_pct: -10.0,
            survival_rate_change_pct: 3.0,
            workers_lifted_above_poverty_line: 5000,
            aggregate_annual_savings_kes: 10_000_000.0,
            cost_to_implement_kes: Some(2_000_000.0),
            roi_ratio: Some(5.0),
        };
        let score = ScenarioModeler::compute_composite_score(&positive_impact);
        assert!(score > 0.0);

        let negative_impact = ImpactMetrics {
            profit_change_pct: -20.0,
            income_change_pct: -15.0,
            savings_change_pct: -5.0,
            debt_change_pct: 30.0,
            survival_rate_change_pct: -10.0,
            workers_lifted_above_poverty_line: 0,
            aggregate_annual_savings_kes: -5_000_000.0,
            cost_to_implement_kes: None,
            roi_ratio: None,
        };
        let neg_score = ScenarioModeler::compute_composite_score(&negative_impact);
        assert!(neg_score < 0.0);
    }

    #[test]
    fn test_apply_change() {
        assert_eq!(ScenarioModeler::apply_change(100.0, &ChangeType::Absolute(50.0), 50.0), 50.0);
        assert_eq!(ScenarioModeler::apply_change(100.0, &ChangeType::RelativePct(-50.0), 0.0), 50.0);
        assert_eq!(ScenarioModeler::apply_change(100.0, &ChangeType::Floor(80.0), 0.0), 100.0);
        assert_eq!(ScenarioModeler::apply_change(60.0, &ChangeType::Floor(80.0), 0.0), 80.0);
        assert_eq!(ScenarioModeler::apply_change(100.0, &ChangeType::Cap(80.0), 0.0), 80.0);
        assert_eq!(ScenarioModeler::apply_change(60.0, &ChangeType::Cap(80.0), 0.0), 60.0);
    }
}
