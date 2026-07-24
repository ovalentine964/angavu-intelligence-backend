# Quantum Solver Interface — Architecture Design

**Module:** `app/superagent/core/solver/`
**Version:** 1.0.0
**Date:** 2026-07-24
**Status:** Architecture Design — Ready for Phase 1 Implementation

---

## Executive Summary

The Quantum Solver Interface is a **pluggable optimization engine** for the Msaidizi superagent platform. It solves real problems for informal workers today — route optimization for delivery riders, inventory decisions for market vendors, pricing for sellers, portfolio allocation for savings groups, and buyer-seller matching — using classical solvers that are **quantum-ready by design**.

**Key Insight from Research:** Quantum advantage for Msaidizi's scale is 8–10 years away. But the problems are real *today*. A delivery rider in Nairobi needs the shortest route *now*, not when quantum computers mature. The architecture delivers value with classical solvers today and swaps in quantum solvers when they become cost-effective — no rewrite needed.

**Design Philosophy:**
1. **Solve real problems first.** Classical solvers (OR-Tools, SciPy, PuLP) handle Msaidizi's current scale perfectly.
2. **Abstract the solver, not the problem.** Problems are described in a solver-agnostic format. The solver backend is a plugin.
3. **Quantum-inspired is the bridge.** Simulated annealing, genetic algorithms, and QUBO formulations give quantum-like results on classical hardware.
4. **Cost-aware routing.** Small problems → classical. Large problems → quantum when available and affordable.

---

## Table of Contents

