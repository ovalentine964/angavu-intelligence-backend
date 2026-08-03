/// Distribution Fitting Bridge — connects Rust to Python distributions module.
///
/// Provides MLE distribution fitting, MGF computation, CLT demonstration,
/// goodness-of-fit tests, and parametric bootstrap via subprocess.
use serde_json::{json, Value};
use std::process::Command;
use tracing::{debug, error};

use super::types::*;

const PYTHON_SCRIPT: &str = "python/statistical/distributions_runner.py";

pub struct DistributionBridge {
    python_path: String,
    script_path: String,
}

impl DistributionBridge {
    pub fn new() -> Self {
        Self {
            python_path: "python3".to_string(),
            script_path: PYTHON_SCRIPT.to_string(),
        }
    }

    fn execute(&self, method: &str, args: Value) -> Result<Value, String> {
        let input = json!({"method": method, "args": args});
        debug!(method = method, "Executing distribution method");

        let output = Command::new(&self.python_path)
            .arg(&self.script_path)
            .arg(input.to_string())
            .output()
            .map_err(|e| format!("Failed to execute Python: {}", e))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            error!(stderr = %stderr, "Python execution failed");
            return Err(format!("Python error: {}", stderr));
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        serde_json::from_str::<Value>(&stdout).map_err(|e| format!("JSON parse error: {}", e))
    }

    /// Fit a distribution to data via MLE.
    pub fn fit_distribution(
        &self,
        data: &[f64],
        distribution: &str,
    ) -> Result<DistributionFitResult, String> {
        let args = json!({"data": data, "distribution": distribution});
        let result = self.execute("fit_distribution", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Compute moment generating function value.
    pub fn mgf(
        &self,
        distribution: &str,
        t: f64,
        params: &std::collections::HashMap<String, f64>,
    ) -> Result<f64, String> {
        let mut args = json!({"distribution": distribution, "t": t});
        for (k, v) in params {
            args[k] = json!(v);
        }
        let result = self.execute("mgf", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        result
            .get("mgf_value")
            .and_then(|v| v.as_f64())
            .ok_or_else(|| "Missing mgf_value in response".to_string())
    }

    /// Demonstrate CLT via sampling distribution.
    pub fn clt_demo(
        &self,
        data: &[f64],
        sample_size: usize,
        n_samples: usize,
    ) -> Result<Value, String> {
        let args = json!({"data": data, "sample_size": sample_size, "n_samples": n_samples, "statistic": "mean"});
        self.execute("clt_demo", args)
    }

    /// Compute CLT-based confidence interval.
    pub fn clt_ci(
        &self,
        data: &[f64],
        confidence: f64,
    ) -> Result<ConfidenceIntervalResult, String> {
        let args = json!({"data": data, "confidence": confidence});
        let result = self.execute("clt_ci", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Parametric bootstrap CI.
    pub fn parametric_bootstrap(
        &self,
        data: &[f64],
        statistic: &str,
        distribution: &str,
        n_bootstrap: usize,
        confidence: f64,
    ) -> Result<Value, String> {
        let args = json!({"data": data, "statistic": statistic, "distribution": distribution, "n_bootstrap": n_bootstrap, "confidence": confidence});
        self.execute("parametric_bootstrap", args)
    }
}
