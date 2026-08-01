// statistical/econometrics_bridge.rs
//
// Rust bridge to Python econometrics module via subprocess.
// Provides OLS, 2SLS, GMM, Panel Data, Probit/Logit, VAR/VECM to the Rust backend.
//
// Academic reference: ECO 414 (Intro to Econometrics), ECO 424 (Advanced Econometrics)

use serde::{Deserialize, Serialize};
use std::process::Command;

/// Econometric method result wrapper
#[derive(Debug, Serialize, Deserialize)]
pub struct EconometricResult {
    pub method: String,
    pub data: serde_json::Value,
    pub error: Option<String>,
}

/// Run an econometric method via Python subprocess.
///
/// # Arguments
/// * `method` - Method name (ols, 2sls, gmm, panel_fe, panel_re, logit, probit, var, cointegration, vecm, bootstrap_test, breusch_pagan, white_test, robust_se)
/// * `args` - Method arguments as JSON value
///
/// # Returns
/// * `EconometricResult` with the output or error
pub fn run_econometric_method(method: &str, args: serde_json::Value) -> EconometricResult {
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
        .arg("python/statistical/econometrics_runner.py")
        .arg(&input_str)
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            return EconometricResult {
                method: method.to_string(),
                data: serde_json::Value::Null,
                error: Some(format!("Failed to run econometrics_runner: {}", e)),
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

/// Convenience: Run OLS regression.
pub fn ols(x: &[Vec<f64>], y: &[f64], feature_names: Option<Vec<String>>) -> EconometricResult {
    let args = serde_json::json!({
        "X": x,
        "y": y,
        "feature_names": feature_names
    });
    run_econometric_method("ols", args)
}

/// Convenience: Run 2SLS estimation.
pub fn two_sls(
    y: &[f64],
    x_endog: &[Vec<f64>],
    z: &[Vec<f64>],
    x_exog: Option<&[Vec<f64>]>,
) -> EconometricResult {
    let mut args = serde_json::json!({
        "y": y,
        "X_endog": x_endog,
        "Z": z
    });
    if let Some(exog) = x_exog {
        args["X_exog"] = serde_json::json!(exog);
    }
    run_econometric_method("2sls", args)
}

/// Convenience: Run GMM estimation.
pub fn gmm(y: &[f64], x: &[Vec<f64>], z: &[Vec<f64>]) -> EconometricResult {
    let args = serde_json::json!({
        "y": y,
        "X": x,
        "Z": z
    });
    run_econometric_method("gmm", args)
}

/// Convenience: Panel fixed effects.
pub fn panel_fe(y: &[f64], x: &[Vec<f64>], groups: &[&str]) -> EconometricResult {
    let args = serde_json::json!({
        "y": y,
        "X": x,
        "groups": groups
    });
    run_econometric_method("panel_fe", args)
}

/// Convenience: Logit model.
pub fn logit(x: &[Vec<f64>], y: &[f64]) -> EconometricResult {
    let args = serde_json::json!({
        "X": x,
        "y": y
    });
    run_econometric_method("logit", args)
}

/// Convenience: Probit model.
pub fn probit(x: &[Vec<f64>], y: &[f64]) -> EconometricResult {
    let args = serde_json::json!({
        "X": x,
        "y": y
    });
    run_econometric_method("probit", args)
}

/// Convenience: VAR model.
pub fn var(data: &[Vec<f64>], max_lags: Option<usize>) -> EconometricResult {
    let args = serde_json::json!({
        "data": data,
        "max_lags": max_lags.unwrap_or(4)
    });
    run_econometric_method("var", args)
}

/// Convenience: Cointegration test.
pub fn cointegration(y: &[f64], x: &[f64]) -> EconometricResult {
    let args = serde_json::json!({
        "y": y,
        "x": x
    });
    run_econometric_method("cointegration", args)
}

/// Convenience: VECM model.
pub fn vecm(data: &[Vec<f64>], rank: Option<usize>, max_lags: Option<usize>) -> EconometricResult {
    let args = serde_json::json!({
        "data": data,
        "cointegrating_rank": rank.unwrap_or(1),
        "max_lags": max_lags.unwrap_or(3)
    });
    run_econometric_method("vecm", args)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ols_basic() {
        // Simple y = 1 + 2x + noise
        let x = vec![vec![1.0], vec![2.0], vec![3.0], vec![4.0], vec![5.0]];
        let y = vec![3.1, 4.9, 7.2, 8.8, 11.1];
        let result = ols(&x, &y, None);
        assert!(result.error.is_none(), "OLS should not error: {:?}", result.error);
    }
}
