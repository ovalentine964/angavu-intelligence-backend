// statistical/time_series_bridge.rs
//
// Rust bridge to Python time series models via subprocess.
// Provides ARIMA, SARIMA, ETS, structural break tests to the Rust backend.
//
// Academic reference: STA 244 (Time Series Analysis)

use serde::{Deserialize, Serialize};
use std::process::Command;

use super::econometrics_bridge::EconometricResult;

/// Run a time series method via Python subprocess.
///
/// # Arguments
/// * `method` - Method name (arima_identify, arima_fit, arima_diagnose, sarima_fit, ets_fit, ets_auto, chow_test, cusum_test, bai_perron)
/// * `args` - Method arguments as JSON value
///
/// # Returns
/// * `EconometricResult` with the output or error
pub fn run_time_series_method(method: &str, args: serde_json::Value) -> EconometricResult {
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
        .arg("python/statistical/time_series_runner.py")
        .arg(&input_str)
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            return EconometricResult {
                method: method.to_string(),
                data: serde_json::Value::Null,
                error: Some(format!("Failed to run time_series_runner: {}", e)),
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

/// Identify best ARIMA(p,d,q) order via AIC grid search.
pub fn arima_identify(
    data: &[f64],
    max_p: Option<usize>,
    max_d: Option<usize>,
    max_q: Option<usize>,
) -> EconometricResult {
    let args = serde_json::json!({
        "data": data,
        "max_p": max_p.unwrap_or(5),
        "max_d": max_d.unwrap_or(2),
        "max_q": max_q.unwrap_or(5),
    });
    run_time_series_method("arima_identify", args)
}

/// Fit ARIMA(p,d,q) model.
pub fn arima_fit(data: &[f64], order: (usize, usize, usize)) -> EconometricResult {
    let args = serde_json::json!({
        "data": data,
        "order": [order.0, order.1, order.2],
    });
    run_time_series_method("arima_fit", args)
}

/// Diagnose ARIMA residuals.
pub fn arima_diagnose(residuals: &[f64], n_params: Option<usize>) -> EconometricResult {
    let args = serde_json::json!({
        "residuals": residuals,
        "n_params": n_params.unwrap_or(2),
    });
    run_time_series_method("arima_diagnose", args)
}

/// Fit SARIMA(p,d,q)(P,D,Q)s model.
pub fn sarima_fit(
    data: &[f64],
    order: (usize, usize, usize),
    seasonal_order: (usize, usize, usize, usize),
) -> EconometricResult {
    let args = serde_json::json!({
        "data": data,
        "order": [order.0, order.1, order.2],
        "seasonal_order": [seasonal_order.0, seasonal_order.1, seasonal_order.2, seasonal_order.3],
    });
    run_time_series_method("sarima_fit", args)
}

/// Fit ETS model.
pub fn ets_fit(
    data: &[f64],
    model_type: &str,
    seasonal_period: Option<usize>,
) -> EconometricResult {
    let args = serde_json::json!({
        "data": data,
        "model_type": model_type,
        "seasonal_period": seasonal_period.unwrap_or(7),
    });
    run_time_series_method("ets_fit", args)
}

/// Automatic ETS model selection.
pub fn ets_auto_select(data: &[f64], seasonal_period: Option<usize>) -> EconometricResult {
    let args = serde_json::json!({
        "data": data,
        "seasonal_period": seasonal_period.unwrap_or(7),
    });
    run_time_series_method("ets_auto", args)
}

/// Chow test for structural break at known break point.
pub fn chow_test(y: &[f64], x: &[Vec<f64>], break_point: usize) -> EconometricResult {
    let args = serde_json::json!({
        "y": y,
        "X": x,
        "break_point": break_point,
    });
    run_time_series_method("chow_test", args)
}

/// CUSUM test for structural breaks.
pub fn cusum_test(y: &[f64], x: &[Vec<f64>], alpha: Option<f64>) -> EconometricResult {
    let args = serde_json::json!({
        "y": y,
        "X": x,
        "alpha": alpha.unwrap_or(0.05),
    });
    run_time_series_method("cusum_test", args)
}

/// Bai-Perron test for multiple structural breaks.
pub fn bai_perron(
    y: &[f64],
    x: &[Vec<f64>],
    max_breaks: Option<usize>,
    min_segment: Option<usize>,
) -> EconometricResult {
    let args = serde_json::json!({
        "y": y,
        "X": x,
        "max_breaks": max_breaks.unwrap_or(5),
        "min_segment": min_segment.unwrap_or(10),
    });
    run_time_series_method("bai_perron", args)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_arima_fit_basic() {
        // Generate simple AR(1) data
        let mut data = vec![0.0; 100];
        data[0] = 1.0;
        for t in 1..100 {
            data[t] = 0.7 * data[t - 1] + 0.1 * (t as f64 * 0.01).sin();
        }
        let result = arima_fit(&data, (1, 0, 0));
        assert!(
            result.error.is_none(),
            "ARIMA fit should not error: {:?}",
            result.error
        );
    }

    #[test]
    fn test_chow_test_basic() {
        let y: Vec<f64> = (0..100)
            .map(|i| {
                if i < 50 {
                    i as f64 * 0.5
                } else {
                    25.0 + (i - 50) as f64 * 1.5
                }
            })
            .collect();
        let x: Vec<Vec<f64>> = (0..100).map(|i| vec![i as f64]).collect();
        let result = chow_test(&y, &x, 50);
        assert!(
            result.error.is_none(),
            "Chow test should not error: {:?}",
            result.error
        );
    }
}
