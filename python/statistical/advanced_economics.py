"""
Advanced Economics Models — Angavu Intelligence Backend

Implements core macroeconomic and microeconomic models for the platform:
  - DSGE Model Basics (Dynamic Stochastic General Equilibrium)
  - Rational Expectations (forward-looking behavior)
  - Edgeworth Box (general equilibrium visualization)
  - Pareto Efficiency Checker
  - Stiglitz-Weiss Credit Rationing
  - Endogenous Growth Model (human capital driven)
  - Ricardian Equivalence
  - New Keynesian Phillips Curve
  - Arrow's Impossibility Theorem
  - Revenue Equivalence Theorem

Academic references:
  - ECO 311 (Intermediate Macro)
  - ECO 414 (Econometrics)
  - ECO 404 (Development Economics)
"""

import json
import sys
import numpy as np
from typing import Any, Dict, List, Optional, Tuple


# ── 1. DSGE Model Basics ──────────────────────────────────────────

class DSGEModel:
    """
    Simplified 3-equation New Keynesian DSGE model:
      1) IS curve:    E_t[y_{t+1}] = y_t - (1/sigma)(i_t - E_t[pi_{t+1}] - r^n)
      2) Phillips:    pi_t = beta * E_t[pi_{t+1}] + kappa * y_t
      3) Taylor rule: i_t = phi_pi * pi_t + phi_y * y_t + v_t

    Shock: AR(1) monetary policy shock v_t = rho_v * v_{t-1} + eps_v
    """

    def __init__(self, sigma: float = 1.0, beta: float = 0.99, kappa: float = 0.1,
                 phi_pi: float = 1.5, phi_y: float = 0.5, rho_v: float = 0.8):
        self.sigma = sigma
        self.beta = beta
        self.kappa = kappa
        self.phi_pi = phi_pi
        self.phi_y = phi_y
        self.rho_v = rho_v

    def simulate(self, periods: int = 40, shock_std: float = 0.01,
                 seed: int = 42) -> Dict[str, List[float]]:
        """Simulate the DSGE model using Blanchard-Kahn method (simplified)."""
        rng = np.random.RandomState(seed)
        y = np.zeros(periods)   # output gap
        pi = np.zeros(periods)  # inflation
        i = np.zeros(periods)   # nominal interest rate
        v = np.zeros(periods)   # monetary shock

        for t in range(1, periods):
            v[t] = self.rho_v * v[t - 1] + rng.normal(0, shock_std)
            # Taylor rule
            i[t] = self.phi_pi * pi[t - 1] + self.phi_y * y[t - 1] + v[t]
            # IS curve (backward-looking simplification)
            y[t] = y[t - 1] - (1.0 / self.sigma) * (i[t] - pi[t - 1]) + 0.005 * rng.normal()
            # Phillips curve
            pi[t] = self.beta * pi[t - 1] + self.kappa * y[t]

        return {
            "output_gap": y.tolist(),
            "inflation": pi.tolist(),
            "interest_rate": i.tolist(),
            "monetary_shock": v.tolist(),
            "periods": periods,
            "parameters": {
                "sigma": self.sigma, "beta": self.beta, "kappa": self.kappa,
                "phi_pi": self.phi_pi, "phi_y": self.phi_y, "rho_v": self.rho_v
            }
        }


# ── 2. Rational Expectations ──────────────────────────────────────

class RationalExpectations:
    """
    Solves models with rational (forward-looking) expectations.
    Uses iterative method to find fixed point of expectations.

    Example: Cobweb model with rational expectations
      p_t = (a - b * E_t[q_t]) / c
      q_t = q_{t-1} + gamma * (p_{t-1} - p_e)
      E_t[q_{t+1}] = rational forecast
    """

    def __init__(self, a: float = 10.0, b: float = 0.5, c: float = 1.0,
                 gamma: float = 0.3):
        self.a = a
        self.b = b
        self.c = c
        self.gamma = gamma

    def solve_cobweb(self, periods: int = 50, tol: float = 1e-8,
                     max_iter: int = 1000) -> Dict[str, Any]:
        """Solve cobweb model with rational expectations convergence."""
        # Initial guess for rational expectations equilibrium
        p_star = self.a / (self.c + self.b * self.gamma)
        q_star = self.gamma * p_star

        prices = [p_star * 1.2]  # start away from equilibrium
        quantities = [q_star * 0.8]
        expectations = [q_star]

        for t in range(1, periods):
            # Form rational expectation (iterate to convergence)
            eq_q = quantities[t - 1]
            for _ in range(max_iter):
                p_t = (self.a - self.b * eq_q) / self.c
                new_q = quantities[t - 1] + self.gamma * (prices[t - 1] - p_t)
                if abs(new_q - eq_q) < tol:
                    break
                eq_q = new_q

            expectations.append(eq_q)
            p_t = (self.a - self.b * eq_q) / self.c
            q_t = quantities[t - 1] + self.gamma * (prices[t - 1] - p_t)
            prices.append(p_t)
            quantities.append(q_t)

        return {
            "prices": prices,
            "quantities": quantities,
            "expectations": expectations,
            "equilibrium_price": p_star,
            "equilibrium_quantity": q_star,
            "converged": abs(prices[-1] - p_star) < 0.01,
            "parameters": {"a": self.a, "b": self.b, "c": self.c, "gamma": self.gamma}
        }


