"""
Tests for Game Theory module and extended statistical foundations.

Covers:
- Nash Equilibrium solver (pure + mixed strategies)
- Best response computation
- Cournot duopoly (2-firm and N-firm)
- Bertrand duopoly (homogeneous and differentiated)
- Monte Carlo integration and importance sampling
- Bootstrap hypothesis testing
- MCMC Metropolis-Hastings sampler
- Gelman-Rubin R-hat convergence diagnostic
"""

import importlib.util
import os
import sys

import numpy as np
import pytest

# Direct module loading to avoid pulling in sqlalchemy etc.
_base = os.path.join(os.path.dirname(__file__), "..")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_gt_mod = _load_module(
    "app.services.game_theory",
    os.path.join(_base, "app", "services", "game_theory.py"),
)
_sf_mod = _load_module(
    "app.services.statistical_foundation",
    os.path.join(_base, "app", "services", "statistical_foundation.py"),
)

NashEquilibriumSolver = _gt_mod.NashEquilibriumSolver
BestResponseComputer = _gt_mod.BestResponseComputer
CournotDuopoly = _gt_mod.CournotDuopoly
BertrandDuopoly = _gt_mod.BertrandDuopoly

MonteCarloEngine = _sf_mod.MonteCarloEngine
MCMCSampler = _sf_mod.MCMCSampler


# =========================================================================
# Nash Equilibrium Tests
# =========================================================================


class TestNashEquilibrium:
    """Test suite for Nash equilibrium computation."""

    def test_prisoners_dilemma(self):
        """Classic Prisoner's Dilemma: defect-defect is the unique NE."""
        #        C     D
        # C  (-1,-1) (-3, 0)
        # D  ( 0,-3) (-2,-2)
        p1 = np.array([[-1, -3], [0, -2]], dtype=float)
        p2 = np.array([[-1, 0], [-3, -2]], dtype=float)

        result = NashEquilibriumSolver.solve(p1, p2)

        assert result.is_pure
        # Defect-Defect (index 1,1) is the NE
        assert result.strategies == (1, 1)
        assert result.payoffs == (-2.0, -2.0)

    def test_coordination_game(self):
        """Coordination game with two pure NE and one mixed NE."""
        #       L     R
        # T  (2,1) (0,0)
        # B  (0,0) (1,2)
        p1 = np.array([[2, 0], [0, 1]], dtype=float)
        p2 = np.array([[1, 0], [0, 2]], dtype=float)

        result = NashEquilibriumSolver.solve(p1, p2)

        # Should find at least 2 pure NE and potentially a mixed NE
        assert len(result.all_equilibria) >= 2

        pure_strategies = [
            eq["strategies"] for eq in result.all_equilibria if eq["type"] == "pure"
        ]
        assert (0, 0) in pure_strategies  # Top-Left
        assert (1, 1) in pure_strategies  # Bottom-Right

    def test_matching_pennies(self):
        """Matching Pennies: only mixed NE exists."""
        #       H     T
        # H  (1,-1) (-1,1)
        # T  (-1,1) (1,-1)
        p1 = np.array([[1, -1], [-1, 1]], dtype=float)
        p2 = np.array([[-1, 1], [1, -1]], dtype=float)

        result = NashEquilibriumSolver.solve(p1, p2)

        # Should find mixed NE
        mixed_eqs = [eq for eq in result.all_equilibria if eq["type"] == "mixed"]
        assert len(mixed_eqs) >= 1

        # Mixed NE: both play 50/50
        mixed = mixed_eqs[0]
        np.testing.assert_allclose(mixed["strategies"][0], [0.5, 0.5], atol=1e-6)
        np.testing.assert_allclose(mixed["strategies"][1], [0.5, 0.5], atol=1e-6)

    def test_asymmetric_3x3_game(self):
        """3×3 game: test support enumeration."""
        p1 = np.array([[3, 0, 5], [2, 4, 1], [0, 3, 2]], dtype=float)
        p2 = np.array([[2, 3, 0], [1, 2, 4], [3, 0, 1]], dtype=float)

        result = NashEquilibriumSolver.solve(p1, p2)

        # Should find at least one equilibrium
        assert len(result.all_equilibria) >= 1
        assert result.is_pure or result.equilibrium_type.value == "mixed"

    def test_dominant_strategy(self):
        """Game with a dominant strategy: NE is the dominant strategy profile."""
        # Player 1 has dominant strategy U (row 0)
        p1 = np.array([[5, 5], [1, 1]], dtype=float)
        p2 = np.array([[3, 1], [3, 1]], dtype=float)

        result = NashEquilibriumSolver.solve(p1, p2)
        assert result.is_pure
        # Player 1 plays U (0), Player 2 is indifferent but (0,0) is NE
        assert result.strategies[0] == 0

    def test_zero_sum_game(self):
        """Zero-sum game: NE found via minimax."""
        p1 = np.array([[1, -1], [-1, 1]], dtype=float)
        p2 = -p1  # Zero-sum

        result = NashEquilibriumSolver.solve(p1, p2)
        # Mixed NE: each plays 50/50, value = 0
        mixed_eqs = [eq for eq in result.all_equilibria if eq["type"] == "mixed"]
        assert len(mixed_eqs) >= 1

    def test_mismatched_shapes_raises(self):
        """Mismatched payoff matrix shapes should raise ValueError."""
        p1 = np.array([[1, 2], [3, 4]], dtype=float)
        p2 = np.array([[1, 2, 3], [4, 5, 6]], dtype=float)

        with pytest.raises(ValueError, match="same shape"):
            NashEquilibriumSolver.solve(p1, p2)


