/// Multivariate Bridge — connects Rust backend to Python multivariate analysis methods.
///
/// Executes Python multivariate_runner.py methods via subprocess with JSON I/O.
/// Methods: PCA, DBSCAN, LDA, QDA, MANOVA

use serde_json::{json, Value};
use std::process::Command;
use tracing::{debug, error};

use super::types::*;

/// Path to the Python multivariate runner.
const PYTHON_SCRIPT: &str = "python/statistical/multivariate_runner.py";

/// Bridge to Python multivariate analysis methods.
pub struct MultivariateBridge {
    python_path: String,
    script_path: String,
}

impl MultivariateBridge {
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

        debug!(method = method, "Executing Python multivariate method");

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

    /// PCA — Principal Component Analysis for feature reduction.
    ///
    /// Reduces p-dimensional data to k principal components capturing
    /// maximum variance. Used for worker profile dimensionality reduction.
    pub fn pca(
        &self,
        data: &[Vec<f64>],
        n_components: Option<usize>,
    ) -> Result<PCAResult, String> {
        let result = self.execute_python(
            "pca",
            json!({
                "data": data,
                "n_components": n_components
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// DBSCAN — Density-based clustering for anomaly detection.
    ///
    /// Groups points by density, identifies noise (potential fraud/errors).
    /// No assumption on cluster shape or count.
    pub fn dbscan(
        &self,
        data: &[Vec<f64>],
        eps: f64,
        min_pts: usize,
    ) -> Result<DBSCANResult, String> {
        let result = self.execute_python(
            "dbscan",
            json!({
                "data": data,
                "eps": eps,
                "min_pts": min_pts
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// LDA — Linear Discriminant Analysis for classification.
    ///
    /// Assumes equal covariance matrices. Decision boundary is linear.
    /// Used for credit score classification (creditworthy vs not).
    pub fn lda(
        &self,
        x: &[Vec<f64>],
        y: &[i32],
        x_new: Option<&[Vec<f64>]>,
    ) -> Result<LDAResult, String> {
        let mut args = json!({
            "X": x,
            "y": y
        });

        if let Some(new_data) = x_new {
            args["X_new"] = json!(new_data);
        }

        let result = self.execute_python("lda", args)?;
        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// QDA — Quadratic Discriminant Analysis for classification.
    ///
    /// Like LDA but allows different covariance per class.
    /// Decision boundary is quadratic — more flexible than LDA.
    pub fn qda(
        &self,
        x: &[Vec<f64>],
        y: &[i32],
    ) -> Result<QDAResult, String> {
        let result = self.execute_python(
            "qda",
            json!({
                "X": x,
                "y": y
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }

    /// MANOVA — Multivariate Analysis of Variance.
    ///
    /// Tests whether group means differ across multiple dependent variables.
    /// Extension of ANOVA to multivariate response (Wilks' Lambda).
    pub fn manova(
        &self,
        groups: &[Vec<Vec<f64>>],
    ) -> Result<MANOVAResult, String> {
        let result = self.execute_python(
            "manova",
            json!({
                "groups": groups
            }),
        )?;

        serde_json::from_value(result).map_err(|e| format!("Deserialization error: {}", e))
    }
}

impl Default for MultivariateBridge {
    fn default() -> Self {
        Self::new()
    }
}
