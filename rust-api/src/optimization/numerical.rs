//! Numerical Methods — Newton-Raphson, Simpson's Rule, Interpolation.
//!
//! Core numerical algorithms for model solving, integration, and estimation.

use serde::{Deserialize, Serialize};

/// Result of a root-finding computation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RootResult {
    pub root: f64,
    pub iterations: usize,
    pub converged: bool,
    pub residual: f64,
}

/// Newton-Raphson root finding.
///
/// Finds x such that f(x) = 0 using iterative refinement:
/// x_{n+1} = x_n - f(x_n) / f'(x_n)
///
/// # Arguments
/// * `f` - Function to find root of
/// * `df` - Derivative of f
/// * `x0` - Initial guess
/// * `tolerance` - Convergence tolerance
/// * `max_iterations` - Maximum iterations
pub fn newton_raphson(
    f: impl Fn(f64) -> f64,
    df: impl Fn(f64) -> f64,
    x0: f64,
    tolerance: f64,
    max_iterations: usize,
) -> RootResult {
    let mut x = x0;

    for i in 0..max_iterations {
        let fx = f(x);
        let dfx = df(x);

        if fx.abs() < tolerance {
            return RootResult {
                root: x,
                iterations: i,
                converged: true,
                residual: fx,
            };
        }

        if dfx.abs() < 1e-15 {
            // Derivative too small, try numerical derivative
            let h = 1e-8;
            let dfx_numerical = (f(x + h) - f(x - h)) / (2.0 * h);
            if dfx_numerical.abs() < 1e-15 {
                return RootResult {
                    root: x,
                    iterations: i,
                    converged: false,
                    residual: fx,
                };
            }
            x -= fx / dfx_numerical;
        } else {
            x -= fx / dfx;
        }
    }

    RootResult {
        root: x,
        iterations: max_iterations,
        converged: f(x).abs() < tolerance * 100.0,
        residual: f(x),
    }
}

/// Newton-Raphson with numerical derivative (when analytical derivative is unavailable).
pub fn newton_raphson_numerical(
    f: impl Fn(f64) -> f64,
    x0: f64,
    tolerance: f64,
    max_iterations: usize,
) -> RootResult {
    let h = 1e-8;
    newton_raphson(
        |x| f(x),
        move |x| (f(x + h) - f(x - h)) / (2.0 * h),
        x0,
        tolerance,
        max_iterations,
    )
}

/// Numerical integration using Simpson's 1/3 Rule.
///
/// Approximates ∫_a^b f(x) dx using quadratic interpolation:
/// ∫ ≈ (h/3) * [f(x₀) + 4f(x₁) + 2f(x₂) + 4f(x₃) + ... + f(xₙ)]
///
/// # Arguments
/// * `f` - Function to integrate
/// * `a` - Lower bound
/// * `b` - Upper bound
/// * `n` - Number of subintervals (must be even)
pub fn simpsons_rule(f: impl Fn(f64) -> f64, a: f64, b: f64, n: usize) -> f64 {
    let n = if n % 2 == 0 { n } else { n + 1 }; // Ensure even
    let h = (b - a) / n as f64;

    let mut sum = f(a) + f(b);

    for i in 1..n {
        let x = a + i as f64 * h;
        if i % 2 == 0 {
            sum += 2.0 * f(x);
        } else {
            sum += 4.0 * f(x);
        }
    }

    sum * h / 3.0
}

/// Adaptive Simpson's rule with error estimation.
///
/// Recursively refines intervals where the error estimate is large.
pub fn adaptive_simpsons(
    f: impl Fn(f64) -> f64 + Copy,
    a: f64,
    b: f64,
    tolerance: f64,
    max_depth: usize,
) -> f64 {
    let s1 = simpsons_rule(f, a, b, 2);
    let s2 = simpsons_rule(f, a, b, 4);

    if (s1 - s2).abs() < tolerance || max_depth == 0 {
        return s2;
    }

    let mid = (a + b) / 2.0;
    adaptive_simpsons(f, a, mid, tolerance / 2.0, max_depth - 1)
        + adaptive_simpsons(f, mid, b, tolerance / 2.0, max_depth - 1)
}

