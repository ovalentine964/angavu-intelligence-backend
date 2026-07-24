use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rayon::prelude::*;

/// Compute dot products of one vector against many candidates in parallel.
///
/// Returns a list of scalar dot products.
#[pyfunction]
pub fn batch_dot_product(query: Vec<f64>, candidates: Vec<Vec<f64>>) -> PyResult<Vec<f64>> {
    let dim = query.len();

    for (i, c) in candidates.iter().enumerate() {
        if c.len() != dim {
            return Err(PyValueError::new_err(format!(
                "Candidate {i} dimension {} != query dimension {dim}",
                c.len()
            )));
        }
    }

    let results: Vec<f64> = candidates
        .par_iter()
        .map(|c| {
            let mut sum = 0.0_f64;
            for i in 0..dim {
                sum += query[i] * c[i];
            }
            sum
        })
        .collect();

    Ok(results)
}

/// L2-normalize a batch of vectors in parallel.
///
/// Each vector is divided by its L2 norm. Zero vectors remain zero.
/// Returns the normalized vectors.
#[pyfunction]
pub fn batch_normalize(vectors: Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    vectors
        .par_iter()
        .map(|v| {
            let norm_sq: f64 = v.iter().map(|x| x * x).sum();
            let norm = norm_sq.sqrt();
            if norm == 0.0 {
                v.clone()
            } else {
                v.iter().map(|x| x / norm).collect()
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dot_products() {
        let q = vec![1.0, 2.0, 3.0];
        let candidates = vec![
            vec![4.0, 5.0, 6.0],
            vec![1.0, 0.0, 0.0],
        ];
        let results = batch_dot_product(q, candidates).unwrap();
        assert!((results[0] - 32.0).abs() < 1e-10); // 1*4 + 2*5 + 3*6
        assert!((results[1] - 1.0).abs() < 1e-10);
    }

    #[test]
    fn normalize_unit() {
        let result = batch_normalize(vec![vec![3.0, 4.0]]);
        let norm_sq: f64 = result[0].iter().map(|x| x * x).sum();
        assert!((norm_sq - 1.0).abs() < 1e-10);
    }

    #[test]
    fn normalize_zero() {
        let result = batch_normalize(vec![vec![0.0, 0.0]]);
        assert_eq!(result[0], vec![0.0, 0.0]);
    }
}
