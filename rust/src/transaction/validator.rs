use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Validation result: (is_valid: bool, errors: list[str])
fn validate_inner(
    amount: f64,
    tx_type: &str,
    phone: Option<&str>,
    timestamp: Option<&str>,
) -> (bool, Vec<String>) {
    let mut errors = Vec::new();

    // Amount checks
    if amount <= 0.0 {
        errors.push("amount must be positive".to_string());
    }
    if amount > 999_999.0 {
        errors.push("amount exceeds M-Pesa single-transaction limit (KES 999,999)".to_string());
    }

    // Transaction type
    let valid_types = [
        "sent", "received", "paybill", "buygoods", "withdraw", "deposit",
        "loan", "fuliza", "send", "receive", "pay_bill", "buy_goods",
    ];
    if !valid_types.contains(&tx_type.to_lowercase().as_str()) {
        errors.push(format!("unknown tx_type: '{tx_type}'"));
    }

    // Phone format (Kenya)
    if let Some(p) = phone {
        let clean: String = p.chars().filter(|c| c.is_ascii_digit() || *c == '+').collect();
        let normalized = if clean.starts_with("+254") {
            clean[1..].to_string()
        } else if clean.starts_with("254") {
            clean
        } else if clean.starts_with('0') && clean.len() == 11 {
            format!("254{}", &clean[1..])
        } else {
            clean.clone()
        };

        if normalized.len() != 12 || !normalized.starts_with("254") {
            errors.push(format!("invalid Kenyan phone number: {p}"));
        }
    }

    // Timestamp sanity (basic format check)
    if let Some(ts) = timestamp {
        if ts.is_empty() {
            errors.push("timestamp is empty".to_string());
        }
    }

    (errors.is_empty(), errors)
}

/// Validate a transaction dict.
///
/// Args:
///     amount: Transaction amount (KES).
///     tx_type: Type string (sent, received, paybill, etc.).
///     phone: Optional phone number.
///     timestamp: Optional timestamp string.
///
/// Returns:
///     dict with `valid` (bool) and `errors` (list[str]).
#[pyfunction]
#[pyo3(signature = (amount, tx_type, phone=None, timestamp=None))]
pub fn validate_transaction(
    py: Python<'_>,
    amount: f64,
    tx_type: &str,
    phone: Option<&str>,
    timestamp: Option<&str>,
) -> PyResult<PyObject> {
    let (valid, errors) = validate_inner(amount, tx_type, phone, timestamp);
    let dict = pyo3::types::PyDict::new_bound(py);
    dict.set_item("valid", valid)?;
    dict.set_item("errors", errors)?;
    Ok(dict.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_tx() {
        let (ok, errs) = validate_inner(500.0, "sent", Some("0712345678"), None);
        assert!(ok, "{:?}", errs);
    }

    #[test]
    fn negative_amount() {
        let (ok, _) = validate_inner(-10.0, "sent", None, None);
        assert!(!ok);
    }

    #[test]
    fn bad_type() {
        let (ok, _) = validate_inner(100.0, "bitcoin_mining", None, None);
        assert!(!ok);
    }

    #[test]
    fn bad_phone() {
        let (ok, _) = validate_inner(100.0, "sent", Some("12345"), None);
        assert!(!ok);
    }
}