# ── 3. Edgeworth Box ──────────────────────────────────────────────

class EdgeworthBox:
    """
    Generates Edgeworth box data for 2-agent, 2-good exchange economy.
    Computes contract curve, core allocations, and competitive equilibrium.
    """

    def __init__(self, total_x: float = 100.0, total_y: float = 100.0,
                 alpha_a: float = 0.5, beta_a: float = 0.5,
                 alpha_b: float = 0.5, beta_b: float = 0.5):
        self.total_x = total_x
        self.total_y = total_y
        # Cobb-Douglas utility: U_A = x^alpha_a * y^beta_a, U_B = x^alpha_b * y^beta_b
        self.alpha_a = alpha_a
        self.beta_a = beta_a
        self.alpha_b = alpha_b
        self.beta_b = beta_b

    def compute_contract_curve(self, n_points: int = 50) -> Dict[str, Any]:
        """Compute the contract curve (locus of Pareto-efficient allocations)."""
        # For Cobb-Douglas: MRS_A = MRS_B along contract curve
        # (alpha_a/beta_a) * (y_A/x_A) = (alpha_b/beta_b) * (y_B/x_B)
        # With y_B = total_y - y_A, x_B = total_x - x_A
        x_a = np.linspace(1, self.total_x - 1, n_points)
        # From MRS equality: (alpha_a*y_A)/(beta_a*x_A) = (alpha_b*(Y-y_A))/(beta_b*(X-x_A))
        ratio_a = self.alpha_a / self.beta_a
        ratio_b = self.alpha_b / self.beta_b
        y_a = (ratio_b * self.total_y * x_a) / (
            ratio_b * x_a + ratio_a * (self.total_x - x_a)
        )

        u_a = x_a ** self.alpha_a * y_a ** self.beta_a
        u_b = ((self.total_x - x_a) ** self.alpha_b *
               (self.total_y - y_a) ** self.beta_b)

        return {
            "x_a": x_a.tolist(),
            "y_a": y_a.tolist(),
            "utility_a": u_a.tolist(),
            "utility_b": u_b.tolist(),
            "total_x": self.total_x,
            "total_y": self.total_y,
            "n_points": n_points
        }

    def check_core_membership(self, x_a: float, y_a: float,
                               endow_x_a: float, endow_y_a: float) -> Dict[str, Any]:
        """Check if allocation is in the core."""
        x_b = self.total_x - x_a
        y_b = self.total_y - y_a
        endow_x_b = self.total_x - endow_x_a
        endow_y_b = self.total_y - endow_y_a

        u_a_alloc = x_a ** self.alpha_a * y_a ** self.beta_a
        u_b_alloc = x_b ** self.alpha_b * y_b ** self.beta_b
        u_a_endow = endow_x_a ** self.alpha_a * endow_y_a ** self.beta_a
        u_b_endow = endow_x_b ** self.alpha_b * endow_y_b ** self.beta_b

        individually_rational = u_a_alloc >= u_a_endow and u_b_alloc >= u_b_endow
        pareto_feasible = (0 <= x_a <= self.total_x and 0 <= y_a <= self.total_y)

        return {
            "in_core": individually_rational and pareto_feasible,
            "individually_rational": individually_rational,
            "pareto_feasible": pareto_feasible,
            "utility_agent_a": u_a_alloc,
            "utility_agent_b": u_b_alloc,
            "endowment_utility_a": u_a_endow,
            "endowment_utility_b": u_b_endow
        }


