use pyo3::prelude::*;
use regex::Regex;
use serde::Deserialize;

/// Parsed M-Pesa transaction fields.
#[derive(Debug, Clone, PartialEq)]
struct MpesaTx {
    tx_code: Option<String>,
    amount: Option<f64>,
    phone: Option<String>,
    name: Option<String>,
    tx_date: Option<String>,
    balance: Option<f64>,
    tx_type: String, // "sent" | "received" | "withdraw" | "deposit" | "paybill" | "buygoods" | "unknown"
}

fn parse_single_sms(sms: &str) -> MpesaTx {
    let sms_upper = sms.to_uppercase();

    // Transaction code: 8-10 alphanumeric at start or after whitespace
    let code_re = Regex::new(r"(?i)\b([A-Z0-9]{8,10})\b").unwrap();
    let tx_code = code_re
        .find(sms)
        .map(|m| m.as_str().to_string());

    // Amount: "Ksh" or "KES" followed by number
    let amt_re = Regex::new(r"(?i)(?:KSH|KES)\s*([\d,]+(?:\.\d{1,2})?)").unwrap();
    let amount = amt_re
        .captures(sms)
        .and_then(|c| c.get(1))
        .and_then(|m| m.as_str().replace(',', "").parse::<f64>().ok());

    // Phone: 07XXXXXXXX or +2547XXXXXXXX or 2547XXXXXXXX
    let phone_re = Regex::new(r"(\+?254[17]\d{8}|0[17]\d{8})").unwrap();
    let phone = phone_re
        .find(sms)
        .map(|m| m.as_str().to_string());

    // Name: typically after "from" or "to" keywords
    let name_re = Regex::new(r"(?i)(?:from|to|confirmed on)\s+([A-Z][A-Za-z\s]+?)(?:\s+on\s|\s+Ref|\s*$)").unwrap();
    let name = name_re
        .captures(sms)
        .and_then(|c| c.get(1))
        .map(|m| m.as_str().trim().to_string());

    // Date: DD/MM/YY or DD/MM/YYYY HH:MM
    let date_re = Regex::new(r"\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}(?:\s?[AP]M)?").unwrap();
    let tx_date = date_re.find(sms).map(|m| m.as_str().to_string());

    // Balance: "New M-PESA balance is Ksh X" or similar
    let bal_re = Regex::new(r"(?i)balance\s+(?:is\s+)?(?:KSH|KES)\s*([\d,]+(?:\.\d{1,2})?)").unwrap();
    let balance = bal_re
        .captures(sms)
        .and_then(|c| c.get(1))
        .and_then(|m| m.as_str().replace(',', "").parse::<f64>().ok());

    // Classify transaction type
    let tx_type = if sms_upper.contains("SENT TO") || sms_upper.contains("SEND MONEY") {
        "sent"
    } else if sms_upper.contains("RECEIVED") || sms_upper.contains("YOU HAVE RECEIVED") {
        "received"
    } else if sms_upper.contains("WITHDRAW") {
        "withdraw"
    } else if sms_upper.contains("DEPOSIT") || sms_upper.contains("CR ") {
        "deposit"
    } else if sms_upper.contains("PAY BILL") || sms_upper.contains("PAYBILL") {
        "paybill"
    } else if sms_upper.contains("BUY GOODS") || sms_upper.contains("TILL NUMBER") {
        "buygoods"
    } else {
        "unknown"
    }
    .to_string();

    MpesaTx {
        tx_code,
        amount,
        phone,
        name,
        tx_date,
        balance,
        tx_type,
    }
}

fn tx_to_pydict(py: Python<'_>, tx: &MpesaTx) -> PyResult<PyObject> {
    let dict = pyo3::types::PyDict::new_bound(py);
    if let Some(ref c) = tx.tx_code {
        dict.set_item("tx_code", c)?;
    } else {
        dict.set_item("tx_code", py.None())?;
    }
    if let Some(a) = tx.amount {
        dict.set_item("amount", a)?;
    } else {
        dict.set_item("amount", py.None())?;
    }
    if let Some(ref p) = tx.phone {
        dict.set_item("phone", p)?;
    } else {
        dict.set_item("phone", py.None())?;
    }
    if let Some(ref n) = tx.name {
        dict.set_item("name", n)?;
    } else {
        dict.set_item("name", py.None())?;
    }
    if let Some(ref d) = tx.tx_date {
        dict.set_item("tx_date", d)?;
    } else {
        dict.set_item("tx_date", py.None())?;
    }
    if let Some(b) = tx.balance {
        dict.set_item("balance", b)?;
    } else {
        dict.set_item("balance", py.None())?;
    }
    dict.set_item("tx_type", &tx.tx_type)?;
    Ok(dict.into())
}

/// Parse a single M-Pesa SMS into a dict with fields:
///   tx_code, amount, phone, name, tx_date, balance, tx_type
#[pyfunction]
pub fn parse_mpesa_sms(py: Python<'_>, sms: &str) -> PyResult<PyObject> {
    let tx = parse_single_sms(sms);
    tx_to_pydict(py, &tx)
}

/// Parse a batch of M-Pesa SMS strings. Returns list of dicts.
#[pyfunction]
pub fn parse_mpesa_sms_batch(py: Python<'_>, sms_list: Vec<String>) -> PyResult<PyObject> {
    let results: Vec<PyObject> = sms_list
        .iter()
        .map(|sms| {
            let tx = parse_single_sms(sms);
            tx_to_pydict(py, &tx)
        })
        .collect::<PyResult<Vec<_>>>()?;
    Ok(results.into_py(py))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_sent() {
        let tx = parse_single_sms(
            "QJ74ABC1234 Confirmed. Ksh1,500.00 sent to John Doe 0712345678 on 15/6/24 at 2:30 PM. New M-PESA balance is Ksh5,000.00.",
        );
        assert_eq!(tx.tx_type, "sent");
        assert_eq!(tx.amount, Some(1500.0));
        assert_eq!(tx.phone, Some("0712345678".to_string()));
    }

    #[test]
    fn parse_received() {
        let tx = parse_single_sms(
            "QJ74XYZ9876 Confirmed. You have received Ksh3,200.00 from Jane Smith 0798765432. New M-PESA balance is Ksh8,200.00.",
        );
        assert_eq!(tx.tx_type, "received");
        assert_eq!(tx.amount, Some(3200.0));
    }
}
