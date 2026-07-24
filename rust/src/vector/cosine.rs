use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rayon::prelude::*;

/// Compute cosine similarity between two vectors.
///
/// Returns a float in [-1, 1]. Returns 0.0 for zero-magnitude vectors.
#[pyfunction]
pub fn cosine_similarity(a: Vec<f64>, b: Vec<f64>) -> PyResult<f64> {
    if a.len() != b.len() {
        return Err(PyValueError::new_err(format!(
            "Vector dimension mismatch: {} vs {}",
            a.len(),
            b.len()
        )));
    }

    if a.is_empty() {
        return Ok(0.0);
    }

    let mut dot = 0.0_f64;
    let mut norm_a = 0.0_f64;
    let mut norm_b = 0.0_f64;

    for i in 0..a.len() {
        dot += a[i] * b[i];
        norm_a += a[i] * a[i];
        norm_b += b[i] * b[i];
    }

    let denom = norm_a.sqrt() * norm_b.sqrt();
    if denom == 0.0 {
        return Ok(0.0);
    }

    Ok(dot / denom)
}

/// Compute cosine similarity between one query vector and many candidate vectors.
///
/// Returns a list of floats, one per candidate.
#[pyfunction]
pub fn cosine_similarity_batch(query: Vec<f64>, candidates: Vec<Vec<f64>>) -> PyResult<Vec<f64>> {
    let dim = query.len();

    // Validate dimensions
    for (i, c) in candidates.iter().enumerate() {
        if c.len() != dim {
            return Err(PyValueError::new_err(format!(
                "Candidate {i} has dimension {}, expected {dim}",
                c.len()
            )));
        }
    }

    if dim == 0 || candidates.is_empty() {
        return Ok(vec![0.0; candidates.len()]);
    }

    // Precompute query norm
    let q_norm_sq: f64 = query.iter().map(|x| x * x).sum();
    let q_norm = q_norm_sq.sqrt();

    if q_norm == 0.0 {
        return Ok(vec![0.0; candidates.len()]);
    }

    // Parallel computation
    let results: Vec<f64> = candidates
        .par_iter()
        .map(|c| {
            let mut dot = 0.0_f64;
            let mut c_norm_sq = 0.0_f64;
            for i in 0..dim {
                dot += query[i] * c[i];
                c_norm_sq += c[i] * c[i];
            }
            let c_norm = c_norm_sq.sqrt();
            if c_norm == 0.0 {
                0.0
            } else {
                dot / (q_norm * c_norm)
            }
        })
        .collect();

    Ok(results)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identical_vectors() {
        let sim = cosine_similarity(vec![1.0, 2.0, 3.0], vec![1.0, 2.0, 3.0]).unwrap();
        assert!((sim - 1.0).abs() < 1e-10);
    }

    #[test]
    fn orthogonal_vectors() {
        let sim = cosine_similarity(vec![1.0, 0.0], vec![0.0, 1.0]).unwrap();
        assert!((sim - 0.0).abs() < 1e-10);
    }

    #[test]
    fn opposite_vectors() {
        let sim = cosine_similarity(vec![1.0, 0.0], vec![-1.0, 0.0]).unwrap();
        assert!((sim - (-1.0)).abs() < 1e-10);
    }

    #[test]
    fn batch_works() {
        let q = vec![1.0, 0.0];
        let candidates = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![-1.0, 0.0]];
        let results = cosine_similarity_batch(q, candidates).unwrap();
        assert!((results[0] - 1.0).abs() < 1e-10);
        assert!((results[1] - 0.0).abs() < 1e-10);
        assert!((results[2] - (-1.0)).abs() < 1e-10);
    }
}
