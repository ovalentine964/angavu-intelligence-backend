"""
Seasonal Analyzer — Msaidizi / Angavu Intelligence

Detects seasonal patterns in informal business data and generates
actionable insights in Swahili, English, and Sheng.

Seasonal patterns are critical for informal workers because:
- December is peak season (holidays, bonuses, Christmas)
- January is slow (back to school, post-holiday)
- March-June can be steady growth
- Agricultural seasons affect food prices
- School terms affect mama mboga sales

This module identifies these patterns from transaction data and
generates forward-looking advice so workers can prepare.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from .whatsapp_charts import (
    ARROW_DOWN,
    ARROW_UP,
    ARROW_UP_RIGHT,
    BLOCK_FULL,
    BLOCK_LIGHT,
    BLOCK_SOLID,
    CHECK,
    CROSS_MARK,
    FIRE,
    WARNING,
    format_currency,
    format_percentage,
    SWAHILI_MONTHS,
    SWAHILI_MONTHS_SHORT,
)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class MonthlyData:
    """Data for a single month."""
    year: int
    month: int              # 1-12
    revenue: float = 0.0
    expenses: float = 0.0
    profit: float = 0.0
    transactions: int = 0
    unique_products: int = 0
    top_product: str = ""
    top_product_revenue: float = 0.0
    active_days: int = 0


@dataclass
class SeasonalPattern:
    """A detected seasonal pattern."""
    pattern_type: str       # "peak", "slow", "growth", "decline", "stable"
    months: List[int]       # Months involved (1-12)
    description_sw: str     # Swahili description
    description_en: str     # English description
    confidence: float       # 0.0-1.0
    avg_revenue: float      # Average revenue during this pattern
    deviation_pct: float    # How much above/below average


@dataclass
class SeasonalInsight:
    """An actionable insight from seasonal analysis."""
    insight_type: str       # "prepare", "capitalize", "reduce", "watch"
    priority: str           # "high", "medium", "low"
    month_target: int       # Which month to act on
    message_sw: str         # Swahili message
    message_en: str         # English message
    action_sw: str          # What to do (Swahili)
    action_en: str          # What to do (English)


@dataclass
class SeasonalAnalysisResult:
    """Complete seasonal analysis result."""
    patterns: List[SeasonalPattern]
    insights: List[SeasonalInsight]
    best_months: List[Tuple[int, float]]       # (month, avg_revenue)
    worst_months: List[Tuple[int, float]]      # (month, avg_revenue)
    growth_months: List[Tuple[int, float]]     # Months with consistent growth
    monthly_averages: Dict[int, float]         # month → avg revenue
    overall_trend: str                          # "growing", "stable", "declining"
    trend_description_sw: str
    trend_description_en: str
    year_over_year_growth: Optional[float]      # If multi-year data available
    summary_sw: str
    summary_en: str


# ---------------------------------------------------------------------------
# Seasonal Analyzer
# ---------------------------------------------------------------------------

class SeasonalAnalyzer:
    """Detects and analyzes seasonal patterns in business data.

    Analysis methods:
    1. Monthly average comparison — which months are consistently above/below average?
    2. Year-over-year comparison — is the same month improving year over year?
    3. Trend detection — is the overall trajectory up, down, or flat?
    4. Pattern clustering — do certain months cluster together?
    5. Anomaly detection — are there unusual spikes or drops?

    Minimum data requirements:
    - 3 months for basic patterns
    - 6 months for reliable patterns
    - 12 months for full seasonal cycle
    - 24 months for year-over-year comparison
    """

    # Classification thresholds (deviation from average)
    PEAK_THRESHOLD = 0.10       # 10% above average = peak
    SLOW_THRESHOLD = -0.10      # 10% below average = slow
    SIGNIFICANT_PEAK = 0.25     # 25% above = significant peak
    SIGNIFICANT_SLOW = -0.25    # 25% below = significant slow

    # Minimum months of data for reliable analysis
    MIN_MONTHS_BASIC = 3
    MIN_MONTHS_RELIABLE = 6
    MIN_MONTHS_FULL_CYCLE = 12
    MIN_MONTHS_YOY = 24

    # Kenyan economic calendar (for contextual insights)
    KENYAN_SEASONS = {
        1: {"name": "Januari", "context": "Back to school, post-holiday slowdown", "context_sw": "Shule zinafunguliaka, biashara ni polepole"},
        2: {"name": "Februari", "context": "Recovery month, valentine's boost", "context_sw": "Biashara inaanza kupanda"},
        3: {"name": "Machi", "context": "School term steady, end of Q1", "context_sw": "Biashara ya kawaida"},
        4: {"name": "Aprili", "context": "Easter boost, school holiday", "context_sw": "Likizo za shule, biashara inapanda"},
        5: {"name": "Mei", "context": "School resumption, steady growth", "context_sw": "Shule zinarudi, biashara ya kawaida"},
        6: {"name": "Juni", "context": "Mid-year, budget season", "context_sw": "Mwaka wa kati"},
        7: {"name": "Julai", "context": "School holiday, higher spending", "context_sw": "Likizo za shule, matumizi ya juu"},
        8: {"name": "Agosti", "context": "Back to school, election effects", "context_sw": "Shule zinafunguliaka"},
        9: {"name": "Septemba", "context": "Third term, steady", "context_sw": "Muhula wa tatu, biashara ya kawaida"},
        10: {"name": "Oktoba", "context": "Build-up to holiday season", "context_sw": "Biashara inaanza kupanda"},
        11: {"name": "Novemba", "context": "Pre-holiday rush, Black Friday", "context_sw": "Msimu wa shukrani unaanza"},
        12: {"name": "Desemba", "context": "Peak holiday season, Christmas", "context_sw": "Msimu wa Krismasi — biashara bora!"},
    }

    # -------------------------------------------------------------------
    # Main Analysis
    # -------------------------------------------------------------------

    def analyze(
        self,
        monthly_data: List[MonthlyData],
        locale: str = "sw",
    ) -> SeasonalAnalysisResult:
        """Run complete seasonal analysis.

        Args:
            monthly_data: List of monthly data points (at least 3 months).
            locale: Language for output ("sw", "en", "sh").

        Returns:
            SeasonalAnalysisResult with patterns, insights, and summaries.
        """
        if len(monthly_data) < self.MIN_MONTHS_BASIC:
            return self._empty_result(
                "Hakuna data ya kutosha" if locale == "sw" else "Not enough data",
                locale,
            )

        # Calculate monthly averages
        monthly_averages = self._calculate_monthly_averages(monthly_data)

        # Detect patterns
        patterns = self._detect_patterns(monthly_data, monthly_averages, locale)

        # Classify months
        overall_avg = statistics.mean(m.revenue for m in monthly_data)
        best_months = self._classify_best_months(monthly_averages, overall_avg)
        worst_months = self._classify_worst_months(monthly_averages, overall_avg)
        growth_months = self._detect_growth_months(monthly_data)

        # Detect overall trend
        trend, trend_desc_sw, trend_desc_en = self._detect_trend(monthly_data)

        # Year-over-year growth
        yoy_growth = self._calculate_yoy_growth(monthly_data)

        # Generate insights
        insights = self._generate_insights(
            monthly_data, patterns, monthly_averages, overall_avg, locale
        )

        # Generate summary
        summary_sw = self._generate_summary_sw(
            patterns, best_months, worst_months, trend, yoy_growth
        )
        summary_en = self._generate_summary_en(
            patterns, best_months, worst_months, trend, yoy_growth
        )

        return SeasonalAnalysisResult(
            patterns=patterns,
            insights=insights,
            best_months=best_months,
            worst_months=worst_months,
            growth_months=growth_months,
            monthly_averages=monthly_averages,
            overall_trend=trend,
            trend_description_sw=trend_desc_sw,
            trend_description_en=trend_desc_en,
            year_over_year_growth=yoy_growth,
            summary_sw=summary_sw,
            summary_en=summary_en,
        )

    # -------------------------------------------------------------------
    # Monthly Averages
    # -------------------------------------------------------------------

    def _calculate_monthly_averages(
        self, monthly_data: List[MonthlyData]
    ) -> Dict[int, float]:
        """Calculate average revenue for each calendar month.

        Groups data by month number (1-12) across all years and computes
        the mean revenue for each month.

        Args:
            monthly_data: List of monthly data points.

        Returns:
            Dict of month_number (1-12) → average revenue.
        """
        month_buckets: Dict[int, List[float]] = defaultdict(list)

        for m in monthly_data:
            month_buckets[m.month].append(m.revenue)

        return {
            month: statistics.mean(revenues)
            for month, revenues in month_buckets.items()
            if revenues
        }

    # -------------------------------------------------------------------
    # Pattern Detection
    # -------------------------------------------------------------------

    def _detect_patterns(
        self,
        monthly_data: List[MonthlyData],
        monthly_averages: Dict[int, float],
        locale: str,
    ) -> List[SeasonalPattern]:
        """Detect seasonal patterns from the data.

        Identifies:
        - Peak months (consistently above average)
        - Slow months (consistently below average)
        - Growth periods (consecutive months of growth)
        - Decline periods (consecutive months of decline)

        Args:
            monthly_data: List of monthly data points.
            monthly_averages: Average revenue per calendar month.
            locale: Language.

        Returns:
            List of detected SeasonalPattern objects.
        """
        patterns = []
        overall_avg = statistics.mean(m.revenue for m in monthly_data)

        # Peak months
        peak_months = []
        for month, avg in monthly_averages.items():
            deviation = (avg - overall_avg) / overall_avg if overall_avg > 0 else 0
            if deviation >= self.PEAK_THRESHOLD:
                peak_months.append((month, avg, deviation))

        if peak_months:
            months_list = [m for m, _, _ in peak_months]
            avg_rev = statistics.mean(avg for _, avg, _ in peak_months)
            avg_dev = statistics.mean(dev for _, _, dev in peak_months)

            if locale == "sw":
                month_names = ", ".join(SWAHILI_MONTHS[m - 1] for m in sorted(months_list))
                desc = f"Msimu mzuri: {month_names} — mauzo ya juu kuliko wastani"
            else:
                month_names = ", ".join(SWAHILI_MONTHS[m - 1] for m in sorted(months_list))
                desc = f"Peak season: {month_names} — above average sales"

            patterns.append(SeasonalPattern(
                pattern_type="peak",
                months=sorted(months_list),
                description_sw=desc if locale == "sw" else desc,
                description_en=desc if locale == "en" else desc,
                confidence=min(len(peak_months) / 3, 1.0),
                avg_revenue=avg_rev,
                deviation_pct=avg_dev * 100,
            ))

        # Slow months
        slow_months = []
        for month, avg in monthly_averages.items():
            deviation = (avg - overall_avg) / overall_avg if overall_avg > 0 else 0
            if deviation <= self.SLOW_THRESHOLD:
                slow_months.append((month, avg, deviation))

        if slow_months:
            months_list = [m for m, _, _ in slow_months]
            avg_rev = statistics.mean(avg for _, avg, _ in slow_months)
            avg_dev = statistics.mean(dev for _, _, dev in slow_months)

            if locale == "sw":
                month_names = ", ".join(SWAHILI_MONTHS[m - 1] for m in sorted(months_list))
                desc = f"Msimu dhaifu: {month_names} — mauzo ya chini kuliko wastani"
            else:
                month_names = ", ".join(SWAHILI_MONTHS[m - 1] for m in sorted(months_list))
                desc = f"Slow season: {month_names} — below average sales"

            patterns.append(SeasonalPattern(
                pattern_type="slow",
                months=sorted(months_list),
                description_sw=desc if locale == "sw" else desc,
                description_en=desc if locale == "en" else desc,
                confidence=min(len(slow_months) / 3, 1.0),
                avg_revenue=avg_rev,
                deviation_pct=avg_dev * 100,
            ))

        # Growth periods (3+ consecutive months of growth)
        if len(monthly_data) >= 3:
            sorted_data = sorted(monthly_data, key=lambda m: (m.year, m.month))
            streak_start = 0
            for i in range(1, len(sorted_data)):
                if sorted_data[i].revenue > sorted_data[i - 1].revenue:
                    continue
                else:
                    streak_len = i - streak_start
                    if streak_len >= 3:
                        months_in_streak = [
                            sorted_data[j].month for j in range(streak_start, i)
                        ]
                        growth_pct = (
                            (sorted_data[i - 1].revenue - sorted_data[streak_start].revenue)
                            / sorted_data[streak_start].revenue * 100
                            if sorted_data[streak_start].revenue > 0 else 0
                        )
                        if locale == "sw":
                            desc = f"Ukuaji wa mfululizo: miezi {streak_len} mfululizo"
                        else:
                            desc = f"Growth streak: {streak_len} consecutive months"
                        patterns.append(SeasonalPattern(
                            pattern_type="growth",
                            months=months_in_streak,
                            description_sw=desc if locale == "sw" else desc,
                            description_en=desc if locale == "en" else desc,
                            confidence=min(streak_len / 6, 1.0),
                            avg_revenue=statistics.mean(
                                sorted_data[j].revenue for j in range(streak_start, i)
                            ),
                            deviation_pct=growth_pct,
                        ))
                    streak_start = i

        return patterns

    # -------------------------------------------------------------------
    # Month Classification
    # -------------------------------------------------------------------

    def _classify_best_months(
        self, monthly_averages: Dict[int, float], overall_avg: float
    ) -> List[Tuple[int, float]]:
        """Identify the best-performing months.

        Args:
            monthly_averages: Average revenue per calendar month.
            overall_avg: Overall average revenue.

        Returns:
            List of (month, avg_revenue) sorted by revenue descending.
        """
        above_avg = [
            (month, avg)
            for month, avg in monthly_averages.items()
            if avg >= overall_avg
        ]
        return sorted(above_avg, key=lambda x: x[1], reverse=True)

    def _classify_worst_months(
        self, monthly_averages: Dict[int, float], overall_avg: float
    ) -> List[Tuple[int, float]]:
        """Identify the worst-performing months.

        Args:
            monthly_averages: Average revenue per calendar month.
            overall_avg: Overall average revenue.

        Returns:
            List of (month, avg_revenue) sorted by revenue ascending.
        """
        below_avg = [
            (month, avg)
            for month, avg in monthly_averages.items()
            if avg < overall_avg
        ]
        return sorted(below_avg, key=lambda x: x[1])

    def _detect_growth_months(
        self, monthly_data: List[MonthlyData]
    ) -> List[Tuple[int, float]]:
        """Identify months with consistent year-over-year growth.

        Args:
            monthly_data: List of monthly data points.

        Returns:
            List of (month, growth_pct) for months showing growth.
        """
        # Group by month across years
        month_years: Dict[int, Dict[int, float]] = defaultdict(dict)
        for m in monthly_data:
            month_years[m.month][m.year] = m.revenue

        growth_months = []
        for month, year_data in month_years.items():
            if len(year_data) >= 2:
                years_sorted = sorted(year_data.items())
                latest = years_sorted[-1][1]
                previous = years_sorted[-2][1]
                if previous > 0:
                    growth = (latest - previous) / previous * 100
                    if growth > 0:
                        growth_months.append((month, growth))

        return sorted(growth_months, key=lambda x: x[1], reverse=True)

    # -------------------------------------------------------------------
    # Trend Detection
    # -------------------------------------------------------------------

    def _detect_trend(
        self, monthly_data: List[MonthlyData]
    ) -> Tuple[str, str, str]:
        """Detect overall business trend.

        Uses linear regression on monthly revenue to determine if the
        business is growing, stable, or declining.

        Args:
            monthly_data: List of monthly data points.

        Returns:
            Tuple of (trend_type, description_sw, description_en).
        """
        if len(monthly_data) < 2:
            return "stable", "Hakuna data ya kutosha", "Not enough data"

        sorted_data = sorted(monthly_data, key=lambda m: (m.year, m.month))
        revenues = [m.revenue for m in sorted_data]

        # Simple linear regression
        n = len(revenues)
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(revenues)

        numerator = sum((i - x_mean) * (r - y_mean) for i, r in enumerate(revenues))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator

        # Normalize slope as percentage of average revenue
        if y_mean > 0:
            slope_pct = (slope / y_mean) * 100
        else:
            slope_pct = 0

        if slope_pct > 3:
            trend = "growing"
            desc_sw = f"Biashara yako inakua! Mauzo yanaongezeka kwa ~{slope_pct:.0f}% kwa mwezi."
            desc_en = f"Your business is growing! Sales increasing ~{slope_pct:.0f}% per month."
        elif slope_pct < -3:
            trend = "declining"
            desc_sw = f"Biashara yako inapungua. Mauzo yanapungua kwa ~{abs(slope_pct):.0f}% kwa mwezi."
            desc_en = f"Your business is declining. Sales decreasing ~{abs(slope_pct):.0f}% per month."
        else:
            trend = "stable"
            desc_sw = "Biashara yako imara — mauzo ni ya kawaida."
            desc_en = "Your business is stable — sales are steady."

        return trend, desc_sw, desc_en

    # -------------------------------------------------------------------
    # Year-over-Year Growth
    # -------------------------------------------------------------------

    def _calculate_yoy_growth(
        self, monthly_data: List[MonthlyData]
    ) -> Optional[float]:
        """Calculate year-over-year growth if multi-year data available.

        Args:
            monthly_data: List of monthly data points.

        Returns:
            YoY growth percentage, or None if insufficient data.
        """
        # Group by year
        year_totals: Dict[int, float] = defaultdict(float)
        for m in monthly_data:
            year_totals[m.year] += m.revenue

        if len(year_totals) < 2:
            return None

        years_sorted = sorted(year_totals.items())
        latest_year = years_sorted[-1][1]
        previous_year = years_sorted[-2][1]

        if previous_year > 0:
            return (latest_year - previous_year) / previous_year * 100
        return None

    # -------------------------------------------------------------------
    # Insight Generation
    # -------------------------------------------------------------------

    def _generate_insights(
        self,
        monthly_data: List[MonthlyData],
        patterns: List[SeasonalPattern],
        monthly_averages: Dict[int, float],
        overall_avg: float,
        locale: str,
    ) -> List[SeasonalInsight]:
        """Generate actionable seasonal insights.

        Creates forward-looking advice based on detected patterns,
        Kenyan economic calendar, and historical data.

        Args:
            monthly_data: List of monthly data points.
            patterns: Detected seasonal patterns.
            monthly_averages: Average revenue per calendar month.
            overall_avg: Overall average revenue.
            locale: Language.

        Returns:
            List of SeasonalInsight objects.
        """
        insights = []

        # Current month context
        now = datetime.now()
        current_month = now.month

        # Generate insights for upcoming months (next 3 months)
        for i in range(1, 4):
            target_month = ((current_month - 1 + i) % 12) + 1
            season_info = self.KENYAN_SEASONS.get(target_month, {})

            # Check if this is a known peak or slow month
            is_peak = any(
                target_month in p.months and p.pattern_type == "peak"
                for p in patterns
            )
            is_slow = any(
                target_month in p.months and p.pattern_type == "slow"
                for p in patterns
            )

            month_avg = monthly_averages.get(target_month, overall_avg)
            deviation = (month_avg - overall_avg) / overall_avg if overall_avg > 0 else 0

            if is_peak:
                if locale == "sw":
                    msg = f"{SWAHILI_MONTHS[target_month - 1]} ni msimu wako mzuri! Jiandae mapema."
                    action = "Ongeza stock, ajiri msaidizi, weka bei nzuri"
                else:
                    msg = f"{SWAHILI_MONTHS[target_month - 1]} is your peak season! Prepare early."
                    action = "Increase stock, hire help, optimize pricing"
                insights.append(SeasonalInsight(
                    insight_type="prepare",
                    priority="high",
                    month_target=target_month,
                    message_sw=msg if locale == "sw" else msg,
                    message_en=msg if locale == "en" else msg,
                    action_sw=action if locale == "sw" else action,
                    action_en=action if locale == "en" else action,
                ))
            elif is_slow:
                if locale == "sw":
                    msg = f"{SWAHILI_MONTHS[target_month - 1]} ni msimu dhaifu. Punguza manunuzi."
                    action = "Punguza stock, kupunguza gharama, weka akiba"
                else:
                    msg = f"{SWAHILI_MONTHS[target_month - 1]} is a slow month. Reduce purchases."
                    action = "Reduce stock, cut costs, save more"
                insights.append(SeasonalInsight(
                    insight_type="reduce",
                    priority="medium",
                    month_target=target_month,
                    message_sw=msg if locale == "sw" else msg,
                    message_en=msg if locale == "en" else msg,
                    action_sw=action if locale == "sw" else action,
                    action_en=action if locale == "en" else action,
                ))

            # Kenyan calendar context
            if season_info:
                if target_month == 12:
                    if locale == "sw":
                        insights.append(SeasonalInsight(
                            insight_type="capitalize",
                            priority="high",
                            month_target=12,
                            message_sw="Desemba ni msimu bora zaidi! Krismasi na mwaka mpya.",
                            message_en="December is the best season! Christmas and New Year.",
                            action_sw="Ongeza bidhaa za Krismasi, ongeza bei kidogo, fungua mapema",
                            action_en="Add Christmas products, slight price increase, open early",
                        ))
                elif target_month == 1:
                    if locale == "sw":
                        insights.append(SeasonalInsight(
                            insight_type="watch",
                            priority="medium",
                            month_target=1,
                            message_sw="Januari ni polepole — watu wanalipa karo na kodi.",
                            message_en="January is slow — people paying school fees and rent.",
                            action_sw="Punguza manunuzi, fokus kwenye bidhaa za bei rahisi",
                            action_en="Reduce purchases, focus on affordable products",
                        ))

        # Limit insights
        return sorted(insights, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x.priority])[:8]

    # -------------------------------------------------------------------
    # Summary Generation
    # -------------------------------------------------------------------

    def _generate_summary_sw(
        self,
        patterns: List[SeasonalPattern],
        best_months: List[Tuple[int, float]],
        worst_months: List[Tuple[int, float]],
        trend: str,
        yoy_growth: Optional[float],
    ) -> str:
        """Generate Swahili summary of seasonal analysis.

        Args:
            patterns: Detected patterns.
            best_months: Best performing months.
            worst_months: Worst performing months.
            trend: Overall trend.
            yoy_growth: Year-over-year growth.

        Returns:
            Summary paragraph in Swahili.
        """
        parts = []

        # Trend
        if trend == "growing":
            parts.append("Biashara yako inakua vizuri!")
        elif trend == "declining":
            parts.append("Biashara yako inapungua — angalia sababu.")
        else:
            parts.append("Biashara yako imara.")

        # Best months
        if best_months:
            top = best_months[0]
            parts.append(
                f"Mwezi bora: {SWAHILI_MONTHS[top[0] - 1]} "
                f"(KSh {top[1]:,.0f} wastani)."
            )

        # Worst months
        if worst_months:
            bottom = worst_months[0]
            parts.append(
                f"Mwezi dhaifu: {SWAHILI_MONTHS[bottom[0] - 1]} "
                f"(KSh {bottom[1]:,.0f} wastani)."
            )

        # YoY growth
        if yoy_growth is not None:
            if yoy_growth > 0:
                parts.append(f"Ukuaji wa mwaka: +{yoy_growth:.0f}%!")
            else:
                parts.append(f"Mauzo ya mwaka yamepungua: {yoy_growth:.0f}%.")

        return " ".join(parts)

    def _generate_summary_en(
        self,
        patterns: List[SeasonalPattern],
        best_months: List[Tuple[int, float]],
        worst_months: List[Tuple[int, float]],
        trend: str,
        yoy_growth: Optional[float],
    ) -> str:
        """Generate English summary of seasonal analysis.

        Args:
            patterns: Detected patterns.
            best_months: Best performing months.
            worst_months: Worst performing months.
            trend: Overall trend.
            yoy_growth: Year-over-year growth.

        Returns:
            Summary paragraph in English.
        """
        parts = []

        if trend == "growing":
            parts.append("Your business is growing well!")
        elif trend == "declining":
            parts.append("Your business is declining — investigate causes.")
        else:
            parts.append("Your business is stable.")

        if best_months:
            top = best_months[0]
            parts.append(
                f"Best month: {SWAHILI_MONTHS[top[0] - 1]} "
                f"(avg KSh {top[1]:,.0f})."
            )

        if worst_months:
            bottom = worst_months[0]
            parts.append(
                f"Weakest month: {SWAHILI_MONTHS[bottom[0] - 1]} "
                f"(avg KSh {bottom[1]:,.0f})."
            )

        if yoy_growth is not None:
            if yoy_growth > 0:
                parts.append(f"Year-over-year growth: +{yoy_growth:.0f}%!")
            else:
                parts.append(f"Year-over-year decline: {yoy_growth:.0f}%.")

        return " ".join(parts)

    # -------------------------------------------------------------------
    # Empty Result
    # -------------------------------------------------------------------

    def _empty_result(self, message: str, locale: str) -> SeasonalAnalysisResult:
        """Return an empty analysis result when data is insufficient.

        Args:
            message: Error/explanation message.
            locale: Language.

        Returns:
            Empty SeasonalAnalysisResult.
        """
        return SeasonalAnalysisResult(
            patterns=[],
            insights=[],
            best_months=[],
            worst_months=[],
            growth_months=[],
            monthly_averages={},
            overall_trend="unknown",
            trend_description_sw=message if locale == "sw" else "",
            trend_description_en=message if locale == "en" else "",
            year_over_year_growth=None,
            summary_sw=message if locale == "sw" else "",
            summary_en=message if locale == "en" else "",
        )

    # -------------------------------------------------------------------
    # Rendering for WhatsApp
    # -------------------------------------------------------------------

    def render_for_whatsapp(
        self,
        result: SeasonalAnalysisResult,
        locale: str = "sw",
    ) -> str:
        """Render seasonal analysis as a WhatsApp-formatted message.

        Args:
            result: Analysis result.
            locale: Language.

        Returns:
            Formatted WhatsApp message string.
        """
        lines = []

        # Header
        if locale == "sw":
            lines.append("📅 *Msimu wa biashara:*")
        else:
            lines.append("📅 *Business Seasonality:*")

        # Monthly heatmap
        if result.monthly_averages:
            lines.append("")
            overall_avg = statistics.mean(result.monthly_averages.values())
            for month in sorted(result.monthly_averages.keys()):
                avg = result.monthly_averages[month]
                if overall_avg > 0:
                    ratio = avg / overall_avg
                else:
                    ratio = 1

                # Visual bar
                bar_len = int(ratio * 10)
                if ratio >= 1.2:
                    bar = BLOCK_SOLID * bar_len
                    indicator = " ⭐" if ratio >= 1.3 else ""
                elif ratio <= 0.8:
                    bar = BLOCK_FULL * bar_len + BLOCK_LIGHT * max(10 - bar_len, 0)
                    indicator = ""
                else:
                    bar = BLOCK_FULL * bar_len + BLOCK_LIGHT * max(10 - bar_len, 0)
                    indicator = ""

                label = SWAHILI_MONTHS_SHORT[month - 1]
                lines.append(f"{label} {bar} {format_currency(avg)}{indicator}")

        # Best and worst
        if result.best_months:
            lines.append("")
            if locale == "sw":
                best_label = "Msimu mzuri"
            else:
                best_label = "Peak season"
            best_names = ", ".join(
                SWAHILI_MONTHS[m - 1] for m, _ in result.best_months[:3]
            )
            lines.append(f"📈 *{best_label}:* {best_names}")

        if result.worst_months:
            if locale == "sw":
                worst_label = "Msimu dhaifu"
            else:
                worst_label = "Slow season"
            worst_names = ", ".join(
                SWAHILI_MONTHS[m - 1] for m, _ in result.worst_months[:3]
            )
            lines.append(f"📉 *{worst_label}:* {worst_names}")

        # Trend
        lines.append("")
        if locale == "sw":
            lines.append(f"📊 *Trendi:* {result.trend_description_sw}")
        else:
            lines.append(f"📊 *Trend:* {result.trend_description_en}")

        # YoY growth
        if result.year_over_year_growth is not None:
            arrow = ARROW_UP if result.year_over_year_growth > 0 else ARROW_DOWN
            lines.append(f"{arrow} *Ukuaji wa mwaka:* {format_percentage(result.year_over_year_growth)}")

        # Insights
        if result.insights:
            lines.append("")
            if locale == "sw":
                lines.append("💡 *Vidokezo vya msimu:*")
            else:
                lines.append("💡 *Seasonal tips:*")
            for insight in result.insights[:5]:
                if locale == "sw":
                    lines.append(f"   • {insight.message_sw}")
                    if insight.action_sw:
                        lines.append(f"     → {insight.action_sw}")
                else:
                    lines.append(f"   • {insight.message_en}")
                    if insight.action_en:
                        lines.append(f"     → {insight.action_en}")

        return "\n".join(lines)
