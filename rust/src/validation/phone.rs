use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Validate a Kenyan phone number.
///
/// Accepted formats:
///   - 07XXXXXXXX  (10 digits)
///   - 01XXXXXXXX  (10 digits)
///   - +2547XXXXXXX  (13 chars)
///   - 2547XXXXXXX  (12 digits)
///
/// Returns true if valid.
#[pyfunction]
pub fn validate_phone_ke(phone: &str) -> bool {
    let clean: String = phone.chars().filter(|c| c.is_ascii_digit() || *c == '+').collect();

    // +2547XXXXXXXXX
    if clean.starts_with("+254") && clean.len() == 13 {
        let rest = &clean[4..];
        return rest.starts_with('7') || rest.starts_with('1') || rest.starts_with('0');
    }

    // 2547XXXXXXXXX
    if clean.starts_with("254") && clean.len() == 12 {
        let rest = &clean[3..];
        return rest.starts_with('7') || rest.starts_with('1') || rest.starts_with('0');
    }

    // 07XXXXXXXX or 01XXXXXXXX
    if clean.starts_with('0') && clean.len() == 10 {
        let second = clean.chars().nth(1).unwrap_or('x');
        return second == '7' || second == '1' || second == '0';
    }

    false
}

/// Normalize a Kenyan phone number to 2547XXXXXXXX format (12 digits).
///
/// Raises ValueError if the phone number is invalid.
#[pyfunction]
pub fn normalize_phone_ke(phone: &str) -> PyResult<String> {
    if !validate_phone_ke(phone) {
        return Err(PyValueError::new_err(format!("Invalid Kenyan phone number: {phone}")));
    }

    let clean: String = phone.chars().filter(|c| c.is_ascii_digit() || *c == '+').collect();

    if clean.starts_with("+254") {
        Ok(clean[1..].to_string()) // strip leading +
    } else if clean.starts_with("254") {
        Ok(clean)
    } else if clean.starts_with('0') {
        Ok(format!("254{}", &clean[1..]))
    } else {
        Err(PyValueError::new_err(format!("Cannot normalize phone: {phone}")))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_formats() {
        assert!(validate_phone_ke("0712345678"));
        assert!(validate_phone_ke("+254712345678"));
        assert!(validate_phone_ke("254712345678"));
        assert!(validate_phone_ke("0112345678"));
        assert!(validate_phone_ke("+254112345678"));
    }

    #[test]
    fn invalid_formats() {
        assert!(!validate_phone_ke("12345"));
        assert!(!validate_phone_ke("0612345678"));
        assert!(!validate_phone_ke("+1234567890"));
        assert!(!validate_phone_ke(""));
        assert!(!validate_phone_ke("not a number"));
    }

    #[test]
    fn normalize_from_local() {
        assert_eq!(normalize_phone_ke("0712345678").unwrap(), "254712345678");
    }

    #[test]
    fn normalize_from_plus() {
        assert_eq!(normalize_phone_ke("+254712345678").unwrap(), "254712345678");
    }

    #[test]
    fn normalize_from_254() {
        assert_eq!(normalize_phone_ke("254712345678").unwrap(), "254712345678");
    }

    #[test]
    fn normalize_invalid() {
        assert!(normalize_phone_ke("12345").is_err());
    }
}
