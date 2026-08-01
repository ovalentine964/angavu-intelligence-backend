"""
International Economics & Public Finance Module (ECO 305/313, ECO 421, ECO 422)

Implements economic analysis tools for the Kenyan informal sector:

1. Exchange Rate Tracker — KES rates, cross-border trade impact
2. Cross-Border Trade Advisor — EAC trade, import/export costs
3. Fiscal Policy Analyzer — government spending impact on informal sector
4. Market Structure Analyzer — HHI, competition metrics, entry barriers
5. Industrial Organization — competition analysis, market power

For Kenya's informal economy:
- Cross-border trade: Uganda, Tanzania, Ethiopia (EAC partners)
- Tax burden: TOT, VAT, mobile money levies
- Market structure: fragmented (mama mboga) vs concentrated (wholesale)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ════════════════════════════════════════════════════════════════
# 1. Exchange Rate Tracker (ECO 305/313: International Economics)
# ════════════════════════════════════════════════════════════════


@dataclass
class ExchangeRateEntry:
    """A single exchange rate observation."""
    currency: str
    rate_to_kes: float
    date: str
    source: str = "manual"


class ExchangeRateTracker:
    """
    Track and analyze exchange rates for cross-border informal trade.

    Kenya's informal traders deal with:
    - UGX (Uganda) — largest informal trade partner
    - TZS (Tanzania) — second largest
    - ETB (Ethiopia) — growing
    - USD — international pricing reference

    Academic concepts:
    - Purchasing Power Parity (PPP)
    - Real exchange rate: RER = (e × P*) / P
    - Exchange rate pass-through to prices
    """

    # Default rates (approximate, update via API)
    DEFAULT_RATES = {
        "USD": 153.50,
        "UGX": 0.042,
        "TZS": 0.059,
        "ETB": 2.68,
        "RWF": 0.12,
        "BIF": 0.053,
        "SSP": 0.25,
        "SOS": 0.27,
    }

    def __init__(self):
        self._history: Dict[str, List[ExchangeRateEntry]] = {}

    def get_rate(self, currency: str, rates: Optional[Dict[str, float]] = None) -> float:
        """Get current rate: 1 unit of currency = X KES."""
        r = rates or self.DEFAULT_RATES
        return r.get(currency.upper(), 0.0)

    def convert(self, amount: float, from_currency: str, to_currency: str = "KES",
                rates: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Convert between currencies via KES.

        Args:
            amount: amount in source currency
            from_currency: source currency code
            to_currency: target currency code
            rates: exchange rates dict

        Returns:
            Dict with converted amount, rate used, inverse rate
        """
        r = rates or self.DEFAULT_RATES

        if from_currency.upper() == to_currency.upper():
            return {"amount": amount, "rate": 1.0, "inverse": 1.0}

        # Convert via KES
        if from_currency.upper() == "KES":
            rate_to_target = 1.0 / r.get(to_currency.upper(), 1.0)
            converted = amount * rate_to_target
        elif to_currency.upper() == "KES":
            rate = r.get(from_currency.upper(), 0.0)
            converted = amount * rate
        else:
            # KES intermediate
            kes_amount = amount * r.get(from_currency.upper(), 0.0)
            rate_to_target = 1.0 / r.get(to_currency.upper(), 1.0)
            converted = kes_amount * rate_to_target

        return {
            "original_amount": amount,
            "from_currency": from_currency.upper(),
            "to_currency": to_currency.upper(),
            "converted_amount": round(converted, 2),
            "rate_used": round(r.get(from_currency.upper(), 0.0), 4),
            "inverse_rate": round(1.0 / r.get(from_currency.upper(), 1.0), 6),
        }

    def real_exchange_rate(
        self,
        nominal_rate: float,
        domestic_price_index: float,
        foreign_price_index: float,
    ) -> Dict[str, Any]:
        """
        Real Exchange Rate: RER = (e × P*) / P

        If RER > 1: domestic goods are cheap (competitive)
        If RER < 1: domestic goods are expensive

        Args:
            nominal_rate: nominal exchange rate (KES per foreign currency)
            domestic_price_index: Kenya CPI
            foreign_price_index: partner country CPI

        Returns:
            Dict with RER and interpretation
        """
        rer = (nominal_rate * foreign_price_index) / domestic_price_index

        if rer > 1.1:
            interpretation = "Kenyan goods are COMPETITIVE — good for exports"
        elif rer > 0.9:
            interpretation = "Near equilibrium"
        else:
            interpretation = "Kenyan goods are EXPENSIVE — imports cheaper"

        return {
            "real_exchange_rate": round(rer, 4),
            "nominal_rate": nominal_rate,
            "domestic_cpi": domestic_price_index,
            "foreign_cpi": foreign_price_index,
            "interpretation": interpretation,
        }

    def ppp_implied_rate(
        self,
        domestic_price_level: float,
        foreign_price_level: float,
    ) -> Dict[str, Any]:
        """
        Purchasing Power Parity implied exchange rate.

        PPP: e = P_domestic / P_foreign

        If actual rate differs from PPP rate, currency is over/undervalued.

        Args:
            domestic_price_level: Kenya price level
            foreign_price_level: foreign price level

        Returns:
            Dict with PPP-implied rate
        """
        ppp_rate = domestic_price_level / foreign_price_level

        return {
            "ppp_implied_rate": round(ppp_rate, 4),
            "domestic_price_level": domestic_price_level,
            "foreign_price_level": foreign_price_level,
            "note": "Compare with actual rate to assess over/undervaluation",
        }


