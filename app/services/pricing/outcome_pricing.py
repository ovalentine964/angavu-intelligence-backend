"""
Outcome-Based Pricing Engine.

Pricing model where buyers pay based on the VALUE they receive,
not a flat subscription. This aligns Biashara Intelligence's
incentives with buyer outcomes.

Products (from product-pricing-strategy.md):

1. Alama Score: 0.5–1.5% of loan value
   → Bank pays when loans are APPROVED based on Alama scores
   → Higher score accuracy = higher approval rate = more revenue

2. Tax Base: 2–5% of incremental tax revenue
   → KRA/county pays based on NEW tax revenue collected
   → Biashara identifies untaxed businesses → KRA collects → Biashara gets %

3. Distribution Gap: 1–3% of first-year revenue from new markets
   → FMCG pays based on revenue from markets Biashara identified
   → Biashara finds the gap → FMCG enters → Biashara gets % of new revenue

4. Soko Pulse: +30% bonus for >90% forecast accuracy
   → Base subscription + accuracy bonus
   → If forecast is >90% accurate, buyer pays 30% premium

Methodology:
- Alama: Outcome = approved loan value × approval_rate × quality_multiplier
- Tax Base: Outcome = incremental_revenue × collection_rate × compliance_rate
- Distribution Gap: Outcome = new_market_revenue × margin × expansion_success
- Soko Pulse: Outcome = base_price × (1 + accuracy_bonus)

Each product has:
- Base fee (minimum revenue floor)
- Outcome component (% of value created)
- Cap (maximum per period)
- Floor (minimum per period)
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pricing Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OutcomePricingConfig:
    """Configuration for outcome-based pricing of a product."""

    product_code: str
    product_name: str
    buyer_segment: str
    outcome_metric: str
    outcome_unit: str
    rate_min_pct: float
    rate_max_pct: float
    base_fee_monthly_usd: float
    cap_monthly_usd: float
    floor_monthly_usd: float
    accuracy_bonus_pct: float = 0.0
    accuracy_threshold_pct: float = 0.0
    description: str = ""


# Product pricing configurations
PRICING_CONFIGS = {
    "alama_score": OutcomePricingConfig(
        product_code="alama_score",
        product_name="Alama Score — Transaction-Based Credit Scoring",
        buyer_segment="Financial Institutions",
        outcome_metric="approved_loan_value",
        outcome_unit="USD",
        rate_min_pct=0.5,
        rate_max_pct=1.5,
        base_fee_monthly_usd=500.0,
        cap_monthly_usd=50_000.0,
        floor_monthly_usd=500.0,
        description=(
            "Bank pays 0.5–1.5% of loan value when loans are approved "
            "based on Alama scores. Rate depends on score tier and volume."
        ),
    ),
    "tax_base": OutcomePricingConfig(
        product_code="tax_base",
        product_name="Tax Base Estimation — Government Revenue Intelligence",
        buyer_segment="Government (KRA / County)",
        outcome_metric="incremental_tax_revenue",
        outcome_unit="KES",
        rate_min_pct=2.0,
        rate_max_pct=5.0,
        base_fee_monthly_usd=1_500.0,
        cap_monthly_usd=100_000.0,
        floor_monthly_usd=1_500.0,
        description=(
            "KRA/county pays 2–5% of incremental tax revenue collected "
            "from businesses identified by Biashara as previously untaxed."
        ),
    ),
    "distribution_gap": OutcomePricingConfig(
        product_code="distribution_gap",
        product_name="Distribution Gap Analysis — FMCG Market Coverage",
        buyer_segment="FMCG Companies",
        outcome_metric="first_year_new_market_revenue",
        outcome_unit="USD",
        rate_min_pct=1.0,
        rate_max_pct=3.0,
        base_fee_monthly_usd=5_000.0,
        cap_monthly_usd=200_000.0,
        floor_monthly_usd=5_000.0,
        description=(
            "FMCG pays 1–3% of first-year revenue from new markets "
            "identified by Biashara's distribution gap analysis."
        ),
    ),
    "soko_pulse": OutcomePricingConfig(
        product_code="soko_pulse",
        product_name="Soko Pulse — FMCG Demand Forecasting",
        buyer_segment="FMCG Companies",
        outcome_metric="forecast_accuracy",
        outcome_unit="percentage",
        rate_min_pct=0.0,
        rate_max_pct=30.0,
        base_fee_monthly_usd=2_000.0,
        cap_monthly_usd=15_000.0,
        floor_monthly_usd=2_000.0,
        accuracy_bonus_pct=30.0,
        accuracy_threshold_pct=90.0,
        description=(
            "Base subscription + 30% accuracy bonus when forecast "
            "accuracy exceeds 90%. Bonus applied to monthly invoice."
        ),
    ),
}


@dataclass
class OutcomeCalculation:
    """Result of an outcome-based pricing calculation."""

    product_code: str
    product_name: str
    buyer_segment: str
    outcome_metric: str
    outcome_value: float
    outcome_unit: str
    rate_applied_pct: float
    outcome_fee_usd: float
    base_fee_usd: float
    total_fee_usd: float
    cap_applied: bool
    floor_applied: bool
    accuracy_bonus_usd: float = 0.0
    tier: str = "standard"
    calculation_notes: str = ""


class OutcomePricingEngine:
    """
    Outcome-Based Pricing Engine.

    Calculates fees based on the VALUE delivered to buyers,
    not flat subscriptions. This aligns incentives:
    - Biashara gets paid more when buyers get more value
    - Buyers pay less if the product doesn't deliver

    Each product has a unique outcome metric:
    - Alama: Approved loan value
    - Tax Base: Incremental tax revenue
    - Distribution Gap: New market revenue
    - Soko Pulse: Forecast accuracy (bonus model)
    """

    @staticmethod
    def calculate_alama_pricing(
        approved_loan_value_usd: float,
        score_tier: str = "standard",
        volume_discount_pct: float = 0.0,
    ) -> OutcomeCalculation:
        """
        Calculate Alama Score outcome-based pricing.

        The bank pays when loans are APPROVED based on Alama scores.
        Rate scales with tier:
        - Basic ($0.05/query): 0.5% of loan value
        - Enhanced ($0.15/query): 1.0% of loan value
        - Full ($0.50/query): 1.5% of loan value

        Args:
            approved_loan_value_usd: Total value of loans approved using Alama
            score_tier: basic, enhanced, or full
            volume_discount_pct: Volume discount (0–30%)

        Returns:
            OutcomeCalculation with fee breakdown
        """
        config = PRICING_CONFIGS["alama_score"]

        # Rate by tier
        tier_rates = {
            "basic": 0.5,
            "enhanced": 1.0,
            "full": 1.5,
        }
        base_rate = tier_rates.get(score_tier, 0.5)

        # Apply volume discount
        effective_rate = base_rate * (1 - volume_discount_pct / 100)

        # Outcome fee
        outcome_fee = approved_loan_value_usd * effective_rate / 100

        # Apply floor and cap
        floor_applied = outcome_fee < config.floor_monthly_usd
        cap_applied = outcome_fee > config.cap_monthly_usd

        total_fee = max(config.floor_monthly_usd, min(outcome_fee, config.cap_monthly_usd))

        return OutcomeCalculation(
            product_code="alama_score",
            product_name=config.product_name,
            buyer_segment=config.buyer_segment,
            outcome_metric="approved_loan_value_usd",
            outcome_value=approved_loan_value_usd,
            outcome_unit="USD",
            rate_applied_pct=round(effective_rate, 2),
            outcome_fee_usd=round(outcome_fee, 2),
            base_fee_usd=config.base_fee_monthly_usd,
            total_fee_usd=round(total_fee, 2),
            cap_applied=cap_applied,
            floor_applied=floor_applied,
            tier=score_tier,
            calculation_notes=(
                f"Base rate: {base_rate}% ({score_tier} tier), "
                f"Volume discount: {volume_discount_pct}%, "
                f"Effective rate: {effective_rate:.2f}%"
            ),
        )

    @staticmethod
    def calculate_tax_base_pricing(
        incremental_tax_revenue_kes: float,
        collection_rate_pct: float = 100.0,
        county: Optional[str] = None,
    ) -> OutcomeCalculation:
        """
        Calculate Tax Base outcome-based pricing.

        KRA/county pays 2–5% of incremental tax revenue collected
        from businesses identified by Biashara. Rate depends on:
        - Collection rate (how much of identified tax was actually collected)
        - Volume (higher volume = lower rate)

        Args:
            incremental_tax_revenue_kes: New tax revenue from identified businesses
            collection_rate_pct: % of identified tax actually collected (0–100)
            county: Optional county for localized pricing

        Returns:
            OutcomeCalculation with fee breakdown
        """
        config = PRICING_CONFIGS["tax_base"]

        # Rate scales with collection efficiency
        # Lower collection rate = lower rate (Biashara's identification was less accurate)
        if collection_rate_pct >= 80:
            rate = 5.0  # High collection → high rate
        elif collection_rate_pct >= 50:
            rate = 3.5
        elif collection_rate_pct >= 20:
            rate = 2.5
        else:
            rate = 2.0  # Low collection → minimum rate

        # Convert to USD for consistency
        kes_to_usd = 1 / 155.0
        incremental_usd = incremental_tax_revenue_kes * kes_to_usd

        outcome_fee = incremental_usd * rate / 100

        floor_applied = outcome_fee < config.floor_monthly_usd
        cap_applied = outcome_fee > config.cap_monthly_usd

        total_fee = max(config.floor_monthly_usd, min(outcome_fee, config.cap_monthly_usd))

        return OutcomeCalculation(
            product_code="tax_base",
            product_name=config.product_name,
            buyer_segment=config.buyer_segment,
            outcome_metric="incremental_tax_revenue_kes",
            outcome_value=incremental_tax_revenue_kes,
            outcome_unit="KES",
            rate_applied_pct=rate,
            outcome_fee_usd=round(outcome_fee, 2),
            base_fee_usd=config.base_fee_monthly_usd,
            total_fee_usd=round(total_fee, 2),
            cap_applied=cap_applied,
            floor_applied=floor_applied,
            calculation_notes=(
                f"Collection rate: {collection_rate_pct}%, "
                f"Rate: {rate}%, "
                f"Incremental revenue: KES {incremental_tax_revenue_kes:,.0f}"
            ),
        )

    @staticmethod
    def calculate_distribution_gap_pricing(
        first_year_new_market_revenue_usd: float,
        margin_pct: float = 25.0,
        expansion_success_pct: float = 100.0,
    ) -> OutcomeCalculation:
        """
        Calculate Distribution Gap outcome-based pricing.

        FMCG pays 1–3% of first-year revenue from markets identified
        by Biashara's gap analysis. Rate depends on:
        - Margin (higher margin products = higher rate)
        - Expansion success (did the market entry succeed?)

        Args:
            first_year_new_market_revenue_usd: Revenue from new markets
            margin_pct: Product margin (affects rate)
            expansion_success_pct: Success rate of market entry (0–100)

        Returns:
            OutcomeCalculation with fee breakdown
        """
        config = PRICING_CONFIGS["distribution_gap"]

        # Rate scales with margin and success
        if margin_pct >= 40 and expansion_success_pct >= 80:
            rate = 3.0  # High margin, high success
        elif margin_pct >= 25 and expansion_success_pct >= 50:
            rate = 2.0
        else:
            rate = 1.0  # Low margin or low success

        outcome_fee = first_year_new_market_revenue_usd * rate / 100

        floor_applied = outcome_fee < config.floor_monthly_usd
        cap_applied = outcome_fee > config.cap_monthly_usd

        total_fee = max(config.floor_monthly_usd, min(outcome_fee, config.cap_monthly_usd))

        return OutcomeCalculation(
            product_code="distribution_gap",
            product_name=config.product_name,
            buyer_segment=config.buyer_segment,
            outcome_metric="first_year_new_market_revenue_usd",
            outcome_value=first_year_new_market_revenue_usd,
            outcome_unit="USD",
            rate_applied_pct=rate,
            outcome_fee_usd=round(outcome_fee, 2),
            base_fee_usd=config.base_fee_monthly_usd,
            total_fee_usd=round(total_fee, 2),
            cap_applied=cap_applied,
            floor_applied=floor_applied,
            calculation_notes=(
                f"Margin: {margin_pct}%, "
                f"Expansion success: {expansion_success_pct}%, "
                f"Rate: {rate}%"
            ),
        )

    @staticmethod
    def calculate_soko_pulse_pricing(
        base_monthly_fee_usd: float,
        forecast_accuracy_pct: float,
    ) -> OutcomeCalculation:
        """
        Calculate Soko Pulse outcome-based pricing (bonus model).

        Base subscription + 30% bonus when forecast accuracy > 90%.

        Args:
            base_monthly_fee_usd: Base subscription fee
            forecast_accuracy_pct: Measured forecast accuracy (0–100)

        Returns:
            OutcomeCalculation with fee breakdown
        """
        config = PRICING_CONFIGS["soko_pulse"]

        # Accuracy bonus
        bonus_usd = 0.0
        if forecast_accuracy_pct >= config.accuracy_threshold_pct:
            bonus_usd = base_monthly_fee_usd * config.accuracy_bonus_pct / 100

        total_fee = base_monthly_fee_usd + bonus_usd

        return OutcomeCalculation(
            product_code="soko_pulse",
            product_name=config.product_name,
            buyer_segment=config.buyer_segment,
            outcome_metric="forecast_accuracy_pct",
            outcome_value=forecast_accuracy_pct,
            outcome_unit="percentage",
            rate_applied_pct=config.accuracy_bonus_pct if bonus_usd > 0 else 0.0,
            outcome_fee_usd=round(bonus_usd, 2),
            base_fee_usd=base_monthly_fee_usd,
            total_fee_usd=round(total_fee, 2),
            cap_applied=False,
            floor_applied=False,
            accuracy_bonus_usd=round(bonus_usd, 2),
            calculation_notes=(
                f"Forecast accuracy: {forecast_accuracy_pct}%, "
                f"Threshold: {config.accuracy_threshold_pct}%, "
                f"Bonus: {'applied' if bonus_usd > 0 else 'not met'}"
            ),
        )

    @classmethod
    def calculate(
        cls,
        product: str,
        client_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generic pricing calculator — routes to product-specific logic.

        Args:
            product: Product code (alama_score, tax_base, distribution_gap, soko_pulse)
            client_id: Optional client identifier
            **kwargs: Product-specific parameters

        Returns:
            Pricing calculation result dict
        """
        if product not in PRICING_CONFIGS:
            return {
                "error": f"Unknown product: {product}",
                "available_products": list(PRICING_CONFIGS.keys()),
            }

        config = PRICING_CONFIGS[product]

        if product == "alama_score":
            result = cls.calculate_alama_pricing(
                approved_loan_value_usd=kwargs.get("approved_loan_value_usd", 0),
                score_tier=kwargs.get("score_tier", "standard"),
                volume_discount_pct=kwargs.get("volume_discount_pct", 0),
            )
        elif product == "tax_base":
            result = cls.calculate_tax_base_pricing(
                incremental_tax_revenue_kes=kwargs.get("incremental_tax_revenue_kes", 0),
                collection_rate_pct=kwargs.get("collection_rate_pct", 100),
                county=kwargs.get("county"),
            )
        elif product == "distribution_gap":
            result = cls.calculate_distribution_gap_pricing(
                first_year_new_market_revenue_usd=kwargs.get("first_year_new_market_revenue_usd", 0),
                margin_pct=kwargs.get("margin_pct", 25),
                expansion_success_pct=kwargs.get("expansion_success_pct", 100),
            )
        elif product == "soko_pulse":
            result = cls.calculate_soko_pulse_pricing(
                base_monthly_fee_usd=kwargs.get("base_monthly_fee_usd", 2000),
                forecast_accuracy_pct=kwargs.get("forecast_accuracy_pct", 0),
            )
        else:
            return {"error": f"Pricing not implemented for {product}"}

        # Convert to dict
        return {
            "product": result.product_code,
            "product_name": result.product_name,
            "buyer_segment": result.buyer_segment,
            "client_id": client_id,
            "outcome_metric": result.outcome_metric,
            "outcome_value": result.outcome_value,
            "outcome_unit": result.outcome_unit,
            "rate_applied_pct": result.rate_applied_pct,
            "outcome_fee_usd": result.outcome_fee_usd,
            "base_fee_usd": result.base_fee_usd,
            "total_fee_usd": result.total_fee_usd,
            "total_fee_kes": round(result.total_fee_usd * 155, 2),
            "cap_applied": result.cap_applied,
            "floor_applied": result.floor_applied,
            "accuracy_bonus_usd": result.accuracy_bonus_usd,
            "tier": result.tier,
            "calculation_notes": result.calculation_notes,
            "pricing_model": "outcome_based",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def get_pricing_config(product: str) -> Optional[Dict[str, Any]]:
        """Get pricing configuration for a product."""
        config = PRICING_CONFIGS.get(product)
        if not config:
            return None

        return {
            "product_code": config.product_code,
            "product_name": config.product_name,
            "buyer_segment": config.buyer_segment,
            "outcome_metric": config.outcome_metric,
            "outcome_unit": config.outcome_unit,
            "rate_range_pct": f"{config.rate_min_pct}–{config.rate_max_pct}%",
            "base_fee_monthly_usd": config.base_fee_monthly_usd,
            "cap_monthly_usd": config.cap_monthly_usd,
            "floor_monthly_usd": config.floor_monthly_usd,
            "accuracy_bonus_pct": config.accuracy_bonus_pct,
            "accuracy_threshold_pct": config.accuracy_threshold_pct,
            "description": config.description,
        }

    @staticmethod
    def get_all_pricing() -> Dict[str, Any]:
        """Get all outcome-based pricing configurations."""
        return {
            "pricing_model": "outcome_based",
            "description": "Pay for value received, not flat subscriptions",
            "products": {
                code: OutcomePricingEngine.get_pricing_config(code)
                for code in PRICING_CONFIGS
            },
            "currency": "USD",
            "kes_exchange_rate": 155.0,
        }
