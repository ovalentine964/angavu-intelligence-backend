"""
WhatsApp Charts — Unicode block-character visualizations for WhatsApp messages.

Generates bar charts, progress bars, heatmaps, sparklines, and cash-flow
diagrams using Unicode characters that render correctly on all WhatsApp clients
(Android, iOS, Web) without images or external dependencies.

Character sets used:
  ▓ █ ░ ▏▎▍▌▋▊▉█ ─ │ ┼ ┐ ┘ ┌ └ ▲ ▼ ● ○ ◉ ◎ ★ ☆ ✦ ✧ ⬆ ⬇ ↗ ↘ ═ ║ ╔ ╗ ╚ ╝
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Full block characters for bar charts (light → dark)
BLOCK_LIGHT = "░"
BLOCK_MED = "▒"
BLOCK_FULL = "▓"
BLOCK_SOLID = "█"

# Fine-grained block characters (1/8 width increments)
BLOCK_EIGHTHS = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]

# Box-drawing for tables
BOX_H = "─"
BOX_V = "│"
BOX_CROSS = "┼"
BOX_T_TOP = "┬"
BOX_T_BOT = "┴"
BOX_T_LEFT = "├"
BOX_T_RIGHT = "┤"
BOX_CORNER_TL = "┌"
BOX_CORNER_TR = "┐"
BOX_CORNER_BL = "└"
BOX_CORNER_BR = "┘"
BOX_DOUBLE_H = "═"
BOX_DOUBLE_V = "║"
BOX_DOUBLE_TL = "╔"
BOX_DOUBLE_TR = "╗"
BOX_DOUBLE_BL = "╚"
BOX_DOUBLE_BR = "╝"

# Indicators
ARROW_UP = "↑"
ARROW_DOWN = "↓"
ARROW_RIGHT = "→"
ARROW_LEFT = "←"
ARROW_UP_RIGHT = "↗"
ARROW_DOWN_RIGHT = "↘"
DOT_FILLED = "●"
DOT_EMPTY = "○"
STAR_FILLED = "★"
STAR_EMPTY = "☆"
DIAMOND_FILLED = "◆"
DIAMOND_EMPTY = "◇"
CHECK = "✅"
CROSS_MARK = "❌"
WARNING = "⚠️"
INFO = "ℹ️"
LIGHTNING = "⚡"
FIRE = "🔥"
HEART = "❤️"

# Emoji indicators for mood/health
MOOD_GREAT = "📈"
MOOD_OK = "📊"
MOOD_SLOW = "📉"
HEALTH_GOOD = "✅"
HEALTH_WARN = "⚠️"
HEALTH_BAD = "❌"

# Day abbreviations in Swahili
SWAHILI_DAYS_SHORT = ["Jumapili", "Jumatatu", "Jumanne", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]
SWAHILI_DAYS_TINY = ["Jp", "Jt", "Jn", "Al", "Ij", "Js", "Jp"]
SWAHILI_MONTHS = [
    "Januari", "Februari", "Machi", "Aprili", "Mei", "Juni",
    "Julai", "Agosti", "Septemba", "Oktoba", "Novemba", "Desemba"
]
SWAHILI_MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"]


@dataclass
class ChartConfig:
    """Configuration for chart generation."""
    bar_width: int = 20              # Maximum bar width in characters
    bar_char: str = BLOCK_FULL       # Character used for filled bars
    empty_char: str = BLOCK_LIGHT    # Character used for empty space
    use_eighths: bool = True         # Use fine-grained 1/8 blocks for partial fills
    show_values: bool = True         # Show numeric values next to bars
    show_percentage: bool = False    # Show percentage labels
    currency_prefix: str = "KSh"     # Currency symbol
    thousands_sep: str = ","         # Thousands separator
    locale: str = "sw"               # "sw" = Swahili, "en" = English, "sh" = Sheng


# ---------------------------------------------------------------------------
# Formatting Utilities
# ---------------------------------------------------------------------------

def format_currency(amount: float, config: ChartConfig | None = None) -> str:
    """Format a number as Kenyan Shillings with thousand separators.

    Args:
        amount: The monetary amount.
        config: Optional chart config for locale settings.

    Returns:
        Formatted string, e.g. "KSh 12,500".
    """
    cfg = config or ChartConfig()
    if amount >= 1_000_000:
        return f"{cfg.currency_prefix} {amount / 1_000_000:,.1f}M"
    elif amount >= 100_000:
        return f"{cfg.currency_prefix} {amount / 1_000:,.0f}K"
    else:
        formatted = f"{amount:,.0f}".replace(",", cfg.thousands_sep)
        return f"{cfg.currency_prefix} {formatted}"


def format_number(n: int, config: ChartConfig | None = None) -> str:
    """Format a plain number with thousand separators."""
    cfg = config or ChartConfig()
    return f"{n:,.0f}".replace(",", cfg.thousands_sep)


def format_percentage(value: float, include_sign: bool = True) -> str:
    """Format a percentage with optional + sign for positive values.

    Args:
        value: The percentage value.
        include_sign: Whether to include +/- sign.

    Returns:
        Formatted string, e.g. "+15.2%" or "-3.1%".
    """
    if include_sign:
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.1f}%"
    return f"{value:.1f}%"


def change_indicator(value: float, threshold: float = 0.0) -> str:
    """Return an arrow indicator for positive/negative change.

    Args:
        value: The change value (percentage or absolute).
        threshold: Value at which to show neutral indicator.

    Returns:
        Arrow emoji string.
    """
    if value > threshold:
        return ARROW_UP
    elif value < -threshold:
        return ARROW_DOWN
    return ARROW_RIGHT


def mood_indicator(daily_sales: float, avg_sales: float) -> str:
    """Determine day mood based on sales vs average.

    Args:
        daily_sales: Today's total sales.
        avg_sales: Average daily sales.

    Returns:
        Mood emoji string.
    """
    if avg_sales == 0:
        return MOOD_OK
    ratio = daily_sales / avg_sales
    if ratio >= 1.2:
        return MOOD_GREAT
    elif ratio <= 0.8:
        return MOOD_SLOW
    return MOOD_OK


def mood_label(daily_sales: float, avg_sales: float, locale: str = "sw") -> str:
    """Return a human-readable mood label.

    Args:
        daily_sales: Today's total sales.
        avg_sales: Average daily sales.
        locale: Language code.

    Returns:
        Mood label string with emoji.
    """
    indicator = mood_indicator(daily_sales, avg_sales)
    labels = {
        "sw": {
            MOOD_GREAT: "Siku nzuri!",
            MOOD_OK: "Siku ya kawaida",
            MOOD_SLOW: "Siku tulivu",
        },
        "en": {
            MOOD_GREAT: "Good day!",
            MOOD_OK: "Normal day",
            MOOD_SLOW: "Slow day",
        },
        "sh": {
            MOOD_GREAT: "Siku poa!",
            MOOD_OK: "Siku tu",
            MOOD_SLOW: "Siku imeenda",
        },
    }
    lang = labels.get(locale, labels["sw"])
    return f"{indicator} {lang.get(indicator, lang[MOOD_OK])}"


# ---------------------------------------------------------------------------
# Bar Chart — Horizontal bars (primary chart type for WhatsApp)
# ---------------------------------------------------------------------------

class BarChart:
    """Horizontal bar chart generator using Unicode block characters.

    Creates aligned, labeled bar charts suitable for WhatsApp monospace display.
    Each bar line shows: LABEL ▓▓▓▓▓░░░ VALUE

    Example output::

        Jumatatu  ▓▓▓▓▓▓▓▓▓▓  KSh 4,100 ⭐
        Jumanne   ▓▓▓▓▓▓▓▓    KSh 3,200
        Alhamisi  ▓▓▓▓▓▓      KSh 2,400
    """

    def __init__(self, config: ChartConfig | None = None):
        self.config = config or ChartConfig()

    def render(
        self,
        data: dict[str, float],
        max_label_width: int = 12,
        highlight_max: bool = True,
        highlight_min: bool = False,
        max_star: str = " ⭐",
        min_star: str = "",
        sort_desc: bool = False,
        currency: bool = True,
        show_rank: bool = False,
    ) -> str:
        """Render a horizontal bar chart.

        Args:
            data: Dict of label → value.
            max_label_width: Width for label column (auto-calculated if 0).
            highlight_max: Add star emoji to highest value.
            highlight_min: Add marker to lowest value.
            max_star: Emoji/marker for max value.
            min_star: Emoji/marker for min value.
            sort_desc: Sort bars by value descending.
            currency: Format values as currency.
            show_rank: Show rank number before label.

        Returns:
            Multi-line string with the chart.
        """
        if not data:
            return "   (hakuna data)\n"

        cfg = self.config
        items = list(data.items())

        if sort_desc:
            items.sort(key=lambda x: x[1], reverse=True)

        # Calculate dimensions
        if max_label_width == 0:
            max_label_width = max(len(label) for label, _ in items)
        max_val = max(v for _, v in items) if items else 1
        if max_val == 0:
            max_val = 1
        min_val = min(v for _, v in items) if items else 0

        lines = []
        for i, (label, value) in enumerate(items):
            # Label
            label_str = label.ljust(max_label_width)

            # Rank prefix
            rank_prefix = ""
            if show_rank:
                rank_prefix = f"{i + 1}. "

            # Bar calculation
            bar_ratio = value / max_val
            full_blocks = int(bar_ratio * cfg.bar_width)

            if cfg.use_eighths:
                # Use fine-grained eighths for partial fill
                exact_chars = bar_ratio * cfg.bar_width
                full = int(exact_chars)
                eighth_idx = round((exact_chars - full) * 8)
                partial = BLOCK_EIGHTHS[min(eighth_idx, 8)] if eighth_idx > 0 and full < cfg.bar_width else ""
                empty_count = cfg.bar_width - full - (1 if partial else 0)
                bar = cfg.bar_char * full + partial + cfg.empty_char * max(empty_count, 0)
            else:
                bar = cfg.bar_char * full_blocks + cfg.empty_char * (cfg.bar_width - full_blocks)

            # Value
            if currency:
                val_str = format_currency(value, cfg)
            else:
                val_str = format_number(int(value), cfg)

            # Highlight markers
            marker = ""
            if highlight_max and value == max_val:
                marker = max_star
            if highlight_min and value == min_val and min_val != max_val:
                marker = min_star

            line = f"{rank_prefix}{label_str} {bar} {val_str}{marker}"
            lines.append(line)

        return "\n".join(lines) + "\n"

    def render_compact(
        self,
        data: dict[str, float],
        bar_width: int = 10,
        currency: bool = True,
    ) -> str:
        """Render a compact bar chart with shorter bars.

        Args:
            data: Dict of label → value.
            bar_width: Width of bars in characters.
            currency: Format values as currency.

        Returns:
            Multi-line string with compact chart.
        """
        cfg = self.config
        old_width = cfg.bar_width
        cfg.bar_width = bar_width
        result = self.render(data, max_label_width=8, currency=currency, highlight_max=True)
        cfg.bar_width = old_width
        return result

    def render_with_comparison(
        self,
        current: dict[str, float],
        previous: dict[str, float],
        max_label_width: int = 12,
    ) -> str:
        """Render bars with comparison to previous period.

        Args:
            current: Current period data.
            previous: Previous period data.
            max_label_width: Width for label column.

        Returns:
            Multi-line string with bars and change indicators.
        """
        cfg = self.config
        max_val = max(max(current.values(), default=1), max(previous.values(), default=1))
        if max_val == 0:
            max_val = 1

        lines = []
        for label, value in current.items():
            label_str = label.ljust(max_label_width)
            bar_ratio = value / max_val
            full = int(bar_ratio * cfg.bar_width)
            bar = cfg.bar_char * full + cfg.empty_char * (cfg.bar_width - full)
            val_str = format_currency(value, cfg)

            # Comparison
            prev_val = previous.get(label, 0)
            if prev_val > 0:
                change_pct = ((value - prev_val) / prev_val) * 100
                arrow = change_indicator(change_pct)
                change_str = f" {arrow}{abs(change_pct):.0f}%"
            else:
                change_str = ""

            lines.append(f"{label_str} {bar} {val_str}{change_str}")

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Progress Bar — Single value out of maximum
# ---------------------------------------------------------------------------

class ProgressBar:
    """Single progress bar using Unicode blocks.

    Example output::

        Akiba: ▓▓▓▓▓▓▓░░░░░░░░ 50% (KSh 25,000 / KSh 50,000)
    """

    def __init__(self, config: ChartConfig | None = None):
        self.config = config or ChartConfig()

    def render(
        self,
        current: float,
        maximum: float,
        width: int = 15,
        label: str | None = None,
        show_percentage: bool = True,
        show_values: bool = True,
        currency: bool = True,
    ) -> str:
        """Render a single progress bar.

        Args:
            current: Current value.
            maximum: Maximum/target value.
            width: Bar width in characters.
            label: Optional label prefix.
            show_percentage: Show percentage at end.
            show_values: Show current/maximum values.
            currency: Format values as currency.

        Returns:
            Single-line progress bar string.
        """
        cfg = self.config
        if maximum == 0:
            ratio = 0.0
        else:
            ratio = min(max(current / maximum, 0.0), 1.0)

        filled = int(ratio * width)
        empty = width - filled
        bar = cfg.bar_char * filled + cfg.empty_char * empty

        parts = []
        if label:
            parts.append(f"{label}:")
        parts.append(bar)

        if show_percentage:
            parts.append(f"{ratio * 100:.0f}%")

        if show_values:
            if currency:
                parts.append(f"({format_currency(current, cfg)} / {format_currency(maximum, cfg)})")
            else:
                parts.append(f"({int(current)} / {int(maximum)})")

        return " ".join(parts)

    def render_multi(
        self,
        items: list[tuple[str, float, float]],
        width: int = 15,
        currency: bool = True,
    ) -> str:
        """Render multiple progress bars.

        Args:
            items: List of (label, current, maximum) tuples.
            width: Bar width in characters.
            currency: Format values as currency.

        Returns:
            Multi-line string with progress bars.
        """
        lines = []
        for label, current, maximum in items:
            line = self.render(current, maximum, width=width, label=label, currency=currency)
            lines.append(line)
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Sparkline — Inline mini-chart for trends
# ---------------------------------------------------------------------------

class Sparkline:
    """Inline sparkline using Unicode block characters.

    Example output::

        Mwezi: ▁▂▃▄▅▆▇█
    """

    # Block characters from low to high
    SPARK_CHARS = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

    def render(
        self,
        values: Sequence[float],
        label: str | None = None,
        highlight_last: bool = False,
    ) -> str:
        """Render a sparkline from a sequence of values.

        Args:
            values: Sequence of numeric values.
            label: Optional label prefix.
            highlight_last: Wrap last value in parentheses.

        Returns:
            Single-line sparkline string.
        """
        if not values:
            return ""

        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val

        chars = []
        for i, v in enumerate(values):
            if val_range == 0:
                idx = 4  # middle character
            else:
                idx = int(((v - min_val) / val_range) * 7)
                idx = min(max(idx, 0), 7)

            char = self.SPARK_CHARS[idx]
            if highlight_last and i == len(values) - 1:
                char = f"({char})"
            chars.append(char)

        spark = "".join(chars)
        if label:
            return f"{label} {spark}"
        return spark

    def render_with_values(
        self,
        values: Sequence[float],
        labels: Sequence[str] | None = None,
        currency: bool = True,
    ) -> str:
        """Render sparkline with labeled values below.

        Args:
            values: Sequence of numeric values.
            labels: Optional labels for each value.
            currency: Format values as currency.

        Returns:
            Two-line string: sparkline + values.
        """
        cfg = ChartConfig()
        spark = self.render(values)

        if labels:
            val_parts = []
            for i, (v, l) in enumerate(zip(values, labels)):
                if currency:
                    val_parts.append(f"{l}: {format_currency(v, cfg)}")
                else:
                    val_parts.append(f"{l}: {int(v)}")
            vals_line = " | ".join(val_parts)
        else:
            if currency:
                vals_line = " → ".join(format_currency(v, cfg) for v in values)
            else:
                vals_line = " → ".join(str(int(v)) for v in values)

        return f"{spark}\n{vals_line}"


# ---------------------------------------------------------------------------
# Heatmap — Grid visualization for monthly patterns
# ---------------------------------------------------------------------------

class Heatmap:
    """Monthly heatmap using filled/empty blocks.

    Example output::

        Jan ░░░░  Januari — chini
        Feb ▓▓░░  Februari — wastani
        Mar ▓▓▓▓  Machi — juu sana
    """

    HEAT_LEVELS = ["░░░░", "▒░░░", "▒▒░░", "▒▒▒░", "▓▒▒░", "▓▓▒░", "▓▓▓░", "▓▓▓▒", "▓▓▓▓", "████"]

    def render(
        self,
        monthly_data: dict[str, float],
        label_width: int = 3,
        show_label: bool = True,
        locale: str = "sw",
    ) -> str:
        """Render a monthly heatmap.

        Args:
            monthly_data: Dict of month_key → value. Keys can be month numbers (1-12),
                         month names, or short names.
            label_width: Width for month label.
            show_label: Show descriptive label after heat bar.
            locale: Language for labels.

        Returns:
            Multi-line string with heatmap.
        """
        if not monthly_data:
            return "   (hakuna data)\n"

        values = list(monthly_data.values())
        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val

        lines = []
        for month_key, value in monthly_data.items():
            # Determine month label
            if isinstance(month_key, int) or month_key.isdigit():
                month_num = int(month_key)
                if locale == "sw":
                    label = SWAHILI_MONTHS_SHORT[month_num - 1]
                else:
                    label = f"Month {month_num}"
            else:
                label = str(month_key)[:label_width]

            # Heat level
            if val_range == 0:
                level = 5
            else:
                level = int(((value - min_val) / val_range) * 9)
                level = min(max(level, 0), 9)

            heat = self.HEAT_LEVELS[level]

            # Descriptive label
            desc = ""
            if show_label:
                if locale == "sw":
                    if level <= 2:
                        desc = " — chini"
                    elif level <= 5:
                        desc = " — wastani"
                    elif level <= 7:
                        desc = " — juu"
                    else:
                        desc = " — juu sana!"
                else:
                    if level <= 2:
                        desc = " — low"
                    elif level <= 5:
                        desc = " — average"
                    elif level <= 7:
                        desc = " — high"
                    else:
                        desc = " — very high!"

            lines.append(f"{label.ljust(3)} {heat}{desc}")

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Cash Flow Diagram — Money in vs Money out
# ---------------------------------------------------------------------------

class CashFlowDiagram:
    """Visual cash flow representation.

    Example output::

        ▶ Pesa inayoingia:
        ┌──────────────────────────────┐
        │ ████████████████████  KSh 18,500  │
        └──────────────────────────────┘

        ◀ Pesa inayotoka:
        ┌──────────────────────────────┐
        │ ▓▓▓▓▓▓▓▓▓▓▓▓▓        KSh 12,300  │
        └──────────────────────────────┘

        💰 Salio: KSh 6,200 ✅
    """

    def render(
        self,
        income: float,
        expenses: float,
        width: int = 25,
        show_balance: bool = True,
        locale: str = "sw",
    ) -> str:
        """Render a cash flow diagram.

        Args:
            income: Total money in.
            expenses: Total money out.
            width: Width of the flow bars.
            show_balance: Show balance line.
            locale: Language for labels.

        Returns:
            Multi-line cash flow diagram string.
        """
        cfg = ChartConfig()
        total = max(income, expenses, 1)

        # Income bar
        income_ratio = income / total
        income_filled = int(income_ratio * width)
        income_bar = BLOCK_SOLID * income_filled + BLOCK_LIGHT * (width - income_filled)

        # Expense bar
        expense_ratio = expenses / total
        expense_filled = int(expense_ratio * width)
        expense_bar = BLOCK_FULL * expense_filled + BLOCK_LIGHT * (width - expense_filled)

        if locale == "sw":
            in_label = "Pesa inayoingia"
            out_label = "Pesa inayotoka"
            balance_label = "Salio"
        elif locale == "sh":
            in_label = "Pesa inaingia"
            out_label = "Pesa inatoka"
            balance_label = "Salio"
        else:
            in_label = "Money In"
            out_label = "Money Out"
            balance_label = "Balance"

        # Determine health emoji
        balance = income - expenses
        if balance > 0:
            health = CHECK
        elif balance < 0:
            health = CROSS_MARK
        else:
            health = WARNING

        lines = [
            f"▶ *{in_label}:*",
            f"  {BLOCK_SOLID} {income_bar} {format_currency(income, cfg)}",
            "",
            f"◀ *{out_label}:*",
            f"  {BLOCK_FULL} {expense_bar} {format_currency(expenses, cfg)}",
        ]

        if show_balance:
            lines.append("")
            lines.append(f"💰 *{balance_label}:* {format_currency(balance, cfg)} {health}")

        return "\n".join(lines) + "\n"

    def render_weekly(
        self,
        daily_income: dict[str, float],
        daily_expenses: dict[str, float],
        bar_width: int = 15,
    ) -> str:
        """Render weekly cash flow with daily breakdown.

        Args:
            daily_income: Dict of day → income amount.
            daily_expenses: Dict of day → expense amount.
            bar_width: Width of each bar.

        Returns:
            Multi-line weekly cash flow string.
        """
        cfg = ChartConfig()
        lines = []

        for day in daily_income:
            inc = daily_income.get(day, 0)
            exp = daily_expenses.get(day, 0)
            total = max(inc, exp, 1)

            inc_filled = int((inc / total) * bar_width)
            exp_filled = int((exp / total) * bar_width)

            inc_bar = BLOCK_SOLID * inc_filled + BLOCK_LIGHT * (bar_width - inc_filled)
            exp_bar = BLOCK_FULL * exp_filled + BLOCK_LIGHT * (bar_width - exp_filled)

            balance = inc - exp
            bal_indicator = CHECK if balance >= 0 else CROSS_MARK

            lines.append(f"*{day}*")
            lines.append(f"  ▶ {inc_bar} {format_currency(inc, cfg)}")
            lines.append(f"  ◀ {exp_bar} {format_currency(exp, cfg)}")
            lines.append(f"  💰 {format_currency(balance, cfg)} {bal_indicator}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trend Line — Using block characters for mini line charts
# ---------------------------------------------------------------------------

class TrendLine:
    """Trend visualization using connected block characters.

    Example output::

        Mauzo ya miezi 6:
        ▁ ▂ ▃ ▅ ▆ █
        Jan Feb Mar Apr Mei Jun
    """

    TREND_CHARS = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

    def render(
        self,
        values: Sequence[float],
        labels: Sequence[str] | None = None,
        width: int = 30,
        show_trend_arrow: bool = True,
    ) -> str:
        """Render a trend line.

        Args:
            values: Sequence of values.
            labels: Optional labels for each point.
            width: Not used for character-based rendering (auto-sized).
            show_trend_arrow: Show overall trend direction.

        Returns:
            Multi-line trend visualization.
        """
        if not values:
            return ""

        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val

        chars = []
        for v in values:
            if val_range == 0:
                idx = 4
            else:
                idx = int(((v - min_val) / val_range) * 7)
                idx = min(max(idx, 0), 7)
            chars.append(self.TREND_CHARS[idx])

        trend_line = " ".join(chars)

        # Trend direction
        trend_arrow = ""
        if show_trend_arrow and len(values) >= 2:
            first_half = sum(values[: len(values) // 2])
            second_half = sum(values[len(values) // 2:])
            if second_half > first_half * 1.05:
                trend_arrow = f" {ARROW_UP_RIGHT} Ukuaji!"
            elif second_half < first_half * 0.95:
                trend_arrow = f" {ARROW_DOWN_RIGHT} Inapungua"

        lines = [trend_line + trend_arrow]

        if labels:
            # Pad labels to align with characters
            label_line = " ".join(l.center(1) for l in labels[: len(values)])
            lines.append(label_line)

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Table Builder — Simple text tables for WhatsApp
# ---------------------------------------------------------------------------

class TableBuilder:
    """Simple text table builder for WhatsApp messages.

    Note: WhatsApp doesn't render markdown tables. This creates
    aligned text using spaces and optional box-drawing characters.
    """

    def __init__(self, config: ChartConfig | None = None):
        self.config = config or ChartConfig()

    def render_simple(
        self,
        headers: list[str],
        rows: list[list[str]],
        align_right: list[int] | None = None,
    ) -> str:
        """Render a simple aligned table without box characters.

        Args:
            headers: Column headers.
            rows: List of row data.
            align_right: List of column indices to right-align.

        Returns:
            Multi-line aligned table string.
        """
        if not headers:
            return ""

        align_right = align_right or []

        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        # Build header
        header_parts = []
        for i, h in enumerate(headers):
            if i in align_right:
                header_parts.append(h.rjust(col_widths[i]))
            else:
                header_parts.append(h.ljust(col_widths[i]))
        header_line = "  ".join(header_parts)

        # Separator
        sep_line = "  ".join("─" * w for w in col_widths)

        # Build rows
        row_lines = []
        for row in rows:
            parts = []
            for i in range(len(headers)):
                cell = str(row[i]) if i < len(row) else ""
                if i in align_right:
                    parts.append(cell.rjust(col_widths[i]))
                else:
                    parts.append(cell.ljust(col_widths[i]))
            row_lines.append("  ".join(parts))

        return "\n".join([header_line, sep_line] + row_lines)

    def render_key_value(
        self,
        items: list[tuple[str, str]],
        separator: str = ":",
        indent: int = 3,
    ) -> str:
        """Render key-value pairs with aligned separators.

        Args:
            items: List of (key, value) tuples.
            separator: Character between key and value.
            indent: Left indentation spaces.

        Returns:
            Multi-line key-value string.
        """
        if not items:
            return ""

        max_key_len = max(len(k) for k, _ in items)
        prefix = " " * indent

        lines = []
        for key, value in items:
            padded_key = key.ljust(max_key_len)
            lines.append(f"{prefix}{padded_key} {separator} {value}")

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Divider / Separator
# ---------------------------------------------------------------------------

def divider(char: str = "═", width: int = 23, label: str | None = None) -> str:
    """Create a horizontal divider line.

    Args:
        char: Character to use.
        width: Width of the divider.
        label: Optional centered label.

    Returns:
        Divider string.
    """
    if label:
        # Center the label within the divider
        label_with_spaces = f" {label} "
        remaining = width - len(label_with_spaces)
        left = remaining // 2
        right = remaining - left
        return char * left + label_with_spaces + char * right
    return char * width


def section_header(title: str, icon: str = "📊") -> str:
    """Create a section header with icon.

    Args:
        title: Section title.
        icon: Emoji icon.

    Returns:
        Formatted section header string.
    """
    return f"\n{icon} *{title}:*"


# ---------------------------------------------------------------------------
# Emoji Number Converter — For visual number representation
# ---------------------------------------------------------------------------

def emoji_number(n: int) -> str:
    """Convert a number to emoji digits.

    Args:
        n: Integer to convert.

    Returns:
        String with emoji digits, e.g. 42 → "4️⃣2️⃣".
    """
    emoji_digits = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
    return "".join(emoji_digits[int(d)] for d in str(n))


# ---------------------------------------------------------------------------
# Star Rating — Visual 1-5 rating
# ---------------------------------------------------------------------------

def star_rating(rating: float, max_stars: int = 5) -> str:
    """Generate a star rating string.

    Args:
        rating: Rating value (0 to max_stars).
        max_stars: Maximum number of stars.

    Returns:
        Star string, e.g. "★★★★☆" for 4/5.
    """
    full = int(rating)
    half = 1 if rating - full >= 0.5 else 0
    empty = max_stars - full - half
    return STAR_FILLED * full + "⭐" * half + STAR_EMPTY * max(empty, 0)


# ---------------------------------------------------------------------------
# Health Score Display
# ---------------------------------------------------------------------------

def health_display(score: float, locale: str = "sw") -> str:
    """Render a health score with visual bar and label.

    Args:
        score: Score from 0 to 100.
        locale: Language.

    Returns:
        Multi-line health display string.
    """
    cfg = ChartConfig()

    # Determine level
    if score >= 80:
        emoji = "🟢"
        if locale == "sw":
            label = "Afya nzuri sana!"
        else:
            label = "Excellent!"
    elif score >= 60:
        emoji = "🟡"
        if locale == "sw":
            label = "Afya nzuri"
        else:
            label = "Good"
    elif score >= 40:
        emoji = "🟠"
        if locale == "sw":
            label = "Inahitaji kuboreshwa"
        else:
            label = "Needs improvement"
    else:
        emoji = "🔴"
        if locale == "sw":
            label = "Inahitaji msaada"
        else:
            label = "Needs help"

    # Progress bar
    bar_width = 15
    filled = int((score / 100) * bar_width)
    bar = BLOCK_SOLID * filled + BLOCK_LIGHT * (bar_width - filled)

    return f"{emoji} {score:.0f}/100 — {label}\n   {bar}"


# ---------------------------------------------------------------------------
# Convenience: Quick chart functions
# ---------------------------------------------------------------------------

def quick_bar(data: dict[str, float], currency: bool = True) -> str:
    """Quick horizontal bar chart. Returns formatted string."""
    chart = BarChart()
    return chart.render(data, currency=currency)


def quick_sparkline(values: Sequence[float], label: str | None = None) -> str:
    """Quick sparkline. Returns formatted string."""
    sl = Sparkline()
    return sl.render(values, label=label)


def quick_progress(current: float, maximum: float, label: str | None = None) -> str:
    """Quick progress bar. Returns formatted string."""
    pb = ProgressBar()
    return pb.render(current, maximum, label=label)


def quick_heatmap(monthly_data: dict[str, float], locale: str = "sw") -> str:
    """Quick monthly heatmap. Returns formatted string."""
    hm = Heatmap()
    return hm.render(monthly_data, locale=locale)


def quick_cashflow(income: float, expenses: float, locale: str = "sw") -> str:
    """Quick cash flow diagram. Returns formatted string."""
    cf = CashFlowDiagram()
    return cf.render(income, expenses, locale=locale)


def quick_trend(values: Sequence[float], labels: Sequence[str] | None = None) -> str:
    """Quick trend line. Returns formatted string."""
    tl = TrendLine()
    return tl.render(values, labels=labels)


# ---------------------------------------------------------------------------
# WhatsAppCharts — Chart image generation for WhatsApp reports
# ---------------------------------------------------------------------------

class WhatsAppCharts:
    """
    Generate chart images (PNG bytes) for WhatsApp report delivery.

    Uses matplotlib to create visual charts that are sent as images
    alongside text reports via WhatsApp.
    """

    def generate_weekly_sales_chart(self, report, language: str = "sw") -> bytes | None:
        """
        Generate a weekly sales bar chart as PNG bytes.

        Args:
            report: Weekly report data object
            language: Language for labels

        Returns:
            PNG image bytes, or None if generation fails
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            from io import BytesIO

            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(8, 4))

            # Extract daily data if available
            if hasattr(report, 'daily_sales') and report.daily_sales:
                days = list(report.daily_sales.keys())
                values = list(report.daily_sales.values())
            else:
                days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                values = [0] * 7

            colors = ['#2E86AB' if v > 0 else '#E8E8E8' for v in values]
            bars = ax.bar(days, values, color=colors, edgecolor='white', linewidth=0.5)

            for bar, val in zip(bars, values):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height(),
                            f'KSh {val:,.0f}', ha='center', va='bottom', fontsize=8)

            title = 'Mauzo ya Wiki' if language == 'sw' else 'Weekly Sales'
            ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
            ax.set_ylabel('KES', fontsize=10)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.set_ylim(0, max(values) * 1.2 if max(values) > 0 else 100)

            plt.tight_layout()

            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.warning("weekly_chart_generation_error", error=str(e))
            return None

    def generate_monthly_chart(self, metrics: dict, language: str = "sw") -> bytes | None:
        """
        Generate a monthly summary chart as PNG bytes.

        Shows: Sales, Costs, Profit as a grouped bar chart.

        Args:
            metrics: Monthly metrics dict
            language: Language for labels

        Returns:
            PNG image bytes, or None if generation fails
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            from io import BytesIO

            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(8, 4))

            categories = []
            values = []
            colors = []

            labels_map = {
                'sw': {'sales': 'Mauzo', 'costs': 'Gharama', 'profit': 'Faida'},
                'en': {'sales': 'Sales', 'costs': 'Costs', 'profit': 'Profit'},
            }
            labels = labels_map.get(language, labels_map['sw'])

            if metrics.get('total_sales', 0) > 0:
                categories.append(labels['sales'])
                values.append(metrics['total_sales'])
                colors.append('#2E86AB')
            costs = metrics.get('total_purchases', 0) + metrics.get('total_expenses', 0)
            if costs > 0:
                categories.append(labels['costs'])
                values.append(costs)
                colors.append('#E85D75')
            if metrics.get('net_profit', 0) != 0:
                categories.append(labels['profit'])
                values.append(metrics['net_profit'])
                colors.append('#4CAF50' if metrics['net_profit'] > 0 else '#E85D75')

            if not categories:
                return None

            bars = ax.bar(categories, values, color=colors, edgecolor='white', linewidth=0.5, width=0.6)

            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height(),
                        f'KSh {val:,.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

            title = 'Ripoti ya Mwezi' if language == 'sw' else 'Monthly Report'
            ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
            ax.set_ylabel('KES', fontsize=10)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            plt.tight_layout()

            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.warning("monthly_chart_generation_error", error=str(e))
            return None
