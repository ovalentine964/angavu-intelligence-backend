// statistical/macro_bridge.rs
//
// Rust bridge to Python macroeconomic models via subprocess.
// Provides Phillips curve, IS-LM, Solow growth, Taylor rule, Okun's law,
// Fisher equation, money multiplier, demographic models to the Rust backend.
//
// Academic reference: ECO 311 (Intermediate Macro), ECO 414 (Econometrics)

use serde::{Deserialize, Serialize};
use std::process::Command;

use super::econometrics_bridge::EconometricResult;

/// Run a macroeconomic model method via Python subprocess.
///
/// # Arguments
/// * `method` - Method name
/// * `args` - Method arguments as JSON value
///
/// # Returns
/// * `EconometricResult` with the output or error
pub fn run_macro_method(method: &str, args: serde_json::Value) -> EconometricResult {
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
        .arg("python/statistical/macro_runner.py")
        .arg(&input_str)
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            return EconometricResult {
                method: method.to_string(),
                data: serde_json::Value::Null,
                error: Some(format!("Failed to run macro_runner: {}", e)),
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
        Ok(data) => {
            if let Some(err) = data.get("error") {
                EconometricResult {
                    method: method.to_string(),
                    data: serde_json::Value::Null,
                    error: Some(err.as_str().unwrap_or("Unknown error").to_string()),
                }
            } else {
                EconometricResult {
                    method: method.to_string(),
                    data,
                    error: None,
                }
            }
        }
        Err(e) => EconometricResult {
            method: method.to_string(),
            data: serde_json::Value::Null,
            error: Some(format!("JSON parse error: {}", e)),
        },
    }
}

/// Estimate Phillips Curve from inflation and unemployment data.
pub fn phillips_estimate(inflation: &[f64], unemployment: &[f64]) -> EconometricResult {
    let args = serde_json::json!({
        "inflation": inflation,
        "unemployment": unemployment,
    });
    run_macro_method("phillips_estimate", args)
}

/// Solve IS-LM model for equilibrium.
pub fn islm_solve(
    consumption_intercept: Option<f64>,
    mpc: Option<f64>,
    tax_rate: Option<f64>,
    investment_intercept: Option<f64>,
    investment_sensitivity: Option<f64>,
    government_spending: Option<f64>,
    money_supply: Option<f64>,
    price_level: Option<f64>,
) -> EconometricResult {
    let mut args = serde_json::json!({});
    if let Some(v) = consumption_intercept {
        args["consumption_intercept"] = serde_json::json!(v);
    }
    if let Some(v) = mpc {
        args["mpc"] = serde_json::json!(v);
    }
    if let Some(v) = tax_rate {
        args["tax_rate"] = serde_json::json!(v);
    }
    if let Some(v) = investment_intercept {
        args["investment_intercept"] = serde_json::json!(v);
    }
    if let Some(v) = investment_sensitivity {
        args["investment_sensitivity"] = serde_json::json!(v);
    }
    if let Some(v) = government_spending {
        args["government_spending"] = serde_json::json!(v);
    }
    if let Some(v) = money_supply {
        args["money_supply"] = serde_json::json!(v);
    }
    if let Some(v) = price_level {
        args["price_level"] = serde_json::json!(v);
    }
    run_macro_method("islm_solve", args)
}

/// Solve Solow growth model steady state.
pub fn solow_steady_state(
    savings_rate: Option<f64>,
    population_growth: Option<f64>,
    depreciation: Option<f64>,
    technology_growth: Option<f64>,
    capital_share: Option<f64>,
) -> EconometricResult {
    let mut args = serde_json::json!({});
    if let Some(v) = savings_rate {
        args["savings_rate"] = serde_json::json!(v);
    }
    if let Some(v) = population_growth {
        args["population_growth"] = serde_json::json!(v);
    }
    if let Some(v) = depreciation {
        args["depreciation"] = serde_json::json!(v);
    }
    if let Some(v) = technology_growth {
        args["technology_growth"] = serde_json::json!(v);
    }
    if let Some(v) = capital_share {
        args["capital_share"] = serde_json::json!(v);
    }
    run_macro_method("solow_steady_state", args)
}

/// Compute Taylor Rule recommended interest rate.
pub fn taylor_rule(
    inflation: f64,
    output_gap: f64,
    target_inflation: Option<f64>,
    real_rate: Option<f64>,
) -> EconometricResult {
    let mut args = serde_json::json!({
        "inflation": inflation,
        "output_gap": output_gap,
    });
    if let Some(v) = target_inflation {
        args["target_inflation"] = serde_json::json!(v);
    }
    if let Some(v) = real_rate {
        args["real_rate"] = serde_json::json!(v);
    }
    run_macro_method("taylor_rule", args)
}

/// Predict unemployment change from GDP growth via Okun's Law.
pub fn okun_predict(gdp_growth: f64, okun_coefficient: Option<f64>) -> EconometricResult {
    let mut args = serde_json::json!({ "gdp_growth": gdp_growth });
    if let Some(v) = okun_coefficient {
        args["okun_coefficient"] = serde_json::json!(v);
    }
    run_macro_method("okun_predict", args)
}

/// Fisher equation calculator.
pub fn fisher(
    nominal_rate: Option<f64>,
    real_rate: Option<f64>,
    inflation_rate: Option<f64>,
) -> EconometricResult {
    let mut args = serde_json::json!({});
    if let Some(v) = nominal_rate {
        args["nominal_rate"] = serde_json::json!(v);
    }
    if let Some(v) = real_rate {
        args["real_rate"] = serde_json::json!(v);
    }
    if let Some(v) = inflation_rate {
        args["inflation_rate"] = serde_json::json!(v);
    }
    run_macro_method("fisher", args)
}

/// Compute money multiplier and money supply.
pub fn money_multiplier(
    monetary_base: Option<f64>,
    reserve_ratio: Option<f64>,
    currency_deposit_ratio: Option<f64>,
) -> EconometricResult {
    let mut args = serde_json::json!({});
    if let Some(v) = monetary_base {
        args["monetary_base"] = serde_json::json!(v);
    }
    if let Some(v) = reserve_ratio {
        args["reserve_ratio"] = serde_json::json!(v);
    }
    if let Some(v) = currency_deposit_ratio {
        args["currency_deposit_ratio"] = serde_json::json!(v);
    }
    run_macro_method("money_multiplier", args)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_taylor_rule_basic() {
        let result = taylor_rule(5.0, 1.0, Some(2.5), Some(2.0));
        assert!(
            result.error.is_none(),
            "Taylor rule should not error: {:?}",
            result.error
        );
    }

    #[test]
    fn test_fisher_basic() {
        let result = fisher(Some(10.0), None, Some(5.0));
        assert!(
            result.error.is_none(),
            "Fisher equation should not error: {:?}",
            result.error
        );
    }

    #[test]
    fn test_money_multiplier_basic() {
        let result = money_multiplier(Some(1000.0), Some(0.0425), Some(0.3));
        assert!(
            result.error.is_none(),
            "Money multiplier should not error: {:?}",
            result.error
        );
    }
}
