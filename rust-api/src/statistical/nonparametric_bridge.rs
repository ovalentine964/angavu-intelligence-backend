/// Nonparametric Bridge — connects Rust backend to Python statistical methods.
///
/// Executes Python nonparametric.py methods via subprocess with JSON I/O.
/// Each method:
///   1. Serializes input data as JSON
///   2. Calls Python script with method name and args
///   3. Deserializes JSON response into typed Rust structs
///
/// This replaces direct Python imports with a clean subprocess boundary.
/// The Python script is self-contained and handles all computation.
use serde_json::{json, Value};
use std::process::Command;
use tracing::{debug, error, warn};

use super::types::*;

/// Path to the Python nonparametric module.
const PYTHON_SCRIPT: &str = "python/statistical/nonparametric_runner.py";

/// Bridge to Python nonparametric statistical methods.
pub struct NonparametricBridge {
    python_path: String,
    script_path: String,
}

impl NonparametricBridge {
    /// Create a new bridge with default paths.
    pub fn new() -> Self {
        Self {
            python_path: "python3".to_string(),
            script_path: PYTHON_SCRIPT.to_string(),
        }
    }

    /// Create with custom Python path (e.g., virtualenv).
    pub fn with_python(python_path: &str, script_path: &str) -> Self {
        Self {
            python_path: python_path.to_string(),
            script_path: script_path.to_string(),
        }
    }

    /// Execute a Python method and return raw JSON value.
    fn execute_python(&self, method: &str, args: Value) -> Result<Value, String> {
        let input = json!({
            "method": method,
            "args": args
        });

        debug!(method = method, "Executing Python statistical method");

        let output = Command::new(&self.python_path)
            .arg(&self.script_path)
            .arg(input.to_string())
            .output()
            .map_err(|e| {
                error!(error = %e, "Failed to execute Python");
                format!("Failed to execute Python: {}", e)
            })?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            error!(stderr = %stderr, "Python script failed");
            return Err(format!("Python error: {}", stderr));
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        serde_json::from_str(&stdout).map_err(|e| {
            error!(error = %e, stdout = %stdout, "Failed to parse Python output");
            format!("JSON parse error: {}", e)
        })
    }

    /// Mann-Whitney U test — non-parametric two-sample comparison.
    pub fn mann_whitney(
        &self,
        sample1: &[f64],
        sample2: &[f64],
        alternative: &str,
    ) -> Result<MannWhitneyResult, String> {
        let result = self.execute_python(
            "mann_whitney",
            json!({
                "sample1": sample1,
                "sample2": sample2,
                "alternative": alternative
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Kruskal-Wallis test — non-parametric multi-group comparison.
    pub fn kruskal_wallis(&self, groups: &[Vec<f64>]) -> Result<KruskalWallisResult, String> {
        let result = self.execute_python(
            "kruskal_wallis",
            json!({
                "groups": groups
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Bootstrap confidence interval for any statistic.
    pub fn bootstrap_ci(
        &self,
        data: &[f64],
        statistic: &str,
        n_bootstrap: usize,
        confidence: f64,
    ) -> Result<BootstrapResult, String> {
        let result = self.execute_python(
            "bootstrap_ci",
            json!({
                "data": data,
                "statistic": statistic,
                "n_bootstrap": n_bootstrap,
                "confidence": confidence
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Permutation test for two samples.
    pub fn permutation_test(
        &self,
        sample1: &[f64],
        sample2: &[f64],
        n_permutations: usize,
        alternative: &str,
    ) -> Result<PermutationResult, String> {
        let result = self.execute_python(
            "permutation_test",
            json!({
                "sample1": sample1,
                "sample2": sample2,
                "n_permutations": n_permutations,
                "alternative": alternative
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Power analysis for sample size determination.
    pub fn power_analysis(
        &self,
        effect_size: f64,
        alpha: f64,
        power: f64,
        test_type: &str,
    ) -> Result<PowerAnalysisResult, String> {
        let result = self.execute_python(
            "power_analysis",
            json!({
                "effect_size": effect_size,
                "alpha": alpha,
                "power": power,
                "test_type": test_type
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Kernel density estimation with multimodality detection.
    pub fn kde(&self, data: &[f64], n_points: usize) -> Result<KDEResult, String> {
        let result = self.execute_python(
            "kde",
            json!({
                "data": data,
                "n_points": n_points
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Market concentration analysis (HHI, Gini).
    pub fn market_concentration(
        &self,
        market_shares: &[f64],
    ) -> Result<ConcentrationResult, String> {
        let result = self.execute_python(
            "market_concentration",
            json!({
                "market_shares": market_shares
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }
}

impl Default for NonparametricBridge {
    fn default() -> Self {
        Self::new()
    }
}
