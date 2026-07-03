"""
Game Theory Module — Competitive Strategy Analysis.

Theoretical Foundations:
- ECO 321: Game Theory — Nash equilibrium, dominant strategies, mechanism design
- ECO 422: Industrial Organization — Cournot/Bertrand competition, market structure

This module provides game-theoretic tools for analyzing strategic interactions
among market participants in the Angavu Intelligence ecosystem.

Key Models:
- Nash Equilibrium: Mutual best-response in normal-form games
- Cournot Duopoly: Quantity competition (firms choose output levels)
- Bertrand Duopoly: Price competition (firms choose prices)
- Best Response: Optimal strategy given competitors' actions
- Mechanism Design: Incentive-compatible screening rules

Use Cases:
- Soko Pulse: How do traders price against competitors? Market competition analysis.
- Alama Score: Mechanism design for credit screening — designing contracts that
  elicit truthful self-reporting from borrowers.
- Market structure analysis: Identifying competitive equilibria in local markets.

References:
- Nash, J. (1950). "Equilibrium Points in N-Person Games." PNAS, 36(1), 48-49.
- Cournot, A.A. (1838). Researches into the Mathematical Principles of the Theory
  of Wealth. (Nash-Cournot equilibrium for quantity competition.)
- Bertrand, J. (1883). Review of 'Théorie mathématique de la richesse sociale'.
  (Price competition model.)
- Fudenberg, D. & Tirole, J. (1991). Game Theory. MIT Press.
- Tadelis, S. (2013). Game Theory: An Introduction. Princeton University Press.
- Osborne, M.J. (2004). An Introduction to Game Theory. Oxford University Press.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class EquilibriumType(str, Enum):
    PURE = "pure"
    MIXED = "mixed"


@dataclass
class NashEquilibriumResult:
    """Result of Nash equilibrium computation."""

    equilibrium_type: EquilibriumType
    strategies: Tuple  # (row_strategy, col_strategy) for 2-player
    payoffs: Tuple[float, float]  # (player1_payoff, player2_payoff)
    is_pure: bool
    support: Optional[Tuple[List[int], List[int]]] = None  # for mixed strategies
    all_equilibria: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equilibrium_type": self.equilibrium_type.value,
            "strategies": [
                s.tolist() if isinstance(s, np.ndarray) else s
                for s in self.strategies
            ],
            "payoffs": self.payoffs,
            "is_pure": self.is_pure,
            "support": self.support,
            "n_equilibria": len(self.all_equilibria),
            "all_equilibria": self.all_equilibria,
        }


@dataclass
class CournotResult:
    """Result of Cournot duopoly computation."""

    firm1_quantity: float
    firm2_quantity: float
    market_price: float
    firm1_profit: float
    firm2_profit: float
    total_quantity: float
    consumer_surplus: float
    is_nash_equilibrium: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "firm1_quantity": round(self.firm1_quantity, 4),
            "firm2_quantity": round(self.firm2_quantity, 4),
            "market_price": round(self.market_price, 4),
            "firm1_profit": round(self.firm1_profit, 4),
            "firm2_profit": round(self.firm2_profit, 4),
            "total_quantity": round(self.total_quantity, 4),
            "consumer_surplus": round(self.consumer_surplus, 4),
            "is_nash_equilibrium": self.is_nash_equilibrium,
        }


@dataclass
class BertrandResult:
    """Result of Bertrand duopoly computation."""

    firm1_price: float
    firm2_price: float
    firm1_quantity: float
    firm2_quantity: float
    firm1_profit: float
    firm2_profit: float
    consumer_surplus: float
    market_structure: str  # "competitive", "collusive", "asymmetric"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "firm1_price": round(self.firm1_price, 4),
            "firm2_price": round(self.firm2_price, 4),
            "firm1_quantity": round(self.firm1_quantity, 4),
            "firm2_quantity": round(self.firm2_quantity, 4),
            "firm1_profit": round(self.firm1_profit, 4),
            "firm2_profit": round(self.firm2_profit, 4),
            "consumer_surplus": round(self.consumer_surplus, 4),
            "market_structure": self.market_structure,
        }


@dataclass
class BestResponseResult:
    """Result of best-response computation."""

    player_id: int
    best_strategy_index: int
    best_strategy_mixed: np.ndarray
    expected_payoff: float
    payoff_against_all: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "best_strategy_index": self.best_strategy_index,
            "best_strategy_mixed": self.best_strategy_mixed.tolist(),
            "expected_payoff": round(self.expected_payoff, 4),
            "payoff_against_all": [round(p, 4) for p in self.payoff_against_all],
        }


# ---------------------------------------------------------------------------
# Nash Equilibrium solver
# ---------------------------------------------------------------------------

class NashEquilibriumSolver:
    """
    Nash Equilibrium solver for 2-player normal-form games.

    A Nash equilibrium is a strategy profile (σ₁*, σ₂*) where each player's
    strategy is a best response to the other's:
        u₁(σ₁*, σ₂*) ≥ u₁(σ₁, σ₂*)  ∀ σ₁
        u₂(σ₁*, σ₂*) ≥ u₂(σ₁*, σ₂)  ∀ σ₂

    Supports:
    - Pure strategy Nash equilibria via best-response enumeration
    - Mixed strategy Nash equilibria via support enumeration (for small games)

    References:
    - Nash, J. (1950). PNAS 36(1), 48-49.
    - Porter, Nudelman & Shoham (2008). "Simple Search Methods for Finding a
      Nash Equilibrium." Games and Economic Behavior, 63(2), 641-662.
    """

    @staticmethod
    def find_pure_equilibria(
        payoff_matrix_p1: np.ndarray,
        payoff_matrix_p2: np.ndarray,
    ) -> List[Dict[str, Any]]:
        """
        Find all pure-strategy Nash equilibria by enumeration.

        A pure NE exists at (i, j) if:
        - i is a best response for P1 given P2 plays j
        - j is a best response for P2 given P1 plays i

        Args:
            payoff_matrix_p1: Player 1's payoff matrix (n1 × n2)
            payoff_matrix_p2: Player 2's payoff matrix (n1 × n2)

        Returns:
            List of equilibria, each with strategies, payoffs, and indices
        """
        payoff_matrix_p1 = np.asarray(payoff_matrix_p1, dtype=float)
        payoff_matrix_p2 = np.asarray(payoff_matrix_p2, dtype=float)
        n1, n2 = payoff_matrix_p1.shape

        equilibria = []

        # For each column j, find P1's best responses
        for j in range(n2):
            p1_payoffs_col = payoff_matrix_p1[:, j]
            best_p1 = np.where(p1_payoffs_col == p1_payoffs_col.max())[0]

            for i in best_p1:
                # Check if j is a best response for P2 given P1 plays i
                p2_payoffs_row = payoff_matrix_p2[i, :]
                best_p2 = np.where(p2_payoffs_row == p2_payoffs_row.max())[0]

                if j in best_p2:
                    equilibria.append({
                        "strategies": (int(i), int(j)),
                        "payoffs": (
                            float(payoff_matrix_p1[i, j]),
                            float(payoff_matrix_p2[i, j]),
                        ),
                        "type": "pure",
                        "indices": (int(i), int(j)),
                    })

        # Deduplicate
        seen = set()
        unique = []
        for eq in equilibria:
            key = eq["strategies"]
            if key not in seen:
                seen.add(key)
                unique.append(eq)

        return unique

    @staticmethod
    def find_mixed_equilibria_2x2(
        payoff_matrix_p1: np.ndarray,
        payoff_matrix_p2: np.ndarray,
    ) -> Optional[Dict[str, Any]]:
        """
        Find mixed-strategy equilibrium for 2×2 games analytically.

        For a 2×2 game with payoff matrices:
            P1: [[a, b], [c, d]]
            P2: [[e, f], [g, h]]

        Mixed NE for P1 (plays row 0 with prob p):
            p = (h - g) / (e - f - g + h)

        Mixed NE for P2 (plays col 0 with prob q):
            q = (d - b) / (a - b - c + d)

        Only valid when 0 < p < 1 and 0 < q < 1.

        Args:
            payoff_matrix_p1: 2×2 payoff matrix for player 1
            payoff_matrix_p2: 2×2 payoff matrix for player 2

        Returns:
            Mixed equilibrium dict or None if no mixed NE exists
        """
        A = np.asarray(payoff_matrix_p1, dtype=float)
        B = np.asarray(payoff_matrix_p2, dtype=float)

        if A.shape != (2, 2) or B.shape != (2, 2):
            raise ValueError("This method requires 2×2 games")

        a, b, c, d = A[0, 0], A[0, 1], A[1, 0], A[1, 1]
        e, f, g, h = B[0, 0], B[0, 1], B[1, 0], B[1, 1]

        denom_p = e - f - g + h
        denom_q = a - b - c + d

        if abs(denom_p) < 1e-12 or abs(denom_q) < 1e-12:
            return None  # Degenerate game

        p = (h - g) / denom_p  # P1 plays row 0 with prob p
        q = (d - b) / denom_q  # P2 plays col 0 with prob q

        if not (0 < p < 1 and 0 < q < 1):
            return None  # Mixed strategy not interior

        # Expected payoffs
        p1_payoff = p * (q * a + (1 - q) * b) + (1 - p) * (q * c + (1 - q) * d)
        p2_payoff = q * (p * e + (1 - p) * g) + (1 - q) * (p * f + (1 - p) * h)

        return {
            "strategies": (np.array([p, 1 - p]), np.array([q, 1 - q])),
            "payoffs": (round(float(p1_payoff), 4), round(float(p2_payoff), 4)),
            "type": "mixed",
            "support": ([0, 1], [0, 1]),
        }

    @staticmethod
    def find_mixed_equilibria_support_enumeration(
        payoff_matrix_p1: np.ndarray,
        payoff_matrix_p2: np.ndarray,
        max_support_size: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Find mixed-strategy equilibria via support enumeration.

        For each pair of supports (S₁ ⊆ strategies of P1, S₂ ⊆ strategies of P2),
        solve for mixed strategies that make all support strategies indifferent.

        This is exact for small games but exponential in support size.
        Practical for games up to ~5×5.

        References:
        - Porter, Nudelman & Shoham (2008). Games and Economic Behavior.
        - Dickhaut, J. & Kaplan, T. (1991). "A Program for Finding Nash
          Equilibria." Mathl. Comput. Modelling, 16(10-11), 87-97.

        Args:
            payoff_matrix_p1: P1's payoff matrix (n1 × n2)
            payoff_matrix_p2: P2's payoff matrix (n1 × n2)
            max_support_size: Maximum support size to enumerate

        Returns:
            List of mixed equilibria
        """
        from itertools import combinations

        A = np.asarray(payoff_matrix_p1, dtype=float)
        B = np.asarray(payoff_matrix_p2, dtype=float)
        n1, n2 = A.shape

        equilibria = []

        for s1_size in range(1, min(n1, max_support_size) + 1):
            for s1 in combinations(range(n1), s1_size):
                for s2_size in range(1, min(n2, max_support_size) + 1):
                    for s2 in combinations(range(n2), s2_size):
                        try:
                            eq = NashEquilibriumSolver._solve_support(
                                A, B, list(s1), list(s2)
                            )
                            if eq is not None:
                                equilibria.append(eq)
                        except (np.linalg.LinAlgError, ValueError):
                            continue

        # Deduplicate
        unique = []
        seen = set()
        for eq in equilibria:
            s1_key = tuple(np.round(eq["strategies"][0], 6))
            s2_key = tuple(np.round(eq["strategies"][1], 6))
            key = (s1_key, s2_key)
            if key not in seen:
                seen.add(key)
                unique.append(eq)

        return unique

    @staticmethod
    def _solve_support(
        A: np.ndarray,
        B: np.ndarray,
        s1: List[int],
        s2: List[int],
    ) -> Optional[Dict[str, Any]]:
        """Solve for mixed equilibrium on given supports."""
        n1, n2 = A.shape
        k1, k2 = len(s1), len(s2)

        # For P1 to be indifferent among s1 strategies against P2's mix over s2:
        # A[s1[i], :] @ q = A[s1[j], :] @ q  for all i,j in support
        # Also: sum(q) = 1

        # Build system: for P1 indifference (k1-1 equations + sum=1)
        # against P2's mix q over s2
        B_sub = B[np.ix_(s1, s2)]  # k1 × k2
        if k1 > 1:
            # Indifference: consecutive rows equal payoff
            diff_rows = B_sub[1:, :] - B_sub[:-1, :]  # (k1-1) × k2
            A_sys = np.vstack([diff_rows, np.ones((1, k2))])
            b_sys = np.zeros(k1)
            b_sys[-1] = 1.0
        else:
            A_sys = np.ones((1, k2))
            b_sys = np.array([1.0])

        q_sub = np.linalg.lstsq(A_sys, b_sys, rcond=None)[0]

        # For P2 indifference: P1's mix p over s1
        A_sub = A[np.ix_(s1, s2)]  # k1 × k2
        if k2 > 1:
            diff_cols = A_sub[:, 1:] - A_sub[:, :-1]  # k1 × (k2-1)
            A_sys2 = np.vstack([diff_cols.T, np.ones((1, k1))])
            b_sys2 = np.zeros(k2)
            b_sys2[-1] = 1.0
        else:
            A_sys2 = np.ones((1, k1))
            b_sys2 = np.array([1.0])

        p_sub = np.linalg.lstsq(A_sys2, b_sys2, rcond=None)[0]

        # Check validity: all probabilities in (0, 1)
        tol = 1e-8
        if np.any(q_sub < -tol) or np.any(p_sub < -tol):
            return None
        if np.any(q_sub > 1 + tol) or np.any(p_sub > 1 + tol):
            return None

        # Clip to [0, 1] and renormalize
        q_sub = np.clip(q_sub, 0, 1)
        p_sub = np.clip(p_sub, 0, 1)
        q_sub /= q_sub.sum()
        p_sub /= p_sub.sum()

        # Build full mixed strategies
        sigma1 = np.zeros(n1)
        sigma2 = np.zeros(n2)
        for i, idx in enumerate(s1):
            sigma1[idx] = p_sub[i]
        for j, idx in enumerate(s2):
            sigma2[idx] = q_sub[j]

        # Expected payoffs
        p1_payoff = float(sigma1 @ A @ sigma2)
        p2_payoff = float(sigma1 @ B @ sigma2)

        return {
            "strategies": (sigma1, sigma2),
            "payoffs": (round(p1_payoff, 4), round(p2_payoff, 4)),
            "type": "mixed",
            "support": ([int(x) for x in s1], [int(x) for x in s2]),
        }

    @classmethod
    def solve(
        cls,
        payoff_matrix_p1: np.ndarray,
        payoff_matrix_p2: np.ndarray,
    ) -> NashEquilibriumResult:
        """
        Find all Nash equilibria for a 2-player normal-form game.

        Combines pure NE enumeration with mixed NE support enumeration.

        Args:
            payoff_matrix_p1: Player 1's payoff matrix (n1 × n2)
            payoff_matrix_p2: Player 2's payoff matrix (n1 × n2)

        Returns:
            NashEquilibriumResult with all found equilibria
        """
        payoff_matrix_p1 = np.asarray(payoff_matrix_p1, dtype=float)
        payoff_matrix_p2 = np.asarray(payoff_matrix_p2, dtype=float)

        if payoff_matrix_p1.shape != payoff_matrix_p2.shape:
            raise ValueError("Payoff matrices must have the same shape")

        # Find pure NE
        pure_eqs = cls.find_pure_equilibria(payoff_matrix_p1, payoff_matrix_p2)

        # Find mixed NE
        mixed_eqs = []
        n1, n2 = payoff_matrix_p1.shape
        if n1 == 2 and n2 == 2:
            mixed = cls.find_mixed_equilibria_2x2(payoff_matrix_p1, payoff_matrix_p2)
            if mixed:
                mixed_eqs.append(mixed)
        else:
            mixed_eqs = cls.find_mixed_equilibria_support_enumeration(
                payoff_matrix_p1, payoff_matrix_p2
            )

        all_eqs = pure_eqs + mixed_eqs

        if not all_eqs:
            # Should not happen by Nash's theorem (for finite games with mixed strategies)
            raise ValueError("No equilibrium found (this should not happen for finite games)")

        # Pick "best" equilibrium (first pure, else first mixed)
        primary = pure_eqs[0] if pure_eqs else mixed_eqs[0]

        return NashEquilibriumResult(
            equilibrium_type=EquilibriumType(primary["type"]),
            strategies=primary["strategies"],
            payoffs=tuple(primary["payoffs"]),
            is_pure=primary["type"] == "pure",
            support=primary.get("support"),
            all_equilibria=[
                {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                 for k, v in eq.items()}
                for eq in all_eqs
            ],
        )