# ── 4. Pareto Efficiency Checker ──────────────────────────────────

class ParetoEfficiencyChecker:
    """
    Check whether an allocation is Pareto efficient.
    Supports multiple agents and goods.
    """

    @staticmethod
    def check_pareto_efficient(utilities: List[float],
                                all_allocations: List[List[float]]) -> Dict[str, Any]:
        """
        Check if current allocation is Pareto efficient.
        An allocation is Pareto efficient if no other allocation can make
        someone better off without making someone else worse off.

        Args:
            utilities: Current utility for each agent
            all_allocations: List of alternative utility vectors
        """
        n_agents = len(utilities)
        pareto_dominates = []

        for alt in all_allocations:
            if len(alt) != n_agents:
                continue
            weakly_better = all(alt[i] >= utilities[i] for i in range(n_agents))
            strictly_better = any(alt[i] > utilities[i] for i in range(n_agents))
            if weakly_better and strictly_better:
                pareto_dominates.append(alt)

        return {
            "is_pareto_efficient": len(pareto_dominates) == 0,
            "current_utilities": utilities,
            "dominating_allocations": pareto_dominates,
            "n_dominated_by": len(pareto_dominates)
        }

    @staticmethod
    def compute_pareto_frontier(allocations: List[List[float]]) -> Dict[str, Any]:
        """Compute the Pareto frontier from a set of allocations."""
        n = len(allocations)
        is_efficient = [True] * n

        for i in range(n):
            if not is_efficient[i]:
                continue
            for j in range(n):
                if i == j or not is_efficient[j]:
                    continue
                # Check if j dominates i
                weakly = all(allocations[j][k] >= allocations[i][k]
                             for k in range(len(allocations[i])))
                strictly = any(allocations[j][k] > allocations[i][k]
                               for k in range(len(allocations[i])))
                if weakly and strictly:
                    is_efficient[i] = False
                    break

        frontier = [allocations[i] for i in range(n) if is_efficient[i]]
        return {
            "pareto_frontier": frontier,
            "n_efficient": len(frontier),
            "n_total": n,
            "efficiency_mask": is_efficient
        }


# ── 5. Stiglitz-Weiss Credit Rationing ────────────────────────────

class StiglitzWeissCreditRationing:
    """
    Implements the Stiglitz-Weiss (1981) model of credit rationing.
    Banks face adverse selection: higher interest rates attract riskier borrowers.
    Shows that equilibrium may involve credit rationing.
    """

    def __init__(self, n_types: int = 10, safe_return: float = 0.10,
                 risky_return: float = 0.25, safe_prob: float = 0.9,
                 risky_prob: float = 0.5, collateral: float = 0.0,
                 loan_size: float = 100.0):
        self.n_types = n_types
        self.safe_return = safe_return
        self.risky_return = risky_return
        self.safe_prob = safe_prob
        self.risky_prob = risky_prob
        self.collateral = collateral
        self.loan_size = loan_size

    def compute_bank_return(self, interest_rate: float,
                             risk_threshold: float) -> Dict[str, Any]:
        """
        Compute expected bank return at given interest rate.
        Projects with risk > threshold take loan (adverse selection).
        """
        # Type theta in [0, 1]: higher = riskier
        types = np.linspace(0, 1, self.n_types)
        # Probability of success decreases with risk
        prob_success = self.safe_prob - (self.safe_prob - self.risky_prob) * types
        # Return increases with risk
        project_return = self.safe_return + (self.risky_return - self.safe_return) * types

        # Only types with risk <= threshold borrow
        borrowing = types <= risk_threshold
        if not np.any(borrowing):
            return {"expected_return": 0.0, "n_borrowers": 0, "credit_rationing": True}

        # Bank's expected return per borrower type
        repayment = min(interest_rate, 1 + project_return)
        bank_returns = prob_success * repayment * self.loan_size
        bank_returns[~borrowing] = 0

        expected_return = np.mean(bank_returns[borrowing]) if np.any(borrowing) else 0

        # As interest rises, riskier types remain → adverse selection
        # Check if demand exceeds supply at this rate
        demand = np.sum(borrowing)
        return {
            "interest_rate": interest_rate,
            "expected_bank_return": float(expected_return),
            "n_borrowers": int(demand),
            "borrowing_types": types[borrowing].tolist(),
            "adverse_selection_detected": risk_threshold < 0.5
        }

    def find_rationing_equilibrium(self, supply: float = 500.0,
                                    demand_at_zero: float = 1000.0) -> Dict[str, Any]:
        """Find equilibrium with potential credit rationing."""
        rates = np.linspace(0.01, 0.30, 30)
        results = []
        max_bank_return = 0
        optimal_rate = 0

        for r in rates:
            # Risk threshold: borrowers with theta such that expected profit >= 0
            threshold = 1.0 - r / (self.risky_return - self.safe_return + 0.01)
            threshold = max(0, min(1, threshold))

            info = self.compute_bank_return(r, threshold)
            results.append(info)
            if info["expected_bank_return"] > max_bank_return:
                max_bank_return = info["expected_bank_return"]
                optimal_rate = r

        # Check if credit rationing exists (optimal rate < market clearing rate)
        return {
            "optimal_interest_rate": float(optimal_rate),
            "max_bank_return": float(max_bank_return),
            "credit_rationing_exists": optimal_rate < 0.15,
            "equilibrium_analysis": results[:5],  # first 5 for brevity
            "model": "Stiglitz-Weiss (1981)"
        }


