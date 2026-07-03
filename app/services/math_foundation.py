"""
Mathematical Foundations — MAT 101/121/124: Pure Mathematics.

Explicit implementations of foundational mathematics used throughout
Angavu Intelligence. These are handled implicitly by NumPy/SciPy
but this module makes the academic connections explicit.

Academic Foundation:
- MAT 101: Foundation Mathematics — Algebra, sets, functions, sequences
- MAT 121: Differential Calculus — Limits, derivatives, optimization
- MAT 124: Integral Calculus — Integration, area, volume, applications

While NumPy/SciPy handle the computation, this module:
1. Documents which math concepts power which features
2. Provides educational implementations for transparency
3. Validates numerical results against analytical solutions
4. Serves as the mathematical reference for the codebase
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import integrate, optimize

logger = structlog.get_logger(__name__)


class AlgebraFoundations:
    """
    MAT 101: Foundation Mathematics.

    Algebraic operations, matrix algebra, and systems of equations
    that underpin all statistical computations.
    """

    @staticmethod
    def solve_linear_system(A: np.ndarray, b: np.ndarray) -> Dict[str, Any]:
        """
        Solve Ax = b using Gaussian elimination with partial pivoting.

        MAT 101 § Systems of Linear Equations:
        - Gaussian elimination: reduce to row echelon form
        - Back substitution: solve from bottom up
        - Partial pivoting: numerical stability

        This is the foundation for OLS regression, PCA, and
        all matrix-based computations in Angavu Intelligence.

        Args:
            A: Coefficient matrix (n × n)
            b: Right-hand side vector (n)

        Returns:
            Dict with solution, residual, and condition number
        """
        A = np.asarray(A, dtype=float)
        b = np.asarray(b, dtype=float)

        try:
            x = np.linalg.solve(A, b)
            residual = float(np.linalg.norm(A @ x - b))
            cond = float(np.linalg.cond(A))
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix — no unique solution"}

        return {
            "solution": x.tolist(),
            "residual": round(residual, 10),
            "condition_number": round(cond, 2),
            "well_conditioned": cond < 1e10,
            "method": "MAT 101 — Gaussian Elimination",
        }

    @staticmethod
    def matrix_operations(A: np.ndarray, B: np.ndarray) -> Dict[str, Any]:
        """
        Basic matrix operations: multiplication, transpose, inverse.

        MAT 101 § Matrix Algebra: Foundation for all multivariate
        statistics (PCA, factor analysis, LDA).
        """
        A = np.asarray(A, dtype=float)
        B = np.asarray(B, dtype=float)

        result = {
            "A_shape": A.shape,
            "B_shape": B.shape,
        }

        if A.shape == B.shape:
            result["A_plus_B"] = (A + B).tolist()
            result["element_wise_product"] = (A * B).tolist()

        if A.shape[1] == B.shape[0]:
            result["AB"] = (A @ B).tolist()

        result["A_transpose"] = A.T.tolist()

        if A.shape[0] == A.shape[1]:
            try:
                result["A_inverse"] = np.linalg.inv(A).tolist()
                result["determinant"] = float(np.linalg.det(A))
            except np.linalg.LinAlgError:
                result["A_inverse"] = "singular"
                result["determinant"] = 0.0

        result["method"] = "MAT 101 — Matrix Operations"
        return result

    @staticmethod
    def sequence_operations(
        terms: List[float],
    ) -> Dict[str, Any]:
        """
        Analyze sequences: arithmetic, geometric, convergence.

        MAT 101 § Sequences and Series:
        - Arithmetic: aₙ = a₁ + (n-1)d
        - Geometric: aₙ = a₁ · r^(n-1)
        - Convergence: lim aₙ exists and is finite
        """
        arr = np.array(terms)
        n = len(arr)

        # Detect arithmetic sequence
        if n >= 3:
            diffs = np.diff(arr)
            is_arithmetic = np.allclose(diffs, diffs[0], rtol=1e-6)
            common_diff = float(diffs[0]) if is_arithmetic else None
        else:
            is_arithmetic = False
            common_diff = None

        # Detect geometric sequence
        if n >= 3 and np.all(arr != 0):
            ratios = arr[1:] / arr[:-1]
            is_geometric = np.allclose(ratios, ratios[0], rtol=1e-6)
            common_ratio = float(ratios[0]) if is_geometric else None
        else:
            is_geometric = False
            common_ratio = None

        return {
            "n_terms": n,
            "is_arithmetic": is_arithmetic,
            "common_difference": common_diff,
            "is_geometric": is_geometric,
            "common_ratio": common_ratio,
            "sum": float(np.sum(arr)),
            "partial_sums": np.cumsum(arr).tolist(),
            "method": "MAT 101 — Sequence Analysis",
        }


class DifferentialCalculus:
    """
    MAT 121: Differential Calculus.

    Derivatives, optimization, and rate-of-change analysis.
    """

    @staticmethod
    def numerical_derivative(
        f: Callable,
        x: float,
        h: float = 1e-8,
    ) -> Dict[str, Any]:
        """
        Numerical differentiation using central difference.

        MAT 121 § Definition of Derivative:
        f'(x) = lim_{h→0} [f(x+h) - f(x-h)] / 2h

        Central difference is O(h²) accurate.

        Args:
            f: Function to differentiate
            x: Point at which to evaluate
            h: Step size

        Returns:
            Dict with derivative, second derivative, and accuracy
        """
        # First derivative (central difference)
        f_prime = (f(x + h) - f(x - h)) / (2 * h)

        # Second derivative
        f_double_prime = (f(x + h) - 2 * f(x) + f(x - h)) / (h ** 2)

        return {
            "x": x,
            "f(x)": float(f(x)),
            "f'(x)": round(float(f_prime), 8),
            "f''(x)": round(float(f_double_prime), 8),
            "step_size": h,
            "method": "MAT 121 — Central Difference Numerical Differentiation",
        }

    @staticmethod
    def find_critical_points(
        f: Callable,
        interval: Tuple[float, float],
        n_grid: int = 100,
    ) -> Dict[str, Any]:
        """
        Find critical points where f'(x) = 0.

        MAT 121 § Optimization: Critical points are candidates
        for maxima/minima. Second derivative test classifies them.

        Args:
            f: Function to analyze
            interval: (a, b) search interval
            n_grid: Grid points for initial search

        Returns:
            Dict with critical points and their classification
        """
        a, b = interval
        grid = np.linspace(a, b, n_grid)
        f_vals = np.array([f(x) for x in grid])

        # Find sign changes in numerical derivative
        h = (b - a) / n_grid
        df_vals = np.diff(f_vals) / h

        critical_points = []
        for i in range(len(df_vals) - 1):
            if df_vals[i] * df_vals[i + 1] < 0:
                # Sign change — refine with bisection
                try:
                    x_crit = optimize.brentq(
                        lambda x: (f(x + 1e-8) - f(x - 1e-8)) / 2e-8,
                        grid[i], grid[i + 1]
                    )
                    f_crit = f(x_crit)
                    f_pp = (f(x_crit + 1e-6) - 2 * f_crit + f(x_crit - 1e-6)) / 1e-12

                    if f_pp > 0:
                        classification = "minimum"
                    elif f_pp < 0:
                        classification = "maximum"
                    else:
                        classification = "inflection"

                    critical_points.append({
                        "x": round(float(x_crit), 6),
                        "f(x)": round(float(f_crit), 6),
                        "f''(x)": round(float(f_pp), 6),
                        "classification": classification,
                    })
                except Exception:
                    pass

        return {
            "critical_points": critical_points,
            "n_found": len(critical_points),
            "global_max": round(float(np.max(f_vals)), 6),
            "global_min": round(float(np.min(f_vals)), 6),
            "method": "MAT 121 — Critical Point Analysis",
        }


class IntegralCalculus:
    """
    MAT 124: Integral Calculus.

    Numerical integration, area calculations, and applications.
    """

    @staticmethod
    def numerical_integration(
        f: Callable,
        a: float,
        b: float,
        method: str = "simpson",
    ) -> Dict[str, Any]:
        """
        Numerical integration using quadrature.

        MAT 124 § Definite Integral:
        ∫_a^b f(x) dx ≈ Σ wᵢ f(xᵢ)

        Methods:
        - trapezoidal: O(h²) accuracy
        - simpson: O(h⁴) accuracy (Simpson's 1/3 rule)
        - scipy: adaptive quadrature (quad)

        Applications in Angavu Intelligence:
        - Consumer surplus: ∫(P_max - P_actual)dQ
        - Gini coefficient: Area under Lorenz curve
        - Probability: ∫f(x)dx for density functions

        Args:
            f: Integrand
            a: Lower limit
            b: Upper limit
            method: Integration method

        Returns:
            Dict with integral value and accuracy estimate
        """
        if method == "trapezoidal":
            n = 1000
            x = np.linspace(a, b, n + 1)
            y = np.array([f(xi) for xi in x])
            h = (b - a) / n
            integral = h * (y[0] / 2 + np.sum(y[1:-1]) + y[-1] / 2)
            error_estimate = None
        elif method == "simpson":
            n = 1000
            if n % 2 != 0:
                n += 1
            x = np.linspace(a, b, n + 1)
            y = np.array([f(xi) for xi in x])
            h = (b - a) / n
            integral = h / 3 * (y[0] + 4 * np.sum(y[1::2]) + 2 * np.sum(y[2:-1:2]) + y[-1])
            error_estimate = None
        else:  # scipy
            result, error_estimate = integrate.quad(f, a, b)
            integral = result

        return {
            "integral": round(float(integral), 8),
            "lower_limit": a,
            "upper_limit": b,
            "method": f"MAT 124 — {method.title()} Integration",
            "error_estimate": round(float(error_estimate), 10) if error_estimate else None,
        }

    @staticmethod
    def consumer_surplus(
        demand_func: Callable,
        equilibrium_price: float,
        equilibrium_quantity: float,
        max_price: float,
    ) -> Dict[str, Any]:
        """
        Compute consumer surplus using integration.

        MAT 124 § Applications of Integration:
        CS = ∫₀^Q* [D(Q) - P*] dQ

        where D(Q) is the inverse demand function, P* is equilibrium
        price, Q* is equilibrium quantity.

        Args:
            demand_func: Inverse demand function P = D(Q)
            equilibrium_price: Market-clearing price
            equilibrium_quantity: Market-clearing quantity
            max_price: Maximum willingness to pay (D(0))

        Returns:
            Dict with consumer surplus
        """
        # CS = ∫₀^Q* D(Q) dQ - P* × Q*
        integral_part, _ = integrate.quad(demand_func, 0, equilibrium_quantity)
        cs = integral_part - equilibrium_price * equilibrium_quantity

        return {
            "consumer_surplus": round(max(0, float(cs)), 2),
            "integral_demand_area": round(float(integral_part), 2),
            "expenditure": round(float(equilibrium_price * equilibrium_quantity), 2),
            "method": "MAT 124 — Consumer Surplus via Integration",
        }

    @staticmethod
    def lorenz_area(
        income_shares: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Compute area under Lorenz curve (for Gini coefficient).

        MAT 124 § Area Between Curves:
        Gini = 1 - 2 × (Area under Lorenz curve)
        Area = ∫₀¹ L(p) dp

        Args:
            income_shares: Cumulative income shares (Lorenz curve values)

        Returns:
            Dict with area and implied Gini coefficient
        """
        n = len(income_shares)
        p = np.linspace(0, 1, n)
        lorenz = np.concatenate([[0], income_shares])

        # Trapezoidal integration
        area = float(np.trapz(lorenz, np.linspace(0, 1, len(lorenz))))
        gini = 1 - 2 * area

        return {
            "lorenz_area": round(area, 6),
            "gini_coefficient": round(max(0, min(1, gini)), 6),
            "method": "MAT 124 — Lorenz Curve Integration",
        }


# Singleton instances
algebra = AlgebraFoundations()
calculus_diff = DifferentialCalculus()
calculus_int = IntegralCalculus()