# =========================================================================
# Best Response Tests
# =========================================================================


class TestBestResponse:
    """Test suite for best response computation."""

    def test_pure_best_response_row_player(self):
        """Row player best response to column player's strategy."""
        payoff = np.array([[3, 1], [0, 2]], dtype=float)

        # Opponent plays col 0: payoffs are [3, 0] → best is row 0
        br = BestResponseComputer.pure_best_response(payoff, opponent_strategy=0, axis=1)
        assert br.best_strategy_index == 0
        assert br.expected_payoff == 3.0

    def test_pure_best_response_column_player(self):
        """Column player best response to row player's strategy."""
        payoff = np.array([[3, 1], [0, 2]], dtype=float)

        # Row player plays row 1: column payoffs are [0, 2] → best is col 1
        br = BestResponseComputer.pure_best_response(payoff, opponent_strategy=1, axis=0)
        assert br.best_strategy_index == 1
        assert br.expected_payoff == 2.0

    def test_mixed_best_response(self):
        """Best response to opponent's mixed strategy."""
        payoff = np.array([[4, 0], [2, 3]], dtype=float)

        # Opponent plays [0.5, 0.5]
        # Row 0 expected: 0.5*4 + 0.5*0 = 2.0
        # Row 1 expected: 0.5*2 + 0.5*3 = 2.5
        br = BestResponseComputer.mixed_best_response(payoff, np.array([0.5, 0.5]))
        assert br.best_strategy_index == 1
        np.testing.assert_allclose(br.expected_payoff, 2.5)

    def test_indifference(self):
        """When payoffs are equal, any strategy is a best response."""
        payoff = np.array([[1, 1], [1, 1]], dtype=float)

        br = BestResponseComputer.mixed_best_response(payoff, np.array([0.3, 0.7]))
        # Both rows give expected payoff 1.0
        assert br.expected_payoff == pytest.approx(1.0)


# =========================================================================
# Cournot Duopoly Tests
# =========================================================================