# ════════════════════════════════════════════════════════════════
# 2. Cross-Border Trade Advisor (ECO 305/313)
# ════════════════════════════════════════════════════════════════


class CrossBorderTradeAdvisor:
    """
    Advise informal traders on cross-border trade within EAC.

    East African Community (EAC) trade considerations:
    - Common External Tariff (CET) for non-EAC imports
    - Rules of Origin for EAC goods
    - Non-tariff barriers (NTBs): delays, bribes, documentation
    - Currency risk from exchange rate fluctuations

    Academic concepts:
    - Comparative advantage (Ricardo)
    - Gravity model of trade
    - Trade creation vs trade diversion
    """

    # Common External Tariff rates (EAC)
    CET_RATES = {
        "raw_materials": 0.10,      # 10%
        "semi_finished": 0.15,      # 15%
        "finished_goods": 0.25,     # 25%
        "sensitive_goods": 0.35,    # 35% (e.g., textiles, food)
    }

    # Informal trade costs (non-tariff)
    NTB_COSTS = {
        "uganda": {"documentation": 500, "transport_markup": 0.05, "delay_days": 1},
        "tanzania": {"documentation": 800, "transport_markup": 0.07, "delay_days": 2},
        "ethiopia": {"documentation": 1200, "transport_markup": 0.10, "delay_days": 3},
        "rwanda": {"documentation": 600, "transport_markup": 0.06, "delay_days": 1},
    }

    def trade_cost_analysis(
        self,
        product_value_kes: float,
        destination: str,
        product_category: str = "finished_goods",
        exchange_rates: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Calculate total cost of cross-border trade.

        Args:
            product_value_kes: value of goods in KES
            destination: destination country
            product_category: for CET classification
            exchange_rates: current rates

        Returns:
            Dict with total cost breakdown, profit margin needed
        """
        dest = destination.lower()
        ntb = self.NTB_COSTS.get(dest, {"documentation": 1000, "transport_markup": 0.10, "delay_days": 3})
        cet = self.CET_RATES.get(product_category, 0.25)

        # Cost components
        cet_cost = product_value_kes * cet
        transport_cost = product_value_kes * ntb["transport_markup"]
        documentation_cost = ntb["documentation"]
        opportunity_cost = product_value_kes * 0.01 * ntb["delay_days"]  # 1% per day

        total_cost = cet_cost + transport_cost + documentation_cost + opportunity_cost
        total_with_goods = product_value_kes + total_cost

        # Exchange rate risk
        risk_premium = product_value_kes * 0.02  # 2% for currency risk

        return {
            "product_value_kes": product_value_kes,
            "destination": destination.title(),
            "product_category": product_category,
            "cost_breakdown": {
                "cet_duty": round(cet_cost, 2),
                "transport": round(transport_cost, 2),
                "documentation": round(documentation_cost, 2),
                "opportunity_cost": round(opportunity_cost, 2),
                "currency_risk_premium": round(risk_premium, 2),
            },
            "total_trade_cost": round(total_cost + risk_premium, 2),
            "total_landed_cost": round(total_with_goods + risk_premium, 2),
            "cost_as_pct_of_goods": round((total_cost + risk_premium) / product_value_kes * 100, 1),
            "breakeven_markup_pct": round((total_cost + risk_premium) / product_value_kes * 100, 1),
            "delay_days": ntb["delay_days"],
        }

    def comparative_advantage(
        self,
        local_cost_per_unit: float,
        foreign_cost_per_unit: float,
        exchange_rate: float,
    ) -> Dict[str, Any]:
        """
        Assess comparative advantage for a product.

        If local cost (in foreign currency) < foreign cost → export opportunity.

        Args:
            local_cost_per_unit: production cost in KES
            foreign_cost_per_unit: foreign competitor cost in their currency
            exchange_rate: KES per unit of foreign currency

        Returns:
            Dict with competitive position
        """
        local_cost_foreign = local_cost_per_unit / exchange_rate
        advantage = (foreign_cost_per_unit - local_cost_foreign) / foreign_cost_per_unit * 100

        return {
            "local_cost_kes": local_cost_per_unit,
            "local_cost_foreign": round(local_cost_foreign, 2),
            "foreign_cost": foreign_cost_per_unit,
            "advantage_pct": round(advantage, 1),
            "competitive": advantage > 0,
            "recommendation": "Export opportunity — you're cheaper" if advantage > 10
                else "Marginal advantage — consider costs carefully" if advantage > 0
                else "Not competitive — foreign goods are cheaper",
        }


# ════════════════════════════════════════════════════════════════
# 3. Fiscal Policy Analyzer (ECO 421: Public Finance)
# ════════════════════════════════════════════════════════════════


class FiscalPolicyAnalyzer:
    """
    Analyze fiscal policy impact on informal workers.

    Kenya's fiscal policy affects informal workers through:
    - Tax burden (TOT, VAT, excise duties)
    - Government spending on infrastructure (markets, roads)
    - Social protection (cash transfers, NHIF subsidies)
    - Monetary policy (CBK rate → mobile money costs)

    Academic concepts:
    - Tax incidence (who bears the burden?)
    - Deadweight loss from taxation
    - Fiscal multiplier
    - Laffer curve
    """

    def tax_burden_analysis(
        self,
        annual_revenue: float,
        employee_count: int = 0,
        monthly_expenses: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Comprehensive tax burden analysis for an informal worker.

        Args:
            annual_revenue: gross annual revenue (KES)
            employee_count: number of employees
            monthly_expenses: monthly operating expenses

        Returns:
            Dict with total tax burden, effective rate, recommendations
        """
        taxes = {}

        # Turnover Tax: 1% for KES 1M-25M
        if 1_000_000 <= annual_revenue <= 25_000_000:
            taxes["tot"] = annual_revenue * 0.01
        else:
            taxes["tot"] = 0.0

        # VAT: 16% if above KES 5M
        if annual_revenue >= 5_000_000:
            taxes["vat_potential"] = annual_revenue * 0.16
        else:
            taxes["vat_potential"] = 0.0

        # NHIF: employer contribution
        taxes["nhif"] = employee_count * 500 * 12  # ~KES 500/employee/month

        # NSSF: employer contribution
        taxes["nssf"] = employee_count * 400 * 12  # ~KES 400/employee/month

        # Mobile money levy: 1.5% on M-Pesa transactions (assumption: 60% of revenue via M-Pesa)
        mpesa_volume = annual_revenue * 0.6
        taxes["mobile_money_levy"] = mpesa_volume * 0.015

        # Digital service tax: 1.5% on digital transactions
        taxes["digital_service_tax"] = annual_revenue * 0.015 if annual_revenue > 500_000 else 0

        total_tax = sum(taxes.values())
        effective_rate = total_tax / annual_revenue * 100 if annual_revenue > 0 else 0

        # Net income estimate
        annual_expenses = monthly_expenses * 12
        net_income = annual_revenue - annual_expenses - total_tax

        # Tax burden assessment
        if effective_rate > 15:
            burden = "HEAVY"
            advice = "Consider formalization for tax benefits, or optimize expense deductions"
        elif effective_rate > 8:
            burden = "MODERATE"
            advice = "Tax burden is manageable — keep records for compliance"
        else:
            burden = "LIGHT"
            advice = "Low tax burden — focus on growing revenue"

        return {
            "annual_revenue": annual_revenue,
            "tax_breakdown": {k: round(v, 2) for k, v in taxes.items()},
            "total_annual_tax": round(total_tax, 2),
            "effective_tax_rate_pct": round(effective_rate, 1),
            "burden_level": burden,
            "estimated_net_income": round(net_income, 2),
            "net_income_margin_pct": round(net_income / annual_revenue * 100, 1) if annual_revenue > 0 else 0,
            "advice": advice,
        }

    def deadweight_loss(
        self,
        tax_rate: float,
        price_elasticity: float,
        quantity: float,
        price: float,
    ) -> Dict[str, Any]:
        """
        Estimate deadweight loss from taxation.

        DWL ≈ 0.5 × t² × |ε| × P × Q

        where t = tax rate, ε = price elasticity, P = price, Q = quantity

        Args:
            tax_rate: tax rate (e.g., 0.01 for TOT)
            price_elasticity: absolute value of price elasticity
            quantity: equilibrium quantity
            price: equilibrium price

        Returns:
            Dict with DWL estimate, revenue, efficiency loss
        """
        dwl = 0.5 * tax_rate ** 2 * abs(price_elasticity) * price * quantity
        revenue = tax_rate * price * quantity

        return {
            "deadweight_loss": round(dwl, 2),
            "tax_revenue": round(revenue, 2),
            "efficiency_ratio": round(dwl / revenue * 100, 2) if revenue > 0 else 0,
            "interpretation": "High efficiency loss" if dwl / revenue > 0.5 else "Manageable efficiency loss",
        }

    def fiscal_multiplier(
        self,
        government_spending: float,
        marginal_propensity_consume: float,
        tax_rate: float,
    ) -> Dict[str, Any]:
        """
        Simple fiscal multiplier.

        Multiplier = 1 / (1 - MPC × (1 - t))

        Args:
            government_spending: change in G (KES)
            marginal_propensity_consume: MPC (0-1)
            tax_rate: tax rate (0-1)

        Returns:
            Dict with multiplier, GDP impact
        """
        mpc = marginal_propensity_consume
        t = tax_rate
        multiplier = 1 / (1 - mpc * (1 - t)) if (1 - mpc * (1 - t)) != 0 else 0
        gdp_impact = government_spending * multiplier

        return {
            "fiscal_multiplier": round(multiplier, 3),
            "government_spending": government_spending,
            "gdp_impact": round(gdp_impact, 2),
            "note": "For informal economy, multiplier may be higher (cash-constrained workers spend more)",
        }


# ════════════════════════════════════════════════════════════════
# 4. Market Structure Analyzer (ECO 422: Industrial Organization)
# ════════════════════════════════════════════════════════════════


class MarketStructureAnalyzer:
    """
    Analyze market structure and competition in informal markets.

    Academic concepts:
    - Perfect competition (mama mboga markets)
    - Monopolistic competition (differentiated services)
    - Oligopoly (wholesale markets)
    - Barriers to entry
    - Market power (Lerner index)

    For Kenya's informal sector:
    - Most markets are atomistic (many small sellers)
    - Wholesale markets have some concentration
    - Digital platforms creating new market structures
    """

    def market_structure_assessment(
        self,
        market_shares: List[float],
        firm_count: int,
        entry_cost_kes: float = 0.0,
        annual_revenue: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Comprehensive market structure assessment.

        Args:
            market_shares: list of market shares (percentages)
            firm_count: number of firms in the market
            entry_cost_kes: estimated cost to enter the market
            annual_revenue: total market revenue

        Returns:
            Dict with HHI, concentration level, market type, competition assessment
        """
        shares = np.array(market_shares, dtype=float)

        # HHI
        hhi = float(np.sum(shares ** 2))

        # Concentration ratio (CR4)
        sorted_shares = np.sort(shares)[::-1]
        cr4 = float(np.sum(sorted_shares[:4]))

        # Number equivalent firms
        hhi_normalized = float(np.sum((shares / shares.sum()) ** 2))
        n_equivalent = 1.0 / hhi_normalized if hhi_normalized > 0 else float('inf')

        # Market type classification
        if firm_count > 100 and hhi < 100:
            market_type = "PERFECT_COMPETITION"
            description = "Atomistic market — many small sellers, no market power"
        elif firm_count > 20 and hhi < 1500:
            market_type = "MONOPOLISTIC_COMPETITION"
            description = "Many sellers with some product differentiation"
        elif firm_count <= 20 and hhi < 2500:
            market_type = "OLIGOPOLY"
            description = "Few dominant sellers — strategic behavior likely"
        elif hhi >= 2500:
            market_type = "MONOPOLY_TENDENCY"
            description = "High concentration — market power exists"
        else:
            market_type = "COMPETITIVE"
            description = "Competitive market structure"

        # Entry barriers
        if entry_cost_kes > 0 and annual_revenue > 0:
            entry_barrier_ratio = entry_cost_kes / annual_revenue
            if entry_barrier_ratio > 1.0:
                entry_barrier = "HIGH"
            elif entry_barrier_ratio > 0.5:
                entry_barrier = "MODERATE"
            else:
                entry_barrier = "LOW"
        else:
            entry_barrier = "UNKNOWN"

        # Lerner Index approximation (if we have price/cost data)
        # L = (P - MC) / P — measures market power

        return {
            "hhi": round(hhi, 1),
            "concentration_level": "unconcentrated" if hhi < 1500
                else "moderately_concentrated" if hhi < 2500
                else "highly_concentrated",
            "cr4": round(cr4, 1),
            "n_firms": firm_count,
            "n_equivalent_firms": round(n_equivalent, 1),
            "market_type": market_type,
            "market_description": description,
            "entry_barrier_level": entry_barrier,
            "doj_thresholds": {"unconcentrated": 1500, "moderately": 2500},
        }

    def lerner_index(
        self,
        price: float,
        marginal_cost: float,
    ) -> Dict[str, Any]:
        """
        Lerner Index: measure of market power.

        L = (P - MC) / P

        L = 0: perfect competition (P = MC)
        L = 1: monopoly (P >> MC)

        Args:
            price: market price
            marginal_cost: marginal cost of production

        Returns:
            Dict with Lerner index, market power assessment
        """
        if price <= 0:
            return {"error": "Price must be positive"}

        lerner = (price - marginal_cost) / price
        lerner = max(0, min(1, lerner))

        if lerner < 0.05:
            power = "NONE — near perfect competition"
        elif lerner < 0.2:
            power = "LOW — some pricing power"
        elif lerner < 0.5:
            power = "MODERATE — significant market power"
        else:
            power = "HIGH — substantial monopoly power"

        return {
            "lerner_index": round(lerner, 4),
            "price": price,
            "marginal_cost": marginal_cost,
            "markup_pct": round((price - marginal_cost) / marginal_cost * 100, 1) if marginal_cost > 0 else 0,
            "market_power": power,
        }

    def herfindahl_hirschman_index(
        self,
        market_shares: List[float],
    ) -> Dict[str, Any]:
        """
        HHI calculation (standalone).

        Args:
            market_shares: list of market shares (as percentages)

        Returns:
            Dict with HHI, concentration level
        """
        shares = np.array(market_shares, dtype=float)
        hhi = float(np.sum(shares ** 2))

        if hhi < 1500:
            level = "Unconcentrated"
        elif hhi < 2500:
            level = "Moderately concentrated"
        else:
            level = "Highly concentrated"

        return {
            "hhi": round(hhi, 1),
            "concentration_level": level,
            "n_firms": len(market_shares),
        }
