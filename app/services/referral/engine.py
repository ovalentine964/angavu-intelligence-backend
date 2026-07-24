"""
Referral Engine — Match workers to financial products.

Core matching logic that considers:
  - Worker type (mama mboga, boda boda, dukawallah, etc.)
  - Alama Score range
  - Business metrics (revenue, margin, age)
  - Regional availability
  - Product suitability

The engine maintains a registry of financial partners and their products,
and generates referral links with tracking codes for attribution.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from .models import (
    CommissionType,
    FinancialPartner,
    ProductCategory,
    ProductMatch,
    ReferralStatus,
)

logger = structlog.get_logger(__name__)


# ── Partner Registry ─────────────────────────────────────────────────────────
# In production, this would be stored in the database.
# Here we define the default partner catalog.

DEFAULT_PARTNERS: list[FinancialPartner] = [
    FinancialPartner(
        partner_id="tala_ke",
        name="Tala",
        name_sw="Tala",
        product_category=ProductCategory.LOAN,
        products=[
            {
                "product_id": "tala_working_capital",
                "name": "Tala Business Loan",
                "name_sw": "Mkopo wa Tala",
                "max_amount_kes": 50000,
                "term_days": 90,
                "rate_pct": 15.0,
                "description": "Quick working capital loan for small businesses",
                "description_sw": "Mkopo wa haraka wa mtaji kwa biashara ndogo",
            },
        ],
        commission_structure={
            "type": CommissionType.PERCENTAGE_OF_AMOUNT,
            "rate": 0.02,  # 2%
            "clawback_period_days": 90,
            "clawback_on_default": True,
        },
        min_score_requirement=400,
        supported_worker_types=["all"],
        supported_regions=["all"],
    ),
    FinancialPartner(
        partner_id="branch_ke",
        name="Branch",
        name_sw="Branch",
        product_category=ProductCategory.LOAN,
        products=[
            {
                "product_id": "branch_sme_loan",
                "name": "Branch SME Loan",
                "name_sw": "Mkopo wa Branch kwa Biashara",
                "max_amount_kes": 100000,
                "term_days": 180,
                "rate_pct": 12.0,
                "description": "Medium-term business expansion loan",
                "description_sw": "Mkopo wa muda wa kati wa kupanua biashara",
            },
        ],
        commission_structure={
            "type": CommissionType.PERCENTAGE_OF_AMOUNT,
            "rate": 0.025,  # 2.5%
            "clawback_period_days": 180,
            "clawback_on_default": True,
        },
        min_score_requirement=550,
        supported_worker_types=["trader", "service", "manufacturing"],
        supported_regions=["all"],
    ),
    FinancialPartner(
        partner_id="jubilee_insurance",
        name="Jubilee Insurance",
        name_sw="Bima ya Jubilee",
        product_category=ProductCategory.INSURANCE,
        products=[
            {
                "product_id": "jubilee_biashara_cover",
                "name": "Biashara Insurance Cover",
                "name_sw": "Bima ya Biashara",
                "premium_annual_kes": 5000,
                "coverage_kes": 200000,
                "description": "Business insurance covering theft, fire, and liability",
                "description_sw": "Bima ya biashara inayofunika wizi, moto, na dhima",
            },
        ],
        commission_structure={
            "type": CommissionType.PERCENTAGE_OF_PREMIUM,
            "rate": 0.20,  # 20% of first-year premium
            "recurring_rate": 0.05,  # 5% renewal commission
            "clawback_period_days": 365,
        },
        min_score_requirement=350,
        supported_worker_types=["all"],
        supported_regions=["all"],
    ),
    FinancialPartner(
        partner_id="m_shwari",
        name="M-Shwari",
        name_sw="M-Shwari",
        product_category=ProductCategory.SAVINGS,
        products=[
            {
                "product_id": "mshwari_lock_savings",
                "name": "M-Shwari Lock Savings",
                "name_sw": "Akiba ya M-Shwari",
                "description": "Lock savings account with competitive interest",
                "description_sw": "Akaunti ya akiba yenye riba nzuri",
            },
        ],
        commission_structure={
            "type": CommissionType.FLAT_FEE,
            "flat_fee_kes": 50,
            "min_transactions": 3,
        },
        min_score_requirement=300,
        supported_worker_types=["all"],
        supported_regions=["all"],
    ),
    FinancialPartner(
        partner_id="mkopa",
        name="M-KOPA",
        name_sw="M-KOPA",
        product_category=ProductCategory.EQUIPMENT_FINANCING,
        products=[
            {
                "product_id": "mkopa_solar",
                "name": "M-KOPA Solar",
                "name_sw": "Jua la M-KOPA",
                "financed_amount_kes": 15000,
                "daily_payment_kes": 100,
                "term_days": 365,
                "description": "Solar power system with daily pay-as-you-go",
                "description_sw": "Mfumo wa nguvu za jua na malipo ya kila siku",
            },
            {
                "product_id": "mkopa_smartphone",
                "name": "M-KOPA Smartphone",
                "name_sw": "Simu ya M-KOPA",
                "financed_amount_kes": 12000,
                "daily_payment_kes": 80,
                "term_days": 365,
                "description": "Smartphone financing for digital access",
                "description_sw": "Ufadhili wa simu ya kisasa",
            },
        ],
        commission_structure={
            "type": CommissionType.PERCENTAGE_OF_AMOUNT,
            "rate": 0.03,  # 3%
            "clawback_period_days": 180,
        },
        min_score_requirement=350,
        supported_worker_types=["all"],
        supported_regions=["all"],
    ),
    FinancialPartner(
        partner_id="kwara_sacco",
        name="Kwara SACCO",
        name_sw="SACCO ya Kwara",
        product_category=ProductCategory.GROUP_LENDING,
        products=[
            {
                "product_id": "kwara_group_loan",
                "name": "Kwara Group Loan",
                "name_sw": "Mkopo wa Kikundi cha Kwara",
                "max_amount_kes": 30000,
                "term_days": 120,
                "rate_pct": 18.0,
                "description": "Group lending with social collateral",
                "description_sw": "Mkopo wa kikundi na dhamana ya kijamii",
            },
        ],
        commission_structure={
            "type": CommissionType.PERCENTAGE_OF_AMOUNT,
            "rate": 0.015,  # 1.5%
            "clawback_period_days": 120,
        },
        min_score_requirement=300,
        supported_worker_types=["trader", "agriculture"],
        supported_regions=["all"],
    ),
]


class ReferralEngine:
    """
    Match workers to financial products and generate referral links.

    Usage:
        engine = ReferralEngine()
        matches = engine.match_products(
            worker_type="mama_mboga",
            alama_score=650,
            monthly_revenue=45000,
            business_age_months=18,
            region="nairobi",
        )
    """

    def __init__(self, partners: list[FinancialPartner] | None = None):
        self.partners = partners or DEFAULT_PARTNERS
        self._partner_map = {p.partner_id: p for p in self.partners}

    def match_products(
        self,
        worker_type: str,
        alama_score: int,
        monthly_revenue: float,
        business_age_months: int,
        profit_margin: float = 0.0,
        region: str = "all",
        product_categories: list[str] | None = None,
        limit: int = 5,
    ) -> list[ProductMatch]:
        """
        Match a worker to suitable financial products.

        Considers:
        1. Worker type compatibility
        2. Alama Score eligibility
        3. Revenue-based amount eligibility
        4. Regional availability
        5. Product category preference

        Args:
            worker_type: Type of worker (mama_mboga, boda_boda, etc.)
            alama_score: Worker's Alama Score (0-1000)
            monthly_revenue: Average monthly revenue in KES
            business_age_months: How old the business is
            profit_margin: Current profit margin (0-1)
            region: Worker's region
            product_categories: Filter by specific categories (None = all)
            limit: Maximum number of matches to return

        Returns:
            List of ProductMatch objects sorted by match_score descending.
        """
        matches = []

        for partner in self.partners:
            if not partner.is_active:
                continue

            # Check region
            if "all" not in partner.supported_regions:
                if region.lower() not in [r.lower() for r in partner.supported_regions]:
                    continue

            # Check worker type
            if "all" not in partner.supported_worker_types:
                if worker_type not in partner.supported_worker_types:
                    continue

            # Check category filter
            if product_categories:
                if partner.product_category.value not in product_categories:
                    continue

            for product in partner.products:
                match = self._evaluate_product(
                    partner=partner,
                    product=product,
                    worker_type=worker_type,
                    alama_score=alama_score,
                    monthly_revenue=monthly_revenue,
                    business_age_months=business_age_months,
                    profit_margin=profit_margin,
                )
                if match:
                    matches.append(match)

        # Sort by match score
        matches.sort(key=lambda m: m.match_score, reverse=True)
        return matches[:limit]

    def _evaluate_product(
        self,
        partner: FinancialPartner,
        product: dict[str, Any],
        worker_type: str,
        alama_score: int,
        monthly_revenue: float,
        business_age_months: int,
        profit_margin: float,
    ) -> ProductMatch | None:
        """Evaluate a single product for a worker."""
        ineligibility_reasons = []
        match_reasons = []
        match_reasons_sw = []

        # 1. Score eligibility
        if alama_score < partner.min_score_requirement:
            ineligibility_reasons.append(
                f"Alama Score {alama_score} below minimum {partner.min_score_requirement}"
            )

        # 2. Calculate match score
        score = 0.0

        # Score fit (0-0.30)
        score_diff = alama_score - partner.min_score_requirement
        if score_diff >= 200:
            score += 0.30
            match_reasons.append("Excellent score fit")
            match_reasons_sw.append("Alama Score inafaa vizuri sana")
        elif score_diff >= 100:
            score += 0.25
            match_reasons.append("Strong score fit")
            match_reasons_sw.append("Alama Score inafaa vizuri")
        elif score_diff >= 0:
            score += 0.15
            match_reasons.append("Meets minimum score")
            match_reasons_sw.append("Inakidhi kiwango cha chini cha alama")
        else:
            score += 0.05

        # Revenue fit (0-0.25)
        max_amount = product.get("max_amount_kes", product.get("financed_amount_kes", 0))
        if max_amount and monthly_revenue > 0:
            # Ideal: loan is 1-3x monthly revenue
            ratio = max_amount / monthly_revenue
            if 1 <= ratio <= 3:
                score += 0.25
                match_reasons.append("Loan amount fits revenue level")
                match_reasons_sw.append("Kiasi cha mkopo kinafaa mapato yako")
            elif ratio < 1:
                score += 0.20
                match_reasons.append("Conservative loan amount")
                match_reasons_sw.append("Kiasi kidogo cha mkopo")
            elif ratio <= 5:
                score += 0.15
            else:
                score += 0.05
        else:
            score += 0.15  # Default for non-amount products

        # Business age fit (0-0.15)
        if business_age_months >= 12:
            score += 0.15
            match_reasons.append("Established business")
            match_reasons_sw.append("Biashara imara")
        elif business_age_months >= 6:
            score += 0.10
        elif business_age_months >= 3:
            score += 0.05
        else:
            score += 0.02

        # Profit margin fit (0-0.15)
        if profit_margin >= 0.25:
            score += 0.15
            match_reasons.append("Strong profit margin")
            match_reasons_sw.append("Faida nzuri")
        elif profit_margin >= 0.15:
            score += 0.10
        elif profit_margin >= 0.05:
            score += 0.05
        else:
            score += 0.02

        # Worker type bonus (0-0.15)
        type_bonuses = {
            ("mama_mboga", ProductCategory.LOAN): 0.10,
            ("mama_mboga", ProductCategory.INSURANCE): 0.15,
            ("boda_boda", ProductCategory.LOAN): 0.10,
            ("boda_boda", ProductCategory.INSURANCE): 0.15,
            ("dukawallah", ProductCategory.LOAN): 0.15,
            ("dukawallah", ProductCategory.EQUIPMENT_FINANCING): 0.10,
            ("vendor", ProductCategory.LOAN): 0.10,
        }
        bonus = type_bonuses.get((worker_type, partner.product_category), 0.05)
        score += bonus

        # Cap at 1.0
        match_score = min(1.0, score)

        # Estimate commission
        commission_info = partner.commission_structure
        commission_type = CommissionType(commission_info.get("type", "flat_fee"))
        commission_rate = commission_info.get("rate", 0)

        if commission_type == CommissionType.PERCENTAGE_OF_AMOUNT and max_amount:
            commission_estimate = max_amount * commission_rate
        elif commission_type == CommissionType.PERCENTAGE_OF_PREMIUM:
            premium = product.get("premium_annual_kes", 0)
            commission_estimate = premium * commission_rate
        elif commission_type == CommissionType.FLAT_FEE:
            commission_estimate = commission_info.get("flat_fee_kes", 0)
        else:
            commission_estimate = 0

        # Generate referral code
        referral_code = self._generate_referral_code(partner.partner_id)

        return ProductMatch(
            partner_id=partner.partner_id,
            partner_name=partner.name,
            product_id=product.get("product_id", f"{partner.partner_id}_default"),
            product_name=product.get("name", partner.name),
            product_name_sw=product.get("name_sw", partner.name_sw),
            product_category=partner.product_category,
            match_score=round(match_score, 2),
            match_reasons=match_reasons,
            match_reasons_sw=match_reasons_sw,
            max_amount_kes=max_amount if max_amount else None,
            estimated_rate_pct=product.get("rate_pct"),
            term_days=product.get("term_days"),
            commission_type=commission_type,
            commission_rate=commission_rate,
            commission_amount_estimate=round(commission_estimate, 2),
            referral_link=f"https://angavu.app/r/{referral_code}",
            referral_code=referral_code,
            eligibility_met=len(ineligibility_reasons) == 0,
            ineligibility_reasons=ineligibility_reasons,
        )

    @staticmethod
    def _generate_referral_code(partner_id: str) -> str:
        """Generate a unique referral tracking code."""
        unique = uuid.uuid4().hex[:8]
        return f"ANG-{partner_id.upper()[:4]}-{unique}"

    def get_partner(self, partner_id: str) -> FinancialPartner | None:
        """Get a partner by ID."""
        return self._partner_map.get(partner_id)

    def list_partners(
        self,
        product_category: str | None = None,
        worker_type: str | None = None,
    ) -> list[FinancialPartner]:
        """List available partners, optionally filtered."""
        result = []
        for p in self.partners:
            if not p.is_active:
                continue
            if product_category and p.product_category.value != product_category:
                continue
            if worker_type and "all" not in p.supported_worker_types:
                if worker_type not in p.supported_worker_types:
                    continue
            result.append(p)
        return result

    def get_commission_rates(self) -> dict[str, Any]:
        """Get a summary of all commission rates by partner."""
        rates = {}
        for p in self.partners:
            rates[p.partner_id] = {
                "name": p.name,
                "category": p.product_category.value,
                "commission": p.commission_structure,
            }
        return rates