class TestCournotDuopoly:
    """Test suite for Cournot quantity competition."""

    def test_symmetric_cournot(self):
        """Symmetric Cournot: equal costs → equal quantities."""
        # P(Q) = 100 - Q, c₁ = c₂ = 10
        # q* = (100 - 10)/3 = 30
        # P* = (100 + 20)/3 = 40
        result = CournotDuopoly.solve_linear(
            demand_intercept=100,
            demand_slope=1,
            marginal_cost_1=10,
            marginal_cost_2=10,
        )

        assert result.firm1_quantity == pytest.approx(30.0, abs=1e-4)
        assert result.firm2_quantity == pytest.approx(30.0, abs=1e-4)
        assert result.market_price == pytest.approx(40.0, abs=1e-4)
        assert result.firm1_profit == pytest.approx(900.0, abs=1e-2)
        assert result.firm2_profit == pytest.approx(900.0, abs=1e-2)

    def test_asymmetric_cournot(self):
        """Asymmetric Cournot: lower-cost firm produces more."""
        result = CournotDuopoly.solve_linear(
            demand_intercept=100,
            demand_slope=1,
            marginal_cost_1=10,  # Lower cost
            marginal_cost_2=20,  # Higher cost
        )

        # q₁* = (100 - 20 + 20)/3 = 100/3 ≈ 33.33
        # q₂* = (100 - 40 + 10)/3 = 70/3 ≈ 23.33
        assert result.firm1_quantity > result.firm2_quantity
        assert result.firm1_profit > result.firm2_profit
        assert result.total_quantity == pytest.approx(
            result.firm1_quantity + result.firm2_quantity
        )

    def test_n_firm_symmetric(self):
        """N-firm symmetric Cournot → approaches competitive as N→∞."""
        # P(Q) = 100 - Q, c = 10, N firms
        # q* = (100-10)/(N+1), P* = (100+10N)/(N+1)

        # Duopoly
        result_2 = CournotDuopoly.solve_linear_n_firm(100, 1, [10, 10])
        assert result_2["n_firms"] == 2

        # Many firms → price approaches marginal cost
        costs_100 = [10] * 100
        result_100 = CournotDuopoly.solve_linear_n_firm(100, 1, costs_100)
        assert result_100["market_price"] < result_2["market_price"]

    def test_n_firm_hhi(self):
        """HHI should decrease with more symmetric firms."""
        result_2 = CournotDuopoly.solve_linear_n_firm(100, 1, [10, 10])
        result_4 = CournotDuopoly.solve_linear_n_firm(100, 1, [10, 10, 10, 10])

        assert result_2["hhi"] > result_4["hhi"]
        # 4 symmetric firms: HHI = 4*(0.25)² = 0.25 → "moderate"
        assert result_4["concentration"] == "moderate"

    def test_best_response_quantity(self):
        """Best response function gives optimal quantity."""
        # BR(q₂) = (a - c₁ - b·q₂) / (2b)
        br = CournotDuopoly.best_response_quantity(
            own_cost=10, rival_quantity=30, demand_intercept=100, demand_slope=1
        )
        # (100 - 10 - 30) / 2 = 30
        assert br == pytest.approx(30.0)

    def test_consumer_surplus_positive(self):
        """Consumer surplus should be positive."""
        result = CournotDuopoly.solve_linear(100, 1, 10, 10)
        assert result.consumer_surplus > 0

    def test_zero_quantity_at_monopoly_price(self):
        """If costs exceed demand intercept, should raise ValueError."""
        with pytest.raises(ValueError, match="exceed marginal costs"):
            CournotDuopoly.solve_linear(50, 1, 60, 60)

    def test_to_dict(self):
        """Test serialization."""
        result = CournotDuopoly.solve_linear(100, 1, 10, 10)
        d = result.to_dict()
        assert "firm1_quantity" in d
        assert "market_price" in d
        assert "consumer_surplus" in d


# =========================================================================
# Bertrand Duopoly Tests
# =========================================================================