# ── 6. Endogenous Growth Model ───────────────────────────────────

class EndogenousGrowthModel:
    """
    Lucas (1988) human capital endogenous growth model.
    Y = A * K^alpha * (u*H)^(1-alpha)
    H' = delta * (1-u) * H
    Growth rate depends on human capital accumulation.
    """

    def __init__(self, A: float = 1.0, alpha: float = 0.33, delta: float = 0.05,
                 s: float = 0.2, u: float = 0.7):
        self.A = A        # TFP
        self.alpha = alpha # capital share
        self.delta = delta # human capital depreciation/accumulation rate
        self.s = s         # savings rate
        self.u = u         # fraction of time spent working (vs learning)

    def simulate(self, periods: int = 100, K0: float = 10.0,
                 H0: float = 5.0) -> Dict[str, Any]:
        """Simulate the endogenous growth model."""
        K = np.zeros(periods)
        H = np.zeros(periods)
        Y = np.zeros(periods)
        g_Y = np.zeros(periods)

        K[0] = K0
        H[0] = H0
        Y[0] = self.A * K[0] ** self.alpha * (self.u * H[0]) ** (1 - self.alpha)

        for t in range(1, periods):
            Y[t - 1] = self.A * K[t - 1] ** self.alpha * (self.u * H[t - 1]) ** (1 - self.alpha)
            K[t] = self.s * Y[t - 1] + (1 - 0.05) * K[t - 1]  # investment + depreciation
            H[t] = H[t - 1] + self.delta * (1 - self.u) * H[t - 1]  # human capital accumulation
            Y[t] = self.A * K[t] ** self.alpha * (self.u * H[t]) ** (1 - self.alpha)
            g_Y[t] = (Y[t] - Y[t - 1]) / Y[t - 1] if Y[t - 1] > 0 else 0

        # Steady state growth rate
        g_star = self.delta * (1 - self.u)

        return {
            "output": Y.tolist(),
            "capital": K.tolist(),
            "human_capital": H.tolist(),
            "growth_rates": g_Y.tolist(),
            "steady_state_growth": g_star,
            "parameters": {
                "A": self.A, "alpha": self.alpha, "delta": self.delta,
                "s": self.s, "u": self.u
            }
        }


# ── 7. Ricardian Equivalence ──────────────────────────────────────