/// Linear interpolation between two data points.
///
/// Given known data points (x_data, y_data), estimate y at x.
///
/// # Arguments
/// * `x_data` - Known x values (must be sorted ascending)
/// * `y_data` - Known y values
/// * `x` - Point to interpolate at
pub fn linear_interpolation(x_data: &[f64], y_data: &[f64], x: f64) -> Option<f64> {
    let n = x_data.len().min(y_data.len());
    if n < 2 {
        return None;
    }

    // Find the interval containing x
    if x < x_data[0] || x > x_data[n - 1] {
        return None; // Extrapolation not supported
    }

    for i in 0..n - 1 {
        if x >= x_data[i] && x <= x_data[i + 1] {
            let t = (x - x_data[i]) / (x_data[i + 1] - x_data[i]);
            return Some(y_data[i] * (1.0 - t) + y_data[i + 1] * t);
        }
    }

    None
}

/// Cubic interpolation using natural cubic splines.
///
/// Produces a smooth curve through data points with continuous
/// first and second derivatives.
///
/// # Arguments
/// * `x_data` - Known x values (must be sorted ascending, unique)
/// * `y_data` - Known y values
/// * `x` - Point to interpolate at
pub fn cubic_interpolation(x_data: &[f64], y_data: &[f64], x: f64) -> Option<f64> {
    let n = x_data.len().min(y_data.len());
    if n < 3 {
        return linear_interpolation(x_data, y_data, x);
    }

    if x < x_data[0] || x > x_data[n - 1] {
        return None;
    }

    // Compute spline coefficients using natural boundary conditions
    let spline = CubicSpline::fit(x_data, y_data)?;
    Some(spline.evaluate(x))
}

/// Cubic spline coefficients for interpolation.
#[derive(Debug, Clone)]
struct CubicSpline {
    x: Vec<f64>,
    a: Vec<f64>, // y values
    b: Vec<f64>, // first derivative coefficients
    c: Vec<f64>, // second derivative / 2
    d: Vec<f64>, // third derivative / 6
}

impl CubicSpline {
    /// Fit a natural cubic spline to data points.
    fn fit(x_data: &[f64], y_data: &[f64]) -> Option<Self> {
        let n = x_data.len().min(y_data.len());
        if n < 2 {
            return None;
        }

        let x = x_data[..n].to_vec();
        let a = y_data[..n].to_vec();

        // Compute h (interval widths)
        let h: Vec<f64> = (0..n - 1).map(|i| x[i + 1] - x[i]).collect();

        if h.iter().any(|&hi| hi <= 0.0) {
            return None; // x values must be strictly increasing
        }

        // Set up tridiagonal system for c coefficients
        // Natural spline: c[0] = c[n-1] = 0
        let mut alpha = vec![0.0; n];
        for i in 1..n - 1 {
            alpha[i] = 3.0 / h[i] * (a[i + 1] - a[i]) - 3.0 / h[i - 1] * (a[i] - a[i - 1]);
        }

        // Tridiagonal solve (Thomas algorithm)
        let mut l = vec![1.0; n];
        let mut mu = vec![0.0; n];
        let mut z = vec![0.0; n];

        for i in 1..n - 1 {
            l[i] = 2.0 * (x[i + 1] - x[i - 1]) - h[i - 1] * mu[i - 1];
            mu[i] = h[i] / l[i];
            z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i];
        }

        // Back substitution
        let mut c = vec![0.0; n];
        let mut b = vec![0.0; n - 1];
        let mut d = vec![0.0; n - 1];

        for j in (0..n - 1).rev() {
            c[j] = z[j] - mu[j] * c[j + 1];
            b[j] = (a[j + 1] - a[j]) / h[j] - h[j] * (c[j + 1] + 2.0 * c[j]) / 3.0;
            d[j] = (c[j + 1] - c[j]) / (3.0 * h[j]);
        }

        Some(CubicSpline { x, a, b, c, d })
    }

    /// Evaluate the spline at a given x.
    fn evaluate(&self, x: f64) -> f64 {
        let n = self.x.len();

        // Find the interval
        let idx = if x >= self.x[n - 1] {
            n - 2
        } else {
            match self
                .x
                .binary_search_by(|xi| xi.partial_cmp(&x).unwrap_or(std::cmp::Ordering::Less))
            {
                Ok(i) => i.min(n - 2),
                Err(i) => i.max(1) - 1,
            }
        };

        let dx = x - self.x[idx];
        self.a[idx] + self.b[idx] * dx + self.c[idx] * dx * dx + self.d[idx] * dx * dx * dx
    }
}

