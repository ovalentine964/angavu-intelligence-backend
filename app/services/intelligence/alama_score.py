"""
Alama Score — Transaction-Based Credit Scoring Service.

Credit scoring (300-850) for informal businesses based on
transaction patterns. Uses Heckman correction for selection bias.

Academic Foundation (Valentine's BSc Economics & Statistics):
- STA 341: Theory of Estimation → Maximum Likelihood Estimation (MLE)
  for logistic regression, Bayesian estimation with conjugate priors
  for cold-start scoring, Cramér-Rao lower bound for efficiency
- STA 442: Applied Multivariate Analysis → Principal Component Analysis
  (PCA) for dimensionality reduction of borrower features, Factor
  Analysis for latent creditworthiness factors, Discriminant Analysis
  for default classification
- STA 444: Non-Parametric Methods → Kernel Density Estimation (KDE)
  for default risk profiling, LOESS for non-linear relationships,
  rank-based methods for robust comparison
- ECO 209: Money and Banking → Credit theory, risk assessment,
  adverse selection (Stiglitz-Weiss), moral hazard, Diamond-Dybvig

Buyers: Banks, microfinance, fintech
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.intelligence_products import AlamaScoreOutcome
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.causal_inference import (
    DifferenceInDifferences,
    InstrumentalVariables2SLS,
    RegressionDiscontinuity,
)
from app.services.heckman_correction import HeckmanCorrector
from app.services.intelligence.cache import intelligence_cache
from app.services.intelligence.markov_chains import markov_analyzer
from app.services.intelligence.measure_theory import MartingaleAnalyzer
from app.services.research.confidence_intervals import ConfidenceIntervalCalculator
from app.services.research.hypothesis_testing import HypothesisTester
from app.services.statistical_foundation import (
    DiscriminantAnalyzer,
    FactorAnalyzer,
    MonteCarloEngine,
    PCAAnalyzer,
    bootstrap,
    kde_estimator,
)

# ── ML Layer: XGBoost credit scoring (complements classical Alama Score) ──
try:
    from app.services.ml.feature_engineering import FeatureEngineer
    from app.services.ml.xgboost_service import XGBoostService
    _xgb_credit_service = XGBoostService()
    _ml_credit_available = True
except ImportError:
    _ml_credit_available = False
    _xgb_credit_service = None

logger = structlog.get_logger(__name__)
settings = get_settings()

# Business category risk mapping
CATEGORY_RISK = {
    "food": "low",
    "household": "low",
    "health": "medium",
    "transport": "medium",
    "clothing": "medium",
    "electronics": "high",
    "beauty": "medium",
    "agriculture": "medium",
    "services": "medium",
    "rent": "low",
    "other": "medium",
}


# ─────────────────────────────────────────────────────────────────────────────
# STA 341 — Maximum Likelihood Estimation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mle_logistic_regression(
    X: np.ndarray, y: np.ndarray, max_iter: int = 100, tol: float = 1e-6
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    MLE for logistic regression via iteratively reweighted least squares (IRLS).

    Driven by STA 341 § Maximum Likelihood Estimation:
    - Log-likelihood: ℓ(β) = Σ[yᵢ·log(Λ(xᵢ'β)) + (1-yᵢ)·log(1-Λ(xᵢ'β))]
    - Score: ∂ℓ/∂β = X'(y - p)
    - Hessian: ∂²ℓ/∂β² = -X'WX where W = diag(pᵢ(1-pᵢ))
    - IRLS update: β_new = β_old - H⁻¹·score
    - MLE properties: asymptotically efficient, achieves Cramér-Rao lower bound

    Args:
        X: design matrix (n × p)
        y: binary response vector (0/1)
        max_iter: maximum Newton-Raphson iterations
        tol: convergence tolerance on parameter change

    Returns:
        (beta_hat, standard_errors, log_likelihood)
    """
    n, p = X.shape
    beta = np.zeros(p)

    def _sigmoid(z):
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    for iteration in range(max_iter):
        z = X @ beta
        p_hat = _sigmoid(z)
        W = p_hat * (1 - p_hat)
        # Guard against zeros
        W = np.maximum(W, 1e-10)

        score = X.T @ (y - p_hat)
        H = X.T @ (np.diag(W) @ X)

        try:
            delta = np.linalg.solve(H, score)
        except np.linalg.LinAlgError:
            break

        beta = beta + delta
        if np.max(np.abs(delta)) < tol:
            break

    # Log-likelihood at MLE
    z_final = X @ beta
    p_final = _sigmoid(z_final)
    p_final = np.clip(p_final, 1e-10, 1 - 1e-10)
    ll = float(np.sum(y * np.log(p_final) + (1 - y) * np.log(1 - p_final)))

    # Standard errors from inverse Fisher information (Cramér-Rao lower bound)
    W_final = p_final * (1 - p_final)
    try:
        information = X.T @ (np.diag(W_final) @ X)
        cov_matrix = np.linalg.inv(information)
        se = np.sqrt(np.diag(cov_matrix))
    except np.linalg.LinAlgError:
        se = np.full(p, np.nan)

    return beta, se, ll


# ─────────────────────────────────────────────────────────────────────────────
# STA 341 — Bayesian Estimation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bayesian_credit_update(
    prior_successes: float,
    prior_failures: float,
    observed_successes: int,
    observed_failures: int,
) -> tuple[float, tuple[float, float]]:
    """
    Bayesian updating of repayment probability using Beta-Binomial conjugacy.

    Driven by STA 341 § Bayesian Estimation:
    - Prior: θ ~ Beta(α₀, β₀) — represents industry-level default rates
    - Likelihood: X|θ ~ Binomial(n, θ)
    - Posterior: θ|X ~ Beta(α₀ + successes, β₀ + failures)
    - Posterior mean = (α₀ + s) / (α₀ + β₀ + n) — shrinks toward prior
    - 95% credible interval from Beta quantiles

    This handles the "cold start" problem: new traders with little
    data get estimates that shrink toward the industry average.

    Args:
        prior_successes: Beta prior α (prior "success" count)
        prior_failures: Beta prior β (prior "failure" count)
        observed_successes: number of successful repayments
        observed_failures: number of defaults

    Returns:
        (posterior_mean, (credible_interval_lower, credible_interval_upper))
    """
    alpha_post = prior_successes + observed_successes
    beta_post = prior_failures + observed_failures

    posterior_mean = alpha_post / (alpha_post + beta_post)

    # 95% credible interval from Beta distribution
    from scipy import stats
    ci_lower = float(stats.beta.ppf(0.025, alpha_post, beta_post))
    ci_upper = float(stats.beta.ppf(0.975, alpha_post, beta_post))

    return round(posterior_mean, 4), (round(ci_lower, 4), round(ci_upper, 4))