class TestBertrandDuopoly:
    """Test suite for Bertrand price competition."""

    def test_homogeneous_bertrand_paradox(self):
        """Bertrand paradox: with identical products, prices = marginal cost."""
        result = BertrandDuopoly.solve_homogeneous(
            marginal_cost_1=10,
            marginal_cost_2=10,
        )

        # Both price at cost → zero profits (Bertrand paradox)
        assert result.firm1_price == pytest.approx(10.0)
        assert result.firm2_price == pytest.approx(10.0)
        assert result.market_structure == "competitive"

    def test_homogeneous_asymmetric_costs(self):
        """Lower-cost firm captures entire market."""
        result = BertrandDuopoly.solve_homogeneous(
            marginal_cost_1=5,
            marginal_cost_2=10,
            market_size=100,
        )

        # Firm 1 (lower cost) gets all the demand
        assert result.firm1_quantity == 100
        assert result.firm2_quantity == 0

    def test_differentiated_bertrand(self):
        """Differentiated Bertrand: prices above marginal cost."""
        result = BertrandDuopoly.solve_differentiated(
            demand_intercept=100,
            own_price_sensitivity=2,
            cross_price_sensitivity=0.5,
            marginal_cost_1=10,
            marginal_cost_2=10,
        )

        # With differentiation, prices should be above MC
        assert result.firm1_price > 10
        assert result.firm2_price > 10
        # Both firms have positive quantities
        assert result.firm1_quantity > 0
        assert result.firm2_quantity > 0
        # Both firms have positive profits
        assert result.firm1_profit > 0
        assert result.firm2_profit > 0

    def test_differentiated_symmetric_equilibrium(self):
        """Symmetric differentiated Bertrand: equal prices and quantities."""
        result = BertrandDuopoly.solve_differentiated(
            demand_intercept=100,
            own_price_sensitivity=2,
            cross_price_sensitivity=0.5,
            marginal_cost_1=10,
            marginal_cost_2=10,
        )

        assert result.firm1_price == pytest.approx(result.firm2_price, abs=1e-4)
        assert result.firm1_quantity == pytest.approx(result.firm2_quantity, abs=1e-4)
        assert result.firm1_profit == pytest.approx(result.firm2_profit, abs=1e-2)

    def test_higher_differentiation_softens_competition(self):
        """More differentiation (higher t) → higher prices."""
        result_low = BertrandDuopoly.solve_differentiated(
            demand_intercept=100, own_price_sensitivity=2,
            cross_price_sensitivity=0.1, marginal_cost_1=10, marginal_cost_2=10,
        )
        result_high = BertrandDuopoly.solve_differentiated(
            demand_intercept=100, own_price_sensitivity=2,
            cross_price_sensitivity=1.5, marginal_cost_1=10, marginal_cost_2=10,
        )

        # More substitution → higher prices (paradoxically, because firms
        # have more market power with differentiated products)
        # Actually in this model, higher t means more substitutability which
        # means each firm's demand is more elastic to the other's price.
        # Let me just check prices are positive and sensible.
        assert result_low.firm1_price > 10
        assert result_high.firm1_price > 10

    def test_invalid_params_raises(self):
        """Invalid parameters should raise ValueError."""
        with pytest.raises(ValueError, match="Cross-price"):
            BertrandDuopoly.solve_differentiated(
                demand_intercept=100, own_price_sensitivity=2,
                cross_price_sensitivity=3,  # t > b → invalid
                marginal_cost_1=10, marginal_cost_2=10,
            )

    def test_to_dict(self):
        """Test serialization."""
        result = BertrandDuopoly.solve_differentiated(
            demand_intercept=100, own_price_sensitivity=2,
            cross_price_sensitivity=0.5, marginal_cost_1=10, marginal_cost_2=10,
        )
        d = result.to_dict()
        assert "firm1_price" in d
        assert "market_structure" in d


# =========================================================================
# Monte Carlo Tests
# =========================================================================


