use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use serde_json::Value;

/// Compute a JSON-merge-patch-style delta between two JSON strings.
///
/// Returns a JSON string representing the changes needed to go from `base` to `target`.
/// Fields present in target but not base are added; fields in base but not target are
/// set to null (deletion marker); changed fields get the new value.
#[pyfunction]
pub fn compute_delta(base_json: &str, target_json: &str) -> PyResult<String> {
    let base: Value = serde_json::from_str(base_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid base JSON: {e}")))?;
    let target: Value = serde_json::from_str(target_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid target JSON: {e}")))?;

    match (&base, &target) {
        (Value::Object(base_map), Value::Object(target_map)) => {
            let mut delta = serde_json::Map::new();

            // Keys in target
            for (key, target_val) in target_map {
                if let Some(base_val) = base_map.get(key) {
                    if base_val != target_val {
                        delta.insert(key.clone(), target_val.clone());
                    }
                } else {
                    delta.insert(key.clone(), target_val.clone());
                }
            }

            // Keys in base but not target → deletion
            for key in base_map.keys() {
                if !target_map.contains_key(key) {
                    delta.insert(key.clone(), Value::Null);
                }
            }

            serde_json::to_string(&Value::Object(delta))
                .map_err(|e| PyValueError::new_err(format!("Serialization error: {e}")))
        }
        _ => Err(PyValueError::new_err("Both inputs must be JSON objects")),
    }
}

/// Apply a delta (computed by `compute_delta`) to a base JSON string.
///
/// Returns the merged JSON string.
#[pyfunction]
pub fn apply_delta(base_json: &str, delta_json: &str) -> PyResult<String> {
    let mut base: Value = serde_json::from_str(base_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid base JSON: {e}")))?;
    let delta: Value = serde_json::from_str(delta_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid delta JSON: {e}")))?;

    match (&mut base, &delta) {
        (Value::Object(base_map), Value::Object(delta_map)) => {
            for (key, val) in delta_map {
                if val.is_null() {
                    base_map.remove(key);
                } else {
                    base_map.insert(key.clone(), val.clone());
                }
            }
            serde_json::to_string(&base)
                .map_err(|e| PyValueError::new_err(format!("Serialization error: {e}")))
        }
        _ => Err(PyValueError::new_err("Both inputs must be JSON objects")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn delta_add_change_remove() {
        let base = r#"{"a":1,"b":2,"c":3}"#;
        let target = r#"{"a":1,"b":5,"d":10}"#;
        let delta = compute_delta(base, target).unwrap();
        let result = apply_delta(base, &delta).unwrap();
        let result_v: serde_json::Value = serde_json::from_str(&result).unwrap();
        assert_eq!(result_v["a"], 1);
        assert_eq!(result_v["b"], 5);
        assert!(result_v.get("c").is_none()); // removed
        assert_eq!(result_v["d"], 10); // added
    }
}