# ---------------------------------------------------------------------------
# Best Response
# ---------------------------------------------------------------------------

class BestResponseComputer:
    """
    Best response computation for normal-form games.

    Player i's best response to opponent strategy σ₋ᵢ:
        BR_i(σ₋ᵢ) = argmax_{σᵢ} u_i(σᵢ, σ₋ᵢ)

    References:
    - Fudenberg & Tirole (1991). Game Theory. MIT Press. Ch. 1.
    """

    @staticmethod
    def pure_best_response(
        payoff_matrix: np.ndarray,
        opponent_strategy: int,
        axis: int = 1,
    ) -> BestResponseResult:
        """
        Find pure best response to opponent's pure strategy.

        Args:
            payoff_matrix: Payoff matrix for the player
            opponent_strategy: Index of opponent's strategy
            axis: 1 if player is row (chooses row given col), 0 if column player

        Returns:
            BestResponseResult
        """
        payoff_matrix = np.asarray(payoff_matrix, dtype=float)

        if axis == 1:
            # Row player: best row given column = opponent_strategy
            payoffs = payoff_matrix[:, opponent_strategy]
        else:
            # Column player: best column given row = opponent_strategy
            payoffs = payoff_matrix[opponent_strategy, :]

        best_idx = int(np.argmax(payoffs))
        n = len(payoffs)
        mixed = np.zeros(n)
        mixed[best_idx] = 1.0

        return BestResponseResult(
            player_id=0,
            best_strategy_index=best_idx,
            best_strategy_mixed=mixed,
            expected_payoff=float(payoffs[best_idx]),
            payoff_against_all=payoffs.tolist(),
        )

    @staticmethod
    def mixed_best_response(
        payoff_matrix: np.ndarray,
        opponent_mixed_strategy: np.ndarray,
    ) -> BestResponseResult:
        """
        Find best response to opponent's mixed strategy.

        Computes expected payoff for each pure strategy against the
        opponent's mixed strategy, then picks the best.

        Args:
            payoff_matrix: Payoff matrix for the player
            opponent_mixed_strategy: Opponent's probability distribution

        Returns:
            BestResponseResult
        """
        payoff_matrix = np.asarray(payoff_matrix, dtype=float)
        opponent_mixed_strategy = np.asarray(opponent_mixed_strategy, dtype=float)

        # Expected payoff for each row strategy
        expected_payoffs = payoff_matrix @ opponent_mixed_strategy
        best_idx = int(np.argmax(expected_payoffs))
        n = len(expected_payoffs)
        mixed = np.zeros(n)
        mixed[best_idx] = 1.0

        return BestResponseResult(
            player_id=0,
            best_strategy_index=best_idx,
            best_strategy_mixed=mixed,
            expected_payoff=float(expected_payoffs[best_idx]),
            payoff_against_all=expected_payoffs.tolist(),
        )