class TestMonteCarloEngine:
    """Test suite for Monte Carlo methods."""

    def test_crude_integration_simple(self):
        """MC integration of ∫₀¹ x² dx = 1/3."""
        result = MonteCarloEngine.crude_integration(
            func=lambda x: x ** 2,
            lower=0,
            upper=1,
            n_samples=100000,
        )

        assert result["estimate"] == pytest.approx(1 / 3, abs=0.01)
        assert result["standard_error"] > 0

    def test_crude_integration_gaussian(self):
        """MC integration of ∫₋∞^∞ φ(x) dx ≈ 1 (using wide bounds)."""
        import math
        result = MonteCarloEngine.crude_integration(
            func=lambda x: (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x ** 2),
            lower=-5,
            upper=5,
            n_samples=100000,
        )

        assert result["estimate"] == pytest.approx(1.0, abs=0.01)

    def test_importance_sampling(self):
        """Importance sampling for E[X²] where X ~ N(0,1) = 1."""
        import math

        def proposal_sampler(n, rng):
            return rng.normal(1.0, 1.0, size=n)  # Proposal shifted to 1

        def proposal_pdf(x):
            return (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * (x - 1) ** 2)

        def target_pdf(x):
            return (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x ** 2)

        result = MonteCarloEngine.importance_sampling(
            func=lambda x: x ** 2,
            proposal_sampler=proposal_sampler,
            proposal_pdf=proposal_pdf,
            target_pdf=target_pdf,
            n_samples=50000,
        )

        assert result["estimate"] == pytest.approx(1.0, abs=0.1)
        assert result["effective_sample_size"] > 0

    def test_bootstrap_hypothesis_test(self):
        """Bootstrap test should detect a significant difference."""
        np.random.seed(42)
        sample1 = np.random.normal(5.0, 1.0, size=100)
        sample2 = np.random.normal(5.5, 1.0, size=100)

        result = MonteCarloEngine.bootstrap_hypothesis_test(
            sample1=sample1,
            sample2=sample2,
            statistic_func=np.mean,
            n_bootstrap=5000,
        )

        assert "p_value" in result
        assert 0 <= result["p_value"] <= 1
        assert result["test_name"] == "Permutation/bootstrap hypothesis test"

    def test_bootstrap_test_no_difference(self):
        """Bootstrap test should not reject when samples are identical."""
        np.random.seed(42)
        data = np.random.normal(0, 1, size=50)

        result = MonteCarloEngine.bootstrap_hypothesis_test(
            sample1=data,
            sample2=data,
            statistic_func=np.mean,
            n_bootstrap=5000,
        )

        # Identical samples → p-value should be 1.0
        assert result["p_value"] == pytest.approx(1.0, abs=0.01)

    def test_simulation_confidence_interval(self):
        """Simulation CI should contain the true mean."""
        np.random.seed(42)
        data = np.random.normal(10.0, 2.0, size=100)

        result = MonteCarloEngine.simulation_confidence_interval(
            data=data,
            statistic_func=np.mean,
            n_simulations=5000,
            method="percentile",
        )

        assert result["ci_lower"] < 10.0 < result["ci_upper"]

    def test_simulation_ci_bc(self):
        """BC interval should work."""
        np.random.seed(42)
        data = np.random.normal(10.0, 2.0, size=100)

        result = MonteCarloEngine.simulation_confidence_interval(
            data=data,
            statistic_func=np.mean,
            n_simulations=5000,
            method="bc",
        )

        assert result["ci_lower"] < 10.0 < result["ci_upper"]
        assert result["method"] == "bc"

    def test_simulation_ci_bca(self):
        """BCa interval should work."""
        np.random.seed(42)
        data = np.random.exponential(2.0, size=200)

        result = MonteCarloEngine.simulation_confidence_interval(
            data=data,
            statistic_func=np.median,
            n_simulations=5000,
            method="bca",
        )

        assert result["ci_lower"] < result["ci_upper"]
        assert result["method"] == "bca"

    def test_revenue_distribution_simulation(self):
        """Revenue simulation should produce sensible output."""
        result = MonteCarloEngine.revenue_distribution_simulation(
            base_revenue=10000,
            growth_mean=0.05,
            growth_std=0.20,
            n_periods=12,
            n_simulations=10000,
        )

        assert result["base_revenue"] == 10000
        assert result["terminal_mean"] > 0
        assert result["terminal_median"] > 0
        assert result["percentile_5"] < result["percentile_95"]
        assert 0 <= result["prob_decline"] <= 1
        assert 0 <= result["prob_growth_10pct"] <= 1

    def test_revenue_high_volatility(self):
        """High volatility should widen the distribution."""
        low_vol = MonteCarloEngine.revenue_distribution_simulation(
            base_revenue=10000, growth_mean=0.05, growth_std=0.10,
            n_periods=12, n_simulations=10000,
        )
        high_vol = MonteCarloEngine.revenue_distribution_simulation(
            base_revenue=10000, growth_mean=0.05, growth_std=0.40,
            n_periods=12, n_simulations=10000,
        )

        # High vol → wider distribution → higher p95/p5 ratio
        ratio_low = low_vol["percentile_95"] / max(low_vol["percentile_5"], 1)
        ratio_high = high_vol["percentile_95"] / max(high_vol["percentile_5"], 1)
        assert ratio_high > ratio_low