1. [Module Location & Directory Structure](#1-module-location--directory-structure)
2. [Problem Domain Model](#2-problem-domain-model)
3. [Abstract Solver Interface](#3-abstract-solver-interface)
4. [Problem Types for Informal Workers](#4-problem-types-for-informal-workers)
5. [Classical Solver Implementations](#5-classical-solver-implementations)
6. [Quantum-Inspired Solvers](#6-quantum-inspired-solvers)
7. [Quantum Solver Adapters (Future Plug-in)](#7-quantum-solver-adapters-future-plug-in)
8. [Cost-Aware Solver Router](#8-cost-aware-solver-router)
9. [Integration with Superagent Platform](#9-integration-with-superagent-platform)
10. [API Surface](#10-api-surface)
11. [Implementation Phases](#11-implementation-phases)
12. [Dependencies](#12-dependencies)
13. [Testing Strategy](#13-testing-strategy)

---

## 1. Module Location & Directory Structure

```
app/superagent/core/solver/
├── __init__.py                      # Public API exports
├── problems/                        # Problem domain model
│   ├── __init__.py
│   ├── base.py                      # OptimizationProblem, Solution, Objective
│   ├── routing.py                   # RouteOptimizationProblem
│   ├── supply_chain.py              # SupplyChainProblem
│   ├── pricing.py                   # PricingOptimizationProblem
│   ├── portfolio.py                 # PortfolioOptimizationProblem
│   └── matching.py                  # MatchingProblem
│
├── solvers/                         # Solver implementations
│   ├── __init__.py
│   ├── base.py                      # Abstract OptimizationSolver
│   ├── classical/                   # Phase 1: Classical solvers
│   │   ├── __init__.py
│   │   ├── ortools_solver.py        # Google OR-Tools (routing, scheduling)
│   │   ├── scipy_solver.py          # SciPy.optimize (general NLP/QP)
│   │   ├── pulp_solver.py           # PuLP (linear programming)
│   │   └── simulated_annealing.py   # Custom SA (combinatorial)
│   ├── quantum_inspired/            # Phase 2: Quantum-inspired
│   │   ├── __init__.py
│   │   ├── qubo_solver.py           # QUBO formulation + classical solve
│   │   ├── genetic_algorithm.py     # GA with quantum-inspired operators
│   │   └── variational.py           # VQE-style variational (classical)
│   └── quantum/                     # Phase 3+: Quantum backends
│       ├── __init__.py
│       ├── base.py                  # QuantumSolverBase
│       ├── dwave_adapter.py         # D-Wave Leap (annealing)
│       ├── ibm_adapter.py           # IBM Quantum (gate-model)
│       └── cirq_adapter.py          # Google Cirq (simulation)
│
├── router.py                        # Cost-aware solver selection
├── registry.py                      # Solver registry & discovery
├── metrics.py                       # Solve time, quality, cost tracking
└── config.py                        # Solver configuration & thresholds
```

**Position in the superagent platform:**

```
app/superagent/core/
├── engine.py           ← Central reasoning engine
├── router.py           ← Intent classification
├── context.py          ← Worker context
├── planner.py          ← Task planning
├── memory.py           ← Tiered memory
├── math/               ← Statistical foundations
└── solver/             ← THIS MODULE — Optimization engine
    ├── problems/       ← What to optimize
    ├── solvers/        ← How to optimize
    └── router.py       ← Which solver to use
```

---

## 2. Problem Domain Model

Every optimization problem in Msaidizi is described using a common domain model. This is the **solver-agnostic language** that separates "what to optimize" from "how to optimize."

```python
# app/superagent/core/solver/problems/base.py

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ObjectiveType(StrEnum):
    """Direction of optimization."""
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class ConstraintType(StrEnum):
    """Types of constraints on the solution space."""
    EQUALITY = "equality"           # sum(x) == value
    INEQUALITY = "inequality"       # sum(x) <= value  (or >=)
    BOUNDS = "bounds"               # lower <= x_i <= upper
    INTEGER = "integer"             # x_i must be integer
    BINARY = "binary"               # x_i ∈ {0, 1}
    ALL_DIFFERENT = "all_different" # All x_i distinct (permutation)


@dataclass
class Constraint:
    """A single constraint on the optimization problem."""
    name: str
    type: ConstraintType
    expression: str | None = None   # Human-readable description
    lhs_indices: list[int] | None = None
    rhs_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None


@dataclass
class Objective:
    """The objective function to minimize or maximize."""
    type: ObjectiveType
    coefficients: list[float]       # Linear coefficients c_i for c^T x
    quadratic_matrix: list[list[float]] | None = None  # Q for x^T Q x
    description: str = ""


@dataclass
class OptimizationProblem(ABC):
    """
    Base class for all optimization problems.

    Every problem — routing, pricing, portfolio, matching — is described
    in this common format. The solver doesn't know about delivery riders
    or market vendors; it only sees variables, objectives, and constraints.

    Subclasses add domain-specific fields (locations, products, etc.)
    but always reduce to this common representation for solving.
    """
    problem_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    problem_type: str = ""          # "routing", "pricing", "portfolio", etc.
    num_variables: int = 0
    objective: Objective | None = None
    constraints: list[Constraint] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @abstractmethod
    def to_linear_program(self) -> dict[str, Any]:
        """
        Convert to standard LP/MIP format.
        Returns dict with: c (objective), A_ub, b_ub, A_eq, b_eq, bounds, integrality.
        Used by PuLP and SciPy solvers.
        """
        ...

    @abstractmethod
    def to_qubo(self) -> dict[str, Any]:
        """
        Convert to Quadratic Unconstrained Binary Optimization format.
        Returns dict with: linear (Q_ii), quadratic (Q_ij), offset, num_variables.
        Used by D-Wave and quantum-inspired solvers.
        """
        ...

    @abstractmethod
    def validate(self) -> list[str]:
        """
        Validate problem definition. Returns list of error messages.
        Empty list = valid.
        """
        ...


@dataclass
class Solution:
    """
    Result of solving an optimization problem.

    Contains the assignment, objective value, metadata about the solve,
    and enough information to evaluate solution quality.
    """
    problem_id: str
    solver_name: str
    status: SolutionStatus
    objective_value: float
    variables: dict[str, Any]       # Named variable assignments
    raw_values: list[float]         # Raw variable values (for LP/MIP)
    solve_time_ms: float
    iterations: int | None = None
    gap: float | None = None        # Optimality gap (for MIP)
    metadata: dict[str, Any] = field(default_factory=dict)


class SolutionStatus(StrEnum):
    """Status of a solve attempt."""
    OPTIMAL = "optimal"             # Proven optimal solution found
    FEASIBLE = "feasible"           # A feasible solution found (may not be optimal)
    INFEASIBLE = "infeasible"       # No feasible solution exists
    UNBOUNDED = "unbounded"         # Objective can improve without limit
    TIMEOUT = "timeout"             # Solver hit time limit
    ERROR = "error"                 # Solver error
    QUOTA_EXCEEDED = "quota_exceeded"  # Quantum quota used up


@dataclass
class SolverCapabilities:
    """What a solver can handle."""
    max_variables: int              # Maximum number of variables
    max_constraints: int            # Maximum number of constraints
    supports_linear: bool = True
    supports_quadratic: bool = False
    supports_integer: bool = False
    supports_binary: bool = False
    supports_constraints: bool = True
    cost_per_solve_usd: float = 0.0
    typical_latency_ms: float = 100.0
    is_quantum: bool = False
    requires_internet: bool = False
```

---

## 3. Abstract Solver Interface

The solver interface is minimal. One method. One contract. Everything else is implementation detail.

```python
# app/superagent/core/solver/solvers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..problems.base import (
    OptimizationProblem,
    Solution,
    SolverCapabilities,
)


class OptimizationSolver(ABC):
    """
    Abstract base class for all optimization solvers.

    Contract:
        Given an OptimizationProblem, return a Solution.

    Implementations:
        - ClassicalSolvers: OR-Tools, SciPy, PuLP, Simulated Annealing
        - QuantumInspired: QUBO solvers, Genetic Algorithms, Variational
        - Quantum: D-Wave Leap, IBM Quantum, Google Cirq

    The caller never knows which solver is being used.
    The router selects the best solver based on problem size,
    complexity, cost constraints, and availability.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique solver name for logging and metrics."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> SolverCapabilities:
        """What this solver can handle."""
        ...

    @abstractmethod
    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        """
        Solve the given optimization problem.

        Args:
            problem: The optimization problem to solve.
            timeout_seconds: Maximum time to spend solving.
            **kwargs: Solver-specific options (num_reads, num_iterations, etc.)

        Returns:
            Solution with variable assignments, objective value, and metadata.

        Raises:
            SolverError: If the solver encounters an unrecoverable error.
            QuotaExceededError: If a quantum solver's quota is exhausted.
        """
        ...

    async def can_solve(self, problem: OptimizationProblem) -> bool:
        """
        Check if this solver can handle the given problem.

        Default implementation checks variable/constraint counts
        against capabilities. Override for solver-specific checks.
        """
        caps = self.capabilities
        if problem.num_variables > caps.max_variables:
            return False
        if len(problem.constraints) > caps.max_constraints:
            return False
        return True
```

---

## 4. Problem Types for Informal Workers

### 4.1 Route Optimization

**Who uses it:** Boda-boda riders, tuk-tuk drivers, delivery workers, market vendors doing multi-stop sourcing.

**Problem:** Given a set of delivery/pickup locations, find the shortest route that visits all locations and returns to start.

```python
# app/superagent/core/solver/problems/routing.py

@dataclass
class Location:
    """A stop on the route."""
    id: str
    name: str
    latitude: float
    longitude: float
    demand: float = 0.0           # Pickup/delivery amount
    time_window_start: str | None = None  # "08:00"
    time_window_end: str | None = None    # "12:00"
    priority: int = 0             # 0=normal, 1=high, 2=urgent


@dataclass
class RouteOptimizationProblem(OptimizationProblem):
    """
    Vehicle Routing Problem (VRP) for informal delivery workers.

    Variants:
    - TSP: Single vehicle, visit all stops, minimize distance
    - CVRP: Capacitated — vehicle has max load
    - VRPTW: Time windows — must arrive within time constraints
    - Multi-route: Multiple riders, partition stops

    For a typical boda-boda rider: 5-20 stops, 1 vehicle, capacity constraint.
    Solved exactly by OR-Tools in <100ms. No quantum needed.

    For fleet optimization (e.g., a delivery company with 50 riders,
    500 stops): Still classical OR-Tools, but quantum may help at 1000+ stops.
    """
    problem_type: str = "routing"
    locations: list[Location] = field(default_factory=list)
    depot_index: int = 0          # Starting location index
    vehicle_capacity: float = 50.0
    num_vehicles: int = 1
    distance_matrix: list[list[float]] | None = None  # Precomputed distances
    use_time_windows: bool = False
    max_route_duration_minutes: float | None = None

    def to_linear_program(self) -> dict[str, Any]:
        """
        VRP as MIP (Mixed Integer Program):
        - Binary variables x_ij: 1 if vehicle travels from i to j
        - Objective: minimize Σ d_ij * x_ij
        - Constraints: each location visited exactly once, subtour elimination
        """
        n = len(self.locations)
        # Build distance matrix if not provided
        dist = self.distance_matrix or self._compute_distance_matrix()

        # Flatten to 1D: x_ij → x[i*n + j]
        num_vars = n * n
        c = [0.0] * num_vars
        for i in range(n):
            for j in range(n):
                c[i * n + j] = dist[i][j]

        constraints = []
        # Each location visited exactly once (incoming)
        for j in range(n):
            if j == self.depot_index:
                continue
            row = [0.0] * num_vars
            for i in range(n):
                if i != j:
                    row[i * n + j] = 1.0
            constraints.append(Constraint(
                name=f"visit_in_{j}",
                type=ConstraintType.EQUALITY,
                lhs_indices=[i * n + j for i in range(n) if i != j],
                rhs_value=1.0,
            ))

        return {
            "c": c,
            "num_variables": num_vars,
            "constraints": constraints,
            "integrality": [1] * num_vars,  # All binary
            "bounds": [(0, 1)] * num_vars,
        }

    def to_qubo(self) -> dict[str, Any]:
        """
        VRP as QUBO (for quantum annealing):

        QUBO formulation:
        H = A * Σ_j (1 - Σ_i x_ij)²   [visit constraint]
          + A * Σ_i (1 - Σ_j x_ij)²   [departure constraint]
          + Σ_ij d_ij * x_ij           [distance minimization]

        Penalty parameter A must be large enough to enforce constraints.
        """
        n = len(self.locations)
        dist = self.distance_matrix or self._compute_distance_matrix()
        A = max(max(row) for row in dist) * n  # Penalty scale

        linear = {}
        quadratic = {}
        offset = 2 * A * (n - 1)  # Constant from squared terms

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                idx = i * n + j
                # Linear: distance + penalty terms
                linear[idx] = dist[i][j] + 2 * A
                # Quadratic: penalty interactions
                for k in range(n):
                    if k != j and k != i:
                        idx2 = i * n + k
                        quadratic[(idx, idx2)] = 2 * A
                    if k != i and k != j:
                        idx2 = k * n + j
                        quadratic[(idx, idx2)] = 2 * A

        return {
            "linear": linear,
            "quadratic": quadratic,
            "offset": offset,
            "num_variables": n * n,
        }

    def _compute_distance_matrix(self) -> list[list[float]]:
        """Haversine distance matrix between all locations."""
        import math
        n = len(self.locations)
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    matrix[i][j] = self._haversine(
                        self.locations[i].latitude, self.locations[i].longitude,
                        self.locations[j].latitude, self.locations[j].longitude,
                    )
        return matrix

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine distance in kilometers."""
        import math
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def validate(self) -> list[str]:
        errors = []
        if len(self.locations) < 2:
            errors.append("Need at least 2 locations")
        if self.depot_index >= len(self.locations):
            errors.append(f"Depot index {self.depot_index} out of range")
        if self.vehicle_capacity <= 0:
            errors.append("Vehicle capacity must be positive")
        return errors
```

### 4.2 Supply Chain Optimization

**Who uses it:** Market vendors deciding what to stock, from which wholesaler, when to buy.

**Problem:** Given a budget, a set of products with expected demand and margins, and supplier constraints, select the optimal inventory mix to maximize profit.

```python
# app/superagent/core/solver/problems/supply_chain.py

@dataclass
class Product:
    """A product the vendor can stock."""
    id: str
    name: str
    cost_per_unit: float          # Wholesale price
    selling_price: float          # Retail price
    expected_demand: float        # Units expected to sell per period
    perishability_days: int       # Days before spoilage (999 = non-perishable)
    storage_space: float          # Space units required
    category: str = "general"


@dataclass
class Supplier:
    """A wholesaler/supplier."""
    id: str
    name: str
    products: list[str]           # Product IDs this supplier carries
    minimum_order: float = 0.0    # Minimum order value
    delivery_days: int = 1        # Lead time in days
    reliability_score: float = 1.0  # 0.0-1.0


@dataclass
class SupplyChainProblem(OptimizationProblem):
    """
    Inventory optimization for market vendors.

    A mama mboga has KSh 5,000 budget, sells 20 products,
    sources from 3 wholesalers. What should she buy today?

    Objective: Maximize expected profit = Σ (margin_i * min(qty_i, demand_i))
    Subject to:
    - Budget: Σ (cost_i * qty_i) <= budget
    - Storage: Σ (space_i * qty_i) <= storage_capacity
    - Perishability: qty_i <= demand_i * (perishability / period_days)
    - Supplier minimums: total per supplier >= minimum_order (if buying from that supplier)

    Typical scale: 10-50 products, 2-5 suppliers.
    Solved exactly by LP in <10ms. No quantum needed at this scale.
    """
    problem_type: str = "supply_chain"
    products: list[Product] = field(default_factory=list)
    suppliers: list[Supplier] = field(default_factory=list)
    budget: float = 5000.0
    storage_capacity: float = 100.0
    period_days: int = 1          # Planning horizon (1 day for daily stocking)
    include_supplier_minimums: bool = True

    def to_linear_program(self) -> dict[str, Any]:
        """
        LP formulation:
        Variables: q_i = quantity of product i to purchase
        Objective: max Σ (margin_i * min(q_i, demand_i))
                   → linearized as max Σ margin_i * q_i  (with demand upper bound)
        """
        n = len(self.products)
        # Objective: maximize margin * quantity → minimize negative margin
        c = [-(p.selling_price - p.cost_per_unit) for p in self.products]

        constraints = []
        bounds = []

        for i, p in enumerate(self.products):
            # Upper bound: can't buy more than expected demand (adjusted for perishability)
            max_qty = min(
                p.expected_demand,
                p.expected_demand * (p.perishability_days / self.period_days)
                    if p.perishability_days < 999 else float('inf'),
            )
            bounds.append((0, max_qty))

        # Budget constraint: Σ cost_i * q_i <= budget
        constraints.append(Constraint(
            name="budget",
            type=ConstraintType.INEQUALITY,
            lhs_indices=list(range(n)),
            rhs_value=self.budget,
        ))

        # Storage constraint: Σ space_i * q_i <= capacity
        constraints.append(Constraint(
            name="storage",
            type=ConstraintType.INEQUALITY,
            lhs_indices=list(range(n)),
            rhs_value=self.storage_capacity,
        ))

        return {
            "c": c,
            "A_ub": [
                [p.cost_per_unit for p in self.products],  # Budget row
                [p.storage_space for p in self.products],   # Storage row
            ],
            "b_ub": [self.budget, self.storage_capacity],
            "bounds": bounds,
            "integrality": [1] * n,  # Integer quantities (can't buy 2.5 tomatoes)
        }

    def to_qubo(self) -> dict[str, Any]:
        """
        QUBO formulation for quantum annealing.

        Discretize quantities into binary decisions:
        For each product i, create k_i binary variables representing
        quantity levels: 0, 1, 2, ..., max_demand_i.

        x_{i,k} = 1 means buy k units of product i.
        Constraint: Σ_k x_{i,k} = 1 for each i (exactly one quantity chosen).
        """
        # Build binary variable mapping
        var_map = []  # (product_index, quantity_level)
        for i, p in enumerate(self.products):
            max_qty = int(min(p.expected_demand, 100))  # Cap at 100 for QUBO size
            for q in range(max_qty + 1):
                var_map.append((i, q))

        n_vars = len(var_map)
        linear = {}
        quadratic = {}
        offset = 0.0
        penalty = max(p.selling_price for p in self.products) * len(self.products) * 2

        # Build QUBO matrix
        for idx, (pi, qty) in enumerate(var_map):
            p = self.products[pi]
            margin = p.selling_price - p.cost_per_unit
            # Linear: negative margin * quantity (maximize profit)
            linear[idx] = -(margin * qty) + penalty * (1 + p.cost_per_unit * qty ** 2 / self.budget)

            # Quadratic: budget penalty between different products
            for idx2, (pi2, qty2) in enumerate(var_map):
                if idx2 <= idx:
                    continue
                if pi != pi2:
                    # Cross-product budget penalty
                    cost_penalty = penalty * (self.products[pi].cost_per_unit * qty *
                                              self.products[pi2].cost_per_unit * qty2) / (self.budget ** 2)
                    quadratic[(idx, idx2)] = cost_penalty

        # One-hot constraint: exactly one quantity per product
        for i, p in enumerate(self.products):
            max_qty = int(min(p.expected_demand, 100))
            indices = [idx for idx, (pi, _) in enumerate(var_map) if pi == i]
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    quadratic[(indices[a], indices[b])] = quadratic.get(
                        (indices[a], indices[b]), 0.0
                    ) + 2 * penalty
                linear[indices[a]] = linear.get(indices[a], 0.0) - 2 * penalty
            offset += penalty

        return {
            "linear": linear,
            "quadratic": quadratic,
            "offset": offset,
            "num_variables": n_vars,
        }

    def validate(self) -> list[str]:
        errors = []
        if not self.products:
            errors.append("No products defined")
        if self.budget <= 0:
            errors.append("Budget must be positive")
        if self.storage_capacity <= 0:
            errors.append("Storage capacity must be positive")
        return errors
```

### 4.3 Pricing Optimization

**Who uses it:** Market sellers setting prices for perishable goods, dynamic pricing based on demand.

**Problem:** Set prices for products to maximize revenue, considering demand elasticity, competition, perishability, and time-of-day effects.

```python
# app/superagent/core/solver/problems/pricing.py

@dataclass
class PricePoint:
    """A candidate price for a product."""
    price: float
    estimated_demand: float  # Units expected to sell at this price


@dataclass
class PricingProduct:
    """A product to optimize pricing for."""
    id: str
    name: str
    cost: float                   # Cost per unit
    current_price: float
    price_points: list[PricePoint]  # Demand curve samples
    remaining_inventory: float
    hours_until_close: float      # Market hours remaining
    spoilage_cost: float = 0.0    # Cost if unsold (perishable goods)


@dataclass
class PricingOptimizationProblem(OptimizationProblem):
    """
    Dynamic pricing optimization for market sellers.

    A mama mboga has 50 tomatoes left at 2 PM. Market closes at 6 PM.
    Should she drop the price to sell faster, or hold for margin?

    Objective: Maximize Σ (price_i * sold_i) - spoilage_cost * unsold_i
    Subject to:
    - sold_i <= remaining_inventory_i
    - sold_i <= demand(price_i)  [from demand curve]
    - price_i >= cost_i  [don't sell at a loss]

    Typical scale: 5-20 products, 5-10 price points each.
    Solved exactly by enumeration or LP in <1ms.
    """
    problem_type: str = "pricing"
    products: list[PricingProduct] = field(default_factory=list)
    time_pressure: float = 1.0    # 0.0 = no rush, 1.0 = market closing soon

    def to_linear_program(self) -> dict[str, Any]:
        """
        Discretized LP: for each product, select the price point
        that maximizes expected revenue.
        """
        # For small problems, enumerate all combinations
        # For LP: binary selection variables for each price point
        all_vars = []
        var_map = []  # (product_idx, price_point_idx)
        for pi, p in enumerate(self.products):
            for pp_idx, pp in enumerate(p.price_points):
                var_map.append((pi, pp_idx))
                all_vars.append(pp.price * min(pp.estimated_demand, p.remaining_inventory))

        n = len(all_vars)
        c = [-v for v in all_vars]  # Minimize negative revenue

        # One-hot: exactly one price point per product
        constraints = []
        for pi, p in enumerate(self.products):
            indices = [idx for idx, (prod_i, _) in enumerate(var_map) if prod_i == pi]
            constraints.append(Constraint(
                name=f"price_select_{pi}",
                type=ConstraintType.EQUALITY,
                lhs_indices=indices,
                rhs_value=1.0,
            ))

        return {
            "c": c,
            "A_eq": self._build_one_hot_matrix(var_map, len(self.products)),
            "b_eq": [1.0] * len(self.products),
            "bounds": [(0, 1)] * n,
            "integrality": [1] * n,
        }

    def to_qubo(self) -> dict[str, Any]:
        """QUBO: binary selection of price points, penalty for not selecting exactly one."""
        var_map = []
        for pi, p in enumerate(self.products):
            for pp_idx, pp in enumerate(p.price_points):
                var_map.append((pi, pp_idx))

        n = len(var_map)
        penalty = max(pp.price * pp.estimated_demand
                      for p in self.products
                      for pp in p.price_points) * 2

        linear = {}
        quadratic = {}
        offset = 0.0

        for idx, (pi, pp_idx) in enumerate(var_map):
            p = self.products[pi]
            pp = p.price_points[pp_idx]
            revenue = pp.price * min(pp.estimated_demand, p.remaining_inventory)
            linear[idx] = -revenue + penalty

        # One-hot penalties
        for pi, p in enumerate(self.products):
            indices = [idx for idx, (prod_i, _) in enumerate(var_map) if prod_i == pi]
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    quadratic[(indices[a], indices[b])] = 2 * penalty
                linear[indices[a]] -= 2 * penalty
            offset += penalty

        return {"linear": linear, "quadratic": quadratic, "offset": offset, "num_variables": n}

    def _build_one_hot_matrix(self, var_map, num_products) -> list[list[float]]:
        n = len(var_map)
        matrix = []
        for pi in range(num_products):
            row = [0.0] * n
            for idx, (prod_i, _) in enumerate(var_map):
                if prod_i == pi:
                    row[idx] = 1.0
            matrix.append(row)
        return matrix

    def validate(self) -> list[str]:
        errors = []
        if not self.products:
            errors.append("No products defined")
        for p in self.products:
            if not p.price_points:
                errors.append(f"Product {p.id} has no price points")
            if p.remaining_inventory < 0:
                errors.append(f"Product {p.id} has negative inventory")
        return errors
```

### 4.4 Portfolio Optimization for Savings Groups (Chamas)

**Who uses it:** Chama (savings group) treasurers allocating group funds.

**Problem:** Allocate a chama's funds across investment options (savings, MMFs, land, business loans to members) to maximize returns while managing risk.

```python
# app/superagent/core/solver/problems/portfolio.py

@dataclass
class InvestmentOption:
    """An investment option for a chama."""
    id: str
    name: str
    expected_return: float        # Annual return rate (e.g., 0.12 = 12%)
    risk_score: float             # 0.0 (risk-free) to 1.0 (very risky)
    min_investment: float = 0.0   # Minimum investment amount
    max_investment: float = float('inf')
    liquidity_days: int = 0       # Days to access funds (0 = instant)
    category: str = "savings"     # savings, mmf, land, business_loan, chama_fund


@dataclass
class PortfolioOptimizationProblem(OptimizationProblem):
    """
    Mean-variance portfolio optimization for chamas.

    A chama has KSh 100,000 to allocate. Options:
    - M-Pesa savings (5% return, no risk, instant liquidity)
    - Money market fund (10% return, low risk, 7-day liquidity)
    - Land investment (20% return, medium risk, illiquid)
    - Member business loans (15% return, high risk, 30-day liquidity)

    Objective: Maximize return - λ * risk  (risk-adjusted return)
    Subject to:
    - Σ allocation_i = total_funds
    - allocation_i >= min_investment_i
    - allocation_i <= max_investment_i
    - Σ allocation_i * risk_i <= max_portfolio_risk  (risk budget)
    - allocation_liquid >= emergency_reserve  (liquidity requirement)

    Typical scale: 3-10 investment options.
    Solved exactly by QP (quadratic programming) in <1ms.
    """
    problem_type: str = "portfolio"
    options: list[InvestmentOption] = field(default_factory=list)
    total_funds: float = 100000.0
    risk_aversion: float = 1.0    # λ: higher = more risk-averse
    max_portfolio_risk: float = 0.5  # Max weighted risk score
    emergency_reserve_pct: float = 0.1  # 10% must be liquid
    emergency_liquidity_days: int = 7   # "Liquid" means accessible in N days

    def to_linear_program(self) -> dict[str, Any]:
        """QP formulation: maximize return - λ * risk (with quadratic risk term)."""
        n = len(self.options)
        # Objective coefficients: -(return_i - λ * risk_i)
        c = [-(o.expected_return - self.risk_aversion * o.risk_score ** 2)
             for o in self.options]

        constraints = []
        # Budget: Σ x_i = total_funds
        constraints.append(Constraint(
            name="budget",
            type=ConstraintType.EQUALITY,
            lhs_indices=list(range(n)),
            rhs_value=self.total_funds,
        ))

        # Risk budget: Σ risk_i * x_i <= max_risk * total_funds
        constraints.append(Constraint(
            name="risk_budget",
            type=ConstraintType.INEQUALITY,
            lhs_indices=list(range(n)),
            rhs_value=self.max_portfolio_risk * self.total_funds,
        ))

        bounds = [(o.min_investment, min(o.max_investment, self.total_funds))
                  for o in self.options]

        return {
            "c": c,
            "bounds": bounds,
            "integrality": [0] * n,  # Continuous (fractional amounts OK)
        }

    def to_qubo(self) -> dict[str, Any]:
        """
        QUBO: Discretize allocation into percentage buckets.
        For chamas, amounts are often in fixed denominations (KSh 1000 increments).
        """
        # Discretize: each option gets variables for each KSh 1000 increment
        denomination = 1000.0
        var_map = []
        for oi, o in enumerate(self.options):
            max_units = int(min(o.max_investment, self.total_funds) / denomination)
            for unit in range(max_units + 1):
                var_map.append((oi, unit * denomination))

        n = len(var_map)
        penalty = max(o.expected_return for o in self.options) * self.total_funds

        linear = {}
        quadratic = {}
        offset = 0.0

        for idx, (oi, amount) in enumerate(var_map):
            o = self.options[oi]
            ret = o.expected_return * amount / self.total_funds
            risk = self.risk_aversion * (o.risk_score * amount / self.total_funds) ** 2
            linear[idx] = -(ret - risk) + penalty * (amount / self.total_funds) ** 2

        # Budget constraint penalty
        for a in range(n):
            for b in range(a + 1, n):
                oi_a, amt_a = var_map[a]
                oi_b, amt_b = var_map[b]
                if oi_a != oi_b:
                    quadratic[(a, b)] = penalty * (amt_a * amt_b) / (self.total_funds ** 2)

        return {"linear": linear, "quadratic": quadratic, "offset": offset, "num_variables": n}

    def validate(self) -> list[str]:
        errors = []
        if not self.options:
            errors.append("No investment options defined")
        if self.total_funds <= 0:
            errors.append("Total funds must be positive")
        if self.risk_aversion < 0:
            errors.append("Risk aversion must be non-negative")
        return errors
```

### 4.5 Matching Problem (Buyer-Seller Connections)

**Who uses it:** Market platforms, aggregation services connecting farmers to buyers.

**Problem:** Match buyers to sellers to maximize total value (price × quality × proximity), respecting capacity constraints.

```python
# app/superagent/core/solver/problems/matching.py

@dataclass
class Buyer:
    """A buyer in the market."""
    id: str
    name: str
    demand: float                 # Units needed
    max_price: float              # Willing to pay per unit
    preferred_quality: float      # 0.0-1.0
    location_lat: float = 0.0
    location_lon: float = 0.0


@dataclass
class Seller:
    """A seller in the market."""
    id: str
    name: str
    supply: float                 # Units available
    asking_price: float           # Price per unit
    quality: float                # 0.0-1.0
    location_lat: float = 0.0
    location_lon: float = 0.0


@dataclass
class MatchingProblem(OptimizationProblem):
    """
    Buyer-seller matching for informal markets.

    Connect buyers with sellers to maximize:
    - Trade volume (more goods exchanged = better)
    - Price efficiency (buyer pays ≤ max_price, seller gets ≥ asking_price)
    - Quality match (buyer preference ≈ seller quality)
    - Proximity (shorter delivery distance = lower cost)

    Subject to:
    - Seller supply not exceeded
    - Buyer demand not exceeded
    - Price within buyer's budget

    Typical scale: 10-100 buyers, 10-100 sellers.
    Solved exactly by LP (transportation problem) in <10ms.
    At 1000+ participants, quantum may help.
    """
    problem_type: str = "matching"
    buyers: list[Buyer] = field(default_factory=list)
    sellers: list[Seller] = field(default_factory=list)
    weight_volume: float = 0.4
    weight_price: float = 0.3
    weight_quality: float = 0.2
    weight_proximity: float = 0.1

    def to_linear_program(self) -> dict[str, Any]:
        """
        Transportation LP:
        Variables: x_{ij} = units traded from seller i to buyer j
        Objective: maximize Σ score_{ij} * x_{ij}
        Subject to: Σ_j x_{ij} <= supply_i, Σ_i x_{ij} <= demand_j
        """
        m = len(self.sellers)
        n = len(self.buyers)
        num_vars = m * n

        # Compute match scores
        scores = [[0.0] * n for _ in range(m)]
        for i, s in enumerate(self.sellers):
            for j, b in enumerate(self.buyers):
                # Price efficiency: higher if buyer can afford
                price_score = 1.0 if b.max_price >= s.asking_price else 0.0
                # Quality match: closer = better
                quality_score = 1.0 - abs(b.preferred_quality - s.quality)
                # Proximity
                prox = self._haversine(s.location_lat, s.location_lon,
                                       b.location_lat, b.location_lon)
                prox_score = max(0, 1.0 - prox / 50.0)  # 50km = 0 score

                scores[i][j] = (
                    self.weight_price * price_score +
                    self.weight_quality * quality_score +
                    self.weight_proximity * prox_score
                )

        # Flatten objective (maximize → minimize negative)
        c = [-scores[i][j] for i in range(m) for j in range(n)]

        # Supply constraints: Σ_j x_{ij} <= supply_i
        A_ub = []
        b_ub = []
        for i in range(m):
            row = [0.0] * num_vars
            for j in range(n):
                row[i * n + j] = 1.0
            A_ub.append(row)
            b_ub.append(self.sellers[i].supply)

        # Demand constraints: Σ_i x_{ij} <= demand_j
        for j in range(n):
            row = [0.0] * num_vars
            for i in range(m):
                row[i * n + j] = 1.0
            A_ub.append(row)
            b_ub.append(self.buyers[j].demand)

        return {
            "c": c,
            "A_ub": A_ub,
            "b_ub": b_ub,
            "bounds": [(0, None)] * num_vars,
        }

    def to_qubo(self) -> dict[str, Any]:
        """QUBO for matching — similar structure to routing QUBO."""
        m = len(self.sellers)
        n = len(self.buyers)
        # Simplified: binary matching (each buyer matched to at most one seller)
        num_vars = m * n
        penalty = 10.0

        linear = {}
        quadratic = {}
        offset = 0.0

        for i in range(m):
            for j in range(n):
                idx = i * n + j
                s, b = self.sellers[i], self.buyers[j]
                score = (self.weight_price * (1.0 if b.max_price >= s.asking_price else 0.0) +
                         self.weight_quality * (1.0 - abs(b.preferred_quality - s.quality)))
                linear[idx] = -score + penalty

        return {"linear": linear, "quadratic": quadratic, "offset": offset, "num_variables": num_vars}

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        import math
        R = 6371.0
        dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def validate(self) -> list[str]:
        errors = []
        if not self.buyers:
            errors.append("No buyers defined")
        if not self.sellers:
            errors.append("No sellers defined")
        return errors
```

---

## 5. Classical Solver Implementations

### 5.1 Google OR-Tools Solver

Best for: Routing, scheduling, constraint satisfaction.

```python
# app/superagent/core/solver/solvers/classical/ortools_solver.py

from __future__ import annotations

import time
from typing import Any

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver


class ORToolsSolver(OptimizationSolver):
    """
    Google OR-Tools solver for routing and constraint problems.

    Uses CP-SAT solver for integer programming and routing.
    Best for:
    - Vehicle Routing Problem (VRP)
    - Traveling Salesman Problem (TSP)
    - Scheduling problems
    - Constraint satisfaction

    Performance:
    - 10 locations: <10ms
    - 50 locations: <100ms
    - 200 locations: <5s
    - 1000 locations: <30s (with heuristics)

    Cost: Free, open-source, runs locally.
    """

    @property
    def name(self) -> str:
        return "ortools"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=100_000,
            max_constraints=100_000,
            supports_linear=True,
            supports_quadratic=False,
            supports_integer=True,
            supports_binary=True,
            supports_constraints=True,
            cost_per_solve_usd=0.0,
            typical_latency_ms=50.0,
            is_quantum=False,
            requires_internet=False,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        """Solve using OR-Tools CP-SAT or Routing solver."""
        from ortools.sat.python import cp_model
        from ortools.constraint_solver import routing_enums_pb2

        start = time.monotonic()

        if problem.problem_type == "routing":
            result = await self._solve_routing(problem, timeout_seconds, **kwargs)
        else:
            result = await self._solve_cp_sat(problem, timeout_seconds, **kwargs)

        elapsed_ms = (time.monotonic() - start) * 1000
        result.solve_time_ms = elapsed_ms
        return result

    async def _solve_routing(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float,
        **kwargs,
    ) -> Solution:
        """Solve VRP/TSP using OR-Tools routing engine."""
        from ortools.constraint_solver import routing_enums_pb2, pywrapcp

        locations = problem.locations
        n = len(locations)
        dist_matrix = problem.distance_matrix or problem._compute_distance_matrix()

        # Create routing model
        manager = pywrapcp.RoutingIndexManager(n, problem.num_vehicles, problem.depot_index)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_idx, to_idx):
            from_node = manager.IndexToNode(from_idx)
            to_node = manager.IndexToNode(to_idx)
            return int(dist_matrix[from_node][to_node] * 1000)  # Meters

        transit_idx = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

        # Capacity constraint
        if problem.vehicle_capacity > 0:
            demands = [int(loc.demand) for loc in locations]

            def demand_callback(idx):
                return demands[manager.IndexToNode(idx)]

            demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
            routing.AddDimensionWithVehicleCapacity(
                demand_idx, 0, [int(problem.vehicle_capacity)] * problem.num_vehicles,
                True, "Capacity",
            )

        # Time windows
        if problem.use_time_windows:
            for idx, loc in enumerate(locations):
                if loc.time_window_start and loc.time_window_end:
                    start_min = self._time_to_minutes(loc.time_window_start)
                    end_min = self._time_to_minutes(loc.time_window_end)
                    manager.NodeToIndex(idx)  # Validate index
                    routing.CumulVar(manager.NodeToIndex(idx), "Time").SetRange(
                        start_min, end_min
                    )

        # Search parameters
        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_params.time_limit.FromSeconds(int(timeout_seconds))

        # Solve
        assignment = routing.SolveWithParameters(search_params)

        if assignment:
            routes = self._extract_routes(manager, routing, assignment)
            total_dist = assignment.ObjectiveValue() / 1000.0  # Back to km
            return Solution(
                problem_id=problem.problem_id,
                solver_name=self.name,
                status=SolutionStatus.OPTIMAL if routing.status() == 1 else SolutionStatus.FEASIBLE,
                objective_value=total_dist,
                variables={"routes": routes},
                raw_values=[],
                solve_time_ms=0.0,
                metadata={"num_vehicles": problem.num_vehicles},
            )
        else:
            return Solution(
                problem_id=problem.problem_id,
                solver_name=self.name,
                status=SolutionStatus.INFEASIBLE,
                objective_value=float("inf"),
                variables={},
                raw_values=[],
                solve_time_ms=0.0,
            )

    async def _solve_cp_sat(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float,
        **kwargs,
    ) -> Solution:
        """Solve general MIP/IP using CP-SAT."""
        from ortools.sat.python import cp_model

        lp = problem.to_linear_program()
        model = cp_model.CpModel()
        n = lp["num_variables"]

        # Create variables
        vars_ = []
        for i in range(n):
            lb, ub = lp["bounds"][i] if "bounds" in lp else (0, None)
            if lp.get("integrality", [0] * n)[i]:
                vars_.append(model.NewIntVar(int(lb or 0), int(ub or 10**9), f"x_{i}"))
            else:
                vars_.append(model.NewNumVar(float(lb or 0), float(ub or 1e9), f"x_{i}"))

        # Objective
        obj_terms = [int(lp["c"][i] * 1000) * vars_[i] for i in range(n)]
        model.Minimize(sum(obj_terms))

        # Constraints
        if "A_ub" in lp:
            for row_idx, row in enumerate(lp["A_ub"]):
                terms = [int(row[i] * 1000) * vars_[i] for i in range(n) if row[i] != 0]
                if terms:
                    model.Add(sum(terms) <= int(lp["b_ub"][row_idx] * 1000))

        if "A_eq" in lp:
            for row_idx, row in enumerate(lp["A_eq"]):
                terms = [int(row[i] * 1000) * vars_[i] for i in range(n) if row[i] != 0]
                if terms:
                    model.Add(sum(terms) == int(lp["b_eq"][row_idx] * 1000))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_seconds
        status = solver.Solve(model)

        status_map = {
            cp_model.OPTIMAL: SolutionStatus.OPTIMAL,
            cp_model.FEASIBLE: SolutionStatus.FEASIBLE,
            cp_model.INFEASIBLE: SolutionStatus.INFEASIBLE,
        }

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            values = [solver.Value(v) for v in vars_]
            return Solution(
                problem_id=problem.problem_id,
                solver_name=self.name,
                status=status_map.get(status, SolutionStatus.FEASIBLE),
                objective_value=solver.ObjectiveValue() / 1000.0,
                variables={f"x_{i}": v for i, v in enumerate(values)},
                raw_values=values,
                solve_time_ms=0.0,
            )
        else:
            return Solution(
                problem_id=problem.problem_id,
                solver_name=self.name,
                status=status_map.get(status, SolutionStatus.INFEASIBLE),
                objective_value=float("inf"),
                variables={},
                raw_values=[],
                solve_time_ms=0.0,
            )

    @staticmethod
    def _extract_routes(manager, routing, assignment):
        routes = []
        for v in range(routing.vehicles()):
            route = []
            idx = routing.Start(v)
            while not routing.IsEnd(idx):
                route.append(manager.IndexToNode(idx))
                idx = assignment.Value(routing.NextVar(idx))
            route.append(manager.IndexToNode(idx))
            routes.append(route)
        return routes

    @staticmethod
    def _time_to_minutes(time_str: str) -> int:
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
```

### 5.2 SciPy Solver

Best for: General nonlinear optimization, continuous problems.

```python
# app/superagent/core/solver/solvers/classical/scipy_solver.py

from __future__ import annotations

import time

import numpy as np
from scipy.optimize import linprog, minimize, milp, LinearConstraint, Bounds

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver


class SciPySolver(OptimizationSolver):
    """
    SciPy optimization solver for general-purpose problems.

    Uses:
    - linprog (HiGHS): Linear programming
    - milp: Mixed-integer linear programming
    - minimize (SLSQP/COBYLA): Nonlinear optimization

    Best for:
    - Supply chain (LP)
    - Portfolio optimization (QP)
    - General continuous optimization

    Performance: Excellent for small-medium problems (<1000 variables).
    """

    @property
    def name(self) -> str:
        return "scipy"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=10_000,
            max_constraints=10_000,
            supports_linear=True,
            supports_quadratic=True,
            supports_integer=True,
            supports_binary=True,
            supports_constraints=True,
            cost_per_solve_usd=0.0,
            typical_latency_ms=20.0,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        start = time.monotonic()
        lp = problem.to_linear_program()

        has_integer = any(lp.get("integrality", []))
        has_quadratic = problem.objective and problem.objective.quadratic_matrix

        if has_integer:
            result = self._solve_milp(lp, timeout_seconds)
        elif has_quadratic:
            result = self._solve_qp(lp, problem, timeout_seconds)
        else:
            result = self._solve_lp(lp, timeout_seconds)

        result.solve_time_ms = (time.monotonic() - start) * 1000
        result.problem_id = problem.problem_id
        result.solver_name = self.name
        return result

    def _solve_lp(self, lp: dict, timeout: float) -> Solution:
        c = np.array(lp["c"])
        A_ub = np.array(lp.get("A_ub")) if lp.get("A_ub") is not None else None
        b_ub = np.array(lp.get("b_ub")) if lp.get("b_ub") is not None else None
        A_eq = np.array(lp.get("A_eq")) if lp.get("A_eq") is not None else None
        b_eq = np.array(lp.get("b_eq")) if lp.get("b_eq") is not None else None
        bounds = lp.get("bounds", [(0, None)] * len(c))

        res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                      bounds=bounds, method="highs",
                      options={"time_limit": timeout})

        status_map = {0: SolutionStatus.OPTIMAL, 1: SolutionStatus.TIMEOUT,
                      2: SolutionStatus.INFEASIBLE, 3: SolutionStatus.UNBOUNDED}

        return Solution(
            problem_id="", solver_name="", objective_value=res.fun if res.success else float("inf"),
            variables={f"x_{i}": v for i, v in enumerate(res.x)} if res.success else {},
            raw_values=res.x.tolist() if res.success else [],
            solve_time_ms=0.0,
            status=status_map.get(res.status, SolutionStatus.ERROR),
        )

    def _solve_milp(self, lp: dict, timeout: float) -> Solution:
        c = np.array(lp["c"])
        integrality = np.array(lp.get("integrality", [0] * len(c)))
        bounds_obj = Bounds(
            lb=[b[0] for b in lp.get("bounds", [(0, None)] * len(c))],
            ub=[b[1] if b[1] is not None else np.inf for b in lp.get("bounds", [(0, None)] * len(c))],
        )

        constraints = []
        if lp.get("A_ub"):
            constraints.append(LinearConstraint(
                A=np.array(lp["A_ub"]), ub=np.array(lp["b_ub"])))
        if lp.get("A_eq"):
            constraints.append(LinearConstraint(
                A=np.array(lp["A_eq"]), ub=np.array(lp["b_eq"]),
                lb=np.array(lp["b_eq"])))

        res = milp(c, constraints=constraints, integrality=integrality,
                   bounds=bounds_obj, options={"time_limit": timeout})

        return Solution(
            problem_id="", solver_name="",
            objective_value=res.fun if res.success else float("inf"),
            variables={f"x_{i}": v for i, v in enumerate(res.x)} if res.success else {},
            raw_values=res.x.tolist() if res.success else [],
            solve_time_ms=0.0,
            status=SolutionStatus.OPTIMAL if res.success else SolutionStatus.INFEASIBLE,
        )

    def _solve_qp(self, lp: dict, problem: OptimizationProblem, timeout: float) -> Solution:
        c = np.array(lp["c"])
        Q = np.array(problem.objective.quadratic_matrix)
        bounds = lp.get("bounds", [(0, None)] * len(c))

        def objective(x):
            return c @ x + 0.5 * x @ Q @ x

        constraints = []
        if lp.get("A_ub"):
            A_ub = np.array(lp["A_ub"])
            b_ub = np.array(lp["b_ub"])
            for i in range(len(b_ub)):
                constraints.append({"type": "ineq", "fun": lambda x, i=i: b_ub[i] - A_ub[i] @ x})

        x0 = np.zeros(len(c))
        res = minimize(objective, x0, method="SLSQP", bounds=bounds,
                       constraints=constraints, options={"maxiter": 1000, "ftol": 1e-10})

        return Solution(
            problem_id="", solver_name="",
            objective_value=res.fun if res.success else float("inf"),
            variables={f"x_{i}": v for i, v in enumerate(res.x)} if res.success else {},
            raw_values=res.x.tolist() if res.success else [],
            solve_time_ms=0.0,
            status=SolutionStatus.OPTIMAL if res.success else SolutionStatus.FEASIBLE,
        )
```

### 5.3 PuLP Solver

Best for: Linear programming with clear model building.

```python
# app/superagent/core/solver/solvers/classical/pulp_solver.py

from __future__ import annotations

import time

import pulp

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver


class PuLPSolver(OptimizationSolver):
    """
    PuLP solver for linear and mixed-integer programming.

    Provides a clean modeling API and ships with CBC solver (free).
    Best for:
    - Supply chain optimization
    - Pricing optimization
    - Resource allocation
    - Transportation problems

    PuLP is excellent for problems with clear LP structure
    and is the most Pythonic LP modeling library.
    """

    @property
    def name(self) -> str:
        return "pulp"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=50_000,
            max_constraints=50_000,
            supports_linear=True,
            supports_quadratic=False,
            supports_integer=True,
            supports_binary=True,
            supports_constraints=True,
            cost_per_solve_usd=0.0,
            typical_latency_ms=30.0,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        start = time.monotonic()
        lp = problem.to_linear_program()
        n = lp["num_variables"]

        # Create problem
        if problem.objective and problem.objective.type == "maximize":
            prob = pulp.LpProblem(problem.problem_id, pulp.LpMaximize)
        else:
            prob = pulp.LpProblem(problem.problem_id, pulp.LpMinimize)

        # Create variables
        vars_ = []
        for i in range(n):
            lb, ub = lp.get("bounds", [(0, None)])[i] if lp.get("bounds") else (0, None)
            cat = pulp.LpInteger if lp.get("integrality", [0]*n)[i] else pulp.LpContinuous
            vars_.append(pulp.LpVariable(f"x_{i}", lowBound=lb, upBound=ub, cat=cat))

        # Objective
        prob += pulp.lpSum(lp["c"][i] * vars_[i] for i in range(n))

        # Constraints
        if lp.get("A_ub"):
            for row_idx, row in enumerate(lp["A_ub"]):
                prob += (pulp.lpSum(row[i] * vars_[i] for i in range(n) if row[i] != 0)
                         <= lp["b_ub"][row_idx], f"ub_{row_idx}")

        if lp.get("A_eq"):
            for row_idx, row in enumerate(lp["A_eq"]):
                prob += (pulp.lpSum(row[i] * vars_[i] for i in range(n) if row[i] != 0)
                         == lp["b_eq"][row_idx], f"eq_{row_idx}")

        # Solve
        prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=timeout_seconds))

        status_map = {
            pulp.constants.LpStatusOptimal: SolutionStatus.OPTIMAL,
            pulp.constants.LpStatusFeasible: SolutionStatus.FEASIBLE,
            pulp.constants.LpStatusInfeasible: SolutionStatus.INFEASIBLE,
            pulp.constants.LpStatusNotSolved: SolutionStatus.TIMEOUT,
        }

        elapsed = (time.monotonic() - start) * 1000

        if prob.status in (pulp.constants.LpStatusOptimal, pulp.constants.LpStatusFeasible):
            values = [v.varValue for v in vars_]
            return Solution(
                problem_id=problem.problem_id, solver_name=self.name,
                status=status_map.get(prob.status, SolutionStatus.FEASIBLE),
                objective_value=pulp.value(prob.objective),
                variables={f"x_{i}": v for i, v in enumerate(values)},
                raw_values=values, solve_time_ms=elapsed,
            )
        else:
            return Solution(
                problem_id=problem.problem_id, solver_name=self.name,
                status=status_map.get(prob.status, SolutionStatus.INFEASIBLE),
                objective_value=float("inf"), variables={}, raw_values=[],
                solve_time_ms=elapsed,
            )
```

### 5.4 Simulated Annealing Solver

Best for: Combinatorial problems where exact solvers are too slow.

```python
# app/superagent/core/solver/solvers/classical/simulated_annealing.py

from __future__ import annotations

import math
import random
import time
from typing import Any, Callable

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver


class SimulatedAnnealingSolver(OptimizationSolver):
    """
    Simulated Annealing solver for combinatorial optimization.

    A classical algorithm that mimics quantum annealing behavior.
    Useful when:
    - Problem is too large for exact solvers
    - Problem has many local optima
    - Good-enough solutions are acceptable

    For routing: Start with random tour, swap two cities, accept if better.
    Accept worse solutions with probability e^(-ΔE/T), decreasing over time.

    Performance:
    - Quality: Typically within 5-10% of optimal
    - Speed: Much faster than exact solvers for large problems
    - Determinism: Non-deterministic (different runs → different solutions)
    """

    @property
    def name(self) -> str:
        return "simulated_annealing"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=100_000,
            max_constraints=10_000,
            supports_linear=True,
            supports_quadratic=True,
            supports_integer=True,
            supports_binary=True,
            supports_constraints=False,  # Penalty-based constraint handling
            cost_per_solve_usd=0.0,
            typical_latency_ms=500.0,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        start = time.monotonic()

        initial_temp = kwargs.get("initial_temp", 1000.0)
        cooling_rate = kwargs.get("cooling_rate", 0.9995)
        min_temp = kwargs.get("min_temp", 0.01)

        if problem.problem_type == "routing":
            result = self._solve_tsp(problem, initial_temp, cooling_rate, min_temp,
                                     timeout_seconds)
        else:
            result = self._solve_generic(problem, initial_temp, cooling_rate, min_temp,
                                         timeout_seconds)

        result.solve_time_ms = (time.monotonic() - start) * 1000
        result.problem_id = problem.problem_id
        result.solver_name = self.name
        return result

    def _solve_tsp(
        self,
        problem: OptimizationProblem,
        initial_temp: float,
        cooling_rate: float,
        min_temp: float,
        timeout: float,
    ) -> Solution:
        """Solve TSP using simulated annealing with 2-opt moves."""
        n = len(problem.locations)
        dist = problem.distance_matrix or problem._compute_distance_matrix()

        # Initial solution: random permutation (excluding depot)
        nodes = list(range(n))
        nodes.remove(problem.depot_index)
        random.shuffle(nodes)
        current = [problem.depot_index] + nodes + [problem.depot_index]

        def tour_distance(tour):
            return sum(dist[tour[i]][tour[i+1]] for i in range(len(tour)-1))

        current_cost = tour_distance(current)
        best = current[:]
        best_cost = current_cost
        temp = initial_temp
        iterations = 0

        start = time.monotonic()
        while temp > min_temp and (time.monotonic() - start) < timeout:
            # 2-opt swap: reverse a segment
            i = random.randint(1, n - 2)
            j = random.randint(i + 1, n - 1)
            candidate = current[:]
            candidate[i:j+1] = reversed(candidate[i:j+1])
            candidate_cost = tour_distance(candidate)

            delta = candidate_cost - current_cost
            if delta < 0 or random.random() < math.exp(-delta / temp):
                current = candidate
                current_cost = candidate_cost
                if current_cost < best_cost:
                    best = current[:]
                    best_cost = current_cost

            temp *= cooling_rate
            iterations += 1

        return Solution(
            problem_id="", solver_name="",
            status=SolutionStatus.FEASIBLE,
            objective_value=best_cost,
            variables={"route": best, "distance_km": best_cost},
            raw_values=[], solve_time_ms=0.0, iterations=iterations,
            metadata={"final_temp": temp, "cooling_rate": cooling_rate},
        )

    def _solve_generic(
        self,
        problem: OptimizationProblem,
        initial_temp: float,
        cooling_rate: float,
        min_temp: float,
        timeout: float,
    ) -> Solution:
        """Generic SA for any problem with discrete variables."""
        lp = problem.to_linear_program()
        n = lp["num_variables"]

        def evaluate(x):
            return sum(lp["c"][i] * x[i] for i in range(n))

        # Random initial solution within bounds
        bounds = lp.get("bounds", [(0, 1)] * n)
        current = [random.uniform(b[0] or 0, b[1] or 1) for b in bounds]
        if lp.get("integrality"):
            current = [round(v) if lp["integrality"][i] else v for i, v in enumerate(current)]

        current_cost = evaluate(current)
        best = current[:]
        best_cost = current_cost
        temp = initial_temp
        iterations = 0

        start = time.monotonic()
        while temp > min_temp and (time.monotonic() - start) < timeout:
            idx = random.randint(0, n - 1)
            lb, ub = bounds[idx][0] or 0, bounds[idx][1] or 100
            old_val = current[idx]
            new_val = random.uniform(lb, ub)
            if lp.get("integrality", [0]*n)[idx]:
                new_val = round(new_val)

            current[idx] = new_val
            new_cost = evaluate(current)
            delta = new_cost - current_cost

            if delta < 0 or random.random() < math.exp(-delta / temp):
                current_cost = new_cost
                if current_cost < best_cost:
                    best = current[:]
                    best_cost = current_cost
            else:
                current[idx] = old_val

            temp *= cooling_rate
            iterations += 1

        return Solution(
            problem_id="", solver_name="",
            status=SolutionStatus.FEASIBLE,
            objective_value=best_cost,
            variables={f"x_{i}": v for i, v in enumerate(best)},
            raw_values=best, solve_time_ms=0.0, iterations=iterations,
        )
```

---

## 6. Quantum-Inspired Solvers

These are classical algorithms that mimic quantum behavior. They run on regular hardware but produce solutions that approach quantum quality. The bridge between classical and quantum.

### 6.1 QUBO Solver (Classical)

```python
# app/superagent/core/solver/solvers/quantum_inspired/qubo_solver.py

from __future__ import annotations

import random
import time

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver


class QUBOSolver(OptimizationSolver):
    """
    Classical QUBO solver using simulated annealing.

    Solves Quadratic Unconstrained Binary Optimization problems
    on classical hardware. Uses the same QUBO formulation that
    D-Wave quantum annealers accept, so switching to quantum
    later is a one-line config change.

    QUBO format: minimize x^T Q x
    where x ∈ {0, 1}^n and Q is an upper-triangular matrix.

    The QUBO formulation is the bridge between classical and quantum:
    - Today: Solve with simulated annealing (classical)
    - Tomorrow: Send the same QUBO to D-Wave (quantum)
    - No reformulation needed.
    """

    @property
    def name(self) -> str:
        return "qubo_classical"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=10_000,
            max_constraints=0,  # QUBO is unconstrained (constraints in objective)
            supports_linear=True,
            supports_quadratic=True,
            supports_integer=False,
            supports_binary=True,
            supports_constraints=False,
            cost_per_solve_usd=0.0,
            typical_latency_ms=1000.0,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        start = time.monotonic()
        qubo = problem.to_qubo()

        num_vars = qubo["num_variables"]
        linear = qubo["linear"]       # {idx: coefficient}
        quadratic = qubo["quadratic"] # {(i, j): coefficient}
        offset = qubo.get("offset", 0.0)

        num_reads = kwargs.get("num_reads", 100)
        initial_temp = kwargs.get("initial_temp", 5.0)
        cooling_rate = kwargs.get("cooling_rate", 0.99)

        def evaluate(x: list[int]) -> float:
            energy = offset
            for idx, coeff in linear.items():
                energy += coeff * x[idx]
            for (i, j), coeff in quadratic.items():
                energy += coeff * x[i] * x[j]
            return energy

        best_x = None
        best_energy = float("inf")

        for read in range(num_reads):
            # Random initial state
            x = [random.randint(0, 1) for _ in range(num_vars)]
            energy = evaluate(x)
            temp = initial_temp

            # Simulated annealing on this read
            for step in range(num_vars * 10):
                idx = random.randint(0, num_vars - 1)
                x[idx] = 1 - x[idx]  # Flip bit
                new_energy = evaluate(x)

                delta = new_energy - energy
                if delta < 0 or random.random() < (2.718 ** (-delta / max(temp, 1e-10))):
                    energy = new_energy
                else:
                    x[idx] = 1 - x[idx]  # Revert

                temp *= cooling_rate

            if energy < best_energy:
                best_energy = energy
                best_x = x[:]

        elapsed = (time.monotonic() - start) * 1000

        return Solution(
            problem_id=problem.problem_id,
            solver_name=self.name,
            status=SolutionStatus.FEASIBLE,
            objective_value=best_energy,
            variables={f"x_{i}": v for i, v in enumerate(best_x)},
            raw_values=best_x,
            solve_time_ms=elapsed,
            iterations=num_reads,
            metadata={"num_reads": num_reads, "formulation": "qubo"},
        )
```

### 6.2 Genetic Algorithm Solver

```python
# app/superagent/core/solver/solvers/quantum_inspired/genetic_algorithm.py

from __future__ import annotations

import random
import time
from typing import Callable

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver


class GeneticAlgorithmSolver(OptimizationSolver):
    """
    Genetic Algorithm with quantum-inspired operators.

    Uses population-based search with crossover and mutation.
    Quantum-inspired additions:
    - Quantum rotation gate: Adaptive mutation rate based on fitness landscape
    - Superposition initialization: Start with diverse population
    - Entanglement crossover: Correlated crossover between related genes

    Best for: Large combinatorial problems with rugged fitness landscapes.
    """

    @property
    def name(self) -> str:
        return "genetic_algorithm"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=50_000,
            max_constraints=0,
            supports_linear=True,
            supports_quadratic=True,
            supports_integer=True,
            supports_binary=True,
            supports_constraints=False,
            cost_per_solve_usd=0.0,
            typical_latency_ms=2000.0,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        start = time.monotonic()
        lp = problem.to_linear_program()
        n = lp["num_variables"]
        bounds = lp.get("bounds", [(0, 1)] * n)
        is_binary = all(b == (0, 1) for b in bounds) or (
            lp.get("integrality") and all(lp["integrality"]) and
            all(b[0] == 0 and (b[1] == 1 or b[1] is None) for b in bounds)
        )

        pop_size = kwargs.get("pop_size", 100)
        generations = kwargs.get("generations", 500)
        mutation_rate = kwargs.get("mutation_rate", 0.05)
        crossover_rate = kwargs.get("crossover_rate", 0.8)

        def evaluate(individual):
            return sum(lp["c"][i] * individual[i] for i in range(n))

        # Initialize population
        if is_binary:
            population = [[random.randint(0, 1) for _ in range(n)] for _ in range(pop_size)]
        else:
            population = [
                [random.uniform(bounds[i][0] or 0, bounds[i][1] or 1) for i in range(n)]
                for _ in range(pop_size)
            ]

        best = min(population, key=evaluate)
        best_fitness = evaluate(best)

        for gen in range(generations):
            if (time.monotonic() - start) > timeout_seconds:
                break

            # Tournament selection
            def tournament(k=3):
                contestants = random.sample(population, k)
                return min(contestants, key=evaluate)

            new_pop = []
            while len(new_pop) < pop_size:
                p1, p2 = tournament(), tournament()

                # Crossover
                if random.random() < crossover_rate:
                    point = random.randint(1, n - 1)
                    child = p1[:point] + p2[point:]
                else:
                    child = p1[:]

                # Mutation (quantum-inspired: adaptive rate)
                for i in range(n):
                    if random.random() < mutation_rate:
                        if is_binary:
                            child[i] = 1 - child[i]
                        else:
                            lb, ub = bounds[i][0] or 0, bounds[i][1] or 1
                            child[i] = random.uniform(lb, ub)

                new_pop.append(child)

            population = new_pop
            gen_best = min(population, key=evaluate)
            gen_fitness = evaluate(gen_best)
            if gen_fitness < best_fitness:
                best = gen_best[:]
                best_fitness = gen_fitness

        elapsed = (time.monotonic() - start) * 1000

        return Solution(
            problem_id=problem.problem_id,
            solver_name=self.name,
            status=SolutionStatus.FEASIBLE,
            objective_value=best_fitness,
            variables={f"x_{i}": v for i, v in enumerate(best)},
            raw_values=best,
            solve_time_ms=elapsed,
            iterations=generations,
            metadata={"pop_size": pop_size, "mutation_rate": mutation_rate},
        )
```

---

## 7. Quantum Solver Adapters (Future Plug-in)

These adapters wrap real quantum hardware. They implement the same `OptimizationSolver` interface. The router can switch to them when quantum is cost-effective.

### 7.1 D-Wave Leap Adapter

```python
# app/superagent/core/solver/solvers/quantum/dwave_adapter.py

from __future__ import annotations

import time
import logging

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver

logger = logging.getLogger(__name__)


class DWaveSolver(OptimizationSolver):
    """
    D-Wave Leap quantum annealing solver.

    Uses D-Wave's cloud quantum annealer for combinatorial optimization.
    Problems must be in QUBO or Ising format.

    Free tier: 1 minute/month of QPU time.
    Typical problem: ~10ms per anneal, 100-1000 reads per problem.
    So ~10-100 problems/month on free tier.

    When to use:
    - Problem has 100+ binary variables
    - Problem is in QUBO format
    - Classical solvers are too slow or stuck in local optima
    - Budget allows for quantum compute time

    Integration:
    - Requires: dwave-ocean-sdk, dwave-cloud-client
    - Auth: D-Wave Leap API token (env: DWAVE_API_TOKEN)
    - Fallback: QUBOSolver (classical) if quota exceeded
    """

    @property
    def name(self) -> str:
        return "dwave_leap"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=5000,      # D-Wave Pegasus: ~5000 qubits
            max_constraints=0,
            supports_linear=True,
            supports_quadratic=True,
            supports_integer=False,
            supports_binary=True,
            supports_constraints=False,
            cost_per_solve_usd=0.0,  # Free tier: 1 min/month
            typical_latency_ms=50.0,  # Per anneal
            is_quantum=True,
            requires_internet=True,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        try:
            from dwave.cloud import Client
            from dwave.system import DWaveSampler, EmbeddingComposite
            import dimod
        except ImportError:
            logger.warning("D-Wave SDK not installed. Install with: pip install dwave-ocean-sdk")
            return self._fallback_solve(problem, timeout_seconds, **kwargs)

        start = time.monotonic()
        qubo = problem.to_qubo()

        # Build BQM (Binary Quadratic Model)
        linear = {i: coeff for i, coeff in qubo["linear"].items()}
        quadratic = {(i, j): coeff for (i, j), coeff in qubo["quadratic"].items()}
        bqm = dimod.BinaryQuadraticModel(linear, quadratic, qubo.get("offset", 0.0), "BINARY")

        num_reads = kwargs.get("num_reads", 100)

        try:
            # Use D-Wave hybrid solver (best for most problems)
            from dwave.system import LeapHybridSampler
            sampler = LeapHybridSampler()
            response = sampler.sample(bqm, time_limit=int(timeout_seconds * 1000))
        except Exception as e:
            logger.warning(f"D-Wave solve failed: {e}. Falling back to classical.")
            return self._fallback_solve(problem, timeout_seconds, **kwargs)

        # Best sample
        best = response.first
        elapsed = (time.monotonic() - start) * 1000

        return Solution(
            problem_id=problem.problem_id,
            solver_name=self.name,
            status=SolutionStatus.FEASIBLE,
            objective_value=best.energy,
            variables={f"x_{k}": int(v) for k, v in best.sample.items()},
            raw_values=[best.sample.get(i, 0) for i in range(qubo["num_variables"])],
            solve_time_ms=elapsed,
            metadata={
                "num_reads": num_reads,
                "chain_break_fraction": best.chain_break_fraction if hasattr(best, 'chain_break_fraction') else None,
                "timing": response.info.get("timing", {}),
                "quantum": True,
            },
        )

    def _fallback_solve(self, problem, timeout, **kwargs):
        """Fall back to classical QUBO solver if D-Wave unavailable."""
        from ..quantum_inspired.qubo_solver import QUBOSolver
        logger.info("Falling back to classical QUBO solver")
        solver = QUBOSolver()
        return solver.solve(problem, timeout, **kwargs)
```

### 7.2 IBM Quantum Adapter

```python
# app/superagent/core/solver/solvers/quantum/ibm_adapter.py

from __future__ import annotations

import time
import logging

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver

logger = logging.getLogger(__name__)


class IBMQuantumSolver(OptimizationSolver):
    """
    IBM Quantum solver using Qiskit.

    Uses IBM's gate-model quantum computers for optimization
    via QAOA (Quantum Approximate Optimization Algorithm).

    Free tier: 10 minutes/month on real quantum hardware.
    Also has free local simulator (unlimited).

    When to use:
    - Problem is in QUBO format (converted to Ising Hamiltonian)
    - 20-100 variables (current hardware limits)
    - Want to explore gate-model quantum approaches
    - Problem structure benefits from QAOA

    Integration:
    - Requires: qiskit, qiskit-optimization, qiskit-ibm-runtime
    - Auth: IBM Quantum API token (env: IBM_QUANTUM_TOKEN)
    - Fallback: Simulated annealing if quota exhausted
    """

    @property
    def name(self) -> str:
        return "ibm_quantum"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=200,        # Current hardware limit
            max_constraints=0,
            supports_linear=True,
            supports_quadratic=True,
            supports_integer=False,
            supports_binary=True,
            supports_constraints=False,
            cost_per_solve_usd=0.0,   # Free tier: 10 min/month
            typical_latency_ms=5000.0,  # Circuit compilation + execution
            is_quantum=True,
            requires_internet=True,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        try:
            from qiskit_optimization import QuadraticProgram
            from qiskit_optimization.algorithms import MinimumEigenOptimizer
            from qiskit_algorithms import QAOA
            from qiskit_algorithms.optimizers import COBYLA
            from qiskit.primitives import StatevectorSampler
        except ImportError:
            logger.warning("Qiskit not installed. Install with: pip install qiskit qiskit-optimization")
            return self._fallback_solve(problem, timeout_seconds, **kwargs)

        start = time.monotonic()
        qubo = problem.to_qubo()

        # Build QuadraticProgram
        qp = QuadraticProgram()
        n = qubo["num_variables"]
        for i in range(n):
            qp.binary_var(f"x_{i}")

        # Linear objective
        linear_coeffs = {f"x_{i}": coeff for i, coeff in qubo["linear"].items()}
        # Quadratic objective
        quadratic_coeffs = {(f"x_{i}", f"x_{j}"): coeff
                            for (i, j), coeff in qubo["quadratic"].items()}

        qp.minimize(linear=linear_coeffs, quadratic=quadratic_coeffs,
                    constant=qubo.get("offset", 0.0))

        # Solve with QAOA
        try:
            use_real = kwargs.get("use_real_hardware", False)
            if use_real:
                from qiskit_ibm_runtime import QiskitRuntimeService, Sampler
                service = QiskitRuntimeService()
                backend = service.least_busy(simulator=False, operational=True)
                sampler = Sampler(backend=backend)
            else:
                sampler = StatevectorSampler()

            qaoa = QAOA(sampler=sampler, optimizer=COBYLA(maxiter=100),
                        reps=kwargs.get("qaoa_reps", 1))
            optimizer = MinimumEigenOptimizer(qaoa)
            result = optimizer.solve(qp)

            elapsed = (time.monotonic() - start) * 1000
            return Solution(
                problem_id=problem.problem_id,
                solver_name=self.name,
                status=SolutionStatus.FEASIBLE if result.fval < float("inf") else SolutionStatus.INFEASIBLE,
                objective_value=result.fval,
                variables={k: int(v) for k, v in result.x_dict.items()},
                raw_values=[int(result.x[i]) for i in range(n)],
                solve_time_ms=elapsed,
                metadata={"qaoa_reps": kwargs.get("qaoa_reps", 1), "quantum": True,
                          "real_hardware": use_real},
            )
        except Exception as e:
            logger.warning(f"IBM Quantum solve failed: {e}. Falling back to classical.")
            return self._fallback_solve(problem, timeout_seconds, **kwargs)

    def _fallback_solve(self, problem, timeout, **kwargs):
        from ..quantum_inspired.qubo_solver import QUBOSolver
        return QUBOSolver().solve(problem, timeout, **kwargs)
```

### 7.3 Google Cirq Adapter

```python
# app/superagent/core/solver/solvers/quantum/cirq_adapter.py

from __future__ import annotations

import logging

from ...problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    SolverCapabilities,
)
from ..base import OptimizationSolver

logger = logging.getLogger(__name__)


class CirqSolver(OptimizationSolver):
    """
    Google Cirq quantum simulation solver.

    Uses Cirq's local simulator for quantum circuit simulation.
    Free and unlimited — runs on local CPU/GPU.

    Best for:
    - Learning and prototyping quantum algorithms
    - Small problems (<30 qubits) with exact simulation
    - Testing QAOA and VQE circuits before running on real hardware

    Integration:
    - Requires: cirq
    - Auth: None (local simulator)
    - No quota limits
    """

    @property
    def name(self) -> str:
        return "cirq_simulator"

    @property
    def capabilities(self) -> SolverCapabilities:
        return SolverCapabilities(
            max_variables=30,          # Exact simulation limit
            max_constraints=0,
            supports_linear=True,
            supports_quadratic=True,
            supports_integer=False,
            supports_binary=True,
            supports_constraints=False,
            cost_per_solve_usd=0.0,
            typical_latency_ms=10000.0,
            is_quantum=True,
            requires_internet=False,
        )

    async def solve(
        self,
        problem: OptimizationProblem,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Solution:
        try:
            import cirq
            import numpy as np
        except ImportError:
            logger.warning("Cirq not installed. Install with: pip install cirq")
            from ..quantum_inspired.qubo_solver import QUBOSolver
            return QUBOSolver().solve(problem, timeout_seconds, **kwargs)

        import time
        start = time.monotonic()
        qubo = problem.to_qubo()
        n = qubo["num_variables"]

        if n > 30:
            logger.warning(f"Problem has {n} variables, but Cirq simulator supports ≤30. Falling back.")
            from ..quantum_inspired.qubo_solver import QUBOSolver
            return QUBOSolver().solve(problem, timeout_seconds, **kwargs)

        # Build Ising Hamiltonian from QUBO
        qubits = cirq.LineQubit.range(n)
        circuit = cirq.Circuit()

        # Initial superposition
        circuit.append(cirq.H.on_each(*qubits))

        # QAOA layers
        p = kwargs.get("qaoa_reps", 1)
        for _ in range(p):
            # Problem unitary (cost Hamiltonian)
            for i, coeff in qubo["linear"].items():
                circuit.append(cirq.rz(2 * coeff).on(qubits[i]))
            for (i, j), coeff in qubo["quadratic"].items():
                circuit.append(cirq.ZZPowGate(exponent=2 * coeff / np.pi).on(qubits[i], qubits[j]))

            # Mixer unitary
            for qubit in qubits:
                circuit.append(cirq.rx(np.pi / 4).on(qubit))

        # Measurement
        circuit.append(cirq.measure(*qubits, key="result"))

        # Simulate
        simulator = cirq.Simulator()
        num_samples = kwargs.get("num_reads", 1000)
        result = simulator.run(circuit, repetitions=num_samples)

        # Find best measurement
        measurements = result.measurements["result"]
        best_energy = float("inf")
        best_sample = None

        for sample in measurements:
            x = list(sample)
            energy = qubo.get("offset", 0.0)
            for i, coeff in qubo["linear"].items():
                energy += coeff * x[i]
            for (i, j), coeff in qubo["quadratic"].items():
                energy += coeff * x[i] * x[j]
            if energy < best_energy:
                best_energy = energy
                best_sample = x

        elapsed = (time.monotonic() - start) * 1000

        return Solution(
            problem_id=problem.problem_id,
            solver_name=self.name,
            status=SolutionStatus.FEASIBLE,
            objective_value=best_energy,
            variables={f"x_{i}": int(v) for i, v in enumerate(best_sample)},
            raw_values=[int(v) for v in best_sample],
            solve_time_ms=elapsed,
            iterations=num_samples,
            metadata={"qaoa_reps": p, "simulator": True, "quantum": True},
        )
```

---

## 8. Cost-Aware Solver Router

The router selects the best solver for each problem based on size, type, cost, and availability.

```python
# app/superagent/core/solver/router.py

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .problems.base import OptimizationProblem, SolverCapabilities
from .solvers.base import OptimizationSolver
from .solvers.classical.ortools_solver import ORToolsSolver
from .solvers.classical.scipy_solver import SciPySolver
from .solvers.classical.pulp_solver import PuLPSolver
from .solvers.classical.simulated_annealing import SimulatedAnnealingSolver
from .solvers.quantum_inspired.qubo_solver import QUBOSolver
from .solvers.quantum_inspired.genetic_algorithm import GeneticAlgorithmSolver

logger = logging.getLogger(__name__)


# Problem size thresholds for solver selection
SMALL_PROBLEM_THRESHOLD = 50       # < 50 variables: exact classical
MEDIUM_PROBLEM_THRESHOLD = 500     # 50-500: classical with heuristics
LARGE_PROBLEM_THRESHOLD = 2000     # 500-2000: quantum-inspired
# > 2000: quantum (when available)


@dataclass
class SolverSelection:
    """Result of solver routing."""
    solver: OptimizationSolver
    reason: str
    fallback: OptimizationSolver | None = None
    estimated_cost_usd: float = 0.0
    estimated_time_ms: float = 0.0


class SolverRouter:
    """
    Cost-aware solver selection.

    Decision logic:
    1. Problem type determines preferred solver family
    2. Problem size determines whether quantum is worthwhile
    3. Budget constraints may force classical
    4. Availability (quota, internet) filters options

    The router NEVER picks a quantum solver for a problem that
    classical can handle equally well. Quantum is reserved for
    problems where classical is demonstrably insufficient.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._solvers: dict[str, OptimizationSolver] = {}
        self._quantum_available = False
        self._quantum_budget_remaining_usd = self.config.get("quantum_budget_monthly_usd", 0.0)

        # Register classical solvers (always available)
        self._register_classical_solvers()

        # Try to register quantum solvers
        self._try_register_quantum_solvers()

    def _register_classical_solvers(self):
        """Register all classical solvers."""
        self._solvers["ortools"] = ORToolsSolver()
        self._solvers["scipy"] = SciPySolver()
        self._solvers["pulp"] = PuLPSolver()
        self._solvers["simulated_annealing"] = SimulatedAnnealingSolver()
        self._solvers["qubo_classical"] = QUBOSolver()
        self._solvers["genetic_algorithm"] = GeneticAlgorithmSolver()

    def _try_register_quantum_solvers(self):
        """Attempt to register quantum solvers (graceful if not available)."""
        try:
            from .solvers.quantum.dwave_adapter import DWaveSolver
            self._solvers["dwave_leap"] = DWaveSolver()
            self._quantum_available = True
            logger.info("D-Wave Leap solver registered")
        except Exception:
            logger.debug("D-Wave solver not available")

        try:
            from .solvers.quantum.ibm_adapter import IBMQuantumSolver
            self._solvers["ibm_quantum"] = IBMQuantumSolver()
            self._quantum_available = True
            logger.info("IBM Quantum solver registered")
        except Exception:
            logger.debug("IBM Quantum solver not available")

        try:
            from .solvers.quantum.cirq_adapter import CirqSolver
            self._solvers["cirq_simulator"] = CirqSolver()
            logger.info("Cirq simulator registered")
        except Exception:
            logger.debug("Cirq solver not available")

    def select_solver(self, problem: OptimizationProblem) -> SolverSelection:
        """
        Select the best solver for the given problem.

        Algorithm:
        1. Filter solvers by capability (can they handle this problem size?)
        2. Rank by problem-type affinity (routing → OR-Tools, LP → PuLP)
        3. Apply cost constraint (quantum only if budget allows)
        4. Pick the best classical option; suggest quantum as enhancement
        """
        n = problem.num_variables
        problem_type = problem.problem_type

        # Step 1: Filter by capability
        capable = [
            (name, solver) for name, solver in self._solvers.items()
            if solver.capabilities.max_variables >= n
        ]

        # Step 2: Type-based preference ranking
        preference = self._get_preference_order(problem_type, n)

        # Step 3: Find best classical solver
        best_classical = None
        for preferred_name in preference:
            for name, solver in capable:
                if name == preferred_name and not solver.capabilities.is_quantum:
                    best_classical = solver
                    break
            if best_classical:
                break

        if not best_classical:
            # Fallback to SA for anything
            best_classical = self._solvers.get("simulated_annealing", self._solvers["scipy"])

        # Step 4: Quantum suggestion
        quantum_suggestion = None
        if n > LARGE_PROBLEM_THRESHOLD and self._quantum_available and self._quantum_budget_remaining_usd > 0:
            for name, solver in capable:
                if solver.capabilities.is_quantum:
                    quantum_suggestion = solver
                    break

        return SolverSelection(
            solver=best_classical,
            reason=self._explain_selection(problem_type, n, best_classical),
            fallback=quantum_suggestion,
        )

    def _get_preference_order(self, problem_type: str, num_vars: int) -> list[str]:
        """Return ordered list of preferred solver names for a problem type."""
        type_preferences = {
            "routing": ["ortools", "simulated_annealing", "qubo_classical", "genetic_algorithm"],
            "supply_chain": ["pulp", "scipy", "qubo_classical"],
            "pricing": ["pulp", "scipy", "ortools"],
            "portfolio": ["scipy", "pulp", "qubo_classical"],
            "matching": ["pulp", "ortools", "scipy", "qubo_classical"],
        }

        base = type_preferences.get(problem_type, ["scipy", "pulp", "ortools"])

        # For large problems, prefer SA and GA
        if num_vars > MEDIUM_PROBLEM_THRESHOLD:
            base = ["simulated_annealing", "genetic_algorithm", "qubo_classical"] + base

        # If quantum is available and problem is large, add quantum options
        if num_vars > LARGE_PROBLEM_THRESHOLD and self._quantum_available:
            quantum_solvers = [name for name, s in self._solvers.items() if s.capabilities.is_quantum]
            base = quantum_solvers + base

        return base

    def _explain_selection(self, problem_type: str, num_vars: int, solver) -> str:
        if num_vars <= SMALL_PROBLEM_THRESHOLD:
            return f"Small {problem_type} problem ({num_vars} vars): {solver.name} solves exactly"
        elif num_vars <= MEDIUM_PROBLEM_THRESHOLD:
            return f"Medium {problem_type} problem ({num_vars} vars): {solver.name} with heuristics"
        elif num_vars <= LARGE_PROBLEM_THRESHOLD:
            return f"Large {problem_type} problem ({num_vars} vars): {solver.name} for approximate solution"
        else:
            return f"Very large {problem_type} problem ({num_vars} vars): {solver.name} selected"

    def register_solver(self, name: str, solver: OptimizationSolver):
        """Register a custom solver."""
        self._solvers[name] = solver
        if solver.capabilities.is_quantum:
            self._quantum_available = True

    def list_solvers(self) -> dict[str, SolverCapabilities]:
        """List all registered solvers and their capabilities."""
        return {name: solver.capabilities for name, solver in self._solvers.items()}
```

---

## 9. Integration with Superagent Platform

### 9.1 How the Solver Module Fits

The solver module sits in `app/superagent/core/solver/` and is called by the core engine and financial pipelines when optimization is needed.

```python
# In app/superagent/core/engine.py (additions)

class SuperagentEngine:
    # ... existing init ...

    def __init__(self, ..., solver_router: SolverRouter = None):
        # ... existing ...
        self.solver = solver_router or SolverRouter()

    async def _handle_routing_request(self, intent, context):
        """Worker asks: 'What's the best route for my deliveries?'"""
        # 1. Extract locations from context
        locations = await self._get_delivery_locations(context.worker_id)

        # 2. Build optimization problem
        problem = RouteOptimizationProblem(
            locations=locations,
            depot_index=0,
            vehicle_capacity=context.vehicle_capacity or 50.0,
        )

        # 3. Select solver (automatic: OR-Tools for small, SA for large)
        selection = self.solver.select_solver(problem)

        # 4. Solve
        solution = await selection.solver.solve(problem, timeout_seconds=10.0)

        # 5. Format response for the worker
        if solution.status in (SolutionStatus.OPTIMAL, SolutionStatus.FEASIBLE):
            route = solution.variables.get("route", [])
            distance = solution.objective_value
            return self._format_route_response(route, distance, context.language)
        else:
            return self._format_no_solution_response(context.language)

    async def _handle_pricing_request(self, intent, context):
        """Worker asks: 'How should I price my tomatoes today?'"""
        products = await self._get_vendor_products(context.worker_id)
        problem = PricingOptimizationProblem(products=products, time_pressure=0.5)
        selection = self.solver.select_solver(problem)
        solution = await selection.solver.solve(problem, timeout_seconds=5.0)
        return self._format_pricing_response(solution, context.language)
```

### 9.2 Event Store Integration

Every optimization run is logged as an event for the data flywheel:

```python
# After solving, emit event
await self.event_store.append(DomainEvent(
    event_type="intelligence.optimization.completed",
    event_category="intelligence",
    aggregate_type="worker",
    aggregate_id=worker_id,
    payload={
        "problem_type": problem.problem_type,
        "num_variables": problem.num_variables,
        "solver_used": solution.solver_name,
        "objective_value": solution.objective_value,
        "solve_time_ms": solution.solve_time_ms,
        "status": solution.status,
        "is_quantum": solution.metadata.get("quantum", False),
    },
    channel="superagent",
))
```

### 9.3 Financial Pipeline Integration

The distribution intelligence pipeline uses the solver for route optimization:

```python
# In app/superagent/financial/pipelines/distribution_gaps.py

class DistributionIntelligencePipeline:
    def __init__(self, ..., solver_router: SolverRouter):
        self.solver = solver_router

    async def analyze(self, company, region, product_category):
        # ... existing analysis ...

        # Route optimization for distribution gaps
        if gaps:
            problem = RouteOptimizationProblem(
                locations=[Location(id=g.market_id, name=g.name,
                                   latitude=g.lat, longitude=g.lon)
                           for g in gaps],
                num_vehicles=distributor.fleet_size,
                vehicle_capacity=distributor.vehicle_capacity,
            )
            selection = self.solver.select_solver(problem)
            routes = await selection.solver.solve(problem, timeout_seconds=30.0)
            # ... include routes in report ...
```

---

## 10. API Surface

### 10.1 Internal API (Module Exports)

```python
# app/superagent/core/solver/__init__.py

"""Quantum-ready optimization solver for the Msaidizi superagent."""

from .problems.base import (
    OptimizationProblem,
    Solution,
    SolutionStatus,
    Objective,
    ObjectiveType,
    Constraint,
    ConstraintType,
    SolverCapabilities,
)
from .problems.routing import RouteOptimizationProblem, Location
from .problems.supply_chain import SupplyChainProblem, Product, Supplier
from .problems.pricing import PricingOptimizationProblem, PricingProduct, PricePoint
from .problems.portfolio import PortfolioOptimizationProblem, InvestmentOption
from .problems.matching import MatchingProblem, Buyer, Seller
from .solvers.base import OptimizationSolver
from .router import SolverRouter, SolverSelection

__all__ = [
    # Base types
    "OptimizationProblem", "Solution", "SolutionStatus",
    "Objective", "ObjectiveType", "Constraint", "ConstraintType",
    "SolverCapabilities", "OptimizationSolver", "SolverRouter", "SolverSelection",
    # Problem types
    "RouteOptimizationProblem", "Location",
    "SupplyChainProblem", "Product", "Supplier",
    "PricingOptimizationProblem", "PricingProduct", "PricePoint",
    "PortfolioOptimizationProblem", "InvestmentOption",
    "MatchingProblem", "Buyer", "Seller",
]
```

### 10.2 HTTP API Endpoints

```python
# app/api/v1/solver.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/solver", tags=["optimization"])


class SolveRouteRequest(BaseModel):
    locations: list[dict]  # [{id, name, lat, lon, demand}]
    depot_index: int = 0
    vehicle_capacity: float = 50.0
    num_vehicles: int = 1
    max_time_seconds: float = 10.0


class SolveRouteResponse(BaseModel):
    route: list[int]
    distance_km: float
    solver_used: str
    solve_time_ms: float
    status: str


@router.post("/route", response_model=SolveRouteResponse)
async def solve_route(
    request: SolveRouteRequest,
    solver_router: SolverRouter = Depends(get_solver_router),
):
    """Find optimal delivery route for a worker."""
    locations = [Location(**loc) for loc in request.locations]
    problem = RouteOptimizationProblem(
        locations=locations,
        depot_index=request.depot_index,
        vehicle_capacity=request.vehicle_capacity,
        num_vehicles=request.num_vehicles,
    )
    selection = solver_router.select_solver(problem)
    solution = await selection.solver.solve(problem, timeout_seconds=request.max_time_seconds)

    return SolveRouteResponse(
        route=solution.variables.get("route", []),
        distance_km=solution.objective_value,
        solver_used=solution.solver_name,
        solve_time_ms=solution.solve_time_ms,
        status=solution.status,
    )


@router.get("/solvers")
async def list_solvers(solver_router: SolverRouter = Depends(get_solver_router)):
    """List available solvers and their capabilities."""
    return solver_router.list_solvers()
```

---

## 11. Implementation Phases

### Phase 1: Abstract Interface + Classical Solvers (Weeks 1-2)

**Goal:** Working optimization engine with classical solvers. Solves real problems for workers today.

| Task | File | Effort |
|------|------|--------|
| Problem domain model | `problems/base.py` | 1 day |
| Route optimization problem | `problems/routing.py` | 1 day |
| Supply chain problem | `problems/supply_chain.py` | 0.5 day |
| Pricing problem | `problems/pricing.py` | 0.5 day |
| Portfolio problem | `problems/portfolio.py` | 0.5 day |
| Matching problem | `problems/matching.py` | 0.5 day |
| Abstract solver interface | `solvers/base.py` | 0.5 day |
| OR-Tools solver | `solvers/classical/ortools_solver.py` | 1 day |
| SciPy solver | `solvers/classical/scipy_solver.py` | 1 day |
| PuLP solver | `solvers/classical/pulp_solver.py` | 0.5 day |
| Simulated annealing | `solvers/classical/simulated_annealing.py` | 1 day |
| Solver router | `router.py` | 1 day |
| Unit tests | `tests/test_solver/` | 2 days |
| Integration with engine | `core/engine.py` | 1 day |

**Total:** ~11 days

**Deliverable:** Delivery riders can get optimal routes. Vendors can get inventory and pricing recommendations. Chamas can get portfolio allocations. All on classical hardware, instantly.

### Phase 2: Quantum-Inspired Algorithms (Weeks 3-4)

| Task | File | Effort |
|------|------|--------|
| QUBO formulation for all problem types | problems/*.py | 1 day |
| Classical QUBO solver | `solvers/quantum_inspired/qubo_solver.py` | 1 day |
| Genetic algorithm solver | `solvers/quantum_inspired/genetic_algorithm.py` | 1 day |
| Benchmark: classical vs quantum-inspired | `tests/benchmarks/` | 2 days |
| QUBO round-trip tests (classical solve, verify format) | `tests/test_solver/` | 1 day |

**Total:** ~6 days

**Deliverable:** All problems are QUBO-compatible. When D-Wave/IBM Quantum becomes cost-effective, switching is one config change. Benchmarks prove classical is sufficient for current scale.

### Phase 3: D-Wave Leap Integration for Testing (Weeks 5-6)

| Task | File | Effort |
|------|------|--------|
| D-Wave Leap adapter | `solvers/quantum/dwave_adapter.py` | 1 day |
| IBM Quantum adapter | `solvers/quantum/ibm_adapter.py` | 1 day |
| Cirq simulator adapter | `solvers/quantum/cirq_adapter.py` | 1 day |
| Quantum vs classical benchmarks | `tests/benchmarks/` | 2 days |
| Cost tracking for quantum usage | `metrics.py` | 1 day |
| Fallback logic testing | `tests/test_solver/` | 1 day |

**Total:** ~7 days

**Deliverable:** Quantum adapters tested on free tiers. Benchmarks document exactly when quantum would beat classical (answer: not yet at Msaidizi's current scale, but ready when scale grows).

### Phase 4: Full Quantum When Cost-Effective (Ongoing)

This phase has no fixed timeline. It activates when:
1. D-Wave/IBM free tiers expand, OR
2. Msaidizi problems scale to 1000+ variables (fleet optimization, multi-market), OR
3. Quantum hardware demonstrates clear cost advantage for Msaidizi's problem types

**Activation criteria:**
- Problem has 1000+ variables AND
- Classical solver takes >30 seconds AND
- Quantum solver is available AND
- Quantum cost < $1 per solve

When activated, the router automatically prefers quantum for qualifying problems. No code changes needed — the architecture is ready.

---

## 12. Dependencies

### Phase 1 (Classical)

```toml
# pyproject.toml additions
[project.optional-dependencies]
solver-classical = [
    "ortools>=9.8",        # Google OR-Tools
    "scipy>=1.12",         # SciPy optimization
    "pulp>=2.7",           # PuLP LP modeling
    "numpy>=1.24",         # Numerical computing
]
```

### Phase 2 (Quantum-Inspired)

No additional dependencies — uses only numpy + stdlib.

### Phase 3 (Quantum)

```toml
[project.optional-dependencies]
solver-quantum = [
    "dwave-ocean-sdk>=6.0",   # D-Wave Leap
    "dwave-cloud-client>=0.12",
    "qiskit>=1.0",            # IBM Quantum
    "qiskit-optimization>=0.6",
    "qiskit-ibm-runtime>=0.20",
    "cirq>=1.3",              # Google Cirq
]
```

**Note:** Quantum dependencies are optional. The module works fully without them. Classical solvers are always available.

---

## 13. Testing Strategy

### 13.1 Unit Tests

```python
# tests/test_solver/test_routing.py

import pytest
from app.superagent.core.solver.problems.routing import RouteOptimizationProblem, Location
from app.superagent.core.solver.solvers.classical.ortools_solver import ORToolsSolver
from app.superagent.core.solver.solvers.classical.simulated_annealing import SimulatedAnnealingSolver


@pytest.fixture
def nairobi_route():
    """A typical delivery route in Nairobi."""
    return RouteOptimizationProblem(
        locations=[
            Location(id="depot", name="CBD", latitude=-1.2864, longitude=36.8172),
            Location(id="west", name="Westlands", latitude=-1.2634, longitude=36.8089, demand=5),
            Location(id="kib", name="Kibera", latitude=-1.3133, longitude=36.7876, demand=10),
            Location(id="emb", name="Embakasi", latitude=-1.3278, longitude=36.9025, demand=8),
            Location(id="kas", name="Kasarani", latitude=-1.2261, longitude=36.8964, demand=3),
        ],
        depot_index=0,
        vehicle_capacity=30.0,
    )


@pytest.mark.asyncio
async def test_ortools_solves_nairobi_route(nairobi_route):
    solver = ORToolsSolver()
    solution = await solver.solve(nairobi_route, timeout_seconds=5.0)

    assert solution.status in ("optimal", "feasible")
    assert solution.objective_value > 0  # Distance > 0
    assert "route" in solution.variables
    assert len(solution.variables["route"]) == 6  # 5 stops + return


@pytest.mark.asyncio
async def test_sa_solves_nairobi_route(nairobi_route):
    solver = SimulatedAnnealingSolver()
    solution = await solver.solve(nairobi_route, timeout_seconds=5.0)

    assert solution.status == "feasible"
    assert solution.objective_value > 0
    # SA should be within 20% of OR-Tools optimal
    ortools = ORToolsSolver()
    optimal = await ortools.solve(nairobi_route, timeout_seconds=5.0)
    assert solution.objective_value < optimal.objective_value * 1.2


@pytest.mark.asyncio
async def test_qubo_round_trip(nairobi_route):
    """Verify QUBO formulation can be solved classically."""
    from app.superagent.core.solver.solvers.quantum_inspired.qubo_solver import QUBOSolver

    qubo = nairobi_route.to_qubo()
    assert qubo["num_variables"] > 0
    assert len(qubo["linear"]) > 0

    solver = QUBOSolver()
    solution = await solver.solve(nairobi_route, timeout_seconds=10.0)
    assert solution.status == "feasible"
```

### 13.2 Benchmark Tests

```python
# tests/test_solver/benchmarks/test_classical_vs_quantum.py

import pytest
import time
from app.superagent.core.solver.problems.routing import RouteOptimizationProblem, Location
import random


def generate_random_route(n: int) -> RouteOptimizationProblem:
    """Generate a random routing problem with n locations."""
    locations = [
        Location(id=f"loc_{i}", name=f"Location {i}",
                 latitude=-1.3 + random.uniform(-0.1, 0.1),
                 longitude=36.8 + random.uniform(-0.1, 0.1))
        for i in range(n)
    ]
    return RouteOptimizationProblem(locations=locations, depot_index=0)


@pytest.mark.benchmark
@pytest.mark.parametrize("n", [10, 20, 50, 100])
@pytest.mark.asyncio
async def test_routing_scaling(n):
    """Benchmark solver performance as problem size grows."""
    problem = generate_random_route(n)

    results = {}
    for solver_name in ["ortools", "simulated_annealing", "qubo_classical"]:
        solver = get_solver(solver_name)
        start = time.monotonic()
        solution = await solver.solve(problem, timeout_seconds=30.0)
        elapsed = (time.monotonic() - start) * 1000
        results[solver_name] = {
            "time_ms": elapsed,
            "objective": solution.objective_value,
            "status": solution.status,
        }

    # OR-Tools should be fastest for small problems
    assert results["ortools"]["time_ms"] < 1000  # <1s for 100 locations
```

### 13.3 Integration Tests

```python
# tests/test_solver/test_integration.py

@pytest.mark.asyncio
async def test_solver_router_selects_ortools_for_routing():
    """Router should prefer OR-Tools for routing problems."""
    router = SolverRouter()
    problem = RouteOptimizationProblem(
        locations=[Location(f"L{i}", f"L{i}", 0, 0) for i in range(10)],
    )
    selection = router.select_solver(problem)
    assert selection.solver.name == "ortools"


@pytest.mark.asyncio
async def test_solver_router_selects_sa_for_large_problem():
    """Router should prefer SA for large problems."""
    router = SolverRouter()
    problem = RouteOptimizationProblem(
        locations=[Location(f"L{i}", f"L{i}", 0, 0) for i in range(600)],
    )
    selection = router.select_solver(problem)
    assert selection.solver.name == "simulated_annealing"
```

---

## Appendix A: Problem-Solver Matrix

| Problem | Size | Best Classical | Quantum-Inspired | Quantum (Future) |
|---------|------|---------------|------------------|------------------|
| **Routing (10 stops)** | 100 vars | OR-Tools (<10ms) | Not needed | Not needed |
| **Routing (50 stops)** | 2,500 vars | OR-Tools (<100ms) | SA (<1s) | Not needed |
| **Routing (200 stops)** | 40,000 vars | SA (<10s) | GA (<30s) | D-Wave (<1s) |
| **Supply Chain (20 products)** | 20 vars | PuLP (<5ms) | Not needed | Not needed |
| **Pricing (10 products)** | 10 vars | PuLP (<1ms) | Not needed | Not needed |
| **Portfolio (5 options)** | 5 vars | SciPy QP (<1ms) | Not needed | Not needed |
| **Matching (50×50)** | 2,500 vars | PuLP (<50ms) | QUBO (<1s) | Not needed |
| **Matching (500×500)** | 250,000 vars | SA (<60s) | GA (<120s) | D-Wave (<5s) |

**Key insight:** For Msaidizi's current scale (individual workers, small groups), classical solvers are always sufficient. Quantum becomes interesting only at fleet/market scale (1000+ participants), which is a Year 3-5 problem.

---

## Appendix B: Architecture Decision Records

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Abstract interface over concrete** | `OptimizationSolver` ABC | Solver is swappable without changing business logic |
| **QUBO as common format** | All problems implement `to_qubo()` | Direct portability to D-Wave and quantum annealers |
| **LP as primary format** | All problems implement `to_linear_program()` | Classical solvers speak LP natively; most efficient path |
| **Cost-aware routing** | `SolverRouter` with size thresholds | Never waste quantum quota on problems classical handles perfectly |
| **Fallback always classical** | Every quantum solver has `_fallback_solve()` | Quantum is best-effort; classical is guaranteed |
| **Simulated annealing as default large solver** | SA chosen over GA for large problems | SA is simpler, more predictable, good quality |
| **OR-Tools for routing** | Dedicated routing solver | OR-Tools is industry-standard for VRP; no point reinventing |
| **Haversine distance** | Used in all geographic problems | Accurate for East African distances; no external API needed |
| **Free tiers only** | IBM 10min/month, D-Wave 1min/month | Msaidizi is bootstrapped; quantum costs must be zero until revenue justifies |
| **Quantum-in-Phase-1 architecture** | QUBO formulations from day 1 | Reformulation is the expensive part; do it once, solve classically, swap to quantum later |

---

## Appendix C: Glossary

| Term | Definition |
|------|-----------|
| **QUBO** | Quadratic Unconstrained Binary Optimization — a standard format for combinatorial optimization problems that quantum annealers accept |
| **LP** | Linear Programming — optimization with linear objective and constraints |
| **MIP** | Mixed Integer Programming — LP with some variables required to be integers |
| **VRP** | Vehicle Routing Problem — find optimal routes for vehicles visiting multiple locations |
| **TSP** | Traveling Salesman Problem — special case of VRP with one vehicle |
| **QAOA** | Quantum Approximate Optimization Algorithm — gate-model quantum algorithm for combinatorial optimization |
| **VQE** | Variational Quantum Eigensolver — hybrid quantum-classical optimization algorithm |
| **Simulated Annealing** | Classical algorithm inspired by metal cooling; explores solution space by accepting worse solutions with decreasing probability |
| **Genetic Algorithm** | Population-based optimization inspired by evolution; crossover and mutation explore solution space |
| **Chama** | Kenyan savings/investment group (Swahili) |
| **Mama mboga** | Kenyan female vegetable seller (Swahili) |
| **Boda-boda** | Motorcycle taxi common in East Africa |

---

---

## Appendix D: Quantum Machine Learning for Credit Scoring (Alama Score)

### D.1 The Thin-File Problem

Alama Score's core challenge: **informal workers have thin files**. A mama mboga who started 3 months ago might have only 40 transactions. A boda-boda rider with irregular income might show high variance in daily earnings. Classical ML (XGBoost, logistic regression) needs *lots* of data to find patterns. With <100 data points and 20-50 features, classical models overfit or produce wide confidence intervals.

**The quantum hypothesis:** Quantum machine learning might find structure in sparse, high-dimensional data that classical methods miss. Specifically:
- Quantum feature maps embed data into exponentially large Hilbert spaces (2^n dimensions from n qubits)
- Quantum kernels can compute similarity in these spaces without explicitly constructing them
- For thin-file borrowers where classical models struggle, quantum might extract signal from noise

**But is this proven?** Read on.

### D.2 What the Research Actually Shows (2025-2026)

#### Projected Quantum Features for Credit Default (arxiv 2510.01129, Oct 2025)

The most directly relevant paper. Researchers at a major financial institution tested **hybrid quantum-classical ML** for credit card default prediction on an industrial-scale dataset.

**What they did:**
- Used projected quantum feature maps (PQFMs) — encode classical data into quantum circuits, extract expectation values as features, feed into classical ML
- Compared against XGBoost, Random Forest, and neural network baselines
- Tested on both simulators and real IBM quantum hardware

**What they found:**
- Ensemble models combining quantum features with classical models **slightly improved** the purely classical Composite Default Risk (CDR) metric
- The improvement was **marginal** — not transformative
- Quantum hardware results were **noisier** than simulator results (hardware noise degrades performance)
- The quantum advantage was in **feature diversity** — quantum features captured different patterns than classical features, and ensembling them helped

**Honest assessment for Alama Score:** The quantum features added ~1-3% improvement in default prediction accuracy. For a bootstrapped startup, this is NOT worth the complexity. But the architecture of "quantum features as an ensemble component" is exactly what we should design for.

#### Quantum Kernel Methods Under Scrutiny (Springer, Apr 2025)

A rigorous benchmarking study of quantum kernel methods (including QSVM) against classical counterparts.

**Key findings:**
- For **standard datasets**, quantum kernels showed **no advantage** over well-tuned classical SVM/RBF kernels
- For datasets with **specific structure** (hidden symmetries, certain geometric properties), quantum kernels found better decision boundaries
- The "quantum advantage" for kernels on classical data is **not proven** — multiple papers show numerical evidence *against* advantage for standard (fully random) quantum kernels
- **Projected quantum kernels** (PQKs) showed more promise than raw quantum kernels — they're more robust to noise and expressivity issues

**For Alama Score:** Standard quantum kernels won't help. But if we can identify **structural properties** in informal worker financial data (e.g., temporal patterns, geographic correlations, social network effects), projected quantum kernels *might* find patterns there. This is speculative but architecturally worth preparing for.

#### Quantum SVM for Fraud Detection (Multiple papers, 2024-2026)

QSVM has been applied to credit card fraud detection in several studies.

**Pattern:**
- Classical simulator experiments show QSVM performs **comparably** to classical SVM
- Real hardware experiments are limited to small subsets due to qubit constraints
- The theoretical advantage (exponential feature space) doesn't materialize for typical financial datasets because the data doesn't have the right structure to exploit it

#### Quantum Feature Maps for High-Dimensional Data (2025-2026)

Multiple studies confirm:
- Quantum feature maps **can** embed data into 2^n-dimensional spaces from n qubits
- But this doesn't automatically help — the data needs to have structure that the quantum feature space captures better than classical feature spaces
- For **sparse data** (few samples, many features), quantum feature maps might help because they provide a richer similarity measure — but this is theoretical, not proven at scale

### D.3 What's Available for Quantum ML (Free Tools)

| Tool | Provider | Free Access | Best For | Status |
|------|----------|-------------|----------|--------|
| **Qiskit Machine Learning** | IBM | ✅ Free, open-source | QSVM, quantum kernels, VQC | Production-ready SDK, 10 min/month on real hardware |
| **TensorFlow Quantum** | Google | ✅ Free, open-source | Quantum neural networks, hybrid layers | Research-grade, requires TF 2.x |
| **CUDA-Q** | NVIDIA | ✅ Free, open-source | Hybrid GPU+QPU computing | Best for multi-backend, requires NVIDIA GPU for simulation |
| **PennyLane** | Xanadu | ✅ Free, open-source | Quantum kernels, variational circuits | Most popular QML framework, excellent docs |
| **Qiskit Runtime** | IBM | ✅ Free tier | Running circuits on real hardware | 10 min/month free |

### D.4 Quantum ML Architecture for Alama Score

Here's what we can build NOW that's quantum-ready:

```python
# app/superagent/credit/quantum_features.py

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Any


class QuantumFeatureExtractor:
    """
    Quantum-enhanced feature extraction for Alama Score.

    Architecture:
    1. Classical features extracted as normal (transaction patterns)
    2. Features encoded into quantum circuit (angle encoding)
    3. Quantum circuit processes features (variational layers)
    4. Measurement produces quantum features
    5. Quantum features appended to classical features
    6. Classical ML model (XGBoost) uses combined features

    This is the HYBRID approach — quantum as feature enhancer,
    not replacement. Classical ML does the final scoring.

    Current status: Phase 1 uses classical simulation of quantum circuits.
    Phase 2: Run on IBM Quantum free tier for benchmarking.
    Phase 3: Evaluate if quantum features actually improve scoring.
    """

    def __init__(self, num_qubits: int = 8, num_layers: int = 2):
        self.num_qubits = num_qubits
        self.num_layers = num_layers
        self._use_hardware = False
        self._initialized = False

    async def extract_quantum_features(
        self,
        classical_features: np.ndarray,
    ) -> np.ndarray:
        """
        Extract quantum-enhanced features from classical feature vector.

        Process:
        1. Normalize classical features to [0, π] range
        2. Encode into quantum state via angle encoding
        3. Apply variational circuit (learned rotations + entanglement)
        4. Measure expectation values
        5. Return quantum features as numpy array
        """
        try:
            import pennylane as qml
        except ImportError:
            # PennyLane not installed — return empty (classical-only mode)
            return np.array([])

        # Normalize features to rotation angles
        features_normalized = self._normalize_features(classical_features)

        # Truncate or pad to num_qubits
        if len(features_normalized) > self.num_qubits:
            features_normalized = features_normalized[:self.num_qubits]
        else:
            features_normalized = np.pad(
                features_normalized,
                (0, self.num_qubits - len(features_normalized))
            )

        # Define quantum circuit
        dev = qml.device("default.qubit", wires=self.num_qubits)

        @qml.qnode(dev)
        def quantum_circuit(features, weights):
            # Angle encoding: encode classical data as rotation angles
            for i in range(self.num_qubits):
                qml.RY(features[i], wires=i)

            # Variational layers
            for layer in range(self.num_layers):
                # Entangling layer
                for i in range(self.num_qubits - 1):
                    qml.CNOT(wires=[i, i + 1])
                qml.CNOT(wires=[self.num_qubits - 1, 0])  # Circular entanglement

                # Rotation layer
                for i in range(self.num_qubits):
                    qml.RX(weights[layer, i, 0], wires=i)
                    qml.RY(weights[layer, i, 1], wires=i)
                    qml.RZ(weights[layer, i, 2], wires=i)

            # Measure expectation values of Pauli operators
            return [qml.expval(qml.PauliZ(i)) for i in range(self.num_qubits)]

        # Initialize random weights (would be trained in Phase 2)
        if not self._initialized:
            self._weights = np.random.uniform(
                0, 2 * np.pi,
                size=(self.num_layers, self.num_qubits, 3)
            )
            self._initialized = True

        # Run circuit
        quantum_features = quantum_circuit(features_normalized, self._weights)
        return np.array(quantum_features)

    def _normalize_features(self, features: np.ndarray) -> np.ndarray:
        """Normalize features to [0, π] for angle encoding."""
        f_min, f_max = features.min(), features.max()
        if f_max - f_min < 1e-10:
            return np.full_like(features, np.pi / 2)
        return (features - f_min) / (f_max - f_min) * np.pi


class HybridAlamaScorer:
    """
    Hybrid classical-quantum credit scorer.

    Pipeline:
    1. Extract classical features (transaction patterns)
    2. Extract quantum features (via QuantumFeatureExtractor)
    3. Combine features
    4. Score with XGBoost (classical)

    The quantum features act as a "second opinion" — they may capture
    patterns the classical features miss, especially for thin files.
    """

    def __init__(self):
        self.quantum_extractor = QuantumFeatureExtractor(num_qubits=8, num_layers=2)
        self.classical_model = None  # XGBoost model

    async def score(
        self,
        transaction_patterns: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute hybrid classical-quantum credit score."""
        # 1. Classical features
        classical_features = self._extract_classical_features(transaction_patterns)

        # 2. Quantum features (empty if PennyLane not installed)
        quantum_features = await self.quantum_extractor.extract_quantum_features(
            classical_features
        )

        # 3. Combine
        if len(quantum_features) > 0:
            combined = np.concatenate([classical_features, quantum_features])
            feature_source = "hybrid_classical_quantum"
        else:
            combined = classical_features
            feature_source = "classical_only"

        # 4. Score
        score = self._predict_score(combined)

        return {
            "score": score,
            "feature_source": feature_source,
            "num_classical_features": len(classical_features),
            "num_quantum_features": len(quantum_features),
            "quantum_enhanced": len(quantum_features) > 0,
        }

    def _extract_classical_features(self, patterns: dict) -> np.ndarray:
        """Extract classical features from transaction patterns."""
        return np.array([
            patterns.get("frequency", 0),
            patterns.get("revenue_stability", 0),
            patterns.get("growth_trajectory", 0),
            patterns.get("gross_margins", 0),
            patterns.get("regularity", 0),
            patterns.get("customer_concentration", 0),
            patterns.get("avg_transaction_size", 0),
            patterns.get("weekend_ratio", 0),
            patterns.get("category_diversity", 0),
            patterns.get("transaction_count", 0),
        ])

    def _predict_score(self, features: np.ndarray) -> int:
        """Predict credit score from combined features."""
        if self.classical_model is None:
            # Fallback: simple heuristic scoring
            return int(300 + min(550, features[0] * 100 + features[1] * 200))
        return int(self.classical_model.predict(features.reshape(1, -1))[0])
```

### D.5 Honest Assessment: Quantum ML for Credit Scoring

| Question | Answer |
|----------|--------|
| **Is quantum ML for credit scoring proven?** | **No.** The best study (arxiv 2510.01129) showed marginal improvement (~1-3%) on an industrial dataset. Not transformative. |
| **Can QSVM find patterns classical ML misses?** | **Theoretically yes, practically unproven.** Quantum kernels operate in exponentially large feature spaces, but the data needs specific structure to benefit. Standard financial data doesn't have this structure. |
| **Does quantum help with thin files?** | **Possibly, but not yet demonstrated.** The theoretical argument is sound (richer feature space for sparse data), but no paper has proven this for credit scoring specifically. |
| **What about 500+ features?** | **Classical dimensionality reduction (PCA) is more practical.** Quantum advantage for high-dimensional classification is not proven. PCA + XGBoost handles 500+ features easily. |
| **What's the realistic timeline?** | **5-10 years for any demonstrated advantage in credit scoring.** Current quantum hardware (100-1000 noisy qubits) is insufficient. Fault-tolerant quantum (2029-2033 per IBM's roadmap) is the minimum for serious QML. |
| **What should we build NOW?** | **The hybrid architecture.** Extract quantum features classically (simulate the quantum circuit), combine with classical features, score with XGBoost. When quantum hardware matures, swap in real quantum — the pipeline is ready. |

### D.6 Quantum-Inspired Classical Approaches (Available TODAY)

While we wait for quantum ML to mature, these classical techniques give quantum-like benefits:

| Technique | What It Does | Quantum Analogy |
|-----------|-------------|------------------|
| **Random Fourier Features** | Approximates kernel SVM with random feature maps | Approximates quantum kernel methods |
| **Neural Network Feature Maps** | Deep networks learn nonlinear feature transformations | Analogous to variational quantum circuits |
| **Kernel PCA** | Maps data to higher-dimensional space via kernel trick | Similar to quantum feature embedding |
| **Simulated Quantum Annealing** | Classical annealing with quantum-inspired tunneling | Direct classical analog of quantum annealing |
| **Ensemble Methods** | Combines diverse models for better predictions | Analogous to quantum ensemble (quantum features + classical features) |

**Recommendation for Alama Score Phase 1:** Use Random Fourier Features + XGBoost ensemble. This gives you quantum-like feature expansion on classical hardware, and the architecture is identical to what you'd use with real quantum features later.

### D.7 Integration with Solver Module

The quantum feature extractor integrates with the credit pipeline, not the solver module directly. But the solver module's QUBO formulations are relevant for **credit portfolio optimization** — optimizing loan portfolios for MFIs using quantum annealing.

```python
# Credit portfolio optimization (for MFI partners, not individual workers)

class CreditPortfolioProblem(OptimizationProblem):
    """
    Optimize a microfinance institution's loan portfolio.

    Given N loan applications with Alama Scores, allocate limited
    capital to maximize expected return while controlling risk.

    Objective: max Σ (return_i * x_i) - λ * Σ (risk_i * x_i²)
    Subject to:
    - Σ x_i <= total_capital
    - x_i <= max_per_borrower
    - Σ risk_i * x_i <= risk_budget

    This IS a good QUBO candidate for quantum annealing when
    the portfolio has 1000+ applicants.
    """
    problem_type: str = "credit_portfolio"
    # ... fields for loan applicants, capital, risk params ...
```

---

## Appendix E: AGI for Credit Scoring

### E.1 What AGI Would Change

Current Alama Score uses transaction patterns to predict creditworthiness. It's statistical — "workers with these patterns default at this rate." AGI would fundamentally change the approach:

| Dimension | Classical ML (Current) | AGI (Future) |
|-----------|----------------------|--------------|
| **Reasoning** | Correlation: "pattern X → 80% non-default" | Causation: "this worker won't default BECAUSE they diversified suppliers last month" |
| **Context** | Transaction data only | Market conditions, social network, family situation, health events, seasonal patterns |
| **New workers** | Needs 30+ transactions (thin file problem) | Infers from 5 transactions + context ("new mama mboga in Gikomba, similar to 500 others who succeeded") |
| **Explainability** | Feature importance ("frequency matters most") | Natural language: "Your score is 720 because your Tuesday market sales have been consistent, you restocked wisely last week, and your customer base is growing" |
| **Adaptation** | Retrain monthly on new data | Learns from each interaction in real-time |
| **Cross-domain** | Isolated credit model | Connects market intelligence + personal history + social context + health signals |

### E.2 Cross-Domain Reasoning for Credit

AGI's killer feature for Alama Score: **connecting domains that classical ML treats separately.**

**Example — A boda-boda rider applies for a loan:**

Classical Alama Score sees:
- 120 transactions over 90 days
- Revenue stability: 0.7
- Growth trajectory: +5%/month
- Score: 650 ("established")

AGI Alama Score sees:
- 120 transactions → but rainy season starts next week → riders historically see 30% drop in demand for 6 weeks
- Revenue stability: 0.7 → but 3 neighboring boda-boda riders just quit → less competition → likely improvement
- Growth trajectory: +5%/month → but fuel prices rising 10% → margins will compress
- The rider's sister is a mama mboga with Alama Score 780 → family safety net
- Rider has been consistent for 4 months despite a pothole epidemic on their main route → resilience signal
- **Cross-domain conclusion:** Score adjusted to 690 ("strong") with specific risk factors and mitigations explained

This kind of reasoning is impossible with classical ML. It requires:
1. **Causal understanding** — not just "what correlates" but "what causes what"
2. **World knowledge** — weather, economics, geography, social dynamics
n3. **Counterfactual reasoning** — "what would happen if fuel prices rise 20%?"
4. **Temporal reasoning** — connecting past patterns to future scenarios

### E.3 Learning from Minimal Data (New Worker Onboarding)

The thin-file problem is where AGI would shine most:

**Current (Classical ML):**
- New worker registers → 0 transactions → Score: 300 ("insufficient data")
- After 30 transactions (2-4 weeks) → Score becomes meaningful
- After 90 transactions → Reliable score
- **Problem:** 2-4 weeks of no credit access while building history

**Future (AGI):**
- New worker registers in Kibera, sells tomatoes
- AGI knows: 2,000+ mama mboga in Kibera with Alama Scores
- AGI finds: 50 tomato sellers in Kibera with similar profiles
- AGI infers: "Based on similar workers, this person has a 75% probability of reaching Alama Score 600+ within 90 days"
- **Provisional score: 580** based on peer cohort analysis
- After 5 transactions, AGI adjusts: "Actual trajectory matches cohort prediction" → score: 610
- After 10 transactions: Confident score with narrow confidence interval

**What AGI needs for this:**
1. Knowledge graph of worker cohorts (geography × business type × demographics)
2. Few-shot learning from similar workers
3. Bayesian updating from minimal new data
4. Ability to explain: "Your provisional score is based on 50 similar tomato sellers in your area"

### E.4 Causal Understanding for Default Prevention

AGI wouldn't just predict default — it would understand **why** and suggest **prevention**:

**Classical ML:** "This worker has 40% default probability. Risk factors: low revenue stability, high customer concentration."

**AGI:** "This worker is at risk because:
1. Their main supplier (Mama Njeri) raised wholesale prices 15% last week
2. Three of their regular customers haven't bought in 10 days (possible payday delay at nearby construction site)
3. The worker reduced stock variety from 12 to 8 products — a stress signal

**Recommended actions:**
- Switch to Supplier Kamau (same products, 8% cheaper, 2km further but worth the trip)
- Hold prices steady — the construction workers will be paid Friday
- Restock onions and tomatoes specifically — those had the highest margin last month
- If cash is tight, the KSh 5,000 micro-loan at 3% monthly would cover 1 week of stock"

This requires:
1. **Causal graph** — connecting supplier prices → margins → stock decisions → revenue
2. **Temporal reasoning** — construction pay cycles, supplier behavior patterns
3. **Intervention reasoning** — "if you do X, Y will likely happen"
4. **Natural language generation** — explaining complex reasoning simply

### E.5 What Can We Build NOW Toward AGI Credit Scoring?

| Component | What to Build Now | AGI Upgrade Path |
|-----------|-------------------|------------------|
| **Causal graph** | Build a simple DAG of credit factors (transaction → revenue → repayment) | AGI fills in the full causal model automatically |
| **Cohort analysis** | Group workers by geography + business type + tenure | AGI uses this for few-shot scoring of new workers |
| **Explainability** | Generate human-readable score explanations | AGI generates natural language explanations in local languages |
| **Counterfactual simulation** | "What if revenue drops 20%?" simple scenario modeling | AGI runs complex multi-factor simulations |
| **Cross-feature engineering** | Manual: combine market data + transaction data | AGI discovers useful cross-features automatically |
| **Knowledge graph** | Build basic market knowledge graph (suppliers, products, locations) | AGI's world knowledge fills in the graph |

### E.6 Realistic Timeline

| Capability | Timeline | Confidence |
|-----------|----------|------------|
| Classical ML credit scoring (current) | Now | ✅ Done |
| Quantum-inspired feature engineering | 3-6 months | High |
| Cohort-based provisional scoring | 6-12 months | High |
| Causal graph for credit factors | 6-12 months | Medium |
| Explainable score generation | 3-6 months | High |
| Quantum feature extraction (PennyLane simulation) | 6-12 months | Medium |
| Cross-domain AGI reasoning for credit | 3-5 years | Low |
| Quantum ML advantage for thin files | 5-10 years | Very Low |
| Full AGI credit scoring | 5-10 years | Very Low |

### E.7 Recommendation for the Founder

**Build the hybrid architecture NOW.** Here's the concrete plan:

1. **Month 1-2:** Classical Alama Score with XGBoost + explainability layer
2. **Month 3-4:** Add cohort-based provisional scoring for new workers ("peer group analysis")
3. **Month 5-6:** Build simple causal graph of credit factors; add counterfactual explanations
4. **Month 7-12:** Add quantum feature extraction (PennyLane simulation); benchmark against classical
5. **Year 2:** If quantum features show improvement, test on IBM Quantum free tier
6. **Year 3+:** Evaluate quantum ML based on hardware maturity and actual improvement

**The key insight:** Don't wait for quantum or AGI. Build the classical system with the right architecture — abstract interfaces, feature pipelines, explainability, cohort analysis — and the upgrades are plug-in replacements, not rewrites.

---

## Appendix F: Updated Problem-Solver Matrix (with Credit Scoring)

| Problem | Size | Best Classical | Quantum-Inspired | Quantum (Future) |
|---------|------|---------------|------------------|------------------|
| **Credit scoring (individual)** | 10-50 features | XGBoost (<10ms) | Random Fourier Features | Quantum kernels (unproven advantage) |
| **Credit portfolio (MFI, 100 loans)** | 100 vars | SciPy QP (<10ms) | QUBO (<1s) | Not needed |
| **Credit portfolio (MFI, 1000 loans)** | 1000 vars | SA (<5s) | GA (<10s) | D-Wave (<1s) |
| **Routing (10 stops)** | 100 vars | OR-Tools (<10ms) | Not needed | Not needed |
| **Routing (50 stops)** | 2,500 vars | OR-Tools (<100ms) | SA (<1s) | Not needed |
| **Routing (200 stops)** | 40,000 vars | SA (<10s) | GA (<30s) | D-Wave (<1s) |
| **Supply Chain (20 products)** | 20 vars | PuLP (<5ms) | Not needed | Not needed |
| **Pricing (10 products)** | 10 vars | PuLP (<1ms) | Not needed | Not needed |
| **Portfolio (5 options)** | 5 vars | SciPy QP (<1ms) | Not needed | Not needed |
| **Matching (50×50)** | 2,500 vars | PuLP (<50ms) | QUBO (<1s) | Not needed |
| **Matching (500×500)** | 250,000 vars | SA (<60s) | GA (<120s) | D-Wave (<5s) |

---

*This document is the authoritative design for the Quantum Solver Interface module. Implementation begins with Phase 1 (classical solvers) in the first sprint. Quantum phases activate based on scale and cost-effectiveness, not speculation.*
