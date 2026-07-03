"""
African Development Intelligence — ECO 204: Issues in African Development.

Cross-border trade analysis, EAC integration, and development economics
for Biashara Intelligence's Soko Pulse product.

Academic Foundation:
- ECO 204: Issues in African Development — Structural transformation,
  institutional economics, gender and development, governance,
  trade liberalization, regional integration (EAC, COMESA, AfCFTA)

Key Applications:
1. Cross-border trade analysis for EAC member states
2. EAC integration scoring (customs union, common market, monetary union)
3. Structural transformation tracking (agriculture → manufacturing → services)
4. Gender-disaggregated development metrics
5. Institutional quality assessment for trade facilitation

This module is wired into SokoPulseService for cross-border intelligence.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# EAC member states
EAC_MEMBER_STATES = {
    "KE": {"name": "Kenya", "gdp_billion_usd": 113.0, "population_million": 54.0,
           "informal_pct_gdp": 0.34, "currency": "KES", "hdi": 0.575},
    "UG": {"name": "Uganda", "gdp_billion_usd": 45.5, "population_million": 47.0,
           "informal_pct_gdp": 0.51, "currency": "UGX", "hdi": 0.525},
    "TZ": {"name": "Tanzania", "gdp_billion_usd": 75.7, "population_million": 65.0,
           "informal_pct_gdp": 0.46, "currency": "TZS", "hdi": 0.549},
    "RW": {"name": "Rwanda", "gdp_billion_usd": 14.1, "population_million": 13.5,
           "informal_pct_gdp": 0.40, "currency": "RWF", "hdi": 0.534},
    "BI": {"name": "Burundi", "gdp_billion_usd": 3.1, "population_million": 13.0,
           "informal_pct_gdp": 0.60, "currency": "BIF", "hdi": 0.426},
    "SS": {"name": "South Sudan", "gdp_billion_usd": 5.3, "population_million": 11.0,
           "informal_pct_gdp": 0.70, "currency": "SSP", "hdi": 0.385},
    "CD": {"name": "DRC", "gdp_billion_usd": 66.4, "population_million": 102.0,
           "informal_pct_gdp": 0.60, "currency": "CDF", "hdi": 0.479},
}


class AfricanDevelopmentEngine:
    """
    African development intelligence engine.

    Implements ECO 204 concepts:
    - Structural transformation: agriculture → manufacturing → services
    - Regional integration: EAC customs union, common market, monetary union
    - Institutional quality: governance, trade facilitation, property rights
    - Gender and development: women's economic empowerment
    - Trade liberalization: AfCFTA impact analysis
    """

    @classmethod
    def eac_integration_score(
        cls,
        origin: str,
        destination: str,
        trade_volume: float,
        tariff_rate: float,
        ntariff_barriers: int = 0,
    ) -> Dict[str, Any]:
        """
        Compute EAC integration score for a bilateral trade pair.

        ECO 204 § Regional Integration: EAC integration has 4 stages:
        1. Customs Union (2005): Common external tariff
        2. Common Market (2010): Free movement of goods, capital, labor
        3. Monetary Union (in progress): Common currency
        4. Political Federation (future): Political integration

        Score components:
        - Tariff reduction (40%): Lower tariffs = higher integration
        - Trade volume (30%): Higher volume = deeper integration
        - NTB reduction (20%): Fewer non-tariff barriers = smoother trade
        - Institutional alignment (10%): Regulatory harmonization

        Args:
            origin: Origin country code
            destination: Destination country code
            trade_volume: Trade volume in USD
            tariff_rate: Current tariff rate (0-1)
            ntariff_barriers: Number of non-tariff barriers

        Returns:
            Dict with integration score and component breakdown
        """
        origin = origin.upper()
        destination = destination.upper()

        if origin not in EAC_MEMBER_STATES or destination not in EAC_MEMBER_STATES:
            return {"error": f"Unknown country: {origin} or {destination}"}

        # Tariff score (40%): EAC customs union = 0% internal tariffs
        # Score: 100 if tariff = 0, 0 if tariff = 25% (CET average)
        tariff_score = max(0, min(100, (1 - tariff_rate / 0.25) * 100))

        # Trade volume score (30%): normalized by GDP
        gdp_origin = EAC_MEMBER_STATES[origin]["gdp_billion_usd"] * 1e9
        gdp_dest = EAC_MEMBER_STATES[destination]["gdp_billion_usd"] * 1e9
        trade_intensity = trade_volume / max(min(gdp_origin, gdp_dest), 1)
        volume_score = min(100, trade_intensity * 1000)

        # NTB score (20%): fewer barriers = higher score
        ntb_score = max(0, 100 - ntariff_barriers * 10)

        # Institutional alignment (10%): HDI similarity as proxy
        hdi_origin = EAC_MEMBER_STATES[origin]["hdi"]
        hdi_dest = EAC_MEMBER_STATES[destination]["hdi"]
        institutional_score = (1 - abs(hdi_origin - hdi_dest)) * 100

        # Weighted composite
        composite = (
            tariff_score * 0.40
            + volume_score * 0.30
            + ntb_score * 0.20
            + institutional_score * 0.10
        )

        # Integration stage
        if composite >= 80:
            stage = "deep_integration"
        elif composite >= 60:
            stage = "moderate_integration"
        elif composite >= 40:
            stage = "shallow_integration"
        else:
            stage = "minimal_integration"

        return {
            "origin": origin,
            "origin_name": EAC_MEMBER_STATES[origin]["name"],
            "destination": destination,
            "destination_name": EAC_MEMBER_STATES[destination]["name"],
            "composite_score": round(composite, 1),
            "integration_stage": stage,
            "components": {
                "tariff_integration": round(tariff_score, 1),
                "trade_volume_intensity": round(volume_score, 1),
                "ntb_reduction": round(ntb_score, 1),
                "institutional_alignment": round(institutional_score, 1),
            },
            "tariff_rate_pct": round(tariff_rate * 100, 1),
            "trade_volume_usd": round(trade_volume, 0),
            "recommendation": cls._integration_recommendation(composite, tariff_rate),
            "method": "ECO 204 — EAC Integration Assessment",
        }

    @classmethod
    def structural_transformation_index(
        cls,
        sector_shares: Dict[str, float],
        employment_shares: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Compute structural transformation index.

        ECO 204 § Structural Transformation: The shift from agriculture
        to manufacturing to services is the hallmark of development.

        - Kuznets process: Agriculture share falls, manufacturing rises
        - Petty commodity production → Modern sector transition
        - Lewis turning point: surplus labor exhausted

        Index measures progress on the transformation ladder:
        STI = 1 - (agri_share * 0.5 + manuf_share * 0.3 + services_share * 0.2)
        Higher STI = more transformed economy

        Args:
            sector_shares: GDP shares by sector (agriculture, manufacturing, services, other)
            employment_shares: Employment shares by sector

        Returns:
            Dict with transformation index and diagnostics
        """
        agri_gdp = sector_shares.get("agriculture", 0)
        manuf_gdp = sector_shares.get("manufacturing", 0)
        services_gdp = sector_shares.get("services", 0)

        agri_emp = employment_shares.get("agriculture", 0)
        manuf_emp = employment_shares.get("manufacturing", 0)
        services_emp = employment_shares.get("services", 0)

        # Structural transformation index
        sti = 1 - (agri_gdp * 0.5 + manuf_gdp * 0.3 + (1 - services_gdp) * 0.2)
        sti = max(0, min(1, sti))

        # Labor productivity gap (modern vs traditional sector)
        modern_gdp = manuf_gdp + services_gdp
        modern_emp = manuf_emp + services_emp
        if modern_emp > 0 and agri_emp > 0:
            productivity_gap = (modern_gdp / modern_emp) / max(agri_gdp / max(agri_emp, 0.01), 0.01)
        else:
            productivity_gap = 1.0

        # Transformation stage
        if sti > 0.7:
            stage = "advanced"
        elif sti > 0.5:
            stage = "intermediate"
        elif sti > 0.3:
            stage = "early"
        else:
            stage = "pre_transformation"

        return {
            "structural_transformation_index": round(sti, 4),
            "stage": stage,
            "sector_gdp_shares": {
                "agriculture": round(agri_gdp, 4),
                "manufacturing": round(manuf_gdp, 4),
                "services": round(services_gdp, 4),
            },
            "sector_employment_shares": {
                "agriculture": round(agri_emp, 4),
                "manufacturing": round(manuf_emp, 4),
                "services": round(services_emp, 4),
            },
            "labor_productivity_gap": round(productivity_gap, 2),
            "interpretation": cls._transformation_interpretation(sti, productivity_gap),
            "method": "ECO 204 — Structural Transformation Index",
        }

    @classmethod
    def gender_development_metrics(
        cls,
        women_owned_pct: float,
        women_revenue_share: float,
        women_digital_adoption: float,
        women_credit_access: float,
    ) -> Dict[str, Any]:
        """
        Gender-disaggregated development metrics.

        ECO 204 § Gender and Development: Women's economic empowerment
        is both a development goal and an economic multiplier.

        - Gender Development Index (GDI): HDI_female / HDI_male
        - Gender Inequality Index (GII): reproductive health, empowerment, labor
        - Women's economic participation: business ownership, revenue, digital access

        Args:
            women_owned_pct: Percentage of businesses owned by women
            women_revenue_share: Women's share of total revenue
            women_digital_adoption: Women's digital payment adoption rate
            women_credit_access: Women's credit access rate

        Returns:
            Dict with gender development indices and recommendations
        """
        # Gender parity index (1 = perfect parity)
        gender_parity = min(women_owned_pct, women_revenue_share) / max(women_owned_pct, women_revenue_share, 1)

        # Women's economic empowerment index
        empowerment_index = (
            women_owned_pct * 0.30
            + women_revenue_share * 0.30
            + women_digital_adoption * 0.20
            + women_credit_access * 0.20
        ) / 100

        # Gender gap
        gender_gap = 1 - gender_parity

        return {
            "women_owned_pct": round(women_owned_pct, 1),
            "women_revenue_share_pct": round(women_revenue_share, 1),
            "gender_parity_index": round(gender_parity, 4),
            "gender_gap_pct": round(gender_gap * 100, 1),
            "empowerment_index": round(empowerment_index, 4),
            "empowerment_level": (
                "high" if empowerment_index > 0.7
                else "moderate" if empowerment_index > 0.4
                else "low"
            ),
            "components": {
                "business_ownership": round(women_owned_pct, 1),
                "revenue_share": round(women_revenue_share, 1),
                "digital_adoption": round(women_digital_adoption, 1),
                "credit_access": round(women_credit_access, 1),
            },
            "recommendations": cls._gender_recommendations(empowerment_index, gender_gap),
            "method": "ECO 204 — Gender and Development Analysis",
        }

    @classmethod
    def cross_border_trade_potential(
        cls,
        origin: str,
        destination: str,
        product_category: str,
        current_volume: float,
    ) -> Dict[str, Any]:
        """
        Estimate cross-border trade potential using development indicators.

        Combines gravity model with development economics:
        - GDP per capita effect on demand
        - Informal sector size as trade opportunity
        - Infrastructure quality as trade facilitator
        - EAC integration as trade enabler

        Args:
            origin: Origin country code
            destination: Destination country code
            product_category: Product category
            current_volume: Current trade volume in USD

        Returns:
            Dict with trade potential and development-adjusted forecast
        """
        origin = origin.upper()
        destination = destination.upper()

        if origin not in EAC_MEMBER_STATES or destination not in EAC_MEMBER_STATES:
            return {"error": "Unknown country"}

        o = EAC_MEMBER_STATES[origin]
        d = EAC_MEMBER_STATES[destination]

        # Gravity model (simplified)
        gdp_effect = np.log(o["gdp_billion_usd"] * d["gdp_billion_usd"])

        # Informal sector opportunity (larger informal = more untapped potential)
        informal_opportunity = (o["informal_pct_gdp"] + d["informal_pct_gdp"]) / 2

        # Development-adjusted potential
        hdi_avg = (o["hdi"] + d["hdi"]) / 2
        development_multiplier = 1 + (1 - hdi_avg) * 0.5  # Lower HDI = higher growth potential

        # Estimated potential volume
        potential_volume = current_volume * development_multiplier * (1 + informal_opportunity)

        # AfCFTA boost (if applicable)
        afcfta_boost = potential_volume * 0.15  # 15% boost from AfCFTA

        return {
            "origin": origin,
            "destination": destination,
            "product_category": product_category,
            "current_volume_usd": round(current_volume, 0),
            "estimated_potential_usd": round(potential_volume, 0),
            "growth_potential_pct": round((potential_volume / max(current_volume, 1) - 1) * 100, 1),
            "afcfta_additional_usd": round(afcfta_boost, 0),
            "total_potential_usd": round(potential_volume + afcfta_boost, 0),
            "drivers": {
                "gdp_effect": round(gdp_effect, 2),
                "informal_opportunity": round(informal_opportunity, 4),
                "development_multiplier": round(development_multiplier, 4),
                "avg_hdi": round(hdi_avg, 4),
            },
            "origin_info": {
                "name": o["name"],
                "gdp_billion_usd": o["gdp_billion_usd"],
                "informal_pct": o["informal_pct_gdp"],
            },
            "destination_info": {
                "name": d["name"],
                "gdp_billion_usd": d["gdp_billion_usd"],
                "informal_pct": d["informal_pct_gdp"],
            },
            "method": "ECO 204 — Development-Adjusted Trade Potential",
        }

    @classmethod
    def _integration_recommendation(cls, score: float, tariff: float) -> str:
        if score >= 80:
            return "Deep integration. Focus on NTB reduction and regulatory harmonization."
        elif score >= 60:
            return "Moderate integration. Prioritize tariff elimination and trade facilitation."
        elif score >= 40:
            return "Shallow integration. Focus on customs union implementation and infrastructure."
        else:
            return "Minimal integration. Bilateral trade agreements and infrastructure investment needed."

    @staticmethod
    def _transformation_interpretation(sti: float, productivity_gap: float) -> str:
        if sti > 0.7:
            return "Advanced structural transformation. Economy dominated by modern services and manufacturing."
        elif sti > 0.5:
            return "Intermediate transformation. Manufacturing growing but agriculture still significant."
        elif sti > 0.3:
            return "Early transformation. Agriculture dominant but services emerging."
        else:
            return "Pre-transformation. Economy heavily agriculture-dependent with large productivity gap."

    @staticmethod
    def _gender_recommendations(empowerment: float, gap: float) -> List[str]:
        recs = []
        if empowerment < 0.4:
            recs.append("Target women-owned businesses for financial inclusion programs")
        if gap > 0.3:
            recs.append("Address gender revenue gap through market access programs")
        recs.append("Promote digital financial literacy for women traders")
        return recs
