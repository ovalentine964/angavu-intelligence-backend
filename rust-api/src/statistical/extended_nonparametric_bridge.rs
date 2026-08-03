/// Extended Nonparametric Bridge — advanced non-parametric methods.
///
/// Executes Python nonparametric_extended_runner.py methods via subprocess.
/// Methods: Friedman test, Kolmogorov-Smirnov, Anderson-Darling,
/// LOESS regression, Bootstrap BCa, Spline regression.
use serde_json::{json, Value};
use std::process::Command;
use tracing::{debug, error};

use super::types::*;

/// Path to the Python extended nonparametric runner.
const PYTHON_SCRIPT: &str = "python/statistical/nonparametric_extended_runner.py";

/// Bridge to Python extended nonparametric methods.
pub struct ExtendedNonparametricBridge {
    python_path: String,
    script_path: String,
}

impl ExtendedNonparametricBridge {
    /// Create a new bridge with default paths.
    pub fn new() -> Self {
        Self {
            python_path: "python3".to_string(),
            script_path: PYTHON_SCRIPT.to_string(),
        }
    }

    /// Create with custom Python path.
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

        debug!(
            method = method,
            "Executing Python extended nonparametric method"
        );

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

    /// Friedman test — non-parametric repeated measures.
    ///
    /// Tests whether k treatments differ across n blocks, using ranks.
    /// Extension of sign test to multiple treatments.
    /// Application: Compare worker income across repeated time periods.
    pub fn friedman(&self, data: &[Vec<f64>]) -> Result<FriedmanResult, String> {
        let result = self.execute_python("friedman", json!({ "data": data }))?;
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// One-sample Kolmogorov-Smirnov test — distribution goodness-of-fit.
    ///
    /// Tests whether a sample comes from a specified distribution.
    /// D = sup|F_n(x) - F_0(x)|
    pub fn ks_one_sample(&self, data: &[f64], distribution: &str) -> Result<KSResult, String> {
        let result = self.execute_python(
            "ks_one_sample",
            json!({
                "data": data,
                "distribution": distribution
            }),
        )?;
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Two-sample Kolmogorov-Smirnov test.
    ///
    /// Tests whether two samples come from the same distribution.
    pub fn ks_two_sample(&self, sample1: &[f64], sample2: &[f64]) -> Result<KSResult, String> {
        let result = self.execute_python(
            "ks_two_sample",
            json!({
                "sample1": sample1,
                "sample2": sample2
            }),
        )?;
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Anderson-Darling test — distribution fit assessment.
    ///
    /// More sensitive to tail deviations than KS test.
    /// Critical for credit risk tail assessment.
    pub fn anderson_darling(
        &self,
        data: &[f64],
        distribution: &str,
    ) -> Result<AndersonDarlingResult, String> {
        let result = self.execute_python(
            "anderson_darling",
            json!({
                "data": data,
                "distribution": distribution
            }),
        )?;
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// LOESS regression — non-parametric local polynomial regression.
    ///
    /// Smooths data without assuming a global functional form.
    /// Application: Income trends, seasonality, credit calibration curves.
    pub fn loess(
        &self,
        x: &[f64],
        y: &[f64],
        span: f64,
        degree: usize,
        n_points: usize,
    ) -> Result<LOESSResult, String> {
        let result = self.execute_python(
            "loess",
            json!({
                "x": x,
                "y": y,
                "span": span,
                "degree": degree,
                "n_points": n_points
            }),
        )?;
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Bootstrap BCa — bias-corrected accelerated confidence intervals.
    ///
    /// Second-order accurate bootstrap CIs that correct for bias and skewness.
    /// More accurate than percentile bootstrap for skewed statistics.
    pub fn bootstrap_bca(
        &self,
        data: &[f64],
        statistic: &str,
        n_bootstrap: usize,
        confidence: f64,
    ) -> Result<BootstrapBCaResult, String> {
        let result = self.execute_python(
            "bootstrap_bca",
            json!({
                "data": data,
                "statistic": statistic,
                "n_bootstrap": n_bootstrap,
                "confidence": confidence
            }),
        )?;
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// Spline regression — non-parametric cubic smoothing splines.
    ///
    /// Fits smooth curve by minimizing penalized residual sum of squares.
    /// Application: Credit score calibration, income trend smoothing.
    pub fn spline_regression(
        &self,
        x: &[f64],
        y: &[f64],
        smoothing_factor: Option<f64>,
        n_points: usize,
    ) -> Result<SplineResult, String> {
        let result = self.execute_python(
            "spline_regression",
            json!({
                "x": x,
                "y": y,
                "smoothing_factor": smoothing_factor,
                "n_points": n_points
            }),
        )?;
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }
}

impl Default for ExtendedNonparametricBridge {
    fn default() -> Self {
        Self::new()
    }
}
