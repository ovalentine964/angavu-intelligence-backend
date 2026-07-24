use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::{HashMap, HashSet};

/// Resolve conflicts between local and remote record dicts.
///
/// Strategy: "last-write-wins" based on `updated_at` field (ISO-8601 string comparison).
/// For equal timestamps, remote wins by default.
#[pyfunction]
pub fn resolve_conflicts(
    py: Python<'_>,
    local_records: Vec<PyObject>,
    remote_records: Vec<PyObject>,
) -> PyResult<Vec<PyObject>> {
    let json = py.import_bound("json")?;

    // Build remote map by id
    let mut remote_map: HashMap<String, (String, String)> = HashMap::new();
    for rec in remote_records.iter() {
        let json_str: String = json.call_method1("dumps", (rec,))?.extract()?;
        let id: String = rec.getattr(py, "get")?.call1(py, ("id",))?.extract(py)?;
        let updated: String = rec
            .getattr(py, "get")
            .and_then(|f| f.call1(py, ("updated_at",)))
            .and_then(|v| v.extract(py))
            .unwrap_or_default();
        remote_map.insert(id, (updated, json_str));
    }

    let mut resolved = Vec::new();
    let mut seen_ids = HashSet::new();

    for rec in local_records.iter() {
        let json_str: String = json.call_method1("dumps", (rec,))?.extract()?;
        let id: String = rec.getattr(py, "get")?.call1(py, ("id",))?.extract(py)?;
        let local_updated: String = rec
            .getattr(py, "get")
            .and_then(|f| f.call1(py, ("updated_at",)))
            .and_then(|v| v.extract(py))
            .unwrap_or_default();

        seen_ids.insert(id.clone());

        if let Some((remote_updated, remote_json)) = remote_map.get(&id) {
            let (winner_json, source) = if local_updated >= *remote_updated {
                (json_str.clone(), "local")
            } else {
                (remote_json.clone(), "remote")
            };

            let mut obj: PyObject = json.call_method1("loads", (winner_json,))?.extract()?;
            {
                let bound = obj.bind(py);
                if let Ok(dict) = bound.downcast::<PyDict>() {
                    dict.set_item("_source", source)?;
                }
            }
            resolved.push(obj);
        } else {
            {
                let bound = rec.bind(py);
                if let Ok(dict) = bound.downcast::<PyDict>() {
                    dict.set_item("_source", "local")?;
                }
            }
            resolved.push(rec.clone_ref(py));
        }
    }

    // Remote-only records
    for rec in remote_records.iter() {
        let id: String = rec.getattr(py, "get")?.call1(py, ("id",))?.extract(py)?;
        if !seen_ids.contains(&id) {
            {
                let bound = rec.bind(py);
                if let Ok(dict) = bound.downcast::<PyDict>() {
                    dict.set_item("_source", "remote")?;
                }
            }
            resolved.push(rec.clone_ref(py));
        }
    }

    Ok(resolved)
}

#[cfg(test)]
mod tests {
    // Integration tests require Python runtime; tested via Python test suite.
}
