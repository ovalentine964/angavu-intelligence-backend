"""
Comparison Engine — Msaidizi / Biashara AI

Compares a business against anonymized, aggregated data from similar
businesses in the same market/region. Provides context that helps
informal workers understand how they're doing relative to peers.

Privacy & Ethics:
- k-anonymity: minimum 10 businesses per comparison group
- All data is aggregated — no individual business data is exposed
- No identifying information in comparisons
- User can opt out of contributing their data
- Data is market/region level, never individual

Comparison dimensions:
1. Revenue — how do sales compare?
2. Profit margin — am I making more or less per sale?
3. Growth rate — am I growing faster or slower?
4. Transaction frequency — am I selling more or less often?
5. Product diversity — do I sell more or fewer products?
6. Savings rate — am I saving more or less than peers?
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .whatsapp_charts import (
    ARROW_DOWN,
    ARROW_UP,
    ARROW_RIGHT,
    BLOCK_FULL,
    BLOCK_LIGHT,
    BLOCK_SOLID,
    CHECK,
    CROSS_MARK,
    WARNING,
    format_currency,
    format_percentage,
    star_rating,
)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class PeerBusiness:
    """Anonymized peer business data (used only in aggregated form)."""
    business_type: str          # e.g., "food_vendor", "duka", "mama_mboga"
    market: str                 # e.g., "Gikomba", "Eastleigh"
    region: str                 # e.g., "Nairobi", "Mombasa"
    monthly_revenue: float
    monthly_expenses: float
    monthly_profit: float
    profit_margin: float
    monthly_transactions: int
    unique_products: int
    savings_rate: float
    growth_rate: float          # MoM growth %
    active_days_ratio: float    # % of days active
    months_of_data: int


@dataclass
class ComparisonResult:
    """Result of comparing a business against peers."""
    # Revenue comparison
    revenue_percentile: float           # 0-100, where the business ranks
    revenue_vs_avg: float               # % above/below average
    revenue_vs_median: float            # % above/below median
    avg_peer_revenue: float
    median_peer_revenue: float

    # Profit margin comparison
    margin_percentile: float
    margin_vs_avg: float
    avg_peer_margin: float

    # Growth comparison
    growth_percentile: float
    growth_vs_avg: float
    avg_peer_growth: float

    # Transaction comparison
    transactions_percentile: float
    transactions_vs_avg: float
    avg_peer_transactions: float

    # Diversity comparison
    diversity_percentile: float
    diversity_vs_avg: float
    avg_peer_diversity: float

    # Savings comparison
    savings_percentile: float
    savings_vs_avg: float
    avg_peer_savings: float

    # Overall ranking
    overall_percentile: float
    peer_count: int                     # How many businesses in comparison group
    comparison_group: str               # Description of comparison group

    # Insights
    strengths_vs_peers: List[str]       # Where the business beats peers
    weaknesses_vs_peers: List[str]      # Where the business lags
    insights_sw: List[str]              # Swahili insights
    insights_en: List[str]              # English insights

    # Privacy
    k_anonymity_met: bool               # Whether k-anonymity threshold was met


@dataclass
class BenchmarkData:
    """Aggregated benchmark data for a comparison group."""
    business_type: str
    market: str
    region: str
    sample_size: int                    # Number of businesses
    revenue_stats: Dict[str, float]     # mean, median, p25, p75, p90
    margin_stats: Dict[str, float]
    growth_stats: Dict[str, float]
    transaction_stats: Dict[str, float]
    diversity_stats: Dict[str, float]
    savings_stats: Dict[str, float]
    last_updated: datetime


# ---------------------------------------------------------------------------
# Comparison Engine
# ---------------------------------------------------------------------------

class ComparisonEngine:
    """Compares a business against anonymized peer benchmarks.

    Privacy guarantees:
    - k-anonymity: Minimum 10 businesses per comparison group
    - All comparisons use aggregated statistics only
    - No individual business data is ever exposed
    - Users can opt out of data contribution

    Comparison methodology:
    1. Find the best comparison group (same type, same market, same region)
    2. Fall back to broader groups if k-anonymity not met
    3. Calculate percentile ranks for each dimension
    4. Generate contextualized insights in user's preferred language
    """

    # k-anonymity threshold
    K_MIN = 10  # Minimum businesses per comparison group

    # Comparison group priority (most specific → least specific)
    GROUP_PRIORITY = [
        ("business_type", "market", "region"),      # e.g., food_vendor in Gikomba, Nairobi
        ("business_type", "region"),                  # e.g., food_vendor in Nairobi
        ("business_type",),                           # e.g., all food vendors
        ("market", "region"),                         # e.g., all businesses in Gikomba
        ("region",),                                  # e.g., all businesses in Nairobi
    ]

    # Percentile thresholds for labeling
    PERCENTILE_EXCELLENT = 75
    PERCENTILE_GOOD = 60
    PERCENTILE_AVERAGE = 40
    PERCENTILE_BELOW = 25

    # -------------------------------------------------------------------
    # Main Comparison
    # -------------------------------------------------------------------

    def compare(
        self,
        user_revenue: float,
        user_margin: float,
        user_growth: float,
        user_transactions: int,
        user_diversity: int,
        user_savings_rate: float,
        peer_data: List[PeerBusiness],
        business_type: str = "",
        market: str = "",
        region: str = "",
        locale: str = "sw",
    ) -> ComparisonResult:
        """Compare a business against peer data.

        Args:
            user_revenue: User's monthly revenue.
            user_margin: User's profit margin (0-1).
            user_growth: User's MoM growth rate (%).
            user_transactions: User's monthly transactions.
            user_diversity: User's number of unique products.
            user_savings_rate: User's savings rate (0-1).
            peer_data: List of peer business data.
            business_type: User's business type.
            market: User's market name.
            region: User's region.
            locale: Language.

        Returns:
            ComparisonResult with rankings and insights.
        """
        # Find best comparison group
        group, group_desc, group_size = self._find_comparison_group(
            peer_data, business_type, market, region
        )

        k_met = group_size >= self.K_MIN

        if not k_met or not group:
            return self._empty_result(
                group_size, group_desc, locale,
                "Hakuna biashara za kutosha za kulinganisha" if locale == "sw"
                else "Not enough businesses for comparison"
            )

        # Extract peer metrics
        peer_revenues = [p.monthly_revenue for p in group]
        peer_margins = [p.profit_margin for p in group]
        peer_growths = [p.growth_rate for p in group]
        peer_transactions = [p.monthly_transactions for p in group]
        peer_diversities = [p.unique_products for p in group]
        peer_savings = [p.savings_rate for p in group]

        # Calculate percentiles
        rev_pct = self._percentile_rank(user_revenue, peer_revenues)
        margin_pct = self._percentile_rank(user_margin, peer_margins)
        growth_pct = self._percentile_rank(user_growth, peer_growths)
        tx_pct = self._percentile_rank(user_transactions, peer_transactions)
        div_pct = self._percentile_rank(user_diversity, peer_diversities)
        sav_pct = self._percentile_rank(user_savings_rate, peer_savings)

        # Calculate averages
        avg_rev = statistics.mean(peer_revenues)
        med_rev = statistics.median(peer_revenues)
        avg_margin = statistics.mean(peer_margins)
        avg_growth = statistics.mean(peer_growths)
        avg_tx = statistics.mean(peer_transactions)
        avg_div = statistics.mean(peer_diversities)
        avg_sav = statistics.mean(peer_savings)

        # Calculate vs average
        rev_vs_avg = ((user_revenue - avg_rev) / avg_rev * 100) if avg_rev > 0 else 0
        rev_vs_med = ((user_revenue - med_rev) / med_rev * 100) if med_rev > 0 else 0
        margin_vs_avg = ((user_margin - avg_margin) / avg_margin * 100) if avg_margin > 0 else 0
        growth_vs_avg = user_growth - avg_growth  # Percentage point difference
        tx_vs_avg = ((user_transactions - avg_tx) / avg_tx * 100) if avg_tx > 0 else 0
        div_vs_avg = ((user_diversity - avg_div) / avg_div * 100) if avg_div > 0 else 0
        sav_vs_avg = ((user_savings_rate - avg_sav) / avg_sav * 100) if avg_sav > 0 else 0

        # Overall percentile (weighted average of all percentiles)
        overall_pct = (
            rev_pct * 0.30 +
            margin_pct * 0.25 +
            growth_pct * 0.20 +
            tx_pct * 0.10 +
            div_pct * 0.10 +
            sav_pct * 0.05
        )

        # Identify strengths and weaknesses
        strengths, weaknesses = self._identify_strengths_weaknesses(
            rev_pct, margin_pct, growth_pct, tx_pct, div_pct, sav_pct, locale
        )

        # Generate insights
        insights_sw = self._generate_insights_sw(
            user_revenue, user_margin, user_growth,
            avg_rev, avg_margin, avg_growth,
            rev_pct, margin_pct, growth_pct, group_desc
        )
        insights_en = self._generate_insights_en(
            user_revenue, user_margin, user_growth,
            avg_rev, avg_margin, avg_growth,
            rev_pct, margin_pct, growth_pct, group_desc
        )

        return ComparisonResult(
            revenue_percentile=round(rev_pct, 1),
            revenue_vs_avg=round(rev_vs_avg, 1),
            revenue_vs_median=round(rev_vs_med, 1),
            avg_peer_revenue=avg_rev,
            median_peer_revenue=med_rev,
            margin_percentile=round(margin_pct, 1),
            margin_vs_avg=round(margin_vs_avg, 1),
            avg_peer_margin=avg_margin,
            growth_percentile=round(growth_pct, 1),
            growth_vs_avg=round(growth_vs_avg, 1),
            avg_peer_growth=avg_growth,
            transactions_percentile=round(tx_pct, 1),
            transactions_vs_avg=round(tx_vs_avg, 1),
            avg_peer_transactions=avg_tx,
            diversity_percentile=round(div_pct, 1),
            diversity_vs_avg=round(div_vs_avg, 1),
            avg_peer_diversity=avg_div,
            savings_percentile=round(sav_pct, 1),
            savings_vs_avg=round(sav_vs_avg, 1),
            avg_peer_savings=avg_sav,
            overall_percentile=round(overall_pct, 1),
            peer_count=group_size,
            comparison_group=group_desc,
            strengths_vs_peers=strengths,
            weaknesses_vs_peers=weaknesses,
            insights_sw=insights_sw,
            insights_en=insights_en,
            k_anonymity_met=k_met,
        )

    # -------------------------------------------------------------------
    # Comparison Group Selection
    # -------------------------------------------------------------------

    def _find_comparison_group(
        self,
        peer_data: List[PeerBusiness],
        business_type: str,
        market: str,
        region: str,
    ) -> Tuple[List[PeerBusiness], str, int]:
        """Find the best comparison group meeting k-anonymity.

        Tries progressively broader groups until k-anonymity is met.

        Args:
            peer_data: All available peer data.
            business_type: User's business type.
            market: User's market.
            region: User's region.

        Returns:
            Tuple of (filtered_peers, description, count).
        """
        for priority in self.GROUP_PRIORITY:
            filtered = self._filter_peers(peer_data, business_type, market, region, priority)

            if len(filtered) >= self.K_MIN:
                desc = self._group_description(business_type, market, region, priority)
                return filtered, desc, len(filtered)

        # If nothing meets k-anonymity, return empty
        return [], "Hakuna kundi la kulinganisha" if business_type else "No comparison group", 0

    def _filter_peers(
        self,
        peer_data: List[PeerBusiness],
        business_type: str,
        market: str,
        region: str,
        fields: Tuple[str, ...],
    ) -> List[PeerBusiness]:
        """Filter peers by specified fields.

        Args:
            peer_data: All peer data.
            business_type: Business type to match.
            market: Market to match.
            region: Region to match.
            fields: Tuple of field names to match on.

        Returns:
            Filtered list of matching peers.
        """
        filtered = []
        for p in peer_data:
            match = True
            for field_name in fields:
                if field_name == "business_type" and p.business_type != business_type:
                    match = False
                    break
                elif field_name == "market" and p.market != market:
                    match = False
                    break
                elif field_name == "region" and p.region != region:
                    match = False
                    break
            if match:
                filtered.append(p)
        return filtered

    def _group_description(
        self,
        business_type: str,
        market: str,
        region: str,
        fields: Tuple[str, ...],
    ) -> str:
        """Generate a human-readable description of the comparison group.

        Args:
            business_type: Business type.
            market: Market name.
            region: Region name.
            fields: Fields used for filtering.

        Returns:
            Description string.
        """
        parts = []
        type_names = {
            "food_vendor": "wauza vyakula",
            "duka": "maduka",
            "mama_mboga": "mama mboga",
            "boda_boda": "boda boda",
            "market_vendor": "wauza soko",
            "clothing": "wauza nguo",
            "electronics": "wauza vifaa vya elektroniki",
        }

        if "business_type" in fields:
            parts.append(type_names.get(business_type, business_type))
        if "market" in fields:
            parts.append(f"soko la {market}")
        if "region" in fields:
            parts.append(region)

        if parts:
            return " na ".join(parts[:2]) + (f" ({parts[2]})" if len(parts) > 2 else "")
        return "Biashara zote"

    # -------------------------------------------------------------------
    # Percentile Ranking
    # -------------------------------------------------------------------

    def _percentile_rank(self, value: float, peer_values: List[float]) -> float:
        """Calculate percentile rank of a value among peers.

        Args:
            value: The user's value.
            peer_values: List of peer values.

        Returns:
            Percentile rank (0-100).
        """
        if not peer_values:
            return 50.0  # Default to median if no data

        below = sum(1 for v in peer_values if v < value)
        equal = sum(1 for v in peer_values if v == value)

        # Percentile = (below + 0.5 * equal) / total * 100
        percentile = (below + 0.5 * equal) / len(peer_values) * 100
        return min(max(percentile, 0), 100)

    # -------------------------------------------------------------------
    # Strengths & Weaknesses
    # -------------------------------------------------------------------

    def _identify_strengths_weaknesses(
        self,
        rev_pct: float,
        margin_pct: float,
        growth_pct: float,
        tx_pct: float,
        div_pct: float,
        sav_pct: float,
        locale: str,
    ) -> Tuple[List[str], List[str]]:
        """Identify where the business beats or lags peers.

        Args:
            rev_pct: Revenue percentile.
            margin_pct: Margin percentile.
            growth_pct: Growth percentile.
            tx_pct: Transaction percentile.
            div_pct: Diversity percentile.
            sav_pct: Savings percentile.
            locale: Language.

        Returns:
            Tuple of (strengths, weaknesses) lists.
        """
        labels_sw = {
            "revenue": "Mauzo ya juu",
            "margin": "Faida nzuri",
            "growth": "Ukuaji mzuri",
            "transactions": "Mauzo mengi",
            "diversity": "Bidhaa mbalimbali",
            "savings": "Akiba nzuri",
        }
        labels_en = {
            "revenue": "High revenue",
            "margin": "Good profit margin",
            "growth": "Strong growth",
            "transactions": "Many transactions",
            "diversity": "Diverse products",
            "savings": "Good savings",
        }

        weaknesses_sw = {
            "revenue": "Mauzo ya chini",
            "margin": "Faida ndogo",
            "growth": "Ukuaji polepole",
            "transactions": "Mauzo machache",
            "diversity": "Bidhaa chache",
            "savings": "Akiba ndogo",
        }
        weaknesses_en = {
            "revenue": "Low revenue",
            "margin": "Low profit margin",
            "growth": "Slow growth",
            "transactions": "Few transactions",
            "diversity": "Few products",
            "savings": "Low savings",
        }

        labels = labels_sw if locale == "sw" else labels_en
        weak_labels = weaknesses_sw if locale == "sw" else weaknesses_en

        strengths = []
        weaknesses = []

        metrics = {
            "revenue": rev_pct,
            "margin": margin_pct,
            "growth": growth_pct,
            "transactions": tx_pct,
            "diversity": div_pct,
            "savings": sav_pct,
        }

        for key, pct in metrics.items():
            if pct >= self.PERCENTILE_GOOD:
                strengths.append(labels[key])
            elif pct < self.PERCENTILE_BELOW:
                weaknesses.append(weak_labels[key])

        return strengths, weaknesses

    # -------------------------------------------------------------------
    # Insight Generation
    # -------------------------------------------------------------------

    def _generate_insights_sw(
        self,
        user_rev: float,
        user_margin: float,
        user_growth: float,
        avg_rev: float,
        avg_margin: float,
        avg_growth: float,
        rev_pct: float,
        margin_pct: float,
        growth_pct: float,
        group_desc: str,
    ) -> List[str]:
        """Generate Swahili comparison insights.

        Args:
            user_*: User's metrics.
            avg_*: Peer averages.
            *_pct: Percentile ranks.
            group_desc: Description of comparison group.

        Returns:
            List of insight strings in Swahili.
        """
        insights = []

        # Revenue insight
        if rev_pct >= self.PERCENTILE_EXCELLENT:
            insights.append(
                f"Mauzo yako ni bora kuliko {rev_pct:.0f}% ya {group_desc}!"
            )
        elif rev_pct >= self.PERCENTILE_GOOD:
            insights.append(
                f"Mauzo yako ni ya juu kuliko wastani wa {group_desc}."
            )
        elif rev_pct < self.PERCENTILE_BELOW:
            diff_pct = ((avg_rev - user_rev) / avg_rev * 100) if avg_rev > 0 else 0
            insights.append(
                f"Mauzo yako ni ya chini kuliko wastani kwa {diff_pct:.0f}%. "
                f"Ongeza matangazo na ubora."
            )

        # Margin insight
        if margin_pct >= self.PERCENTILE_EXCELLENT:
            insights.append(
                f"Margin yako ya faida ({user_margin * 100:.1f}%) ni bora! "
                f"Wastani ni {avg_margin * 100:.1f}%."
            )
        elif margin_pct < self.PERCENTILE_BELOW:
            insights.append(
                f"Margin yako ({user_margin * 100:.1f}%) ni ya chini. "
                f"Jaribu kupunguza gharama au kuongeza bei."
            )

        # Growth insight
        if growth_pct >= self.PERCENTILE_EXCELLENT:
            insights.append(
                f"Biashara yako inakua kwa kasi! Ukuaji wa {user_growth:.0f}% "
                f"(wastani: {avg_growth:.0f}%)."
            )
        elif growth_pct < self.PERCENTILE_BELOW:
            insights.append(
                f"Ukuaji wako ni polepole ({user_growth:.0f}%) ukilinganishwa "
                f"na wastani ({avg_growth:.0f}%)."
            )

        return insights[:4]

    def _generate_insights_en(
        self,
        user_rev: float,
        user_margin: float,
        user_growth: float,
        avg_rev: float,
        avg_margin: float,
        avg_growth: float,
        rev_pct: float,
        margin_pct: float,
        growth_pct: float,
        group_desc: str,
    ) -> List[str]:
        """Generate English comparison insights.

        Args:
            user_*: User's metrics.
            avg_*: Peer averages.
            *_pct: Percentile ranks.
            group_desc: Description of comparison group.

        Returns:
            List of insight strings in English.
        """
        insights = []

        if rev_pct >= self.PERCENTILE_EXCELLENT:
            insights.append(
                f"Your sales are better than {rev_pct:.0f}% of {group_desc}!"
            )
        elif rev_pct >= self.PERCENTILE_GOOD:
            insights.append(
                f"Your sales are above average for {group_desc}."
            )
        elif rev_pct < self.PERCENTILE_BELOW:
            diff_pct = ((avg_rev - user_rev) / avg_rev * 100) if avg_rev > 0 else 0
            insights.append(
                f"Your sales are {diff_pct:.0f}% below average. "
                f"Consider marketing and quality improvements."
            )

        if margin_pct >= self.PERCENTILE_EXCELLENT:
            insights.append(
                f"Your profit margin ({user_margin * 100:.1f}%) is excellent! "
                f"Average is {avg_margin * 100:.1f}%."
            )
        elif margin_pct < self.PERCENTILE_BELOW:
            insights.append(
                f"Your margin ({user_margin * 100:.1f}%) is below average. "
                f"Try reducing costs or increasing prices."
            )

        if growth_pct >= self.PERCENTILE_EXCELLENT:
            insights.append(
                f"Your business is growing fast! {user_growth:.0f}% growth "
                f"(average: {avg_growth:.0f}%)."
            )
        elif growth_pct < self.PERCENTILE_BELOW:
            insights.append(
                f"Your growth ({user_growth:.0f}%) is slower than average ({avg_growth:.0f}%)."
            )

        return insights[:4]

    # -------------------------------------------------------------------
    # Empty Result
    # -------------------------------------------------------------------

    def _empty_result(
        self, peer_count: int, group_desc: str, locale: str, message: str
    ) -> ComparisonResult:
        """Return an empty comparison result.

        Args:
            peer_count: Number of peers found.
            group_desc: Group description.
            locale: Language.
            message: Explanation message.

        Returns:
            Empty ComparisonResult.
        """
        return ComparisonResult(
            revenue_percentile=50,
            revenue_vs_avg=0,
            revenue_vs_median=0,
            avg_peer_revenue=0,
            median_peer_revenue=0,
            margin_percentile=50,
            margin_vs_avg=0,
            avg_peer_margin=0,
            growth_percentile=50,
            growth_vs_avg=0,
            avg_peer_growth=0,
            transactions_percentile=50,
            transactions_vs_avg=0,
            avg_peer_transactions=0,
            diversity_percentile=50,
            diversity_vs_avg=0,
            avg_peer_diversity=0,
            savings_percentile=50,
            savings_vs_avg=0,
            avg_peer_savings=0,
            overall_percentile=50,
            peer_count=peer_count,
            comparison_group=group_desc,
            strengths_vs_peers=[],
            weaknesses_vs_peers=[],
            insights_sw=[message] if locale == "sw" else [],
            insights_en=[message] if locale == "en" else [],
            k_anonymity_met=False,
        )

    # -------------------------------------------------------------------
    # Rendering for WhatsApp
    # -------------------------------------------------------------------

    def render_for_whatsapp(
        self,
        result: ComparisonResult,
        locale: str = "sw",
    ) -> str:
        """Render comparison result as a WhatsApp-formatted message.

        Args:
            result: Comparison result.
            locale: Language.

        Returns:
            Formatted WhatsApp message string.
        """
        lines = []

        # Privacy notice
        if not result.k_anonymity_met:
            if locale == "sw":
                lines.append("🔒 *Ulinganisho:* Hakuna data ya kutosha ya kulinganisha")
            else:
                lines.append("🔒 *Comparison:* Not enough peer data for comparison")
            return "\n".join(lines)

        # Header
        if locale == "sw":
            lines.append(f"👥 *Ulinganisho na biashara zingine:*")
            lines.append(f"   Kundi: {result.comparison_group}")
            lines.append(f"   Biashara: {result.peer_count}+")
        else:
            lines.append(f"👥 *Peer Comparison:*")
            lines.append(f"   Group: {result.comparison_group}")
            lines.append(f"   Businesses: {result.peer_count}+")

        # Overall ranking
        lines.append("")
        overall_bar_len = int(result.overall_percentile / 10)
        overall_bar = BLOCK_SOLID * overall_bar_len + BLOCK_LIGHT * (10 - overall_bar_len)
        if locale == "sw":
            lines.append(f"📊 *Nafasi yako:* {result.overall_percentile:.0f}/100")
        else:
            lines.append(f"📊 *Your ranking:* {result.overall_percentile:.0f}/100")
        lines.append(f"   {overall_bar}")

        # Dimension comparisons
        lines.append("")
        dimensions = [
            ("revenue", "💰 Mauzo" if locale == "sw" else "💰 Revenue",
             result.revenue_percentile, result.revenue_vs_avg),
            ("margin", "📈 Faida" if locale == "sw" else "📈 Margin",
             result.margin_percentile, result.margin_vs_avg),
            ("growth", "🚀 Ukuaji" if locale == "sw" else "🚀 Growth",
             result.growth_percentile, result.growth_vs_avg),
            ("transactions", "🛒 Mauzo" if locale == "sw" else "🛒 Transactions",
             result.transactions_percentile, result.transactions_vs_avg),
            ("diversity", "📦 Bidhaa" if locale == "sw" else "📦 Products",
             result.diversity_percentile, result.diversity_vs_avg),
            ("savings", "🏦 Akiba" if locale == "sw" else "🏦 Savings",
             result.savings_percentile, result.savings_vs_avg),
        ]

        for _, label, pct, vs_avg in dimensions:
            bar_len = int(pct / 10)
            bar = BLOCK_FULL * bar_len + BLOCK_LIGHT * (10 - bar_len)
            arrow = ARROW_UP if vs_avg > 0 else (ARROW_DOWN if vs_avg < 0 else ARROW_RIGHT)
            lines.append(f"   {label}: {bar} {pct:.0f}% {arrow}")

        # Strengths
        if result.strengths_vs_peers:
            lines.append("")
            if locale == "sw":
                lines.append("✅ *Nguvu zako:*")
            else:
                lines.append("✅ *Your strengths:*")
            for s in result.strengths_vs_peers:
                lines.append(f"   • {s}")

        # Weaknesses
        if result.weaknesses_vs_peers:
            lines.append("")
            if locale == "sw":
                lines.append("⚠️ *Mapungufu:*")
            else:
                lines.append("⚠️ *Areas to improve:*")
            for w in result.weaknesses_vs_peers:
                lines.append(f"   • {w}")

        # Insights
        insights = result.insights_sw if locale == "sw" else result.insights_en
        if insights:
            lines.append("")
            if locale == "sw":
                lines.append("💡 *Vidokezo:*")
            else:
                lines.append("💡 *Insights:*")
            for insight in insights:
                lines.append(f"   • {insight}")

        # Privacy footer
        lines.append("")
        if locale == "sw":
            lines.append("🔒 Data yako ni ya faragha — tunatumia data iliyokusanywa tu.")
        else:
            lines.append("🔒 Your data is private — we use only aggregated data.")

        return "\n".join(lines)