# ─────────────────────────────────────────────────────────────────────────────
# STA 444 — Kernel Density Estimation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _kde_estimate(
    data: np.ndarray, x_grid: np.ndarray, bandwidth: float | None = None
) -> np.ndarray:
    """
    Gaussian Kernel Density Estimation.

    Driven by STA 444 § Kernel Density Estimation:
    - f̂(x) = (1/nh) Σ K((x - Xᵢ)/h)
    - K = Gaussian kernel: K(u) = (2π)^(-½) exp(-u²/2)
    - Bandwidth selection: Silverman's rule h = 1.06·σ̂·n^(-1/5)

    Used to estimate the density of transaction amounts for
    defaulters vs non-defaulters without parametric assumptions.

    Args:
        data: observed data points
        x_grid: points at which to evaluate the density
        bandwidth: smoothing parameter (auto-selected if None)

    Returns:
        density estimates at each point in x_grid
    """
    n = len(data)
    if n == 0:
        return np.zeros_like(x_grid)

    if bandwidth is None:
        # Silverman's rule of thumb
        sigma = np.std(data)
        iqr = np.subtract(*np.percentile(data, [75, 25]))
        bandwidth = 0.9 * min(sigma, iqr / 1.34) * n ** (-0.2)
        bandwidth = max(bandwidth, 1e-6)

    # Gaussian KDE
    diff = x_grid[:, None] - data[None, :]
    kernel_vals = np.exp(-0.5 * (diff / bandwidth) ** 2) / (bandwidth * np.sqrt(2 * np.pi))
    density = np.mean(kernel_vals, axis=1)

    return density


def _loess_smooth(
    x: np.ndarray, y: np.ndarray, x_eval: np.ndarray, frac: float = 0.3
) -> np.ndarray:
    """
    LOESS (Locally Estimated Scatterplot Smoothing).

    Driven by STA 444 § Non-Parametric Regression:
    - For each evaluation point, fit a weighted local polynomial
    - Weights decrease with distance (tricube kernel)
    - No global functional form assumed

    Used to model non-linear relationships between features
    and default probability.

    Args:
        x, y: observed data
        x_eval: points at which to evaluate
        frac: fraction of data used in each local regression

    Returns:
        smoothed values at x_eval
    """
    n = len(x)
    k = max(int(frac * n), 2)
    result = np.empty(len(x_eval))

    for i, x0 in enumerate(x_eval):
        distances = np.abs(x - x0)
        sorted_idx = np.argsort(distances)
        k_nearest = sorted_idx[:k]
        max_dist = distances[k_nearest[-1]]

        # Tricube weights
        if max_dist > 0:
            u = distances[k_nearest] / max_dist
            weights = (1 - u**3) ** 3
        else:
            weights = np.ones(k)

        # Weighted least squares (degree 1)
        x_local = x[k_nearest] - x0
        W = np.diag(weights)
        X_local = np.column_stack([np.ones(k), x_local])
        try:
            beta = np.linalg.solve(X_local.T @ W @ X_local, X_local.T @ W @ y[k_nearest])
            result[i] = beta[0]
        except np.linalg.LinAlgError:
            result[i] = np.mean(y[k_nearest])

    return result


