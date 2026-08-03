/// Advanced Economics Models Bridge
///
/// Rust bridge to Python advanced economics models via subprocess.
/// Provides DSGE, rational expectations, Edgeworth box, Pareto efficiency,
/// Stiglitz-Weiss credit rationing, endogenous growth, Ricardian equivalence,
/// New Keynesian Phillips curve, Arrow's impossibility theorem, and
/// revenue equivalence theorem.
///
/// Academic references: ECO 311, ECO 404, ECO 414
use serde::{Deserialize, Serialize};
use std::process::Command;

use super::econometrics_bridge::EconometricResult;

/// Run an advanced economics method via Python subprocess.
pub fn run_advanced_economics_method(method: &str, args: serde_json::Value) -> EconometricResult {
    let input = serde_json::json!({
        "method": method,
        "args": args
    });

    let input_str = match serde_json::to_string(&input) {
        Ok(s) => s,
        Err(e) => {
            return EconometricResult {
                method: method.to_string(),
                data: serde_json::Value::Null,
                error: Some(format!("JSON serialization error: {}", e)),
            }
        }
    };

    let output = match Command::new("python3")
        .arg("python/statistical/advanced_economics_runner.py")
        .arg(&input_str)
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            return EconometricResult {
                method: method.to_string(),
                data: serde_json::Value::Null,
                error: Some(format!("Failed to run advanced_economics_runner: {}", e)),
            }
        }
    };

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return EconometricResult {
            method: method.to_string(),
            data: serde_json::Value::Null,
            error: Some(format!("Runner error: {}", stderr)),
        };
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    match serde_json::from_str::<serde_json::Value>(&stdout) {
        Ok(data) => EconometricResult {
            method: method.to_string(),
            data,
            error: None,
        },
        Err(e) => EconometricResult {
            method: method.to_string(),
            data: serde_json::Value::Null,
            error: Some(format!("JSON parse error: {}", e)),
        },
    }
}

/// DSGE model simulation parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DSGEParams {
    pub sigma: Option<f64>,
    pub beta: Option<f64>,
    pub kappa: Option<f64>,
    pub phi_pi: Option<f64>,
    pub phi_y: Option<f64>,
    pub rho_v: Option<f64>,
    pub periods: Option<usize>,
    pub shock_std: Option<f64>,
    pub seed: Option<u64>,
}

/// Run DSGE model simulation
pub fn dsge_simulate(params: DSGEParams) -> EconometricResult {
    run_advanced_economics_method("dsge_simulate", serde_json::to_value(params).unwrap())
}

/// Rational expectations cobweb model parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RationalExpectationsParams {
    pub a: Option<f64>,
    pub b: Option<f64>,
    pub c: Option<f64>,
    pub gamma: Option<f64>,
    pub periods: Option<usize>,
}

/// Solve rational expectations cobweb model
pub fn rational_expectations_cobweb(params: RationalExpectationsParams) -> EconometricResult {
    run_advanced_economics_method(
        "rational_expectations_cobweb",
        serde_json::to_value(params).unwrap(),
    )
}

/// Edgeworth box parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeworthParams {
    pub total_x: Option<f64>,
    pub total_y: Option<f64>,
    pub alpha_a: Option<f64>,
    pub beta_a: Option<f64>,
    pub alpha_b: Option<f64>,
    pub beta_b: Option<f64>,
    pub n_points: Option<usize>,
}

/// Compute Edgeworth box contract curve
pub fn edgeworth_box(params: EdgeworthParams) -> EconometricResult {
    run_advanced_economics_method("edgeworth_box", serde_json::to_value(params).unwrap())
}

/// Pareto efficiency check parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParetoCheckParams {
    pub utilities: Vec<f64>,
    pub all_allocations: Vec<Vec<f64>>,
}

/// Check Pareto efficiency of an allocation
pub fn pareto_check(params: ParetoCheckParams) -> EconometricResult {
    run_advanced_economics_method("pareto_check", serde_json::to_value(params).unwrap())
}