/// Bilinear interpolation on a 2D grid.
///
/// Used for spatial data interpolation (e.g., price surfaces, demand maps).
pub fn bilinear_interpolation(
    x_data: &[f64],
    y_data: &[f64],
    z_grid: &[Vec<f64>],
    x: f64,
    y: f64,
) -> Option<f64> {
    let nx = x_data.len();
    let ny = y_data.len();

    if nx < 2 || ny < 2 || z_grid.len() < ny {
        return None;
    }

    // Find interval
    let x_idx = match x_data
        .binary_search_by(|xi| xi.partial_cmp(&x).unwrap_or(std::cmp::Ordering::Less))
    {
        Ok(i) => i,
        Err(i) => i.max(1) - 1,
    }
    .min(nx - 2);

    let y_idx = match y_data
        .binary_search_by(|yi| yi.partial_cmp(&y).unwrap_or(std::cmp::Ordering::Less))
    {
        Ok(i) => i,
        Err(i) => i.max(1) - 1,
    }
    .min(ny - 2);

    let tx = (x - x_data[x_idx]) / (x_data[x_idx + 1] - x_data[x_idx]);
    let ty = (y - y_data[y_idx]) / (y_data[y_idx + 1] - y_data[y_idx]);

    let z00 = z_grid[y_idx][x_idx];
    let z10 = z_grid[y_idx][x_idx + 1];
    let z01 = z_grid[y_idx + 1][x_idx];
    let z11 = z_grid[y_idx + 1][x_idx + 1];

    Some(
        z00 * (1.0 - tx) * (1.0 - ty)
            + z10 * tx * (1.0 - ty)
            + z01 * (1.0 - tx) * ty
            + z11 * tx * ty,
    )
}

/// Bisection method for root finding (robust fallback).
pub fn bisection(
    f: impl Fn(f64) -> f64,
    mut a: f64,
    mut b: f64,
    tolerance: f64,
    max_iterations: usize,
) -> RootResult {
    let fa = f(a);
    let fb = f(b);

    if fa * fb > 0.0 {
        return RootResult {
            root: (a + b) / 2.0,
            iterations: 0,
            converged: false,
            residual: f64::MAX,
        };
    }

    for i in 0..max_iterations {
        let mid = (a + b) / 2.0;
        let fmid = f(mid);

        if fmid.abs() < tolerance || (b - a) / 2.0 < tolerance {
            return RootResult {
                root: mid,
                iterations: i,
                converged: true,
                residual: fmid,
            };
        }

        if fa * fmid < 0.0 {
            b = mid;
        } else {
            a = mid;
        }
    }

    let root = (a + b) / 2.0;
    RootResult {
        root,
        iterations: max_iterations,
        converged: false,
        residual: f(root),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_newton_raphson_quadratic() {
        // f(x) = x² - 4, root at x = 2
        let result = newton_raphson(|x| x * x - 4.0, |x| 2.0 * x, 3.0, 1e-10, 100);
        assert!(result.converged);
        assert!((result.root - 2.0).abs() < 1e-8);
    }

    #[test]
    fn test_newton_raphson_numerical() {
        // f(x) = x³ - 27, root at x = 3
        let result = newton_raphson_numerical(|x| x * x * x - 27.0, 4.0, 1e-10, 100);
        assert!(result.converged);
        assert!((result.root - 3.0).abs() < 1e-6);
    }

    #[test]
    fn test_simpsons_rule() {
        // ∫₀¹ x² dx = 1/3
        let result = simpsons_rule(|x| x * x, 0.0, 1.0, 100);
        assert!((result - 1.0 / 3.0).abs() < 1e-10);
    }

    #[test]
    fn test_simpsons_rule_sin() {
        // ∫₀^π sin(x) dx = 2
        let result = simpsons_rule(|x| x.sin(), 0.0, std::f64::consts::PI, 100);
        assert!((result - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_linear_interpolation() {
        let x = vec![0.0, 1.0, 2.0, 3.0];
        let y = vec![0.0, 2.0, 4.0, 6.0];

        let result = linear_interpolation(&x, &y, 1.5).unwrap();
        assert!((result - 3.0).abs() < 1e-10);
    }

    #[test]
    fn test_cubic_interpolation() {
        let x = vec![0.0, 1.0, 2.0, 3.0, 4.0];
        let y = vec![0.0, 1.0, 4.0, 9.0, 16.0]; // y = x²

        let result = cubic_interpolation(&x, &y, 2.5).unwrap();
        assert!((result - 6.25).abs() < 0.1); // Should be close to 2.5² = 6.25
    }

    #[test]
    fn test_bisection() {
        // f(x) = x² - 4, root at x = 2 in [0, 3]
        let result = bisection(|x| x * x - 4.0, 0.0, 3.0, 1e-10, 100);
        assert!(result.converged);
        assert!((result.root - 2.0).abs() < 1e-8);
    }
}