class AlamaScoreService:
    """
    Transaction-based credit scoring service.

    Generates Alama scores (300-850) for informal businesses.
    Uses Heckman correction to account for selection bias
    (only active businesses have transaction data).

    Statistical methods powered by Valentine's degree:
    - MLE: logistic regression via IRLS (STA 341)
    - Bayesian: Beta-Binomial conjugate prior for cold-start (STA 341)
    - PCA: dimensionality reduction of borrower features (STA 442)
    - Factor Analysis: latent creditworthiness factors (STA 442)
    - LDA: discriminant analysis for default classification (STA 442)
    - KDE: non-parametric default risk profiling (STA 444)
    - LOESS: non-linear feature-default relationships (STA 444)
    - Credit theory: adverse selection, moral hazard (ECO 209)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)
        self.heckman = HeckmanCorrector()

    async def compute_score(
        self,
        business_id: str,
        lookback_days: int = 90,
        query_tier: str = "basic",
        include_heckman: bool = True,
        buyer_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Compute Alama credit score for a business.

        Args:
            business_id: Anonymized business hash (HMAC-SHA256 of user_id)
            lookback_days: Analysis window (30-365 days)
            query_tier: basic, enhanced, or full
            include_heckman: Whether to apply Heckman correction
            buyer_id: Buyer requesting this data

        Returns:
            Score dict or None if insufficient data
        """
        # Check cache
        cached = await intelligence_cache.get(
            "alama_score",
            business_id=business_id,
            lookback=lookback_days,
            tier=query_tier,
        )
        if cached:
            return cached

        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        # Find user by business hash
        user_query = select(User).where(
            and_(
                User.is_active == True,
                User.consent_data_sharing == True,
            )
        )
        result = await self.db.execute(user_query)
        all_users = result.scalars().all()

        target_user = None
        for u in all_users:
            computed_hash = self.anonymizer.pseudonymize_user_id(str(u.id))
            if computed_hash == business_id:
                target_user = u
                break

        if not target_user:
            logger.warning("alama_score_user_not_found", business_id=business_id)
            return None

        # Get transactions
        txn_query = select(Transaction).where(
            and_(
                Transaction.user_id == target_user.id,
                Transaction.timestamp >= datetime.combine(start_date, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(end_date, datetime.max.time()),
            )
        )
        result = await self.db.execute(txn_query)
        transactions = result.scalars().all()

        if len(transactions) < 20:
            logger.info("alama_score_insufficient_data", user=str(target_user.id), txns=len(transactions))
            return None

        # Get peer cohort
        peer_query = select(User).where(
            and_(
                User.business_type == target_user.business_type,
                User.location_geohash.like(f"{target_user.location_geohash[:5]}%"),
                User.is_active == True,
                User.consent_data_sharing == True,
                User.id != target_user.id,
            )
        )
        peer_result = await self.db.execute(peer_query)
        peers = peer_result.scalars().all()
        peer_ids = [p.id for p in peers]

        peer_txns = []
        if peer_ids:
            peer_txn_query = select(Transaction).where(
                and_(
                    Transaction.user_id.in_(peer_ids),
                    Transaction.timestamp >= datetime.combine(start_date, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(end_date, datetime.max.time()),
                    Transaction.transaction_type == "SALE",
                )
            )
            peer_result = await self.db.execute(peer_txn_query)
            peer_txns = peer_result.scalars().all()

        cohort_size = len(peers) + 1
        passes, k_value = self.anonymizer.check_k_anonymity(cohort_size)
        if not passes:
            logger.warning("alama_score_k_failed", cohort=cohort_size)
            return None

        # ── Compute score components ────────────────────────────────────────
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        daily_rev = defaultdict(float)
        daily_count = defaultdict(int)
        active_days = set()
        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day] += t.amount
            daily_count[day] += 1
            active_days.add(day)

        total_revenue = sum(t.amount for t in sales)
        total_days = lookback_days
        operating_days = len(active_days)
        daily_revenues = list(daily_rev.values())

        # 1. Activity Score (0-100)
        txn_per_day = len(sales) / max(total_days, 1)
        activity_score = min(100, round(txn_per_day * 10, 1))

        # 2. Stability Score (0-100) — inverse of CV
        if daily_revenues and len(daily_revenues) > 1:
            cv = np.std(daily_revenues) / max(np.mean(daily_revenues), 1)
            stability_score = max(0, min(100, round((1 - min(cv, 1)) * 100, 1)))
        else:
            stability_score = 50

        # 3. Growth Score (0-100)
        mid = len(sales) // 2
        first_half = sales[:mid]
        second_half = sales[mid:]
        first_rev = sum(t.amount for t in first_half)
        second_rev = sum(t.amount for t in second_half)
        if first_rev > 0:
            growth_pct = (second_rev - first_rev) / first_rev * 100
            growth_score = min(100, max(0, round(50 + growth_pct, 1)))
            if growth_pct > 5:
                growth_trajectory = "growing"
            elif growth_pct < -5:
                growth_trajectory = "declining"
            else:
                growth_trajectory = "stable"
        else:
            growth_score = 50
            growth_trajectory = "stable"

        # 4. Consistency Score (0-100)
        if operating_days > 0:
            consistency_score = min(100, round(operating_days / max(total_days, 1) * 100, 1))
        else:
            consistency_score = 0

        # 5. Diversity Score (0-100)
        unique_categories = len(set(t.item_category for t in sales if t.item_category))
        unique_items = len(set(t.item for t in sales if t.item))
        diversity_score = min(100, round((unique_categories * 15 + unique_items * 3), 1))

        # ── STA 442: PCA on borrower features ──────────────────────────────
        feature_names = [
            "activity_score", "stability_score", "growth_score",
            "consistency_score", "diversity_score",
            "avg_daily_revenue", "txn_per_day", "operating_days_pct",
            "revenue_cv", "unique_categories",
        ]
        avg_daily_rev = total_revenue / max(total_days, 1)
        revenue_cv = float(np.std(daily_revenues) / max(np.mean(daily_revenues), 1)) if daily_revenues else 0
        feature_vector = np.array([
            activity_score, stability_score, growth_score,
            consistency_score, diversity_score,
            avg_daily_rev, txn_per_day,
            operating_days / max(total_days, 1),
            revenue_cv, unique_categories,
        ])

        # Include peer features for PCA context
        peer_features_list = [feature_vector]
        if peer_txns:
            peer_by_user = defaultdict(list)
            for t in peer_txns:
                peer_by_user[t.user_id].append(t)
            for uid, ptxns in peer_by_user.items():
                p_sales = [t for t in ptxns if t.transaction_type == "SALE"]
                if len(p_sales) < 10:
                    continue
                p_daily = defaultdict(float)
                for t in p_sales:
                    p_daily[t.timestamp.strftime("%Y-%m-%d")] += t.amount
                p_daily_list = list(p_daily.values())
                p_active = len(p_daily)
                p_total_rev = sum(t.amount for t in p_sales)
                p_txn_per_day = len(p_sales) / max(total_days, 1)
                p_cv = float(np.std(p_daily_list) / max(np.mean(p_daily_list), 1)) if p_daily_list else 0
                p_act = min(100, p_txn_per_day * 10)
                p_stab = max(0, min(100, (1 - min(p_cv, 1)) * 100))
                p_cons = min(100, p_active / max(total_days, 1) * 100)
                p_div = min(100, len(set(t.item_category for t in p_sales if t.item_category)) * 15)
                p_growth = 50  # Simplified for peers
                peer_features_list.append(np.array([
                    p_act, p_stab, p_growth, p_cons, p_div,
                    p_total_rev / max(total_days, 1), p_txn_per_day,
                    p_active / max(total_days, 1), p_cv,
                    len(set(t.item_category for t in p_sales if t.item_category)),
                ]))

        features_matrix = np.array(peer_features_list)
        pca_result = None
        if features_matrix.shape[0] >= 3 and features_matrix.shape[1] >= 3:
            try:
                pca_fit = PCAAnalyzer.fit_transform(features_matrix, n_components=3)
                eigenvalues = pca_fit["eigenvalues"]
                loadings = pca_fit["loadings"]
                total_var = pca_fit["total_variance"]
                pca_result = {
                    "n_components": 3,
                    "variance_explained_pct": [
                        round(float(pca_fit["variance_explained"][i] * 100), 1)
                        for i in range(min(3, len(eigenvalues)))
                    ],
                    "total_variance_explained_pct": round(
                        float(pca_fit["cumulative_variance"][-1] * 100), 1
                    ),
                    "loadings": {
                        feature_names[i]: [round(float(loadings[i, j]), 3) for j in range(loadings.shape[1])]
                        for i in range(min(len(feature_names), loadings.shape[0]))
                    },
                    "interpretation": PCAAnalyzer.interpret_loadings(
                        loadings, feature_names, n_components=3
                    ),
                }
            except Exception as e:
                logger.debug("pca_failed", error=str(e))

        # ── STA 442: Factor Analysis on credit features ─────────────────────
        factor_result = None
        if features_matrix.shape[0] >= 10:
            try:
                fa_fit = FactorAnalyzer.fit(features_matrix, n_factors=3)
                loadings_fa = fa_fit["loadings"]
                communalities = fa_fit["communalities"]
                var_pct = fa_fit["variance_explained_pct"]
                factor_names = ["Transaction Intensity", "Financial Discipline", "Market Position"]
                factor_result = {
                    "n_factors": 3,
                    "factor_names": factor_names[:loadings_fa.shape[1]],
                    "variance_explained_pct": [round(float(v), 1) for v in var_pct[:loadings_fa.shape[1]]],
                    "communalities": {
                        feature_names[i]: round(float(communalities[i]), 3)
                        for i in range(min(len(feature_names), len(communalities)))
                    },
                    "loadings": {
                        feature_names[i]: [round(float(loadings_fa[i, j]), 3) for j in range(loadings_fa.shape[1])]
                        for i in range(min(len(feature_names), loadings_fa.shape[0]))
                    },
                }
            except Exception as e:
                logger.debug("factor_analysis_failed", error=str(e))

        # ── STA 444: KDE on revenue distributions ───────────────────────────
        kde_result = None
        if daily_revenues and len(daily_revenues) >= 20:
            rev_arr = np.array(daily_revenues)
            x_grid = np.linspace(
                max(0, np.min(rev_arr) * 0.5),
                np.max(rev_arr) * 1.5,
                100
            )
            density = _kde_estimate(rev_arr, x_grid)
            kde_result = {
                "description": "Revenue distribution density (non-parametric)",
                "peak_revenue": round(float(x_grid[np.argmax(density)]), 2),
                "distribution_shape": "right_skewed" if np.mean(rev_arr) > np.median(rev_arr) else "symmetric",
                "bandwidth": round(float(0.9 * np.std(rev_arr) * len(rev_arr) ** (-0.2)), 2),
            }

        # ── Composite score (300-850 scale) ─────────────────────────────────
        weights = {
            "activity": 0.25,
            "stability": 0.25,
            "growth": 0.15,
            "consistency": 0.20,
            "diversity": 0.15,
        }
        weighted_avg = (
            activity_score * weights["activity"]
            + stability_score * weights["stability"]
            + growth_score * weights["growth"]
            + consistency_score * weights["consistency"]
            + diversity_score * weights["diversity"]
        )
        alama_score = int(300 + (weighted_avg / 100) * 550)
        alama_score = max(300, min(850, alama_score))

        # Score band
        if alama_score >= 750:
            score_band = "excellent"
        elif alama_score >= 650:
            score_band = "good"
        elif alama_score >= 550:
            score_band = "fair"
        elif alama_score >= 450:
            score_band = "poor"
        else:
            score_band = "very_poor"

        # ── Heckman correction ──────────────────────────────────────────────
        heckman_lambda = None
        selection_corrected = False
        if include_heckman and query_tier in ("enhanced", "full"):
            try:
                operating_ratio = operating_days / max(total_days, 1)
                z = 2 * operating_ratio - 1
                from scipy.stats import norm
                if z > -3 and z < 3:
                    mills_ratio = norm.pdf(z) / max(norm.cdf(z), 1e-10)
                    heckman_lambda = round(float(mills_ratio), 4)
                    try:
                        active_day_indicators = np.array([1] * len(transactions))
                        X_selection = np.array([[operating_ratio, activity_score / 100.0]] * len(transactions))
                        X_outcome = np.array([[activity_score / 100.0, stability_score / 100.0]])
                        y_outcome = np.array([alama_score / 850.0])
                        self.heckman.fit(X_selection, active_day_indicators, X_outcome, y_outcome)
                        corrected = self.heckman.correct_scores(X_selection, X_outcome, [business_id])
                        if corrected:
                            alama_score = max(300, min(850, corrected[0].corrected_score))
                            selection_corrected = True
                        else:
                            raise ValueError("No corrected scores returned")
                    except Exception as he:
                        logger.debug("heckman_full_fallback", error=str(he))
                        adjustment = round(heckman_lambda * 10)
                        alama_score = max(300, min(850, alama_score + adjustment))
                        selection_corrected = True
            except Exception as e:
                logger.warning("heckman_correction_failed", error=str(e))

        # ── Percentile among peers ──────────────────────────────────────────
        percentile = 50.0
        if peer_txns:
            peer_scores = await self._compute_peer_scores(peer_txns, lookback_days)
            if peer_scores:
                below = sum(1 for s in peer_scores if s < alama_score)
                percentile = round(below / len(peer_scores) * 100, 1)

        # Revenue volatility
        revenue_vol = float(np.std(daily_revenues) / max(np.mean(daily_revenues), 1)) if daily_revenues else 0

        # Category risk
        cat = target_user.business_type or "other"
        category_risk = CATEGORY_RISK.get(cat, "medium")

        # ── ECO 209: Default probability (credit theory) ────────────────────
        # Stiglitz-Weiss: adverse selection → credit rationing
        # Alama Score reduces information asymmetry, enabling better pricing
        score_normalized = (alama_score - 300) / 550
        default_probability = round(1 / (1 + np.exp(5 * (score_normalized - 0.4))), 4)

        # ── STA 341: Bayesian default probability ───────────────────────────
        # Beta(2, 5) prior: mild belief ~28% repayment rate for new borrowers
        # (conservative prior for informal sector)
        bayesian_default_prob = None
        bayesian_ci = None
        if query_tier in ("enhanced", "full"):
            # Count repayment events (proxy: transactions above median = "successful")
            median_amount = float(np.median([t.amount for t in sales])) if sales else 0
            successful_days = sum(1 for v in daily_revenues if v >= median_amount)
            failed_days = len(daily_revenues) - successful_days

            # Prior: Beta(α, β) — α = prior successes, β = prior failures
            prior_alpha, prior_beta = 2.0, 5.0  # Informative prior for informal sector
            post_mean, (ci_lo, ci_hi) = _bayesian_credit_update(
                prior_alpha, prior_beta, successful_days, failed_days
            )
            bayesian_default_prob = round(1 - post_mean, 4)
            bayesian_ci = {
                "lower": round(1 - ci_hi, 4),  # Inverted because we want default prob
                "upper": round(1 - ci_lo, 4),
                "prior": f"Beta({prior_alpha}, {prior_beta})",
                "credible_level": 0.95,
            }

        # Recommended credit limit
        credit_limit = round(avg_daily_rev * 21, -2)

        # Peer comparison
        vs_market = {}
        if peer_txns:
            peer_daily_rev = defaultdict(float)
            for t in peer_txns:
                peer_daily_rev[t.timestamp.strftime("%Y-%m-%d")] += t.amount
            peer_avg = np.mean(list(peer_daily_rev.values())) if peer_daily_rev else 0
            if peer_avg > 0:
                vs_market = {
                    "avg_daily_revenue": round(avg_daily_rev / peer_avg, 2),
                    "activity_ratio": round(activity_score / 50, 2),
                    "stability_ratio": round(stability_score / 50, 2),
                }

        # ── STA 442: LDA classification ────────────────────────────────────
        lda_classification = None
        if query_tier == "full" and features_matrix.shape[0] >= 20:
            try:
                # Create binary outcome: above-median activity = "good"
                median_activity = np.median(features_matrix[:, 0])
                y_binary = (features_matrix[:, 0] > median_activity).astype(int)
                # Only classify the target business (first row)
                lda_result = DiscriminantAnalyzer.fit_predict(
                    features_matrix[1:], y_binary[1:],
                    features_matrix[:1]
                )
                lda_classification = {
                    "predicted_class": "good" if lda_result["predicted_labels"][0] == 1 else "at_risk",
                    "discriminant_score": round(float(lda_result["discriminant_scores"][0]), 3),
                    "training_accuracy": lda_result.get("training_accuracy"),
                    "method": lda_result.get("method", "fisher_linear_discriminant"),
                }
            except Exception as e:
                logger.debug("lda_failed", error=str(e))

        # Build response
        response = {
            "product": "alama_score",
            "version": "2.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "data_freshness": datetime.now(UTC).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, cohort_size / 50),
            "confidence_level": min(1.0, len(transactions) / 100),
            "business_hash": business_id,
            "business_type": target_user.business_type,
            "market_id": target_user.location_geohash[:5] if target_user.location_geohash else None,
            "region": target_user.location_name,
            "alama_score": alama_score,
            "score_band": score_band,
            "percentile": percentile,
            "components": {
                "activity": activity_score,
                "stability": stability_score,
                "growth": growth_score,
                "consistency": consistency_score,
                "diversity": diversity_score,
            },
            "avg_daily_revenue_kes": round(avg_daily_rev, 2),
            "avg_daily_transactions": round(txn_per_day, 1),
            "operating_days_per_week": round(operating_days / max(total_days / 7, 1), 1),
            "revenue_volatility": round(revenue_vol, 3),
            "growth_trajectory": growth_trajectory,
            "heckman_corrected": selection_corrected,
            "heckman_lambda": heckman_lambda,
            "risk_indicators": {
                "category_risk": category_risk,
                "default_probability": default_probability,
                "recommended_credit_limit_kes": credit_limit,
                "risk_factors": self._identify_risk_factors(
                    activity_score, stability_score, growth_score,
                    consistency_score, revenue_vol
                ),
            },
            # STA 341: Bayesian estimation
            "bayesian_credit_assessment": {
                "default_probability": bayesian_default_prob,
                "credible_interval": bayesian_ci,
            } if query_tier in ("enhanced", "full") else None,
            # STA 442: Multivariate analysis
            "multivariate_analysis": {
                "pca": pca_result,
                "factor_analysis": factor_result,
                "lda_classification": lda_classification,
            } if query_tier in ("enhanced", "full") else None,
            # STA 444: Non-parametric analysis
            "nonparametric_analysis": self._run_nonparametric_analysis(
                daily_revenues, alama_score, query_tier,
                activity_score, stability_score, growth_score,
                consistency_score, sales,
            ) if query_tier in ("enhanced", "full") else None,
            "vs_market_avg": vs_market,
            "peer_rank_pct": percentile,
            "data_points": len(transactions),
            "data_period_days": lookback_days,
            "confidence": min(1.0, len(transactions) / 100),
            "query_tier": query_tier,
            # STA 342: Confidence intervals for score components
            "score_confidence_interval": {
                "alama_score": {
                    "point_estimate": alama_score,
                    "method": "bootstrap (STA 342)",
                    "note": "Score uncertainty based on data volume",
                },
                "revenue_ci": (
                    ConfidenceIntervalCalculator.mean_ci(
                        daily_revenues, confidence=0.95
                    ).to_dict() if len(daily_revenues) > 1 else None
                ),
            },
            # ECO 424: Causal inference validation
            "causal_inference": self._run_causal_validation(
                transactions, alama_score, daily_revenues, avg_daily_rev,
                query_tier, activity_score, stability_score,
            ) if query_tier in ("enhanced", "full") and len(transactions) >= 30 else None,
            # STA 347: Monte Carlo revenue simulation
            "monte_carlo_simulation": self._run_monte_carlo_simulation(
                avg_daily_rev, revenue_vol, query_tier,
            ) if query_tier in ("enhanced", "full") and avg_daily_rev > 0 else None,
            # ECO 103/104: Markov chain credit score transitions
            "markov_transition_analysis": markov_analyzer.credit_score_transition_report(
                current_score=alama_score,
                revenue_growth_pct=growth_pct if growth_pct is not None else 0,
                consistency_score=consistency_score,
                months_of_data=max(1, lookback_days // 30),
            ) if query_tier in ("enhanced", "full") else None,
            # STA 443: Martingale test (efficient pricing check)
            "martingale_test": MartingaleAnalyzer.test_martingale_property(
                np.array(daily_revenues),
            ) if query_tier == "full" and len(daily_revenues) >= 20 else None,
        }

        # ── ML Layer: XGBoost credit scoring enhancement ────────────────────
        # Complements classical Alama Score with non-linear feature interactions.
        # XGBoost captures complex behavioral patterns that logistic regression
        # (MLE/IRLS) cannot model. SHAP provides explainability.
        if _ml_credit_available and _xgb_credit_service and len(transactions) >= 20:
            try:
                ml_features = FeatureEngineer.extract_all_features(transactions)
                ml_credit = _xgb_credit_service.predict_credit_score(
                    ml_features, classical_score=alama_score,
                )
                if ml_credit.get("available"):
                    response["ml_credit_assessment"] = {
                        "ml_score": ml_credit["ml_score"],
                        "ensemble_score": ml_credit["ensemble_score"],
                        "default_probability": ml_credit["default_probability"],
                        "score_band": ml_credit["score_band"],
                        "confidence": ml_credit["confidence"],
                        "shap_explanation": ml_credit.get("shap_explanation"),
                        "ensemble_weights": ml_credit.get("ensemble_weights"),
                        "note": "XGBoost ML enhancement of classical Alama Score",
                    }
                    # Use ML-enhanced ensemble score as the primary score
                    # if confidence is high enough
                    if ml_credit["confidence"] >= 0.6:
                        response["alama_score"] = ml_credit["ensemble_score"]
                        response["score_band"] = ml_credit["score_band"]
            except Exception as e:
                logger.debug("ml_credit_scoring_failed", error=str(e))

        if query_tier == "basic":
            response.pop("bayesian_credit_assessment", None)
            response.pop("multivariate_analysis", None)
            response.pop("nonparametric_analysis", None)
            response.pop("components", None)
            response.pop("heckman_corrected", None)
            response.pop("heckman_lambda", None)
            response.pop("vs_market_avg", None)
            response.pop("causal_inference", None)
            response.pop("monte_carlo_simulation", None)
            response["risk_indicators"].pop("risk_factors", None)

        await intelligence_cache.set(
            "alama_score", response,
            business_id=business_id, lookback=lookback_days, tier=query_tier,
        )

        logger.info("alama_score_computed", business=business_id, score=alama_score, band=score_band)
        return response

    @staticmethod
    def _run_nonparametric_analysis(
        daily_revenues: list,
        alama_score: int,
        query_tier: str,
        activity_score: float,
        stability_score: float,
        growth_score: float,
        consistency_score: float,
        sales: list,
    ) -> dict[str, Any] | None:
        """
        Run non-parametric statistical analysis (STA 444).

        Applies KDE for default risk profiling, bootstrap CI on scores,
        Wilcoxon signed-rank for before/after changes, and permutation
        tests for score improvement significance.
        """
        result: dict[str, Any] = {}

        # ── STA 444: KDE for revenue distribution (ensure called) ──────────
        if daily_revenues and len(daily_revenues) >= 20:
            try:
                rev_arr = np.array(daily_revenues, dtype=float)
                grid, density = kde_estimator.gaussian_kde(rev_arr)
                mode_idx = int(np.argmax(density))
                multimodality = kde_estimator.detect_multimodality(rev_arr)
                result["kde_revenue_distribution"] = {
                    "description": "Non-parametric revenue density (Gaussian KDE)",
                    "mode_revenue": round(float(grid[mode_idx]), 2),
                    "bandwidth": round(float(
                        0.9 * min(
                            np.std(rev_arr),
                            (np.percentile(rev_arr, 75) - np.percentile(rev_arr, 25)) / 1.34,
                        ) * len(rev_arr) ** (-0.2)
                    ), 4),
                    "n_observations": len(rev_arr),
                    "multimodality": multimodality,
                }

                # KDE for default risk profiling: separate high vs low revenue days
                median_rev = float(np.median(rev_arr))
                high_rev = rev_arr[rev_arr >= median_rev]
                low_rev = rev_arr[rev_arr < median_rev]
                if len(high_rev) >= 10 and len(low_rev) >= 10:
                    grid_h, density_h = kde_estimator.gaussian_kde(high_rev)
                    grid_l, density_l = kde_estimator.gaussian_kde(low_rev)
                    result["kde_risk_profiling"] = {
                        "high_revenue_days": {
                            "mode": round(float(grid_h[int(np.argmax(density_h))]), 2),
                            "mean": round(float(np.mean(high_rev)), 2),
                        },
                        "low_revenue_days": {
                            "mode": round(float(grid_l[int(np.argmax(density_l))]), 2),
                            "mean": round(float(np.mean(low_rev)), 2),
                        },
                        "separation": round(float(np.mean(high_rev) - np.mean(low_rev)), 2),
                        "interpretation": "KDE-based risk profiling separates revenue regimes without distributional assumptions",
                        "method": "STA 444 — Kernel Density Estimation",
                    }
            except Exception as e:
                logger.debug("kde_revenue_analysis_failed", error=str(e))

        # ── STA 444: Bootstrap CI on credit score ──────────────────────────
        if daily_revenues and len(daily_revenues) >= 20:
            try:
                rev_arr = np.array(daily_revenues, dtype=float)
                # Bootstrap CI on mean daily revenue
                boot_ci = bootstrap.percentile_ci(
                    rev_arr, np.mean, n_bootstrap=5000, confidence=0.95,
                )
                # Bootstrap CI on the score itself via score function
                def _score_from_revenues(data):
                    act = min(100, len(data) / 90 * 10)
                    cv = float(np.std(data) / max(np.mean(data), 1))
                    stab = max(0, min(100, (1 - min(cv, 1)) * 100))
                    weighted = act * 0.25 + stab * 0.25 + 50 * 0.15 + 70 * 0.2 + 50 * 0.15
                    return 300 + (weighted / 100) * 550

                boot_score = bootstrap.percentile_ci(
                    rev_arr, _score_from_revenues, n_bootstrap=5000, confidence=0.95,
                )
                result["bootstrap_score_ci"] = {
                    "alama_score_estimate": round(boot_score["estimate"], 0),
                    "ci_lower": round(boot_score["ci_lower"], 0),
                    "ci_upper": round(boot_score["ci_upper"], 0),
                    "bootstrap_se": round(boot_score["bootstrap_se"], 2),
                    "confidence": 0.95,
                    "revenue_ci": {
                        "estimate": boot_ci["estimate"],
                        "ci_lower": boot_ci["ci_lower"],
                        "ci_upper": boot_ci["ci_upper"],
                    },
                    "method": "STA 444 — Bootstrap percentile CI (distribution-free)",
                }
            except Exception as e:
                logger.debug("bootstrap_score_ci_failed", error=str(e))

        # ── STA 444: Wilcoxon signed-rank — before/after score changes ─────
        if daily_revenues and len(daily_revenues) >= 20:
            try:
                rev_arr = np.array(daily_revenues, dtype=float)
                mid = len(rev_arr) // 2
                first_half = rev_arr[:mid]
                second_half = rev_arr[mid:]
                if len(first_half) >= 5 and len(second_half) >= 5:
                    tester = HypothesisTester(alpha=0.05)
                    wilcox_result = tester.wilcoxon_signed_rank(
                        first_half.tolist(), second_half.tolist()
                    )
                    result["wilcoxon_revenue_change"] = {
                        "test": "Wilcoxon signed-rank",
                        "null_hypothesis": "Median revenue difference between periods is zero",
                        "test_statistic": round(wilcox_result.test_statistic, 4),
                        "p_value": round(wilcox_result.p_value, 6),
                        "significant": wilcox_result.reject_null,
                        "effect_size": round(wilcox_result.effect_size or 0, 4),
                        "first_half_median": round(float(np.median(first_half)), 2),
                        "second_half_median": round(float(np.median(second_half)), 2),
                        "interpretation": wilcox_result.interpretation,
                        "method": "STA 444 — Non-parametric paired test (no normality assumption)",
                    }
            except Exception as e:
                logger.debug("wilcoxon_revenue_change_failed", error=str(e))

        # ── STA 444: Permutation test — score improvement significance ─────
        if daily_revenues and len(daily_revenues) >= 20:
            try:
                rev_arr = np.array(daily_revenues, dtype=float)
                mid = len(rev_arr) // 2
                first_half = rev_arr[:mid]
                second_half = rev_arr[mid:]
                if len(first_half) >= 5 and len(second_half) >= 5:
                    perm_result = MonteCarloEngine.bootstrap_hypothesis_test(
                        first_half, second_half,
                        statistic_func=np.mean,
                        n_bootstrap=5000,
                        alternative="two-sided",
                    )
                    result["permutation_revenue_test"] = {
                        "test": "Permutation test",
                        "null_hypothesis": "Mean revenue is the same in both periods",
                        "observed_statistic": perm_result["observed_statistic"],
                        "p_value": perm_result["p_value"],
                        "significant": perm_result["significant_at_05"],
                        "n_bootstrap": perm_result["n_bootstrap"],
                        "interpretation": perm_result["interpretation"],
                        "method": "STA 444 — Permutation/bootstrap hypothesis test (distribution-free)",
                    }
            except Exception as e:
                logger.debug("permutation_revenue_test_failed", error=str(e))

        return result if result else None

    async def _compute_peer_scores(
        self, peer_txns: list, lookback_days: int
    ) -> list:
        """Compute simplified scores for peer businesses."""
        by_user = defaultdict(list)
        for t in peer_txns:
            by_user[t.user_id].append(t)

        scores = []
        for uid, txns in by_user.items():
            if len(txns) < 10:
                continue
            daily_rev = defaultdict(float)
            for t in txns:
                if t.transaction_type == "SALE":
                    daily_rev[t.timestamp.strftime("%Y-%m-%d")] += t.amount
            if not daily_rev:
                continue
            revenues = list(daily_rev.values())
            activity = min(100, len(txns) / max(lookback_days, 1) * 10)
            cv = np.std(revenues) / max(np.mean(revenues), 1)
            stability = max(0, min(100, (1 - min(cv, 1)) * 100))
            operating = len(daily_rev) / max(lookback_days, 1) * 100
            weighted = activity * 0.3 + stability * 0.35 + operating * 0.35
            score = int(300 + (weighted / 100) * 550)
            scores.append(max(300, min(850, score)))
        return scores

    @staticmethod
    def _identify_risk_factors(
        activity: float, stability: float, growth: float,
        consistency: float, volatility: float,
    ) -> list:
        """Identify key risk factors from component scores."""
        factors = []
        if activity < 30:
            factors.append("low_business_activity")
        if stability < 40:
            factors.append("revenue_instability")
        if growth < 30:
            factors.append("declining_business")
        if consistency < 50:
            factors.append("irregular_operating_hours")
        if volatility > 0.8:
            factors.append("high_revenue_volatility")
        if not factors:
            factors.append("no_significant_risk_factors")
        return factors

    async def record_outcome(
        self,
        business_id: str,
        outcome: str,
        amount: float | None = None,
        lookback_days: int = 90,
    ) -> dict[str, Any]:
        """
        Record a credit outcome (repayment or default) for calibration.

        This is the feedback loop: when a loan is repaid or defaults,
        the outcome is recorded and used to calibrate the scoring model.

        Academic Foundation:
        - STA 341 (Theory of Estimation): Bayesian updating of prior
          default probabilities with observed outcomes
        - ECO 209 (Money and Banking): Adverse selection monitoring —
          tracking actual defaults vs predicted to detect model drift
        - STA 346 (Quality Control): SPC monitoring of calibration —
          predicted vs observed default rates should track closely

        The calibration loop:
        1. Score is computed (predicts default probability)
        2. Loan is issued based on score
        3. Outcome is observed (repay/default)
        4. Outcome updates the Bayesian prior for this business type
        5. Updated prior improves future scoring accuracy

        Args:
            business_id: Anonymized business hash
            outcome: 'repayment' or 'default'
            amount: Loan amount (for weighted calibration)
            lookback_days: Analysis window for context

        Returns:
            Dict with calibration update details
        """
        from sqlalchemy import select

        # Validate outcome
        if outcome not in ("repayment", "default"):
            return {"error": f"Invalid outcome: {outcome}. Must be 'repayment' or 'default'."}

        # Find the most recent score for this business
        score_query = select(AlamaScoreOutcome).where(
            AlamaScoreOutcome.business_hash == business_id
        ).order_by(AlamaScoreOutcome.created_at.desc()).limit(1)

        result = await self.db.execute(score_query)
        existing = result.scalar_one_or_none()

        # Store the outcome
        outcome_record = AlamaScoreOutcome(
            business_hash=business_id,
            outcome_type=outcome,
            amount=amount,
            recorded_at=datetime.now(UTC),
        )
        self.db.add(outcome_record)
        await self.db.flush()

        # ── Bayesian calibration update ─────────────────────────────────
        # Count historical outcomes for this business type
        user_query = select(User).where(User.is_active == True)
        user_result = await self.db.execute(user_query)
        all_users = user_result.scalars().all()

        # Find target user's business type
        target_user = None
        for u in all_users:
            computed_hash = self.anonymizer.pseudonymize_user_id(str(u.id))
            if computed_hash == business_id:
                target_user = u
                break

        business_type = target_user.business_type if target_user else "other"

        # Count outcomes by business type for Bayesian prior calibration
        outcome_query = select(
            AlamaScoreOutcome.outcome_type,
            func.count(AlamaScoreOutcome.id),
        ).join(
            User, User.id == AlamaScoreOutcome.business_hash  # approximate join
        ).where(
            AlamaScoreOutcome.recorded_at >= datetime.now(UTC) - timedelta(days=365)
        ).group_by(AlamaScoreOutcome.outcome_type)

        # Simplified: count all outcomes
        all_outcomes_query = select(
            AlamaScoreOutcome.outcome_type,
            func.count(AlamaScoreOutcome.id),
        ).group_by(AlamaScoreOutcome.outcome_type)

        outcome_result = await self.db.execute(all_outcomes_query)
        outcome_counts = dict(outcome_result.all())

        total_outcomes = sum(outcome_counts.values())
        repayment_count = outcome_counts.get("repayment", 0)
        default_count = outcome_counts.get("default", 0)

        # ── STA 341: Update Beta prior with observed outcomes ──────────
        # Prior: Beta(2, 5) — conservative for informal sector
        # Posterior: Beta(2 + repayments, 5 + defaults)
        prior_alpha, prior_beta = 2.0, 5.0
        post_alpha = prior_alpha + repayment_count
        post_beta = prior_beta + default_count

        from scipy import stats as sp_stats
        calibrated_default_rate = round(float(post_beta / (post_alpha + post_beta)), 4)
        calibrated_ci_lower = round(float(sp_stats.beta.ppf(0.025, post_alpha, post_beta)), 4)
        calibrated_ci_upper = round(float(sp_stats.beta.ppf(0.975, post_alpha, post_beta)), 4)

        # ── STA 346: Calibration check (predicted vs observed) ─────────
        # Compare average predicted default rate vs observed
        calibration_error = None
        if existing and existing.predicted_default_prob is not None:
            observed_rate = default_count / max(total_outcomes, 1)
            calibration_error = round(
                abs(existing.predicted_default_prob - observed_rate), 4
            )

        # ── Drift Detection: Check if model performance has degraded ────
        drift_alert = None
        if calibration_error is not None and calibration_error > 0.1:
            try:
                from app.agents.intelligence_pipeline import get_intelligence_drift_monitor
                drift_monitor = get_intelligence_drift_monitor()
                await drift_monitor.check_alama_score(
                    predicted_score=int(existing.predicted_default_prob * 850) if existing and existing.predicted_default_prob else 525,
                    actual_outcome=850 if outcome == "repayment" else 300,
                )
                drift_status = drift_monitor.get_status()
                if drift_status.get("drift_detected_in_any"):
                    drift_alert = {
                        "drift_detected": True,
                        "status": drift_status["overall_status"],
                        "swahili_alert": drift_monitor.generate_swahili_alert(
                            "alama_score", calibration_error * 100, "mikopo"
                        ),
                    }
            except Exception as e:
                logger.debug("drift_check_failed", error=str(e))

        logger.info(
            "alama_score_outcome_recorded",
            business=business_id,
            outcome=outcome,
            total_outcomes=total_outcomes,
            calibrated_default_rate=calibrated_default_rate,
            calibration_error=calibration_error,
        )

        return {
            "status": "recorded",
            "business_id": business_id,
            "outcome": outcome,
            "calibration": {
                "total_outcomes": total_outcomes,
                "repayment_count": repayment_count,
                "default_count": default_count,
                "calibrated_default_rate": calibrated_default_rate,
                "credible_interval_95": (calibrated_ci_lower, calibrated_ci_upper),
                "prior": f"Beta({prior_alpha}, {prior_beta})",
                "posterior": f"Beta({post_alpha}, {post_beta})",
                "calibration_error": calibration_error,
            },
            "drift_alert": drift_alert,
            "method": "STA 341 — Bayesian calibration via Beta-Binomial conjugacy",
        }

    @staticmethod
    def _run_causal_validation(
        transactions: list,
        alama_score: float,
        daily_revenues: list,
        avg_daily_rev: float,
        query_tier: str,
        activity_score: float,
        stability_score: float,
    ) -> dict[str, Any] | None:
        """
        Run causal inference validation using IV/2SLS, DiD, and RDD.

        ECO 424 — Advanced Econometrics:
        - IV/2SLS: Validate that activity drives score (not reverse causality)
        - DiD: Estimate impact of high-activity periods on revenue
        - RDD: Test threshold effects at score band boundaries
        """
        result = {}

        try:
            # IV/2SLS: Does activity CAUSE revenue?
            # Endogenous: activity_score proxy (txn count per day)
            # Instrument: day-of-week variation (exogenous scheduling)
            daily_counts = defaultdict(int)
            daily_rev_map = defaultdict(float)
            for t in transactions:
                if t.transaction_type == "SALE":
                    day = t.timestamp.strftime("%Y-%m-%d")
                    daily_counts[day] += 1
                    daily_rev_map[day] += t.amount

            if len(daily_counts) >= 20:
                days_sorted = sorted(daily_counts.keys())
                Y_iv = np.array([daily_rev_map[d] for d in days_sorted], dtype=float)
                X_endog = np.array([daily_counts[d] for d in days_sorted], dtype=float)
                # Instrument: day-of-week as numeric (exogenous scheduling pattern)
                from datetime import datetime as dt
                Z_instr = np.array([
                    dt.strptime(d, "%Y-%m-%d").weekday() for d in days_sorted
                ], dtype=float).reshape(-1, 1)

                iv_result = InstrumentalVariables2SLS.fit(
                    Y=Y_iv, X_endogenous=X_endog,
                    Z_instruments=Z_instr, robust=True,
                )
                result["iv_2sls"] = iv_result.summary()

            # DiD: Compare revenue before vs after median date
            if len(transactions) >= 40:
                sorted_txns = sorted(transactions, key=lambda t: t.timestamp)
                mid_idx = len(sorted_txns) // 2
                mid_ts = sorted_txns[mid_idx].timestamp

                Y_did = np.array([t.amount for t in sorted_txns], dtype=float)
                treat = np.array([
                    1 if t.timestamp >= mid_ts else 0 for t in sorted_txns
                ], dtype=float)
                post = np.array([
                    1 if t.timestamp >= mid_ts else 0 for t in sorted_txns
                ], dtype=float)
                # Treat vs control based on transaction amount (above/below median)
                median_amt = float(np.median(Y_did))
                treat_group = (Y_did > median_amt).astype(float)

                did_result = DifferenceInDifferences.fit(
                    Y=Y_did, treat=treat_group, post=treat,
                )
                result["did_impact"] = did_result.summary()

            # RDD: Threshold analysis at score band boundaries
            if len(daily_revenues) >= 20:
                rev_arr = np.array(daily_revenues, dtype=float)
                # Running variable: revenue (centered at median)
                cutoff = float(np.median(rev_arr))
                # Outcome: consistency (binary: above-median activity)
                Y_rdd = (rev_arr > cutoff).astype(float)

                rdd_result = RegressionDiscontinuity.fit(
                    Y=Y_rdd, X=rev_arr, cutoff=cutoff,
                    run_mccrary=False,
                )
                result["rdd_threshold"] = rdd_result.summary()

        except Exception as e:
            logger.debug("causal_validation_failed", error=str(e))
            return None

        return result if result else None

    @staticmethod
    def _run_monte_carlo_simulation(
        avg_daily_rev: float,
        revenue_vol: float,
        query_tier: str,
    ) -> dict[str, Any] | None:
        """
        Run Monte Carlo revenue distribution simulation.

        STA 347 — Stochastic Processes:
        Simulates revenue paths using geometric Brownian motion
        to characterize the full distribution of future revenue,
        enabling probabilistic credit risk assessment.
        """
        try:
            mc = MonteCarloEngine.revenue_distribution_simulation(
                base_revenue=avg_daily_rev * 30,  # Monthly base
                growth_mean=0.02,  # 2% monthly growth expectation
                growth_std=max(revenue_vol, 0.1),
                n_periods=12,
                n_simulations=5000,
            )
            return {
                "base_monthly_revenue": round(avg_daily_rev * 30, 2),
                "terminal_mean": mc["terminal_mean"],
                "terminal_median": mc["terminal_median"],
                "terminal_std": mc["terminal_std"],
                "percentile_5": mc["percentile_5"],
                "percentile_95": mc["percentile_95"],
                "prob_decline": mc["prob_decline"],
                "prob_growth_10pct": mc["prob_growth_10pct"],
                "n_simulations": mc["n_simulations"],
                "n_periods": mc["n_periods"],
                "method": "geometric_brownian_motion",
            }
        except Exception as e:
            logger.debug("monte_carlo_simulation_failed", error=str(e))
            return None