/// Stiglitz-Weiss credit rationing parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StiglitzWeissParams {
    pub n_types: Option<usize>,
    pub safe_return: Option<f64>,
    pub risky_return: Option<f64>,
    pub supply: Option<f64>,
    pub demand_at_zero: Option<f64>,
}

/// Run Stiglitz-Weiss credit rationing model
pub fn stiglitz_weiss(params: StiglitzWeissParams) -> EconometricResult {
    run_advanced_economics_method("stiglitz_weiss", serde_json::to_value(params).unwrap())
}

/// Endogenous growth model parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EndogenousGrowthParams {
    pub A: Option<f64>,
    pub alpha: Option<f64>,
    pub delta: Option<f64>,
    pub s: Option<f64>,
    pub u: Option<f64>,
    pub periods: Option<usize>,
    pub K0: Option<f64>,
    pub H0: Option<f64>,
}

/// Run endogenous growth model
pub fn endogenous_growth(params: EndogenousGrowthParams) -> EconometricResult {
    run_advanced_economics_method("endogenous_growth", serde_json::to_value(params).unwrap())
}

/// Ricardian equivalence parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RicardianParams {
    pub beta: Option<f64>,
    pub r: Option<f64>,
    pub y: Option<f64>,
    pub G: Option<f64>,
    pub periods: Option<usize>,
    pub tax_cut: Option<f64>,
}

/// Run Ricardian equivalence comparison
pub fn ricardian_equivalence(params: RicardianParams) -> EconometricResult {
    run_advanced_economics_method(
        "ricardian_equivalence",
        serde_json::to_value(params).unwrap(),
    )
}

/// New Keynesian Phillips Curve parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NKPCParams {
    pub beta: Option<f64>,
    pub kappa: Option<f64>,
    pub theta: Option<f64>,
    pub output_gap: Option<Vec<f64>>,
    pub inflation_data: Option<Vec<f64>>,
    pub output_gap_data: Option<Vec<f64>>,
}

/// Run NKPC simulation
pub fn nkpc_simulate(params: NKPCParams) -> EconometricResult {
    run_advanced_economics_method("nkpc_simulate", serde_json::to_value(params).unwrap())
}

/// Arrow's impossibility theorem parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArrowParams {
    pub preferences: Vec<Vec<i64>>,
    pub rule: Option<String>,
}

/// Check Arrow's impossibility theorem properties
pub fn arrow_voting(params: ArrowParams) -> EconometricResult {
    run_advanced_economics_method("arrow_voting", serde_json::to_value(params).unwrap())
}

/// Revenue equivalence theorem parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RevenueEquivalenceParams {
    pub n_bidders: Option<usize>,
    pub n_simulations: Option<usize>,
    pub val_min: Option<f64>,
    pub val_max: Option<f64>,
    pub seed: Option<u64>,
}

/// Run revenue equivalence theorem simulation
pub fn revenue_equivalence(params: RevenueEquivalenceParams) -> EconometricResult {
    run_advanced_economics_method("revenue_equivalence", serde_json::to_value(params).unwrap())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dsge_params_serialize() {
        let params = DSGEParams {
            sigma: Some(1.0),
            beta: Some(0.99),
            kappa: Some(0.1),
            phi_pi: Some(1.5),
            phi_y: Some(0.5),
            rho_v: Some(0.8),
            periods: Some(40),
            shock_std: Some(0.01),
            seed: Some(42),
        };
        let json = serde_json::to_string(&params).unwrap();
        assert!(json.contains("sigma"));
    }

    #[test]
    fn test_pareto_params_serialize() {
        let params = ParetoCheckParams {
            utilities: vec![10.0, 8.0],
            all_allocations: vec![vec![11.0, 7.0], vec![9.0, 9.0]],
        };
        let json = serde_json::to_string(&params).unwrap();
        assert!(json.contains("utilities"));
    }
}
