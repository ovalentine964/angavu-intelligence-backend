use pyo3::prelude::*;
use rayon::prelude::*;
use serde::Deserialize;

/// A transaction dict coming from Python.
#[derive(Debug, Deserialize)]
struct RawTransaction {
    id: String,
    amount: f64,
    tx_type: String,
    timestamp: Option<String>,
    phone: Option<String>,
    metadata: Option<String>,
}

/// Processed transaction result.
#[derive(Debug)]
struct ProcessedTx {
    id: String,
    amount: f64,
    tx_type: String,
    category: String,
    risk_score: f64,
    flags: Vec<String>,
}

fn categorize(tx_type: &str, amount: f64) -> (String, f64, Vec<String>) {
    let mut flags = Vec::new();
    let mut risk: f64 = 0.0;

    // High-value flag
    if amount > 70_000.0 {
        flags.push("high_value".to_string());
        risk += 0.3;
    }

    // Category from tx_type
    let category = match tx_type.to_lowercase().as_str() {
        "sent" | "send" => {
            if amount > 50_000.0 {
                risk += 0.1;
            }
            "transfer_out"
        }
        "received" | "receive" => "transfer_in",
        "paybill" | "pay_bill" => "bill_payment",
        "buygoods" | "buy_goods" | "till" => "merchant_payment",
        "withdraw" => "cash_withdrawal",
        "deposit" => "cash_deposit",
        "loan" | "fuliza" | "kcb_mpesa" => {
            risk += 0.2;
            flags.push("credit".to_string());
            "credit"
        }
        _ => "other",
    }
    .to_string();

    // Normalize risk to 0..1
    if risk > 1.0 {
        risk = 1.0;
    }

    (category, risk, flags)
}

/// Process a batch of transaction dicts in parallel using rayon.
///
/// Each dict must have: id, amount, tx_type (string).
/// Optional: timestamp, phone, metadata.
///
/// Returns a list of dicts with: id, amount, tx_type, category, risk_score, flags.
#[pyfunction]
pub fn process_transactions_batch(py: Python<'_>, transactions: Vec<PyObject>) -> PyResult<PyObject> {
    // Deserialize in parallel
    let raw_txs: Vec<RawTransaction> = transactions
        .iter()
        .map(|obj| {
            Python::with_gil(|py| {
                let json_str: String = py
                    .import_bound("json")
                    .and_then(|json| json.call_method1("dumps", (obj,)) )
                    .and_then(|s| s.extract())?;
                serde_json::from_str(&json_str)
                    .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Deserialization error: {e}")))
            })
        })
        .collect::<PyResult<Vec<_>>>()?;

    // Process in parallel (no GIL needed)
    let processed: Vec<(String, f64, String, f64, Vec<String>)> = raw_txs
        .par_iter()
        .map(|tx| {
            let (cat, risk, flags) = categorize(&tx.tx_type, tx.amount);
            (tx.id.clone(), tx.amount, cat, risk, flags)
        })
        .collect();

    // Build Python results
    let results: Vec<PyObject> = Python::with_gil(|py| {
        processed
            .iter()
            .map(|(id, amount, cat, risk, flags)| {
                let dict = pyo3::types::PyDict::new_bound(py);
                dict.set_item("id", id)?;
                dict.set_item("amount", amount)?;
                dict.set_item("tx_type", &raw_txs.iter().find(|t| &t.id == id).map(|t| t.tx_type.clone()).unwrap_or_default())?;
                dict.set_item("category", cat)?;
                dict.set_item("risk_score", risk)?;
                dict.set_item("flags", flags)?;
                Ok(dict.into())
            })
            .collect::<PyResult<Vec<_>>>()
    })?;

    Ok(results.into_py(py))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn categorize_high_value() {
        let (cat, risk, flags) = categorize("sent", 100_000.0);
        assert_eq!(cat, "transfer_out");
        assert!(risk > 0.0);
        assert!(flags.contains(&"high_value".to_string()));
    }

    #[test]
    fn categorize_normal() {
        let (cat, risk, flags) = categorize("received", 500.0);
        assert_eq!(cat, "transfer_in");
        assert_eq!(risk, 0.0);
        assert!(flags.is_empty());
    }
}