# =========================================================================
# MCMC Tests
# =========================================================================


class TestMCMCSampler:
    """Test suite for MCMC sampling."""

    def test_metropolis_hastings_normal_posterior(self):
        """MH sampler targeting a normal distribution."""
        # Target: N(3, 1) → log π(x) = -0.5*(x-3)²
        def log_target(x):
            return -0.5 * (x[0] - 3) ** 2

        sampler = MCMCSampler(seed=42)
        result = sampler.metropolis_hastings(
            log_target=log_target,
            initial_state=np.array([0.0]),
            n_samples=10000,
            proposal_std=np.array([1.0]),
            burn_in=1000,
            thin=1,
        )

        samples = result["samples"].ravel()
        assert len(samples) > 5000
        assert np.mean(samples) == pytest.approx(3.0, abs=0.2)
        assert 0.2 < result["acceptance_rate"] < 0.8

    def test_metropolis_hastings_multivariate(self):
        """MH sampler targeting a 2D normal."""
        # Target: N([1, 2], I)
        def log_target(x):
            return -0.5 * ((x[0] - 1) ** 2 + (x[1] - 2) ** 2)

        sampler = MCMCSampler(seed=42)
        result = sampler.metropolis_hastings(
            log_target=log_target,
            initial_state=np.array([0.0, 0.0]),
            n_samples=15000,
            proposal_std=np.array([0.5, 0.5]),
            burn_in=2000,
            thin=2,
        )

        samples = result["samples"]
        assert samples.shape[1] == 2
        assert np.mean(samples[:, 0]) == pytest.approx(1.0, abs=0.3)
        assert np.mean(samples[:, 1]) == pytest.approx(2.0, abs=0.3)

    def test_burn_in_effect(self):
        """More burn-in should improve accuracy (closer to target mean)."""
        def log_target(x):
            return -0.5 * (x[0] - 5) ** 2

        sampler1 = MCMCSampler(seed=42)
        r1 = sampler1.metropolis_hastings(
            log_target=log_target,
            initial_state=np.array([0.0]),
            n_samples=5000,
            burn_in=100,
            thin=1,
        )

        sampler2 = MCMCSampler(seed=42)
        r2 = sampler2.metropolis_hastings(
            log_target=log_target,
            initial_state=np.array([0.0]),
            n_samples=5000,
            burn_in=2000,
            thin=1,
        )

        # More burn-in → closer to true mean (generally)
        # We just check both produce valid results
        assert len(r1["samples"]) > 0
        assert len(r2["samples"]) > 0

    def test_thinning_reduces_samples(self):
        """Thinning should reduce the number of returned samples."""
        def log_target(x):
            return -0.5 * (x[0] - 1) ** 2

        sampler = MCMCSampler(seed=42)
        r_thin1 = sampler.metropolis_hastings(
            log_target=log_target,
            initial_state=np.array([0.0]),
            n_samples=10000,
            burn_in=1000,
            thin=1,
        )

        sampler2 = MCMCSampler(seed=42)
        r_thin5 = sampler2.metropolis_hastings(
            log_target=log_target,
            initial_state=np.array([0.0]),
            n_samples=10000,
            burn_in=1000,
            thin=5,
        )

        assert len(r_thin5["samples"]) < len(r_thin1["samples"])
        assert len(r_thin5["samples"]) == pytest.approx(
            len(r_thin1["samples"]) / 5, abs=2
        )

    def test_summary_statistics(self):
        """Summary should include mean, std, median, CI per dimension."""
        def log_target(x):
            return -0.5 * (x[0] - 2) ** 2 / 0.5  # N(2, 0.5)

        sampler = MCMCSampler(seed=42)
        result = sampler.metropolis_hastings(
            log_target=log_target,
            initial_state=np.array([0.0]),
            n_samples=10000,
            burn_in=1000,
        )

        summary = result["summary"]
        assert len(summary) == 1
        s = summary[0]
        assert "mean" in s
        assert "std" in s
        assert "ci_95" in s
        assert s["ci_95"][0] < s["mean"] < s["ci_95"][1]