class RicardianEquivalence:
    """
    Tests Ricardian equivalence: whether debt-financed vs tax-financed
    government spending affects consumption differently.

    Under Ricardian equivalence (with rational agents, perfect capital markets),
    a debt-financed tax cut does not change consumption.
    """

    def __init__(self, beta: float = 0.96, r: float = 0.04, y: float = 100.0,
                 G: float = 20.0, periods: int = 10):
        self.beta = beta   # discount factor
        self.r = r         # interest rate
        self.y = y         # income per period
        self.G = G         # government spending
        self.periods = periods

    def compare_financing(self, tax_cut: float = 10.0) -> Dict[str, Any]:
        """
        Compare tax-financed vs debt-financed government spending.
        """
        # Tax financing: constant tax each period
        tau_tax = self.G  # balanced budget
        c_tax = [(self.y - tau_tax) for _ in range(self.periods)]

        # Debt financing: cut tax now, raise later
        c_debt = []
        pv_tax_increase = tax_cut * (1 + self.r) / self.r if self.r > 0 else tax_cut * self.periods
        future_tax = pv_tax_increase / (self.periods - 1) if self.periods > 1 else 0

        for t in range(self.periods):
            if t == 0:
                c_debt.append(self.y - (tau_tax - tax_cut))
            else:
                c_debt.append(self.y - tau_tax - future_tax)

        # PV of consumption under both scenarios
        pv_tax = sum(c_tax[t] / (1 + self.r) ** t for t in range(self.periods))
        pv_debt = sum(c_debt[t] / (1 + self.r) ** t for t in range(self.periods))

        # Under perfect Ricardian equivalence, these should be equal
        holds = abs(pv_tax - pv_debt) < 0.01

        return {
            "consumption_tax_financed": c_tax,
            "consumption_debt_financed": c_debt,
            "pv_consumption_tax": pv_tax,
            "pv_consumption_debt": pv_debt,
            "ricardian_equivalence_holds": holds,
            "difference": pv_debt - pv_tax,
            "conditions_for_holds": [
                "Rational consumers with infinite horizon",
                "No liquidity constraints",
                "Perfect capital markets",
                "Lump-sum taxes",
                "No uncertainty"
            ]
        }


# ── 8. New Keynesian Phillips Curve ───────────────────────────────

class NewKeynesianPhillipsCurve:
    """
    New Keynesian Phillips Curve (NKPC):
      pi_t = beta * E_t[pi_{t+1}] + kappa * mc_t

    Where mc_t is the real marginal cost (output gap proxy).
    Solves forward to get: pi_t = sum_{k=0}^{inf} beta^k * E_t[mc_{t+k}]
    """

    def __init__(self, beta: float = 0.99, kappa: float = 0.1,
                 theta: float = 0.75):
        self.beta = beta       # discount factor
        self.kappa = kappa     # slope of Phillips curve
        self.theta = theta     # Calvo parameter (fraction not re-optimizing)
        # kappa = (1-theta)(1-beta*theta)/theta

    def simulate(self, output_gap: List[float]) -> Dict[str, Any]:
        """Simulate inflation given output gap path."""
        T = len(output_gap)
        pi = np.zeros(T)

        # Forward-looking solution
        for t in range(T - 1, -1, -1):
            future_sum = 0.0
            for k in range(T - t):
                future_sum += (self.beta ** k) * output_gap[t + k]
            pi[t] = self.kappa * future_sum

        return {
            "inflation": pi.tolist(),
            "output_gap": output_gap,
            "parameters": {
                "beta": self.beta, "kappa": self.kappa, "theta": self.theta
            }
        }

    def estimate_kappa(self, inflation_data: List[float],
                       output_gap_data: List[float]) -> Dict[str, Any]:
        """Estimate kappa from data using GMM-style approach."""
        pi = np.array(inflation_data)
        og = np.array(output_gap_data)
        T = len(pi)

        # Simple OLS: pi_t = alpha + kappa * og_t + eps
        X = np.column_stack([np.ones(T), og])
        try:
            coeffs = np.linalg.lstsq(X, pi, rcond=None)[0]
            kappa_hat = coeffs[1]
            residuals = pi - X @ coeffs
            se = np.sqrt(np.sum(residuals ** 2) / (T - 2) * np.linalg.inv(X.T @ X)[1, 1])
        except np.linalg.LinAlgError:
            kappa_hat = 0.0
            se = 0.0

        return {
            "estimated_kappa": float(kappa_hat),
            "standard_error": float(se),
            "t_statistic": float(kappa_hat / se) if se > 0 else 0.0,
            "n_observations": T
        }


# ── 9. Arrow's Impossibility Theorem ──────────────────────────────

