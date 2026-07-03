"""
Audience-Aware Report Generation — BCB 108: Business Communication Skills.

Generates reports tailored to different audience types:
- Worker: Simple, actionable, Swahili-first
- Bank: Formal, risk-focused, compliance-ready
- Government: Policy-oriented, aggregate statistics
- NGO: Impact-focused, demographic breakdowns

Academic Foundation:
- BCB 108: Business Communication Skills — audience analysis, report
  writing, formal vs informal communication, data presentation,
  cross-cultural communication

The core insight from BCB 108: The same data tells different stories
to different audiences. A 15% revenue increase means:
- To a worker: "Your biashara is growing! Keep it up!"
- To a bank: "Revenue growth supports 20% credit limit increase"
- To government: "Sector contribution to county GDP up 15%"
- To NGO: "Financial inclusion program showing measurable impact"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class AudienceType(Enum):
    """Target audience for report generation."""
    WORKER = "worker"
    BANK = "bank"
    GOVERNMENT = "government"
    NGO = "ngo"
    FMCG = "fmcg"


@dataclass
class ReportSection:
    """A single section in a report."""
    title: str
    content: str
    priority: int = 5  # 1 = highest priority
    audience_types: List[AudienceType] = field(default_factory=lambda: list(AudienceType))
    format_hint: str = "text"  # text, table, chart, kpi


@dataclass
class AudienceReport:
    """A complete audience-specific report."""
    audience: AudienceType
    title: str
    executive_summary: str
    sections: List[ReportSection]
    language: str
    format_style: str  # whatsapp, formal, policy, impact
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audience": self.audience.value,
            "title": self.title,
            "executive_summary": self.executive_summary,
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "priority": s.priority,
                    "format_hint": s.format_hint,
                }
                for s in sorted(self.sections, key=lambda x: x.priority)
            ],
            "language": self.language,
            "format_style": self.format_style,
            "generated_at": self.generated_at.isoformat(),
        }


class AudienceReportGenerator:
    """
    Generate audience-aware reports from intelligence data.

    Driven by BCB 108 § Business Communication:
    - Audience analysis: Who is reading this? What do they need?
    - Register selection: Formal vs informal language
    - Data presentation: Tables for banks, narratives for workers
    - Executive summary: Key message first (pyramid principle)
    - Action orientation: Every report should suggest next steps

    Usage:
        generator = AudienceReportGenerator()
        worker_report = generator.generate(data, AudienceType.WORKER)
        bank_report = generator.generate(data, AudienceType.BANK)
    """

    # Audience-specific templates
    TEMPLATES = {
        AudienceType.WORKER: {
            "title_prefix": "📊 Ripoti ya",
            "greeting_sw": "Habari {name}, hii ripoti ya biashara yako:",
            "greeting_en": "Hi {name}, here's your business report:",
            "format_style": "whatsapp",
            "language": "sw",
            "tone": "warm, encouraging, simple",
            "max_sections": 5,
            "currency_format": "KSh {amount:,.0f}",
        },
        AudienceType.BANK: {
            "title_prefix": "Credit Intelligence Report —",
            "greeting_sw": "",
            "greeting_en": "To: Credit Committee\nSubject: Business Intelligence Assessment",
            "format_style": "formal",
            "language": "en",
            "tone": "formal, data-driven, risk-focused",
            "max_sections": 10,
            "currency_format": "KES {amount:,.2f}",
        },
        AudienceType.GOVERNMENT: {
            "title_prefix": "Economic Activity Brief —",
            "greeting_sw": "",
            "greeting_en": "Economic Intelligence Briefing\nPrepared for Policy Analysis",
            "format_style": "policy",
            "language": "en",
            "tone": "formal, aggregate, policy-relevant",
            "max_sections": 8,
            "currency_format": "KES {amount:,.0f}",
        },
        AudienceType.NGO: {
            "title_prefix": "Impact Report —",
            "greeting_sw": "Ripoti ya Athari — {name}",
            "greeting_en": "Impact Assessment Report — {name}",
            "format_style": "impact",
            "language": "en",
            "tone": "impact-focused, demographic, human-centered",
            "max_sections": 8,
            "currency_format": "KES {amount:,.0f}",
        },
        AudienceType.FMCG: {
            "title_prefix": "Market Intelligence —",
            "greeting_sw": "",
            "greeting_en": "FMCG Market Intelligence Report\nPrepared for Category Management",
            "format_style": "executive",
            "language": "en",
            "tone": "commercial, actionable, trend-focused",
            "max_sections": 8,
            "currency_format": "KES {amount:,.0f}",
        },
    }

    def generate(
        self,
        data: Dict[str, Any],
        audience: AudienceType,
        name: str = "Biashara",
        language: Optional[str] = None,
    ) -> AudienceReport:
        """
        Generate an audience-specific report from intelligence data.

        Args:
            data: Intelligence data dict (from any service)
            audience: Target audience type
            name: Business/person name for personalization
            language: Override language (default: audience-specific)

        Returns:
            AudienceReport tailored to the audience
        """
        template = self.TEMPLATES[audience]
        lang = language or template["language"]

        # Generate audience-specific sections
        if audience == AudienceType.WORKER:
            sections = self._worker_sections(data, lang)
            title = f"{template['title_prefix']} {name}"
            summary = self._worker_summary(data, name, lang)
        elif audience == AudienceType.BANK:
            sections = self._bank_sections(data)
            title = f"{template['title_prefix']} {name}"
            summary = self._bank_summary(data)
        elif audience == AudienceType.GOVERNMENT:
            sections = self._government_sections(data)
            title = f"{template['title_prefix']} {data.get('region', 'National')}"
            summary = self._government_summary(data)
        elif audience == AudienceType.NGO:
            sections = self._ngo_sections(data)
            title = f"{template['title_prefix']} {name}"
            summary = self._ngo_summary(data)
        elif audience == AudienceType.FMCG:
            sections = self._fmcg_sections(data)
            title = f"{template['title_prefix']} {data.get('product_category', 'Category')}"
            summary = self._fmcg_summary(data)
        else:
            sections = []
            title = f"Report — {name}"
            summary = "No data available."

        return AudienceReport(
            audience=audience,
            title=title,
            executive_summary=summary,
            sections=sections[:template["max_sections"]],
            language=lang,
            format_style=template["format_style"],
        )

    def _worker_sections(self, data: Dict[str, Any], lang: str) -> List[ReportSection]:
        """Generate worker-friendly sections (Swahili-first, simple)."""
        sections = []

        # Sales summary
        total_sales = data.get("total_sales", data.get("total_revenue", 0))
        if total_sales:
            if lang == "sw":
                sections.append(ReportSection(
                    title="💰 Mauzo",
                    content=f"Mauzo jumla: KSh {total_sales:,.0f}\nFaida: KSh {data.get('gross_profit', data.get('net_profit', 0)):,.0f}",
                    priority=1,
                    format_hint="kpi",
                ))
            else:
                sections.append(ReportSection(
                    title="💰 Sales",
                    content=f"Total sales: KSh {total_sales:,.0f}\nProfit: KSh {data.get('gross_profit', data.get('net_profit', 0)):,.0f}",
                    priority=1,
                    format_hint="kpi",
                ))

        # Top products
        top_products = data.get("top_products", [])
        if top_products:
            if lang == "sw":
                lines = ["Bidhaa bora:"]
                for i, p in enumerate(top_products[:3], 1):
                    lines.append(f"  {i}. {p.get('item', 'N/A')} — KSh {p.get('revenue', 0):,.0f}")
                sections.append(ReportSection(
                    title="🏆 Bidhaa Bora",
                    content="\n".join(lines),
                    priority=2,
                ))
            else:
                lines = ["Top products:"]
                for i, p in enumerate(top_products[:3], 1):
                    lines.append(f"  {i}. {p.get('item', 'N/A')} — KSh {p.get('revenue', 0):,.0f}")
                sections.append(ReportSection(
                    title="🏆 Top Products",
                    content="\n".join(lines),
                    priority=2,
                ))

        # Trends
        trends = data.get("trends", [])
        if trends:
            if lang == "sw":
                lines = ["Mwelekeo:"]
                for t in trends:
                    arrow = "📈" if t.get("direction") == "up" else "📉" if t.get("direction") == "down" else "➡️"
                    lines.append(f"  {arrow} {t.get('metric', '')}: {t.get('change_pct', 0):+.1f}%")
                sections.append(ReportSection(
                    title="📈 Mwelekeo",
                    content="\n".join(lines),
                    priority=3,
                ))
            else:
                lines = ["Trends:"]
                for t in trends:
                    arrow = "📈" if t.get("direction") == "up" else "📉" if t.get("direction") == "down" else "➡️"
                    lines.append(f"  {arrow} {t.get('metric', '')}: {t.get('change_pct', 0):+.1f}%")
                sections.append(ReportSection(
                    title="📈 Trends",
                    content="\n".join(lines),
                    priority=3,
                ))

        # Tip
        if lang == "sw":
            sections.append(ReportSection(
                title="💡 Kidokezo",
                content="Endelea kurekodi mauzo yako kila siku — data inasaidia kufanya maamuzi bora!",
                priority=5,
            ))
        else:
            sections.append(ReportSection(
                title="💡 Tip",
                content="Keep recording your sales daily — data helps you make better decisions!",
                priority=5,
            ))

        return sections

    def _bank_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        """Generate bank-formal sections (risk-focused, compliance-ready)."""
        sections = []

        # Credit score
        alama_score = data.get("alama_score")
        if alama_score:
            sections.append(ReportSection(
                title="1. Credit Score Assessment",
                content=(
                    f"Alama Score: {alama_score}\n"
                    f"Score Band: {data.get('score_band', 'N/A')}\n"
                    f"Percentile: {data.get('percentile', 'N/A')}th\n"
                    f"Heckman Corrected: {data.get('heckman_corrected', False)}"
                ),
                priority=1,
                format_hint="kpi",
            ))

        # Risk indicators
        risk = data.get("risk_indicators", {})
        if risk:
            sections.append(ReportSection(
                title="2. Risk Assessment",
                content=(
                    f"Category Risk: {risk.get('category_risk', 'N/A')}\n"
                    f"Default Probability: {risk.get('default_probability', 'N/A')}\n"
                    f"Recommended Credit Limit: KES {risk.get('recommended_credit_limit_kes', 0):,.2f}\n"
                    f"Risk Factors: {', '.join(risk.get('risk_factors', []))}"
                ),
                priority=2,
                format_hint="table",
            ))

        # Revenue analysis
        avg_daily = data.get("avg_daily_revenue_kes", 0)
        if avg_daily:
            sections.append(ReportSection(
                title="3. Revenue Analysis",
                content=(
                    f"Average Daily Revenue: KES {avg_daily:,.2f}\n"
                    f"Revenue Volatility: {data.get('revenue_volatility', 'N/A')}\n"
                    f"Growth Trajectory: {data.get('growth_trajectory', 'N/A')}\n"
                    f"Operating Days/Week: {data.get('operating_days_per_week', 'N/A')}"
                ),
                priority=3,
            ))

        # Components
        components = data.get("components", {})
        if components:
            lines = ["Score Components:"]
            for k, v in components.items():
                lines.append(f"  • {k.replace('_', ' ').title()}: {v}/100")
            sections.append(ReportSection(
                title="4. Score Components",
                content="\n".join(lines),
                priority=4,
            ))

        # Recommendation
        sections.append(ReportSection(
            title="5. Recommendation",
            content=self._bank_recommendation(data),
            priority=5,
        ))

        return sections

    def _government_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        """Generate government-policy sections (aggregate, policy-relevant)."""
        sections = []

        # GDP contribution
        gdp = data.get("nominal_gdp_kes", data.get("total_value_added_kes"))
        if gdp:
            sections.append(ReportSection(
                title="1. Economic Output",
                content=(
                    f"Estimated Informal GDP: KES {gdp:,.0f}\n"
                    f"Annualized: KES {data.get('annualized_nominal_gdp_kes', gdp * 4):,.0f}\n"
                    f"Growth Rate: {data.get('gdp_growth_pct', 'N/A')}%\n"
                    f"Business Cycle Phase: {data.get('business_cycle_phase', 'N/A')}"
                ),
                priority=1,
                format_hint="kpi",
            ))

        # Employment
        employment = data.get("estimated_employment", data.get("employment_created"))
        if employment:
            sections.append(ReportSection(
                title="2. Employment Impact",
                content=(
                    f"Estimated Employment: {employment:,}\n"
                    f"Livelihoods Supported: {data.get('livelihoods_supported', employment * 3):,}\n"
                    f"Active Businesses: {data.get('total_businesses', 'N/A'):,}"
                ),
                priority=2,
            ))

        # Sector breakdown
        sectors = data.get("sector_gdp_breakdown", data.get("category_breakdown", {}))
        if sectors:
            lines = ["Sector Breakdown:"]
            for sector, info in sorted(
                sectors.items(),
                key=lambda x: x[1].get("value_added", x[1].get("revenue", 0)),
                reverse=True,
            )[:5]:
                value = info.get("value_added", info.get("revenue", 0))
                share = info.get("share_of_total_pct", 0)
                lines.append(f"  • {sector}: KES {value:,.0f} ({share:.1f}%)")
            sections.append(ReportSection(
                title="3. Sector Analysis",
                content="\n".join(lines),
                priority=3,
                format_hint="table",
            ))

        # Inclusion metrics
        inclusion = data.get("inclusion_metrics", {})
        if inclusion:
            sections.append(ReportSection(
                title="4. Financial Inclusion",
                content=(
                    f"Financial Inclusion Index: {inclusion.get('financial_inclusion_index', 'N/A')}\n"
                    f"Digital Payment Adoption: {inclusion.get('digital_payment_adoption', 'N/A')}%\n"
                    f"Savings Behavior: {inclusion.get('savings_behavior_score', 'N/A')}"
                ),
                priority=4,
            ))

        # Policy recommendations
        sections.append(ReportSection(
            title="5. Policy Implications",
            content=self._government_policy_implications(data),
            priority=5,
        ))

        return sections

    def _ngo_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        """Generate NGO-impact sections (impact-focused, human-centered)."""
        sections = []

        # Beneficiaries
        user_count = data.get("sample_size", data.get("user_count", 0))
        if user_count:
            sections.append(ReportSection(
                title="1. Beneficiary Reach",
                content=(
                    f"Total Beneficiaries: {user_count:,}\n"
                    f"Youth-Owned: {data.get('youth_owned_pct', 'N/A')}%\n"
                    f"Women-Owned: {data.get('women_owned_pct', 'N/A')}%\n"
                    f"Employment Created: {data.get('employment_created', 'N/A'):,}"
                ),
                priority=1,
                format_hint="kpi",
            ))

        # Financial inclusion
        inclusion = data.get("inclusion_metrics", {})
        if inclusion:
            sections.append(ReportSection(
                title="2. Financial Inclusion Progress",
                content=(
                    f"Inclusion Index: {inclusion.get('financial_inclusion_index', 'N/A')}\n"
                    f"Digital Payments: {inclusion.get('digital_payment_adoption', 'N/A')}%\n"
                    f"Credit Access: {inclusion.get('credit_access_score', 'N/A')}%\n"
                    f"Savings Score: {inclusion.get('savings_behavior_score', 'N/A')}"
                ),
                priority=2,
            ))

        # Poverty indicators
        poverty = data.get("poverty_indicators", {})
        if poverty:
            sections.append(ReportSection(
                title="3. Poverty Analysis",
                content=(
                    f"Poverty Line: KES {poverty.get('poverty_line_monthly_kes', 0):,.0f}/month\n"
                    f"Headcount Ratio (P₀): {poverty.get('headcount_ratio_P0', 'N/A')}\n"
                    f"Poverty Gap (P₁): {poverty.get('poverty_gap_P1', 'N/A')}\n"
                    f"Method: {poverty.get('method', 'FGT')}"
                ),
                priority=3,
            ))

        # Inequality
        inequality = data.get("inequality", {})
        if inequality:
            sections.append(ReportSection(
                title="4. Inequality Analysis",
                content=(
                    f"Gini Coefficient: {inequality.get('gini_coefficient', 'N/A')}\n"
                    f"Theil Index: {inequality.get('theil_index', 'N/A')}\n"
                    f"Atkinson Index: {inequality.get('atkinson_index', 'N/A')}"
                ),
                priority=4,
            ))

        # Barriers
        barriers = data.get("barriers", [])
        if barriers:
            lines = ["Barriers to Inclusion:"]
            for b in barriers[:3]:
                lines.append(f"  • {b.get('barrier', 'N/A')}: Severity {b.get('severity', 0)}/100")
                lines.append(f"    → {b.get('recommended_intervention', '')}")
            sections.append(ReportSection(
                title="5. Barriers & Recommendations",
                content="\n".join(lines),
                priority=5,
            ))

        return sections

    def _fmcg_sections(self, data: Dict[str, Any]) -> List[ReportSection]:
        """Generate FMCG-commercial sections (trend-focused, actionable)."""
        sections = []

        # Market overview
        sections.append(ReportSection(
            title="1. Market Overview",
            content=(
                f"Category: {data.get('product_category', 'N/A')}\n"
                f"Region: {data.get('region', 'National')}\n"
                f"Total Volume: {data.get('total_volume', 'N/A'):,}\n"
                f"Avg Daily Volume: {data.get('avg_daily_volume', 'N/A'):,.0f}\n"
                f"Demand Trend: {data.get('demand_trend', 'N/A')}"
            ),
            priority=1,
            format_hint="kpi",
        ))

        # Price intelligence
        price = data.get("price_intelligence", {})
        if price:
            sections.append(ReportSection(
                title="2. Price Intelligence",
                content=(
                    f"Avg Price: KES {price.get('avg_price', 0):,.2f}\n"
                    f"Price Range: KES {price.get('min_price', 0):,.2f} — KES {price.get('max_price', 0):,.2f}\n"
                    f"Price Trend: {price.get('price_trend', 'N/A')} ({price.get('price_change_pct', 0):+.1f}%)\n"
                    f"Price Elasticity: {price.get('price_elasticity', {}).get('elasticity', 'N/A')}"
                ),
                priority=2,
            ))

        # Forecast
        forecast = data.get("forecast", {})
        if forecast:
            sections.append(ReportSection(
                title="3. Demand Forecast",
                content=(
                    f"Forecasted Volume: {forecast.get('forecasted_volume', 'N/A'):,.0f}\n"
                    f"CI: [{forecast.get('confidence_interval_low', 0):,.0f}, {forecast.get('confidence_interval_high', 0):,.0f}]\n"
                    f"Method: {forecast.get('forecast_method', 'N/A')}\n"
                    f"MAPE: {forecast.get('mape', 'N/A')}%"
                ),
                priority=3,
            ))

        # Day-of-week pattern
        dow = data.get("day_of_week_pattern", {})
        if dow:
            best_day = max(dow, key=dow.get) if dow else "N/A"
            sections.append(ReportSection(
                title="4. Demand Patterns",
                content=f"Peak Day: {best_day}\nSeasonal Factor: {data.get('seasonal_factor', 'N/A')}",
                priority=4,
            ))

        # Segmentation
        seg = data.get("market_segmentation", {})
        if seg:
            sections.append(ReportSection(
                title="5. Market Segments",
                content=f"Optimal Segments: {seg.get('optimal_k', 'N/A')}\nSilhouette Score: {seg.get('silhouette_score', 'N/A')}",
                priority=5,
            ))

        return sections

    # -------------------------------------------------------------------
    # Summary generators
    # -------------------------------------------------------------------

    def _worker_summary(self, data: Dict[str, Any], name: str, lang: str) -> str:
        total = data.get("total_sales", data.get("total_revenue", 0))
        profit = data.get("gross_profit", data.get("net_profit", 0))
        if lang == "sw":
            return f"{name}, biashara yako imefanya mauzo ya KSh {total:,.0f} na faida ya KSh {profit:,.0f}."
        return f"{name}, your business recorded KSh {total:,.0f} in sales with KSh {profit:,.0f} profit."

    def _bank_summary(self, data: Dict[str, Any]) -> str:
        score = data.get("alama_score", "N/A")
        band = data.get("score_band", "N/A")
        limit = data.get("risk_indicators", {}).get("recommended_credit_limit_kes", 0)
        return (
            f"Business credit score: {score} ({band}). "
            f"Recommended credit limit: KES {limit:,.2f}. "
            f"Risk profile: {data.get('risk_indicators', {}).get('category_risk', 'moderate')}."
        )

    def _government_summary(self, data: Dict[str, Any]) -> str:
        gdp = data.get("nominal_gdp_kes", data.get("total_value_added_kes", 0))
        return (
            f"Estimated informal sector GDP: KES {gdp:,.0f}. "
            f"Active businesses: {data.get('total_businesses', 'N/A')}. "
            f"Business cycle: {data.get('business_cycle_phase', 'N/A')}."
        )

    def _ngo_summary(self, data: Dict[str, Any]) -> str:
        return (
            f"Beneficiaries: {data.get('sample_size', data.get('user_count', 0)):,}. "
            f"Financial inclusion index: {data.get('inclusion_metrics', {}).get('financial_inclusion_index', 'N/A')}. "
            f"Women-owned: {data.get('women_owned_pct', 'N/A')}%."
        )

    def _fmcg_summary(self, data: Dict[str, Any]) -> str:
        return (
            f"Category: {data.get('product_category', 'N/A')}. "
            f"Demand trend: {data.get('demand_trend', 'N/A')}. "
            f"Avg price: KES {data.get('price_intelligence', {}).get('avg_price', 0):,.2f}."
        )

    def _bank_recommendation(self, data: Dict[str, Any]) -> str:
        score = data.get("alama_score", 0)
        if score >= 700:
            return "RECOMMENDATION: Approve credit. Strong transaction history with consistent revenue patterns."
        elif score >= 550:
            return "RECOMMENDATION: Approve with monitoring. Moderate risk — suggest smaller initial limit with growth-based increases."
        else:
            return "RECOMMENDATION: Decline or require collateral. High-risk profile based on transaction analysis."

    def _government_policy_implications(self, data: Dict[str, Any]) -> str:
        phase = data.get("business_cycle_phase", "stable")
        if phase == "expansion":
            return "Policy: Economy expanding. Consider formalization incentives and tax registration drives."
        elif phase == "contraction":
            return "Policy: Economy contracting. Consider stimulus measures and support programs for informal workers."
        return "Policy: Stable economic activity. Maintain current support infrastructure."
