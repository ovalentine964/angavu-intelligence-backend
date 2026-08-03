/// Control Charts Bridge — CUSUM, EWMA, process capability.
///
/// Connects Rust backend to Python control_charts module.
use serde_json::{json, Value};
use std::process::Command;
use tracing::{debug, error};

use super::types::*;

const PYTHON_SCRIPT: &str = "python/statistical/control_charts.py";

pub struct ControlChartsBridge {
    python_path: String,
    script_path: String,
}

impl ControlChartsBridge {
    pub fn new() -> Self {
        Self {
            python_path: "python3".to_string(),
            script_path: PYTHON_SCRIPT.to_string(),
        }
    }

    fn execute(&self, method: &str, args: Value) -> Result<Value, String> {
        let input = json!({"method": method, "args": args});
        debug!(method = method, "Executing control chart method");

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
        serde_json::from_str::<Value>(&stdout).map_err(|e| format!("JSON parse error: {}", e))
    }

    /// CUSUM chart for detecting small persistent shifts.
    pub fn cusum(
        &self,
        data: &[f64],
        target: Option<f64>,
        sigma: Option<f64>,
        k_factor: f64,
        h_factor: f64,
    ) -> Result<CUSUMResult, String> {
        let mut args = json!({"data": data, "k_factor": k_factor, "h_factor": h_factor});
        if let Some(t) = target {
            args["target"] = json!(t);
        }
        if let Some(s) = sigma {
            args["sigma"] = json!(s);
        }
        let result = self.execute("cusum", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// EWMA chart for smooth monitoring.
    pub fn ewma(
        &self,
        data: &[f64],
        target: Option<f64>,
        sigma: Option<f64>,
        lambda_param: f64,
        L: f64,
    ) -> Result<EWMAResult, String> {
        let mut args = json!({"data": data, "lambda": lambda_param, "L": L});
        if let Some(t) = target {
            args["target"] = json!(t);
        }
        if let Some(s) = sigma {
            args["sigma"] = json!(s);
        }
        let result = self.execute("ewma", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Process capability (Cp, Cpk).
    pub fn process_capability(
        &self,
        data: &[f64],
        usl: f64,
        lsl: f64,
    ) -> Result<ProcessCapabilityResult, String> {
        let args = json!({"data": data, "usl": usl, "lsl": lsl});
        let result = self.execute("process_capability", args)?;
        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("Unknown error").to_string());
        }
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }
}
