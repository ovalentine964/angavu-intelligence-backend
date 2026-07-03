"""
Markov Chains & Optimization — ECO 103/104: Mathematics for Economists.

Implements Markov chain credit score transitions and optimization
theory for Biashara Intelligence.

Academic Foundation:
- ECO 103: Introduction to Mathematics for Economists — Matrix algebra,
  systems of equations, basic optimization
- ECO 104: Mathematics for Economists — Advanced optimization (Lagrange
  multipliers, Kuhn-Tucker conditions), Markov chains, difference
  equations, dynamic programming

Key Applications:
1. Credit Score Transitions: Model how businesses move between score
   bands (excellent → good → fair → poor → very_poor) as a Markov
   chain. The transition matrix P gives P(score_t+1 | score_t).
2. Steady-State Distribution: The long-run proportion of businesses
   in each score band (eigenvector of P corresponding to eigenvalue 1).
3. Optimization: Revenue maximization subject to constraints using
   Lagrange multipliers and Kuhn-Tucker conditions.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import optimize

logger = structlog.get_logger(__name__)

# Score band definitions
SCORE_BANDS = ["excellent", "good", "fair", "poor", "very_poor"]
SCORE_BAND_THRESHOLDS = [(750, 850), (650, 749), (550, 649), (450, 549), (300, 449)]


class MarkovChainAnalyzer:
    """
    Markov chain analysis for credit score transitions.

    Driven by ECO 104 § Markov Chains:
    - Transition matrix P where P_ij = P(X_{t+1}=j | X_t=i)
    - Row sums equal 1: Σ_j P_ij = 1
    - Steady state π: πP = π, Σ π_i = 1
    - n-step transition: P^n gives probabilities after n periods
    - Absorbing states: states that once entered, never left

    For credit scoring:
    - States = score bands (excellent, good, fair, poor, very_poor)
    - Transitions based on revenue growth, consistency, payment behavior
    - Steady state = long-run distribution of credit quality
    - Absorbing analysis = probability of default (absorbing state)
    """

    def __init__(self):
        self.transition_matrix: Optional[np.ndarray] = None
        self.steady_state: Optional[np.ndarray] = None
        self.n_states = len(SCORE_BANDS)

    def estimate_transition_matrix(
        self,
        score_sequences: List[List[int]],
        n_states: int = 5,
    ) -> np.ndarray:
        """
        Estimate transition matrix from observed score sequences.

        Uses maximum likelihood estimation:
        P_ij = N_ij / N_i where N_ij = count of transitions i→j,
        N_i = total transitions from state i.

        Args:
            score_sequences: List of score band index sequences
            n_states: Number of states (default 5 for score bands)

        Returns:
            Transition matrix P (n_states × n_states)
        """
        counts = np.zeros((n_states, n_states))

        for seq in score_sequences:
            for t in range(len(seq) - 1):
                i, j = seq[t], seq[t + 1]
                if 0 <= i < n_states and 0 <= j < n_states:
                    counts[i, j] += 1

        # Normalize rows
        row_sums = counts.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1)  # Avoid division by zero
        P = counts / row_sums

        self.transition_matrix = P
        return P

    def compute_steady_state(self, P: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Compute steady-state distribution π such that πP = π.

        Solves: (P' - I)π = 0 with constraint Σπ_i = 1.

        Args:
            P: Transition matrix (uses self.transition_matrix if None)

        Returns:
            Steady-state probability vector π
        """
        if P is None:
            P = self.transition_matrix
        if P is None:
            raise ValueError("No transition matrix available")

        n = P.shape[0]
        # Solve (P' - I)π = 0 with Σπ = 1
        # Replace last equation with Σπ = 1
        A = P.T - np.eye(n)
        A[-1, :] = 1.0
        b = np.zeros(n)
        b[-1] = 1.0

        try:
            pi = np.linalg.solve(A, b)
            pi = np.maximum(pi, 0)  # Ensure non-negative
            pi = pi / pi.sum()  # Normalize
        except np.linalg.LinAlgError:
            # Fallback: uniform distribution
            pi = np.ones(n) / n

        self.steady_state = pi
        return pi

    def n_step_transition(
        self, P: Optional[np.ndarray], n: int
    ) -> np.ndarray:
        """
        Compute n-step transition matrix P^n.

        Args:
            P: Transition matrix
            n: Number of steps

        Returns:
            P^n matrix
        """
        if P is None:
            P = self.transition_matrix
        if P is None:
            raise ValueError("No transition matrix available")

        return np.linalg.matrix_power(P, n)

    def absorption_probability(
        self,
        P: np.ndarray,
        transient_states: List[int],
        absorbing_states: List[int],
    ) -> np.ndarray:
        """
        Compute absorption probabilities.

        For a Markov chain with transient and absorbing states,
        computes the probability of being absorbed in each absorbing
        state starting from each transient state.

        Uses fundamental matrix: N = (I - Q)^(-1)
        Absorption matrix: B = NR

        Args:
            P: Full transition matrix
            transient_states: Indices of transient states
            absorbing_states: Indices of absorbing states

        Returns:
            Absorption probability matrix B (|transient| × |absorbing|)
        """
        t_idx = np.array(transient_states)
        a_idx = np.array(absorbing_states)

        Q = P[np.ix_(t_idx, t_idx)]  # Transient → Transient
        R = P[np.ix_(t_idx, a_idx)]  # Transient → Absorbing

        I = np.eye(len(t_idx))
        try:
            N = np.linalg.inv(I - Q)  # Fundamental matrix
        except np.linalg.LinAlgError:
            N = np.linalg.pinv(I - Q)

        B = N @ R  # Absorption probabilities
        return B

    def expected_time_to_absorption(
        self,
        P: np.ndarray,
        transient_states: List[int],
    ) -> np.ndarray:
        """
        Expected number of steps before absorption.

        Uses fundamental matrix: t = N·1 where N = (I-Q)^(-1)

        Args:
            P: Full transition matrix
            transient_states: Indices of transient states

        Returns:
            Vector of expected steps from each transient state
        """
        t_idx = np.array(transient_states)
        Q = P[np.ix_(t_idx, t_idx)]

        I = np.eye(len(t_idx))
        try:
            N = np.linalg.inv(I - Q)
        except np.linalg.LinAlgError:
            N = np.linalg.pinv(I - Q)

        t = N @ np.ones(len(t_idx))
        return t

    def credit_score_transition_report(
        self,
        current_score: int,
        revenue_growth_pct: float,
        consistency_score: float,
        months_of_data: int,
    ) -> Dict[str, Any]:
        """
        Generate credit score transition report.

        Estimates transition probabilities based on current score
        and business metrics.

        Args:
            current_score: Current Alama score (300-850)
            revenue_growth_pct: Revenue growth percentage
            consistency_score: Business consistency (0-100)
            months_of_data: Months of transaction history

        Returns:
            Dict with transition probabilities, steady state, and recommendations
        """
        # Determine current band
        current_band = self._score_to_band(current_score)

        # Estimate transition probabilities based on metrics
        P = self._build_transition_matrix(
            revenue_growth_pct, consistency_score, months_of_data
        )

        # Compute steady state
        pi = self.compute_steady_state(P)

        # 3-month transition probabilities
        P_3m = self.n_step_transition(P, 3)

        # Probability of improvement/decline
        current_idx = SCORE_BANDS.index(current_band)
        prob_improve = sum(P_3m[current_idx, j] for j in range(current_idx))
        prob_decline = sum(P_3m[current_idx, j] for j in range(current_idx + 1, self.n_states))
        prob_stay = P_3m[current_idx, current_idx]

        return {
            "current_score": current_score,
            "current_band": current_band,
            "transition_matrix": P.tolist(),
            "steady_state_distribution": {
                band: round(float(pi[i]), 4)
                for i, band in enumerate(SCORE_BANDS)
            },
            "three_month_outlook": {
                "prob_improve": round(float(prob_improve), 4),
                "prob_maintain": round(float(prob_stay), 4),
                "prob_decline": round(float(prob_decline), 4),
                "expected_band": SCORE_BANDS[int(np.argmin(np.abs(
                    P_3m[current_idx] - np.ones(self.n_states) / self.n_states
                )))],
            },
            "recommendation": self._transition_recommendation(
                prob_improve, prob_decline, revenue_growth_pct, consistency_score
            ),
            "method": "ECO 104 — Markov Chain Credit Score Transitions",
        }

    def _build_transition_matrix(
        self,
        revenue_growth: float,
        consistency: float,
        months: int,
    ) -> np.ndarray:
        """Build transition matrix from business metrics."""
        n = self.n_states
        P = np.zeros((n, n))

        # Base: probability of staying in same band
        base_stay = 0.70
        # Higher consistency → higher stay probability
        consistency_bonus = (consistency / 100) * 0.15
        # More data → more confident (higher stay)
        data_bonus = min(months / 12, 1.0) * 0.05

        for i in range(n):
            stay_prob = min(0.95, base_stay + consistency_bonus + data_bonus)
            P[i, i] = stay_prob

            # Improvement probability (higher for lower bands)
            if revenue_growth > 0:
                improve_boost = min(revenue_growth / 100, 0.20)
                improve_prob = (1 - stay_prob) * (0.6 + improve_boost)
                if i > 0:
                    P[i, i - 1] = min(improve_prob, 0.25)
            else:
                P[i, i - 1] = (1 - stay_prob) * 0.2

            # Decline probability
            if revenue_growth < -5:
                decline_boost = min(abs(revenue_growth) / 100, 0.20)
                decline_prob = (1 - stay_prob - P[i, i - 1]) * (0.5 + decline_boost)
                if i < n - 1:
                    P[i, i + 1] = min(decline_prob, 0.20)
            else:
                if i < n - 1:
                    P[i, i + 1] = (1 - stay_prob - P[i, max(0, i - 1)]) * 0.3

            # Ensure row sums to 1
            row_sum = P[i].sum()
            if row_sum > 0:
                P[i] = P[i] / row_sum
            else:
                P[i] = np.ones(n) / n

        return P

    def _score_to_band(self, score: int) -> str:
        """Convert numeric score to band name."""
        for band, (lo, hi) in zip(SCORE_BANDS, SCORE_BAND_THRESHOLDS):
            if lo <= score <= hi:
                return band
        return "fair"

    def _transition_recommendation(
        self, prob_improve: float, prob_decline: float,
        growth: float, consistency: float,
    ) -> str:
        """Generate recommendation based on transition analysis."""
        if prob_improve > 0.3:
            return "Strong upward trajectory. Maintain current practices — likely to improve score band."
        elif prob_decline > 0.3:
            return "Risk of score decline. Focus on revenue consistency and reducing transaction volatility."
        elif consistency < 50:
            return "Low consistency is the primary risk factor. Record transactions daily to stabilize."
        else:
            return "Stable trajectory. Small improvements in revenue growth can accelerate score improvement."