# ---------------------------------------------------------------------------
# Cournot Duopoly
# ---------------------------------------------------------------------------

class CournotDuopoly:
    """
    Cournot model of quantity competition.

    Two firms simultaneously choose quantities q₁, q₂.
    Market price: P(Q) = a - b·Q  where Q = q₁ + q₂
    Firm i profit: πᵢ = (P - cᵢ)·qᵢ

    Nash-Cournot equilibrium:
        q₁* = (a - 2c₁ + c₂) / (3b)
        q₂* = (a - 2c₂ + c₁) / (3b)
        P*  = (a + c₁ + c₂) / 3

    With symmetric costs (c₁ = c₂ = c):
        q* = (a - c) / (3b)
        P* = (a + 2c) / 3

    References:
    - Cournot, A.A. (1838). Researches into the Mathematical Principles of
      the Theory of Wealth.
    - Tirole, J. (1988). The Theory of Industrial Organization. MIT Press.
    - Varian, H.R. (2014). Intermediate Microeconomics. 9th ed. Ch. 28.
    """

    @staticmethod
    def solve_linear(
        demand_intercept: float,
        demand_slope: float,
        marginal_cost_1: float,
        marginal_cost_2: float,
    ) -> CournotResult:
        """
        Solve Cournot duopoly with linear demand P(Q) = a - b·Q.

        Args:
            demand_intercept: a — maximum price (when Q=0)
            demand_slope: b — price sensitivity to total quantity
            marginal_cost_1: c₁ — firm 1's constant marginal cost
            marginal_cost_2: c₂ — firm 2's constant marginal cost

        Returns:
            CournotResult with equilibrium quantities, prices, profits

        Raises:
            ValueError: If parameters are inconsistent (e.g., costs > intercept)
        """
        a = demand_intercept
        b = demand_slope
        c1 = marginal_cost_1
        c2 = marginal_cost_2

        if b <= 0:
            raise ValueError("Demand slope must be positive")
        if a <= max(c1, c2):
            raise ValueError("Demand intercept must exceed marginal costs")

        # Nash-Cournot equilibrium
        q1 = (a - 2 * c1 + c2) / (3 * b)
        q2 = (a - 2 * c2 + c1) / (3 * b)

        q1 = max(q1, 0)
        q2 = max(q2, 0)

        Q = q1 + q2
        P = a - b * Q

        profit1 = (P - c1) * q1
        profit2 = (P - c2) * q2

        # Consumer surplus: ∫₀^Q (a - b·x) dx - P·Q = (a·Q - b·Q²/2) - P·Q
        cs = (a * Q - b * Q ** 2 / 2) - P * Q

        return CournotResult(
            firm1_quantity=q1,
            firm2_quantity=q2,
            market_price=P,
            firm1_profit=profit1,
            firm2_profit=profit2,
            total_quantity=Q,
            consumer_surplus=cs,
        )

    @staticmethod
    def solve_linear_n_firm(
        demand_intercept: float,
        demand_slope: float,
        marginal_costs: List[float],
    ) -> Dict[str, Any]:
        """
        Solve Cournot oligopoly with N firms and linear demand.

        Generalized Nash-Cournot: each firm i maximizes (a - b·Q - cᵢ)·qᵢ.
        FOC: a - b·qᵢ - b·Q₋ᵢ - cᵢ = 0

        Symmetric case: q* = (a - c) / (b·(N+1)), P = (a + Nc)/(N+1)

        Args:
            demand_intercept: a
            demand_slope: b
            marginal_costs: List of marginal costs [c₁, c₂, ..., cₙ]

        Returns:
            Dict with equilibrium quantities, prices, profits, HHI
        """
        a = demand_intercept
        b = demand_slope
        costs = list(marginal_costs)
        N = len(costs)

        if b <= 0:
            raise ValueError("Demand slope must be positive")
        if N == 0:
            raise ValueError("Need at least one firm")

        # Solve system of FOCs:
        # a - b·qᵢ - b·(Σqⱼ - qᵢ) - cᵢ = 0  for each i
        # => a - b·Σqⱼ - cᵢ = 0  (since the -b·qᵢ + b·qᵢ cancel... no)
        # Actually: a - b·qᵢ - b·Σ_{j≠i} qⱼ - cᵢ = 0
        # => (N+1)·b·qᵢ = a - cᵢ - b·Σ_{j≠i} qⱼ
        # In matrix form: (I + 11ᵀ)·b·q = (a - c)·1  ... actually:
        #
        # The system is: for each i, a - b·qᵢ - b·∑_{j≠i} qⱼ - cᵢ = 0
        # => b·qᵢ + b·∑_{j≠i} qⱼ = a - cᵢ
        # => b·∑_j qⱼ = a - cᵢ
        # => Q = (a - cᵢ)/b  ... this must hold for all i simultaneously,
        # which is only possible if all cᵢ are equal.
        #
        # For asymmetric costs, we use the general FOC system:
        # a - 2b·qᵢ - b·∑_{j≠i} qⱼ = cᵢ
        # => 2b·qᵢ + b·∑_{j≠i} qⱼ = a - cᵢ
        # Matrix form: (b·I + b·11ᵀ)·q = (a - c)  ... no:
        # The coefficient matrix is b·(I + 11ᵀ - I) = b·11ᵀ? No...
        #
        # Let's be careful:
        # ∂πᵢ/∂qᵢ = a - 2b·qᵢ - b·∑_{j≠i} qⱼ - cᵢ = 0
        # => 2b·qᵢ + b·∑_{j≠i} qⱼ = a - cᵢ
        # For the matrix: diagonal = 2b, off-diagonal = b
        # A = b·(I + 11ᵀ) where I is identity and 1 is ones vector
        # Actually: A[i,i] = 2b, A[i,j] = b for j≠i
        # So A = b·I + b·(11ᵀ - I) = b·I + b·11ᵀ - b·I = b·11ᵀ? No.
        # A = b·(I + 11ᵀ - I) ... hmm.
        # A[i,i] = 2b, A[i,j≠i] = b
        # This is: A = b·I + b·ones(N,N)
        # Wait: b·I has b on diagonal, b·ones has b everywhere.
        # So A = b·I + b·ones = b on diagonal + b off diagonal = 2b on diag, b off. Yes!

        A_mat = b * np.eye(N) + b * np.ones((N, N))
        rhs = np.array([a - c for c in costs])
        quantities = np.linalg.solve(A_mat, rhs)
        quantities = np.maximum(quantities, 0)

        Q = quantities.sum()
        P = a - b * Q

        profits = [(P - c) * q for c, q in zip(costs, quantities)]
        cs = (a * Q - b * Q ** 2 / 2) - P * Q

        # HHI (Herfindahl-Hirschman Index)
        shares = quantities / Q if Q > 0 else np.ones(N) / N
        hhi = float(np.sum(shares ** 2))

        return {
            "quantities": [round(float(q), 4) for q in quantities],
            "market_price": round(float(P), 4),
            "total_quantity": round(float(Q), 4),
            "profits": [round(float(p), 4) for p in profits],
            "consumer_surplus": round(float(cs), 4),
            "hhi": round(hhi, 4),
            "n_firms": N,
            "concentration": "competitive" if hhi < 0.15 else (
                "moderate" if hhi < 0.25 else "concentrated"
            ),
        }

    @staticmethod
    def best_response_quantity(
        own_cost: float,
        rival_quantity: float,
        demand_intercept: float,
        demand_slope: float,
    ) -> float:
        """
        Best response quantity in Cournot duopoly.

        BR(q₋ᵢ) = (a - cᵢ - b·q₋ᵢ) / (2b)

        Args:
            own_cost: Firm's marginal cost
            rival_quantity: Rival firm's quantity
            demand_intercept: a
            demand_slope: b

        Returns:
            Optimal quantity
        """
        a = demand_intercept
        b = demand_slope
        br = (a - own_cost - b * rival_quantity) / (2 * b)
        return max(br, 0)


