use pyo3::prelude::*;
use regex::Regex;

/// Sanitize a single input string against:
/// - SQL injection patterns
/// - XSS / HTML injection
/// - Path traversal
/// - Null bytes
///
/// Returns the sanitized string with dangerous patterns removed/escaped.
#[pyfunction]
pub fn sanitize_input(input: &str) -> String {
    let mut out = input.to_string();

    // Remove null bytes
    out = out.replace('\0', "");

    // SQL injection: strip common injection patterns
    let sql_patterns: Vec<(&str, &str)> = vec![
        (r"(?i)(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|EXECUTE)\b)", ""),
        (r"(?i)(--|/\*|\*/)", ""),
        (r"(?i)(\bOR\b\s+\d+\s*=\s*\d+)", ""),
        (r"(?i)(\bAND\b\s+\d+\s*=\s*\d+)", ""),
        ("[\'\"\\\\]", ""),
        (r";", ""),
    ];

    for (pattern, replacement) in &sql_patterns {
        if let Ok(re) = Regex::new(pattern) {
            out = re.replace_all(&out, *replacement).to_string();
        }
    }

    // XSS: escape angle brackets and event handlers
    out = out.replace('<', "&lt;");
    out = out.replace('>', "&gt;");
    out = out.replace("\"", "&quot;");
    out = out.replace("'", "&#x27;");

    // Path traversal
    let traversal_re = Regex::new(r"\.\./").unwrap();
    out = traversal_re.replace_all(&out, "").to_string();

    // Trim excessive whitespace
    let ws_re = Regex::new(r"\s{3,}").unwrap();
    out = ws_re.replace_all(&out, "  ").to_string();

    out
}

/// Sanitize a batch of input strings in parallel.
#[pyfunction]
pub fn sanitize_input_batch(inputs: Vec<String>) -> Vec<String> {
    use rayon::prelude::*;
    inputs.par_iter().map(|s| sanitize_input(s)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_sql_injection() {
        let result = sanitize_input("'; DROP TABLE users; --");
        assert!(!result.contains("DROP"));
        assert!(!result.contains("TABLE"));
    }

    #[test]
    fn escapes_xss() {
        let result = sanitize_input("<script>alert('xss')</script>");
        assert!(!result.contains("<script>"));
        assert!(result.contains("&lt;"));
    }

    #[test]
    fn preserves_clean_input() {
        let result = sanitize_input("John Doe");
        assert_eq!(result, "John Doe");
    }

    #[test]
    fn removes_null_bytes() {
        let result = sanitize_input("hello\0world");
        assert_eq!(result, "helloworld");
    }

    #[test]
    fn path_traversal() {
        let result = sanitize_input("../../etc/passwd");
        assert!(!result.contains("../"));
    }
}