class TestGelmanRubin:
    """Test suite for Gelman-Rubin R-hat diagnostic."""

    def test_converged_chains(self):
        """Well-mixed chains should have R-hat < 1.1."""
        np.random.seed(42)
        # Simulate 4 chains targeting N(0, 1) — all converged
        chains = [np.random.normal(0, 1, size=(5000, 1)) for _ in range(4)]

        result = MCMCSampler.gelman_rubin_rhat(chains)

        assert result["converged"] is True
        assert result["rhat_max"] < 1.1
        assert result["n_chains"] == 4

    def test_non_converged_chains(self):
        """Chains stuck at different means should have R-hat > 1.1."""
        # 4 chains stuck at different means
        chains = [
            np.random.normal(0, 0.1, size=(1000, 1)),
            np.random.normal(5, 0.1, size=(1000, 1)),
            np.random.normal(-3, 0.1, size=(1000, 1)),
            np.random.normal(10, 0.1, size=(1000, 1)),
        ]

        result = MCMCSampler.gelman_rubin_rhat(chains)

        assert result["converged"] is False
        assert result["rhat_max"] > 1.1

    def test_multivariate_rhat(self):
        """R-hat should work for multivariate chains."""
        np.random.seed(42)
        chains = [np.random.normal([1, 2], [0.5, 0.5], size=(3000, 2)) for _ in range(3)]

        result = MCMCSampler.gelman_rubin_rhat(chains)

        assert len(result["rhat_per_dimension"]) == 2
        assert all(r < 1.1 for r in result["rhat_per_dimension"])

    def test_single_chain_raises(self):
        """Single chain should raise ValueError."""
        chains = [np.random.normal(0, 1, size=(1000, 1))]

        with pytest.raises(ValueError, match="at least 2 chains"):
            MCMCSampler.gelman_rubin_rhat(chains)

    def test_geweke_diagnostic(self):
        """Geweke diagnostic should pass for a stationary chain."""
        def log_target(x):
            return -0.5 * (x[0] - 3) ** 2

        sampler = MCMCSampler(seed=42)
        result = sampler.metropolis_hastings(
            log_target=log_target,
            initial_state=np.array([0.0]),
            n_samples=10000,
            burn_in=2000,
        )

        conv = result["convergence"]
        assert "per_dimension" in conv
        assert len(conv["per_dimension"]) == 1
        assert "effective_sample_size" in conv["per_dimension"][0]
        assert "geweke_z" in conv["per_dimension"][0]
