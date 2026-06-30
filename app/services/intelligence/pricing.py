"""
Pricing tiers for intelligence products.

Defines pricing for each product across buyer segments.
All prices in KES with USD equivalents.

Revenue Model (from Doc 18):
- Year 1: $310K → Year 5: $8.2M
- 4 buyer segments: FMCG, Government, Financial Institutions, NGOs
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TierPricing:
    """Pricing for a single tier."""

    tier: str
    price_monthly_kes: float
    price_monthly_usd: float
    features: List[str]
    refresh_frequency: str
    max_markets: Optional[int] = None
    api_queries_per_month: Optional[int] = None
    support_level: str = "email"


@dataclass
class ProductPricing:
    """Full pricing for a product across tiers."""

    product_name: str
    product_code: str
    buyer_segment: str
    tiers: List[TierPricing]
    one_time_price_kes: Optional[float] = None
    one_time_price_usd: Optional[float] = None
    per_query_price_usd: Optional[float] = None


# USD to KES rate (approximate)
USD_TO_KES = 155.0

# =========================================================================
# Soko Pulse Pricing
# =========================================================================

SOKO_PULSE_PRICING = ProductPricing(
    product_name="Soko Pulse — FMCG Demand Forecasting",
    product_code="soko_pulse",
    buyer_segment="FMCG",
    tiers=[
        TierPricing(
            tier="standard",
            price_monthly_kes=310_000,    # ~$2,000
            price_monthly_usd=2_000,
            features=[
                "5 markets, weekly updates",
                "Demand trend analysis",
                "Basic price intelligence",
                "Day-of-week patterns",
                "Monthly email reports",
            ],
            refresh_frequency="weekly",
            max_markets=5,
            api_queries_per_month=500,
            support_level="email",
        ),
        TierPricing(
            tier="premium",
            price_monthly_kes=775_000,    # ~$5,000
            price_monthly_usd=5_000,
            features=[
                "20 markets, daily updates",
                "Demand forecasting (4-week ahead)",
                "Full price intelligence",
                "Seasonal analysis",
                "Stockout frequency tracking",
                "API access",
                "Priority support",
            ],
            refresh_frequency="daily",
            max_markets=20,
            api_queries_per_month=5_000,
            support_level="priority",
        ),
        TierPricing(
            tier="enterprise",
            price_monthly_kes=1_860_000,  # ~$12,000
            price_monthly_usd=12_000,
            features=[
                "All markets, real-time updates",
                "Advanced demand forecasting",
                "Full price intelligence + alerts",
                "Competitive intelligence",
                "Custom reports",
                "Unlimited API access",
                "Dedicated account manager",
                "Performance bonus (up to $3K/mo)",
            ],
            refresh_frequency="real_time",
            max_markets=None,  # unlimited
            api_queries_per_month=None,  # unlimited
            support_level="dedicated",
        ),
    ],
)

# =========================================================================
# Biashara Pulse Pricing
# =========================================================================

BIASHARA_PULSE_PRICING = ProductPricing(
    product_name="Biashara Pulse — Government MSME Activity Index",
    product_code="biashara_pulse",
    buyer_segment="Government",
    tiers=[
        TierPricing(
            tier="standard",
            price_monthly_kes=385_000,    # ~$2,500/year → ~$208/mo per county
            price_monthly_usd=250,
            features=[
                "Single county coverage",
                "Monthly activity index",
                "Basic sector breakdown",
                "Quarterly PDF reports",
            ],
            refresh_frequency="monthly",
            max_markets=1,
            api_queries_per_month=100,
            support_level="email",
        ),
        TierPricing(
            tier="premium",
            price_monthly_kes=1_160_000,  # ~$7,500/year → ~$625/mo for 3 counties
            price_monthly_usd=750,
            features=[
                "Up to 5 counties",
                "Weekly activity index",
                "Full sector breakdown",
                "Business formation tracking",
                "Employment estimates",
                "API access",
            ],
            refresh_frequency="weekly",
            max_markets=5,
            api_queries_per_month=1_000,
            support_level="priority",
        ),
        TierPricing(
            tier="enterprise",
            price_monthly_kes=7_750_000,  # ~$50,000/year → ~$4,167/mo national
            price_monthly_usd=5_000,
            features=[
                "All 47 counties + national",
                "Daily activity indices",
                "Full analytics suite",
                "Policy impact simulation",
                "Custom dashboards",
                "Unlimited API access",
                "Dedicated government liaison",
            ],
            refresh_frequency="daily",
            max_markets=None,
            api_queries_per_month=None,
            support_level="dedicated",
        ),
    ],
)

# =========================================================================
# Alama Score Pricing
# =========================================================================

ALAMA_SCORE_PRICING = ProductPricing(
    product_name="Alama Score — Transaction-Based Credit Scoring",
    product_code="alama_score",
    buyer_segment="Financial Institutions",
    tiers=[
        TierPricing(
            tier="standard",
            price_monthly_kes=0,  # Per-query pricing
            price_monthly_usd=0,
            features=[
                "Basic score (300-850)",
                "Score band classification",
                "Activity score",
                "Stability index",
            ],
            refresh_frequency="on_demand",
            api_queries_per_month=10_000,
            support_level="email",
        ),
        TierPricing(
            tier="premium",
            price_monthly_kes=0,  # Per-query pricing
            price_monthly_usd=0,
            features=[
                "Full score with components",
                "Heckman-corrected score",
                "Risk indicators",
                "Peer comparison",
                "Recommended credit limit",
            ],
            refresh_frequency="on_demand",
            api_queries_per_month=50_000,
            support_level="priority",
        ),
        TierPricing(
            tier="enterprise",
            price_monthly_kes=0,  # Per-query pricing
            price_monthly_usd=0,
            features=[
                "Full profile with all signals",
                "Portfolio monitoring",
                "Batch scoring",
                "Custom risk models",
                "Real-time alerts",
                "Dedicated support",
            ],
            refresh_frequency="real_time",
            api_queries_per_month=None,
            support_level="dedicated",
        ),
    ],
    per_query_price_usd=0.05,  # Base price; tiers: basic=$0.05, enhanced=$0.15, full=$0.50
)

# Volume discounts for Alama Score
ALAMA_VOLUME_DISCOUNTS = {
    10_000: 0.08,   # 10K queries/mo → $0.08/query (small bank)
    50_000: 0.06,   # 50K queries/mo → $0.06/query (medium bank)
    200_000: 0.04,  # 200K queries/mo → $0.04/query (large bank)
    500_000: 0.03,  # 500K queries/mo → $0.03/query (Safaricom)
}

# Per-query pricing by tier
ALAMA_QUERY_PRICES = {
    "basic": 0.05,      # $0.05/query — basic score
    "enhanced": 0.15,   # $0.15/query — with Heckman correction
    "full": 0.50,       # $0.50/query — full profile
}

# =========================================================================
# Jamii Insights Pricing
# =========================================================================

JAMII_INSIGHTS_PRICING = ProductPricing(
    product_name="Jamii Insights — NGO Financial Inclusion",
    product_code="jamii_insights",
    buyer_segment="Development/NGO",
    tiers=[
        TierPricing(
            tier="standard",
            price_monthly_kes=310_000,    # ~$2,000 per study
            price_monthly_usd=2_000,
            features=[
                "Single region analysis",
                "Financial inclusion index",
                "Basic demographics",
                "PDF report",
            ],
            refresh_frequency="one_time",
            api_queries_per_month=100,
            support_level="email",
        ),
        TierPricing(
            tier="premium",
            price_monthly_kes=775_000,    # ~$5,000 per study
            price_monthly_usd=5_000,
            features=[
                "Multi-region analysis",
                "Impact measurement",
                "Barrier analysis",
                "Program evaluation",
                "API access",
            ],
            refresh_frequency="quarterly",
            api_queries_per_month=500,
            support_level="priority",
        ),
        TierPricing(
            tier="enterprise",
            price_monthly_kes=1_550_000,  # ~$10,000 per study
            price_monthly_usd=10_000,
            features=[
                "National coverage",
                "Full impact evaluation",
                "Custom surveys",
                "Longitudinal tracking",
                "Co-branded reports",
                "Unlimited API access",
                "Dedicated research support",
            ],
            refresh_frequency="monthly",
            api_queries_per_month=None,
            support_level="dedicated",
        ),
    ],
)

# =========================================================================
# Tax Base Estimation Pricing
# =========================================================================

TAX_BASE_PRICING = ProductPricing(
    product_name="Tax Base Estimation — Government Revenue",
    product_code="tax_base_estimation",
    buyer_segment="Government (KRA/County)",
    tiers=[
        TierPricing(
            tier="standard",
            price_monthly_kes=2_325_000,  # ~$15,000/year
            price_monthly_usd=1_500,
            features=[
                "Single county estimation",
                "VAT base analysis",
                "Quarterly reports",
                "Basic sector breakdown",
            ],
            refresh_frequency="quarterly",
            max_markets=1,
            api_queries_per_month=100,
            support_level="email",
        ),
        TierPricing(
            tier="premium",
            price_monthly_kes=5_425_000,  # ~$35,000/year
            price_monthly_usd=3_500,
            features=[
                "Multi-county estimation",
                "Full tax gap analysis",
                "Monthly reports",
                "Sector breakdown",
                "API access",
            ],
            refresh_frequency="monthly",
            max_markets=10,
            api_queries_per_month=500,
            support_level="priority",
        ),
        TierPricing(
            tier="enterprise",
            price_monthly_kes=15_500_000, # ~$100,000/year
            price_monthly_usd=10_000,
            features=[
                "National coverage",
                "Full tax intelligence suite",
                "Weekly updates",
                "Custom dashboards",
                "Policy simulation",
                "Unlimited API access",
                "Dedicated government liaison",
            ],
            refresh_frequency="weekly",
            max_markets=None,
            api_queries_per_month=None,
            support_level="dedicated",
        ),
    ],
)

# =========================================================================
# Distribution Gap Pricing
# =========================================================================

DISTRIBUTION_GAP_PRICING = ProductPricing(
    product_name="Distribution Gap Analysis — FMCG Market Coverage",
    product_code="distribution_gap",
    buyer_segment="FMCG Distribution",
    tiers=[
        TierPricing(
            tier="standard",
            price_monthly_kes=0,  # One-time pricing
            price_monthly_usd=0,
            features=[
                "Single product category",
                "Coverage analysis",
                "Gap market identification",
                "PDF report",
            ],
            refresh_frequency="one_time",
            api_queries_per_month=100,
            support_level="email",
        ),
        TierPricing(
            tier="premium",
            price_monthly_kes=0,  # One-time + monitoring
            price_monthly_usd=0,
            features=[
                "Multi-category analysis",
                "Competitive landscape",
                "ROI recommendations",
                "Quarterly monitoring",
                "API access",
            ],
            refresh_frequency="quarterly",
            api_queries_per_month=500,
            support_level="priority",
        ),
        TierPricing(
            tier="enterprise",
            price_monthly_kes=0,  # Custom pricing
            price_monthly_usd=0,
            features=[
                "Full market coverage",
                "Real-time gap monitoring",
                "Route optimization",
                "Custom dashboards",
                "Unlimited API access",
                "Dedicated account manager",
            ],
            refresh_frequency="weekly",
            api_queries_per_month=None,
            support_level="dedicated",
        ),
    ],
    one_time_price_kes=2_325_000,   # $15,000 basic
    one_time_price_usd=15_000,
)

# One-time pricing tiers for Distribution Gap
DISTRIBUTION_GAP_ONE_TIME = {
    "basic": {"kes": 2_325_000, "usd": 15_000},     # Single category
    "standard": {"kes": 3_875_000, "usd": 25_000},   # Multi-category
    "comprehensive": {"kes": 4_650_000, "usd": 30_000},  # Full analysis
}
# Monitoring add-on: $3,000/month
DISTRIBUTION_MONITORING_MONTHLY_KES = 465_000
DISTRIBUTION_MONITORING_MONTHLY_USD = 3_000


# =========================================================================
# Helper Functions
# =========================================================================


def get_product_pricing(product_code: str) -> Optional[ProductPricing]:
    """Get pricing configuration for a product."""
    pricing_map = {
        "soko_pulse": SOKO_PULSE_PRICING,
        "biashara_pulse": BIASHARA_PULSE_PRICING,
        "alama_score": ALAMA_SCORE_PRICING,
        "jamii_insights": JAMII_INSIGHTS_PRICING,
        "tax_base_estimation": TAX_BASE_PRICING,
        "distribution_gap": DISTRIBUTION_GAP_PRICING,
    }
    return pricing_map.get(product_code)


def get_alama_query_price(query_tier: str, volume: int = 0) -> float:
    """
    Get per-query price for Alama Score with volume discounts.

    Args:
        query_tier: basic, enhanced, or full
        volume: Monthly query volume

    Returns:
        Price per query in USD
    """
    base_price = ALAMA_QUERY_PRICES.get(query_tier, 0.05)

    # Apply volume discount
    if volume >= 500_000:
        return min(base_price, 0.03)
    elif volume >= 200_000:
        return min(base_price, 0.04)
    elif volume >= 50_000:
        return min(base_price, 0.06)
    elif volume >= 10_000:
        return min(base_price, 0.08)

    return base_price


def calculate_monthly_cost(
    product_code: str,
    tier: str,
    volume: int = 0,
) -> Dict[str, float]:
    """
    Calculate monthly cost for a product/tier combination.

    Returns:
        Dict with 'kes' and 'usd' amounts
    """
    pricing = get_product_pricing(product_code)
    if not pricing:
        return {"kes": 0, "usd": 0}

    # Per-query products (Alama Score)
    if product_code == "alama_score":
        price_per_query = get_alama_query_price(tier, volume)
        return {
            "kes": price_per_query * volume * USD_TO_KES,
            "usd": price_per_query * volume,
        }

    # Tier-based products
    for t in pricing.tiers:
        if t.tier == tier:
            return {
                "kes": t.price_monthly_kes,
                "usd": t.price_monthly_usd,
            }

    return {"kes": 0, "usd": 0}
