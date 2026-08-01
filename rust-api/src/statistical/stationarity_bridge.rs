/// Stationarity & Causality Bridge — KPSS, Granger causality, CIs, bootstrap.
///
/// Connects Rust backend to Python stationarity_causality module.

use serde_json::{json, Value};
use std::process::Command;
use tracing::{debug, error};

use super::types::*;

const PYTHON_SCRIPT: &str = "python/statistical/stationarity_causality.py";

pub struct StationarityBridge {
    python_path: String,
    script_path: String,
}

impl StationarityBridge {
    pub fn new() -> Self {
        Self {
            python_path: "python3".to_string(),
            script_path: PYTHON_SCRIPT.to_string(),
        }
    }

    fn execute(&self, method: &str, args: Value) -> Result<Value, String> {
        let input = json!({"method": method, "args": args});
        debug!(method = method, "Executing stationarity method");

        let output = Command::new(&self.python_path)
            .arg(&self.script_path)
            .arg(input.to_string())
            .output()
            .map_err(|e| format!("Failed to execute Python: {}", e))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("Python error: {}", stderr));
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        serde_json::from_str::<Value>(&stdout)
            .map_err(|e| format!("JSON parse error: {}", e))
    }

    /// KPSS stationarity test (complement to ADF).
    pub fn kpss_test(&self, data: &[f64], regression: &str, lags: Option<usize>) -> Result<KPSSResult, String> {
        let mut args = json!({"data": data, "regression": regression});
        if let Some(l) = lags {
            args["lags"] = json!(l);
        }
        let result = self.execute("kpss", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Granger causality test.
    pub fn granger_causality(&self, x: &[f64], y: &[f64], max_lag: usize) -> Result<GrangerCausalityResult, String> {
        let args = json!({"x": x, "y": y, "max_lag": max_lag, "significance": 0.05});
        let result = self.execute("granger_causality", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Confidence interval for mean.
    pub fn ci_mean(&self, data: &[f64], confidence: f64, method: &str) -> Result<ConfidenceIntervalResult, String> {
        let args = json!({"data": data, "confidence": confidence, "ci_method": method});
        let result = self.execute("ci_mean", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// BCa bootstrap confidence interval.
    pub fn bootstrap_bca(&self, data: &[f64], statistic: &str, confidence: f64, n_bootstrap: usize) -> Result<Value, String> {
        let args = json!({"data": data, "statistic": statistic, "confidence": confidence, "n_bootstrap": n_bootstrap});
        self.execute("bootstrap_bca", args)
    }
}