class OptimizationEngine:
    """
    Optimization methods for economic decision-making.

    Driven by ECO 103/104 § Optimization:
    - Unconstrained: FOC (first-order conditions), SOC (second-order)
    - Constrained: Lagrange multipliers, Kuhn-Tucker conditions
    - Linear programming: Simplex method for resource allocation
    - Dynamic optimization: Bellman equation for sequential decisions

    Applications:
    - Optimal pricing for informal businesses
    - Resource allocation across product lines
    - Savings-consumption optimization
    - Inventory optimization under uncertainty
    """

    @staticmethod
    def lagrange_optimize(
        objective: callable,
        constraint: callable,
        x0: np.ndarray,
        bounds: Optional[List[Tuple[float, float]]] = None,
    ) -> Dict[str, Any]:
        """
        Constrained optimization using Lagrange multiplier method.

        Solves: max f(x) subject to g(x) = 0

        Lagrangian: L(x, λ) = f(x) - λ·g(x)
        FOC: ∂L/∂x = 0, ∂L/∂λ = 0

        Args:
            objective: Objective function f(x) to maximize
            constraint: Constraint function g(x) = 0
            x0: Initial guess
            bounds: Variable bounds [(lo, hi), ...]

        Returns:
            Dict with optimal x, objective value, multiplier, and status
        """
        x0 = np.asarray(x0, dtype=float)

        # Augmented Lagrangian
        def lagrangian(params):
            x = params[:-1]
            lam = params[-1]
            return -(objective(x) - lam * constraint(x))

        x0_aug = np.append(x0, 0.0)  # Initial lambda = 0
        bounds_aug = bounds + [(None, None)] if bounds else None

        result = optimize.minimize(
            lagrangian, x0_aug, method="SLSQP",
            bounds=bounds_aug,
        )

        x_opt = result.x[:-1]
        lambda_opt = result.x[-1]

        return {
            "optimal_x": x_opt.tolist(),
            "optimal_value": float(-result.fun),
            "lagrange_multiplier": float(lambda_opt),
            "constraint_value": float(constraint(x_opt)),
            "converged": result.success,
            "method": "Lagrange (ECO 103/104)",
        }

    @staticmethod
    def kuhn_tucker_optimize(
        objective: callable,
        inequality_constraints: List[callable],
        x0: np.ndarray,
        bounds: Optional[List[Tuple[float, float]]] = None,
    ) -> Dict[str, Any]:
        """
        Constrained optimization with inequality constraints (Kuhn-Tucker).

        Solves: max f(x) subject to g_i(x) ≤ 0 for all i

        KKT conditions:
        1. ∇f = Σ λ_i ∇g_i (stationarity)
        2. λ_i ≥ 0 (dual feasibility)
        3. λ_i · g_i(x) = 0 (complementary slackness)
        4. g_i(x) ≤ 0 (primal feasibility)

        Args:
            objective: Objective function to maximize
            inequality_constraints: List of constraint functions g_i(x) ≤ 0
            x0: Initial guess
            bounds: Variable bounds

        Returns:
            Dict with optimal solution and KKT conditions
        """
        n_vars = len(x0)
        n_constraints = len(inequality_constraints)

        def neg_objective(x):
            return -objective(x)

        constraints = [
            {"type": "ineq", "fun": lambda x, i=i: -inequality_constraints[i](x)}
            for i in range(n_constraints)
        ]

        result = optimize.minimize(
            neg_objective, x0, method="SLSQP",
            bounds=bounds, constraints=constraints,
        )

        # Check KKT conditions
        constraint_values = [c(result.x) for c in inequality_constraints]
        active_constraints = [
            i for i, v in enumerate(constraint_values) if abs(v) < 1e-6
        ]

        return {
            "optimal_x": result.x.tolist(),
            "optimal_value": float(-result.fun),
            "constraint_values": [float(v) for v in constraint_values],
            "active_constraints": active_constraints,
            "converged": result.success,
            "method": "Kuhn-Tucker (ECO 104)",
        }

    @staticmethod
    def revenue_maximization(
        prices: np.ndarray,
        demand_func: callable,
        cost_func: callable,
        n_products: int,
    ) -> Dict[str, Any]:
        """
        Optimal pricing for revenue maximization.

        Solves: max Σ p_i · q_i(p_i) - C(q) subject to q_i ≥ 0

        Args:
            prices: Initial price guesses
            demand_func: Demand function q(p) for each product
            cost_func: Cost function C(q)
            n_products: Number of products

        Returns:
            Dict with optimal prices, quantities, and revenue
        """
        def neg_profit(p):
            q = np.array([demand_func(p[i]) for i in range(n_products)])
            revenue = np.sum(p * q)
            cost = cost_func(q)
            return -(revenue - cost)

        bounds = [(0.01, None)] * n_products

        result = optimize.minimize(
            neg_profit, prices, method="L-BFGS-B",
            bounds=bounds,
        )

        optimal_prices = result.x
        optimal_quantities = np.array([demand_func(p) for p in optimal_prices])
        revenue = float(np.sum(optimal_prices * optimal_quantities))
        cost = float(cost_func(optimal_quantities))

        return {
            "optimal_prices": optimal_prices.tolist(),
            "optimal_quantities": optimal_quantities.tolist(),
            "revenue": round(revenue, 2),
            "cost": round(cost, 2),
            "profit": round(revenue - cost, 2),
            "converged": result.success,
            "method": "Revenue Maximization (ECO 103/104)",
        }

    @staticmethod
    def savings_consumption_optimization(
        income: float,
        utility_func: callable,
        interest_rate: float,
        periods: int = 12,
        risk_aversion: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Optimal savings-consumption allocation.

        Driven by ECO 104 § Dynamic Optimization:
        max Σ β^t U(c_t) subject to: a_{t+1} = (1+r)(a_t + y_t - c_t)

        Uses CRRA utility: U(c) = c^(1-γ)/(1-γ) for γ ≠ 1
        Euler equation: U'(c_t) = β(1+r)U'(c_{t+1})

        Args:
            income: Monthly income in KES
            utility_func: Utility function (default: CRRA)
            interest_rate: Monthly interest rate
            periods: Number of periods
            risk_aversion: CRRA risk aversion parameter γ

        Returns:
            Dict with optimal consumption path and savings rate
        """
        beta = 0.96  # Discount factor (patient)

        # For CRRA utility, optimal consumption is a constant fraction
        # of permanent income (certainty equivalence)
        # c* = [(1-β(1+r))/(1-β(1+r)^T)] * permanent_income
        # Simplified: c* ≈ (1 - β(1+r)) * income for infinite horizon

        discount_factor = beta * (1 + interest_rate)
        if discount_factor >= 1:
            # Impatient: consume everything
            optimal_consumption = income
            savings_rate = 0.0
        else:
            # Patient: smooth consumption
            optimal_consumption = income * (1 - discount_factor)
            savings_rate = 1 - optimal_consumption / income

        # Consumption path (constant for CRRA with constant income)
        consumption_path = [round(optimal_consumption, 2)] * periods
        savings_path = [round(income - c, 2) for c in consumption_path]
        wealth_path = []
        wealth = 0
        for s in savings_path:
            wealth = wealth * (1 + interest_rate) + s
            wealth_path.append(round(wealth, 2))

        return {
            "optimal_monthly_consumption": round(optimal_consumption, 2),
            "optimal_savings_rate": round(savings_rate, 4),
            "consumption_path": consumption_path,
            "savings_path": savings_path,
            "wealth_path": wealth_path,
            "total_wealth_end": wealth_path[-1] if wealth_path else 0,
            "discount_factor": round(discount_factor, 4),
            "risk_aversion": risk_aversion,
            "method": "ECO 104 — Dynamic Consumption-Savings Optimization",
        }


# Singleton instances
markov_analyzer = MarkovChainAnalyzer()
optimization_engine = OptimizationEngine()