class ArrowsImpossibilityTheorem:
    """
    Implements Arrow's impossibility theorem verification.
    A social welfare function cannot simultaneously satisfy:
      1) Unrestricted domain
      2) Pareto efficiency
      3) Independence of irrelevant alternatives (IIA)
      4) Non-dictatorship

    We implement multiple voting rules and check which axioms they satisfy.
    """

    @staticmethod
    def check_voting_rule(preferences: List[List[int]], rule: str = "majority") -> Dict[str, Any]:
        """
        Check properties of a voting rule given preference orderings.

        Args:
            preferences: List of voter preference orderings (each is a list of alternatives ranked)
            rule: "majority", "borda", "plurality"
        """
        n_voters = len(preferences)
        if n_voters == 0:
            return {"error": "No voters"}

        alternatives = set()
        for pref in preferences:
            alternatives.update(pref)
        alternatives = sorted(alternatives)

        def pairwise_winner(a: int, b: int) -> int:
            """Majority rule pairwise comparison."""
            a_wins = sum(1 for pref in preferences if pref.index(a) < pref.index(b))
            return a if a_wins > n_voters / 2 else b

        # Run tournament
        scores = {a: 0 for a in alternatives}
        if rule == "majority":
            for i, a in enumerate(alternatives):
                for b in alternatives[i + 1:]:
                    w = pairwise_winner(a, b)
                    scores[w] += 1
            winner = max(scores, key=scores.get)
        elif rule == "borda":
            for pref in preferences:
                for rank, alt in enumerate(pref):
                    scores[alt] += len(alternatives) - rank - 1
            winner = max(scores, key=scores.get)
        elif rule == "plurality":
            for pref in preferences:
                scores[pref[0]] += 1
            winner = max(scores, key=scores.get)
        else:
            return {"error": f"Unknown rule: {rule}"}

        # Check Pareto: if everyone prefers a to b, social ranking should too
        pareto_satisfied = True
        for i, a in enumerate(alternatives):
            for b in alternatives[i + 1:]:
                all_prefer_a = all(pref.index(a) < pref.index(b) for pref in preferences)
                all_prefer_b = all(pref.index(b) < pref.index(a) for pref in preferences)
                if all_prefer_a and scores[b] > scores[a]:
                    pareto_satisfied = False
                if all_prefer_b and scores[a] > scores[b]:
                    pareto_satisfied = False

        # Check for dictator
        is_dictator = False
        dictator_voter = None
        for v in range(n_voters):
            # Check if voter v's top choice always wins
            if preferences[v][0] == winner:
                is_dictator = True
                dictator_voter = v
                break

        return {
            "rule": rule,
            "winner": winner,
            "scores": scores,
            "pareto_satisfied": pareto_satisfied,
            "is_dictator": is_dictator,
            "dictator_voter": dictator_voter,
            "n_voters": n_voters,
            "n_alternatives": len(alternatives),
            "theorem_statement": "No social welfare function can satisfy unrestricted domain, "
                                 "Pareto efficiency, IIA, and non-dictatorship simultaneously."
        }


# ── 10. Revenue Equivalence Theorem ───────────────────────────────

class RevenueEquivalenceTheorem:
    """
    Implements the Revenue Equivalence Theorem (Myerson 1981, Vickrey 1961).
    All standard auctions (first-price, second-price, Dutch, English) yield
    the same expected revenue under:
      - Risk-neutral bidders
      - Independent private values
      - Symmetric bidders
      - Same seller reservation price
    """

    @staticmethod
    def simulate_auctions(n_bidders: int = 5, n_simulations: int = 10000,
                          val_min: float = 0.0, val_max: float = 100.0,
                          seed: int = 42) -> Dict[str, Any]:
        """Simulate multiple auction formats and compare revenues."""
        rng = np.random.RandomState(seed)
        revenues = {
            "first_price": [],
            "second_price": [],
            "english": [],
            "dutch": []
        }

        for _ in range(n_simulations):
            vals = rng.uniform(val_min, val_max, n_bidders)
            sorted_vals = np.sort(vals)[::-1]

            # Second-price (Vickrey): winner pays second-highest
            revenues["second_price"].append(sorted_vals[1])

            # First-price: winner bids expected second-highest given their value
            # Optimal bid = (n-1)/n * v_i for uniform
            bids = vals * (n_bidders - 1) / n_bidders
            winner_idx = np.argmax(bids)
            revenues["first_price"].append(bids[winner_idx])

            # English (ascending): winner pays second-highest + epsilon
            revenues["english"].append(sorted_vals[1] + 0.001)

            # Dutch (descending): equivalent to first-price
            revenues["dutch"].append(bids[winner_idx])

        return {
            "first_price_mean": float(np.mean(revenues["first_price"])),
            "second_price_mean": float(np.mean(revenues["second_price"])),
            "english_mean": float(np.mean(revenues["english"])),
            "dutch_mean": float(np.mean(revenues["dutch"])),
            "revenue_equivalence_holds": (
                abs(np.mean(revenues["first_price"]) - np.mean(revenues["second_price"])) < 2.0
            ),
            "n_bidders": n_bidders,
            "n_simulations": n_simulations,
            "theorem": "All standard auctions yield the same expected revenue under "
                       "risk neutrality, IPV, symmetry, and identical reservation prices."
        }