# ---------------------------------------------------------------------------
# Bertrand Duopoly
# ---------------------------------------------------------------------------

class BertrandDuopoly:
    """
    Bertrand model of price competition.

    Two firms simultaneously choose prices p₁, p₂.
    Consumers buy from the lowest-price firm (tie splits demand).
    Each firm has constant marginal cost cᵢ.

    Standard result (with homogeneous goods):
    - Nash equilibrium: p₁* = p₂* = min(c₁, c₂)  (competitive pricing)
    - With symmetric costs: p* = c, π₁ = π₂ = 0

    With differentiated goods (Hotelling-style):
    - Demand: qᵢ(pᵢ, pⱼ) = a - pᵢ + t·pⱼ  (t = differentiation parameter)
    - NE prices are above marginal cost (softer competition with differentiation)

    References:
    - Bertrand, J. (1883). Journal des Savants, 67, 499-508.
    - Tirole, J. (1988). The Theory of Industrial Organization. MIT Press. Ch. 5.
    - Singh, N. & Vives, X. (1984). "Price and Quantity Competition in a
      Differentiated Duopoly." RAND Journal of Economics, 15(4), 546-554.
    """

    @staticmethod
    def solve_homogeneous(
        marginal_cost_1: float,
        marginal_cost_2: float,
        market_size: float = 1000.0,
    ) -> BertrandResult:
        """
        Solve Bertrand duopoly with homogeneous goods.

        With identical products, the firm with the lower price captures
        the entire market. Nash equilibrium drives prices to marginal cost.

        Args:
            marginal_cost_1: Firm 1's marginal cost
            marginal_cost_2: Firm 2's marginal cost
            market_size: Total market demand at competitive price

        Returns:
            BertrandResult
        """
        c1 = marginal_cost_1
        c2 = marginal_cost_2

        # NE: both price at the higher cost (competitive pricing)
        # Firm with lower cost can price infinitesimally below rival
        if c1 <= c2:
            p_eq = c2  # Firm 1 could undercut but in NE both price at c2
            # Actually, in the standard model: p* = c (Bertrand paradox)
            # With asymmetric costs: the efficient firm prices at c₂ - ε
            # For practical purposes: p* ≈ max(c₁, c₂) or both at c₁
            # We use the standard result: both at marginal cost
            p1 = c1
            p2 = c2
            q1 = market_size  # Firm 1 gets all demand
            q2 = 0
        else:
            p1 = c1
            p2 = c2
            q1 = 0
            q2 = market_size

        # Profits (competitive: zero for the marginal firm)
        profit1 = (p1 - c1) * q1
        profit2 = (p2 - c2) * q2

        # Consumer surplus (full surplus at competitive price)
        cs = market_size * (max(c1, c2) - min(c1, c2))  # Savings from competition

        return BertrandResult(
            firm1_price=p1,
            firm2_price=p2,
            firm1_quantity=q1,
            firm2_quantity=q2,
            firm1_profit=profit1,
            firm2_profit=profit2,
            consumer_surplus=cs,
            market_structure="competitive",
        )

    @staticmethod
    def solve_differentiated(
        demand_intercept: float,
        own_price_sensitivity: float,
        cross_price_sensitivity: float,
        marginal_cost_1: float,
        marginal_cost_2: float,
    ) -> BertrandResult:
        """
        Solve Bertrand duopoly with differentiated products.

        Linear demand system:
            q₁ = a - b·p₁ + t·p₂
            q₂ = a - b·p₂ + t·p₁

        Where:
            a = base demand
            b = own-price sensitivity
            t = cross-price sensitivity (0 ≤ t < b for stability)

        Nash equilibrium (symmetric case c₁ = c₂ = c):
            p* = (a + t·c) / (2b - t)  ... but let me derive properly.

        FOC for firm 1: ∂π₁/∂p₁ = a - 2b·p₁ + t·p₂ + b·c₁ = 0
        => p₁ = (a + t·p₂ + b·c₁) / (2b)

        Symmetric NE: p₁ = p₂ = p*
        => p* = (a + b·c) / (2b - t)

        Args:
            demand_intercept: a — base demand
            own_price_sensitivity: b — own-price effect
            cross_price_sensitivity: t — cross-price effect (substitution)
            marginal_cost_1: c₁
            marginal_cost_2: c₂

        Returns:
            BertrandResult
        """
        a = demand_intercept
        b = own_price_sensitivity
        t = cross_price_sensitivity

        if t >= b:
            raise ValueError("Cross-price sensitivity must be less than own-price sensitivity")
        if b <= 0:
            raise ValueError("Own-price sensitivity must be positive")

        # Solve system of FOCs:
        # 2b·p₁ - t·p₂ = a + b·c₁
        # -t·p₁ + 2b·p₂ = a + b·c₂
        A_mat = np.array([[2 * b, -t], [-t, 2 * b]])
        rhs = np.array([a + b * marginal_cost_1, a + b * marginal_cost_2])
        prices = np.linalg.solve(A_mat, rhs)

        p1, p2 = float(prices[0]), float(prices[1])
        q1 = a - b * p1 + t * p2
        q2 = a - b * p2 + t * p1

        q1 = max(q1, 0)
        q2 = max(q2, 0)

        profit1 = (p1 - marginal_cost_1) * q1
        profit2 = (p2 - marginal_cost_2) * q2

        # Consumer surplus approximation
        cs = 0.5 * (q1 + q2) * (a / b)  # Simplified

        # Market structure classification
        markup1 = (p1 - marginal_cost_1) / p1 if p1 > 0 else 0
        markup2 = (p2 - marginal_cost_2) / p2 if p2 > 0 else 0
        avg_markup = (markup1 + markup2) / 2

        if avg_markup < 0.05:
            structure = "competitive"
        elif avg_markup < 0.20:
            structure = "differentiated"
        else:
            structure = "oligopolistic"

        return BertrandResult(
            firm1_price=p1,
            firm2_price=p2,
            firm1_quantity=q1,
            firm2_quantity=q2,
            firm1_profit=profit1,
            firm2_profit=profit2,
            consumer_surplus=cs,
            market_structure=structure,
        )


# ---------------------------------------------------------------------------
# Singleton instances
# ---------------------------------------------------------------------------

nash_solver = NashEquilibriumSolver()
best_response = BestResponseComputer()
cournot = CournotDuopoly()
bertrand = BertrandDuopoly()