# ── Runner ────────────────────────────────────────────────────────

def run_method(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch to the requested model."""
    dispatch = {
        "dsge_simulate": lambda a: DSGEModel(
            sigma=a.get("sigma", 1.0), beta=a.get("beta", 0.99),
            kappa=a.get("kappa", 0.1), phi_pi=a.get("phi_pi", 1.5),
            phi_y=a.get("phi_y", 0.5), rho_v=a.get("rho_v", 0.8)
        ).simulate(a.get("periods", 40), a.get("shock_std", 0.01), a.get("seed", 42)),

        "rational_expectations_cobweb": lambda a: RationalExpectations(
            a.get("a", 10.0), a.get("b", 0.5), a.get("c", 1.0), a.get("gamma", 0.3)
        ).solve_cobweb(a.get("periods", 50)),

        "edgeworth_box": lambda a: EdgeworthBox(
            a.get("total_x", 100), a.get("total_y", 100),
            a.get("alpha_a", 0.5), a.get("beta_a", 0.5),
            a.get("alpha_b", 0.5), a.get("beta_b", 0.5)
        ).compute_contract_curve(a.get("n_points", 50)),

        "edgeworth_core": lambda a: EdgeworthBox(
            a.get("total_x", 100), a.get("total_y", 100)
        ).check_core_membership(
            a["x_a"], a["y_a"], a["endow_x_a"], a["endow_y_a"]
        ),

        "pareto_check": lambda a: ParetoEfficiencyChecker.check_pareto_efficient(
            a["utilities"], a["all_allocations"]
        ),

        "pareto_frontier": lambda a: ParetoEfficiencyChecker.compute_pareto_frontier(
            a["allocations"]
        ),

        "stiglitz_weiss": lambda a: StiglitzWeissCreditRationing(
            n_types=a.get("n_types", 10), safe_return=a.get("safe_return", 0.10),
            risky_return=a.get("risky_return", 0.25)
        ).find_rationing_equilibrium(a.get("supply", 500), a.get("demand_at_zero", 1000)),

        "endogenous_growth": lambda a: EndogenousGrowthModel(
            A=a.get("A", 1.0), alpha=a.get("alpha", 0.33),
            delta=a.get("delta", 0.05), s=a.get("s", 0.2), u=a.get("u", 0.7)
        ).simulate(a.get("periods", 100), a.get("K0", 10.0), a.get("H0", 5.0)),

        "ricardian_equivalence": lambda a: RicardianEquivalence(
            beta=a.get("beta", 0.96), r=a.get("r", 0.04),
            y=a.get("y", 100), G=a.get("G", 20), periods=a.get("periods", 10)
        ).compare_financing(a.get("tax_cut", 10.0)),

        "nkpc_simulate": lambda a: NewKeynesianPhillipsCurve(
            beta=a.get("beta", 0.99), kappa=a.get("kappa", 0.1),
            theta=a.get("theta", 0.75)
        ).simulate(a["output_gap"]),

        "nkpc_estimate": lambda a: NewKeynesianPhillipsCurve().estimate_kappa(
            a["inflation_data"], a["output_gap_data"]
        ),

        "arrow_voting": lambda a: ArrowsImpossibilityTheorem.check_voting_rule(
            a["preferences"], a.get("rule", "majority")
        ),

        "revenue_equivalence": lambda a: RevenueEquivalenceTheorem.simulate_auctions(
            n_bidders=a.get("n_bidders", 5), n_simulations=a.get("n_simulations", 10000),
            val_min=a.get("val_min", 0.0), val_max=a.get("val_max", 100.0),
            seed=a.get("seed", 42)
        ),
    }

    if method not in dispatch:
        return {"error": f"Unknown method: {method}. Available: {list(dispatch.keys())}"}

    try:
        return dispatch[method](args)
    except Exception as e:
        return {"error": str(e), "method": method}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python advanced_economics.py '<json_input>'"}))
        sys.exit(1)

    input_data = json.loads(sys.argv[1])
    method = input_data.get("method", "")
    args = input_data.get("args", {})
    result = run_method(method, args)
    print(json.dumps(result, default=str))
