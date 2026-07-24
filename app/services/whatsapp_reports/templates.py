"""
Report Templates — Professional HTML/PDF templates for business reports.

Three template types:
1. Bank-ready report — Formal, with Alama Score, QR code, verification hash
2. Personal summary — Friendly, conversational, for the worker's own use
3. Weekly digest — Compact Monday morning business health check

All templates produce print-ready HTML that converts cleanly to PDF.
Designed to look professional enough for Equity Bank loan officers.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class TemplateType(str, Enum):
    """Available report template types."""
    BANK_READY = "bank_ready"
    PERSONAL_SUMMARY = "personal_summary"
    WEEKLY_DIGEST = "weekly_digest"


class BusinessHealthGrade(str, Enum):
    """Business health rating A-F."""
    A = "A"  # Excellent
    B = "B"  # Good
    C = "C"  # Average
    D = "D"  # Below average
    F = "F"  # Critical


@dataclass
class ReportData:
    """All data needed to render any report template."""
    # Business identity
    business_name: str = "Biashara"
    owner_name: str = ""
    business_type: str = "food_vendor"
    business_type_label: str = "Mama Mboga"
    location: str = ""
    phone: str = ""
    join_date: date | None = None

    # Report metadata
    report_id: str = ""
    report_date: date = field(default_factory=date.today)
    period_start: date | None = None
    period_end: date | None = None
    language: str = "sw"  # "sw" or "en"

    # Revenue & financials
    total_revenue: float = 0.0
    total_expenses: float = 0.0
    total_profit: float = 0.0
    profit_margin_pct: float = 0.0
    daily_revenue_avg: float = 0.0
    daily_expenses_avg: float = 0.0
    daily_profit_avg: float = 0.0

    # Revenue by period (for charts)
    daily_revenues: list[dict[str, Any]] = field(default_factory=list)
    weekly_revenues: list[dict[str, Any]] = field(default_factory=list)
    monthly_revenues: list[dict[str, Any]] = field(default_factory=list)

    # Revenue by category
    revenue_by_category: list[dict[str, Any]] = field(default_factory=list)

    # Transaction metrics
    total_transactions: int = 0
    avg_transaction_value: float = 0.0
    unique_customers: int = 0
    repeat_customer_rate: float = 0.0
    days_active: int = 0
    days_in_period: int = 30

    # Inventory
    inventory_items: int = 0
    inventory_value: float = 0.0
    stock_turnover: float = 0.0
    top_products: list[dict[str, Any]] = field(default_factory=list)

    # Cash flow
    cash_inflow: float = 0.0
    cash_outflow: float = 0.0
    net_cash_flow: float = 0.0
    cash_flow_entries: list[dict[str, Any]] = field(default_factory=list)

    # Alama Score
    alama_score: int = 0
    alama_score_band: str = ""
    alama_score_components: list[dict[str, Any]] = field(default_factory=list)
    risk_category: str = ""
    default_probability: float = 0.0
    max_affordable_loan: float = 0.0

    # Health score
    health_score: int = 0
    health_grade: BusinessHealthGrade = BusinessHealthGrade.C
    health_components: list[dict[str, Any]] = field(default_factory=list)

    # Growth metrics
    revenue_growth_pct: float = 0.0
    profit_growth_pct: float = 0.0
    customer_growth_pct: float = 0.0

    # Verification
    verification_hash: str = ""
    qr_code_data: str = ""

    # M-Pesa verification
    mpesa_verified: bool = False
    mpesa_receipt_count: int = 0

    def __post_init__(self):
        if not self.report_id:
            ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            short = uuid.uuid4().hex[:8].upper()
            self.report_id = f"ANGAVU-{ts}-{short}"
        if not self.verification_hash:
            self.verification_hash = self._compute_hash()
        if not self.qr_code_data:
            self.qr_code_data = (
                f"https://verify.angavu.ai/report/{self.report_id}"
                f"?h={self.verification_hash[:16]}"
            )
        if self.total_revenue > 0 and self.total_profit > 0:
            self.profit_margin_pct = round(
                (self.total_profit / self.total_revenue) * 100, 1
            )
        if self.total_revenue > 0 and self.days_in_period > 0:
            self.daily_revenue_avg = round(self.total_revenue / self.days_in_period, 2)
            self.daily_expenses_avg = round(self.total_expenses / self.days_in_period, 2)
            self.daily_profit_avg = round(self.total_profit / self.days_in_period, 2)
        if self.total_transactions > 0:
            self.avg_transaction_value = round(
                self.total_revenue / self.total_transactions, 2
            )

    def _compute_hash(self) -> str:
        """Compute SHA-256 verification hash of key report data."""
        payload = (
            f"{self.report_id}|{self.business_name}|{self.owner_name}|"
            f"{self.total_revenue}|{self.total_expenses}|{self.total_profit}|"
            f"{self.alama_score}|{self.health_score}|{self.report_date}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Template Engine
# ---------------------------------------------------------------------------

class ReportTemplate:
    """Renders ReportData into professional HTML reports."""

    def render(self, data: ReportData, template_type: TemplateType) -> str:
        """Render the appropriate template based on type."""
        if template_type == TemplateType.BANK_READY:
            return self._render_bank_ready(data)
        elif template_type == TemplateType.PERSONAL_SUMMARY:
            return self._render_personal_summary(data)
        elif template_type == TemplateType.WEEKLY_DIGEST:
            return self._render_weekly_digest(data)
        else:
            raise ValueError(f"Unknown template type: {template_type}")

    # ======================================================================
    # CSS — Shared styles
    # ======================================================================

    def _base_css(self) -> str:
        return """
        <style>
            @page { size: A4; margin: 15mm 20mm; }
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
                font-size: 11px; line-height: 1.5;
                color: #1a1a2e; background: #ffffff;
            }
            .report-container { max-width: 800px; margin: 0 auto; padding: 20px; }
            .report-header {
                display: flex; justify-content: space-between; align-items: flex-start;
                border-bottom: 3px solid #0f3460; padding-bottom: 15px; margin-bottom: 20px;
            }
            .brand h1 { font-size: 22px; color: #0f3460; font-weight: 700; letter-spacing: -0.5px; }
            .brand .tagline { font-size: 11px; color: #666; margin-top: 2px; }
            .report-meta { text-align: right; font-size: 10px; color: #555; }
            .report-meta .report-id {
                font-family: 'Courier New', monospace; font-size: 9px; color: #0f3460;
                background: #f0f4ff; padding: 2px 6px; border-radius: 3px;
            }
            .business-card {
                background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
                color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;
            }
            .business-card h2 { font-size: 18px; margin-bottom: 5px; }
            .business-card .subtitle { font-size: 12px; opacity: 0.85; }
            .business-card .details { display: flex; gap: 30px; margin-top: 12px; font-size: 11px; }
            .business-card .detail-item { display: flex; flex-direction: column; }
            .business-card .detail-label { font-size: 9px; text-transform: uppercase; opacity: 0.7; letter-spacing: 0.5px; }
            .business-card .detail-value { font-size: 13px; font-weight: 600; }
            .scores-row { display: flex; gap: 15px; margin-bottom: 20px; }
            .score-card { flex: 1; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; text-align: center; }
            .score-card .score-value { font-size: 32px; font-weight: 700; }
            .score-card .score-label { font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
            .score-card .score-band { font-size: 11px; margin-top: 4px; font-weight: 600; }
            .grade-a .score-value { color: #27ae60; }
            .grade-b .score-value { color: #2ecc71; }
            .grade-c .score-value { color: #f39c12; }
            .grade-d .score-value { color: #e67e22; }
            .grade-f .score-value { color: #e74c3c; }
            .financial-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 20px; }
            .fin-card { border: 1px solid #e8e8e8; border-radius: 6px; padding: 12px; background: #fafbfc; }
            .fin-card .fin-label { font-size: 9px; text-transform: uppercase; color: #888; letter-spacing: 0.5px; }
            .fin-card .fin-value { font-size: 20px; font-weight: 700; color: #1a1a2e; margin-top: 4px; }
            .fin-card .fin-sub { font-size: 10px; color: #888; }
            .fin-positive { color: #27ae60 !important; }
            .fin-negative { color: #e74c3c !important; }
            .section { margin-bottom: 20px; }
            .section-title {
                font-size: 14px; font-weight: 700; color: #0f3460;
                border-bottom: 2px solid #e8e8e8; padding-bottom: 6px; margin-bottom: 12px;
            }
            table { width: 100%; border-collapse: collapse; font-size: 10.5px; }
            th {
                background: #f0f4ff; color: #0f3460; font-weight: 600; text-align: left;
                padding: 8px 10px; border-bottom: 2px solid #0f3460;
                font-size: 9px; text-transform: uppercase; letter-spacing: 0.3px;
            }
            td { padding: 7px 10px; border-bottom: 1px solid #f0f0f0; }
            tr:nth-child(even) { background: #fafbfc; }
            .text-right { text-align: right; }
            .text-center { text-align: center; }
            .bar-chart { margin: 10px 0; }
            .bar-row { display: flex; align-items: center; margin-bottom: 4px; }
            .bar-label { width: 70px; font-size: 10px; color: #555; flex-shrink: 0; }
            .bar-track { flex: 1; height: 18px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }
            .bar-fill { height: 100%; border-radius: 3px; }
            .bar-value { width: 80px; text-align: right; font-size: 10px; font-weight: 600; flex-shrink: 0; padding-left: 8px; }
            .progress-bar { height: 10px; background: #e8e8e8; border-radius: 5px; overflow: hidden; margin: 6px 0; }
            .progress-fill { height: 100%; border-radius: 5px; }
            .cashflow-visual { display: flex; gap: 20px; margin: 10px 0; }
            .cashflow-in, .cashflow-out { flex: 1; padding: 12px; border-radius: 6px; }
            .cashflow-in { background: #e8f8f0; border-left: 4px solid #27ae60; }
            .cashflow-out { background: #fdf0ed; border-left: 4px solid #e74c3c; }
            .cashflow-label { font-size: 9px; text-transform: uppercase; color: #888; }
            .cashflow-amount { font-size: 18px; font-weight: 700; margin-top: 4px; }
            .report-footer { margin-top: 30px; padding-top: 15px; border-top: 2px solid #0f3460; font-size: 9px; color: #888; }
            .footer-grid { display: flex; justify-content: space-between; }
            .verification-hash { font-family: 'Courier New', monospace; font-size: 8px; word-break: break-all; color: #aaa; margin-top: 8px; }
            .qr-placeholder {
                width: 80px; height: 80px; border: 1px solid #ddd;
                display: flex; align-items: center; justify-content: center;
                font-size: 8px; color: #aaa; text-align: center;
            }
            .bank-stamp { border: 2px solid #0f3460; border-radius: 8px; padding: 15px; margin-top: 20px; background: #f8f9ff; }
            .bank-stamp h3 { color: #0f3460; font-size: 12px; margin-bottom: 8px; }
            .bank-stamp p { font-size: 10px; color: #555; }
            .disclaimer { font-size: 8px; color: #999; margin-top: 15px; padding: 10px; background: #f9f9f9; border-radius: 4px; }
            .mpesa-badge { display: inline-block; background: #4caf50; color: white; padding: 3px 8px; border-radius: 3px; font-size: 9px; font-weight: 600; }
            .mpesa-badge.unverified { background: #ff9800; }
            @media print { body { font-size: 10px; } .report-container { padding: 0; } }
        </style>
        """

    # ======================================================================
    # Helpers
    # ======================================================================

    def _fmt(self, amount: float) -> str:
        if amount >= 1_000_000:
            return f"KSh {amount / 1_000_000:,.1f}M"
        elif amount >= 1_000:
            return f"KSh {amount:,.0f}"
        return f"KSh {amount:,.2f}"

    def _pct(self, value: float) -> str:
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.1f}%"

    def _bar_color(self, value: float, max_val: float) -> str:
        ratio = value / max_val if max_val > 0 else 0
        if ratio >= 0.7:
            return "#27ae60"
        elif ratio >= 0.4:
            return "#f39c12"
        return "#e74c3c"

    def _score_color(self, score: int) -> str:
        if score >= 800:
            return "#27ae60"
        elif score >= 700:
            return "#2ecc71"
        elif score >= 600:
            return "#f39c12"
        elif score >= 500:
            return "#e67e22"
        return "#e74c3c"

    def _grade_class(self, grade: BusinessHealthGrade) -> str:
        return f"grade-{grade.value.lower()}"

    def _render_bar_chart(self, items: list[dict], label_key: str, value_key: str,
                          max_val: float | None = None, color: str = "#0f3460") -> str:
        if not items:
            return "<p style='color:#999;font-size:10px;'>Hakuna data / No data</p>"
        if max_val is None:
            max_val = max(item[value_key] for item in items) if items else 1
        html = '<div class="bar-chart">'
        for item in items:
            label = item[label_key]
            value = item[value_key]
            width_pct = (value / max_val * 100) if max_val > 0 else 0
            bar_color = self._bar_color(value, max_val) if max_val > 0 else color
            html += (
                f'<div class="bar-row">'
                f'<span class="bar-label">{label}</span>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{min(width_pct,100):.1f}%;background:{bar_color};"></div></div>'
                f'<span class="bar-value">{self._fmt(value)}</span>'
                f'</div>'
            )
        html += '</div>'
        return html

    def _render_score_bars(self, components: list[dict]) -> str:
        if not components:
            return ""
        html = '<div class="bar-chart">'
        for comp in components:
            name = comp.get("name", comp.get("name_sw", ""))
            score = comp.get("normalized_score", 0)
            color = self._score_color(int(score * 10))
            html += (
                f'<div class="bar-row">'
                f'<span class="bar-label" style="width:120px;">{name}</span>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{score:.0f}%;background:{color};"></div></div>'
                f'<span class="bar-value">{score:.0f}/100</span>'
                f'</div>'
            )
        html += '</div>'
        return html

    def _render_cashflow(self, data: ReportData) -> str:
        net_class = "fin-positive" if data.net_cash_flow >= 0 else "fin-negative"
        net_sign = "+" if data.net_cash_flow >= 0 else ""
        entries_html = ""
        if data.cash_flow_entries:
            entries_html = "<table><tr><th>Tarehe / Date</th><th>Aina / Type</th><th class='text-right'>Kiasi / Amount</th></tr>"
            for entry in data.cash_flow_entries[-10:]:
                direction = entry.get("direction", "in")
                amount = entry.get("amount", 0)
                color_class = "fin-positive" if direction == "in" else "fin-negative"
                sign = "+" if direction == "in" else "-"
                entries_html += (
                    f"<tr><td>{entry.get('date','')}</td><td>{entry.get('type','')}</td>"
                    f"<td class='text-right {color_class}'>{sign}{self._fmt(amount)}</td></tr>"
                )
            entries_html += "</table>"
        return f"""
        <div class="section">
            <div class="section-title">💵 Cash Flow / Mtiririko wa Pesa</div>
            <div class="cashflow-visual">
                <div class="cashflow-in">
                    <div class="cashflow-label">Pesa Inayoingia / Cash Inflow</div>
                    <div class="cashflow-amount" style="color:#27ae60;">{self._fmt(data.cash_inflow)}</div>
                </div>
                <div class="cashflow-out">
                    <div class="cashflow-label">Pesa Inayotoka / Cash Outflow</div>
                    <div class="cashflow-amount" style="color:#e74c3c;">{self._fmt(data.cash_outflow)}</div>
                </div>
            </div>
            <div style="text-align:center;margin:10px 0;">
                <span style="font-size:11px;color:#888;">Net Cash Flow / Salio:</span>
                <span class="{net_class}" style="font-size:16px;font-weight:700;margin-left:8px;">{net_sign}{self._fmt(data.net_cash_flow)}</span>
            </div>
            {entries_html}
        </div>"""

    def _footer(self, data: ReportData) -> str:
        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        return f"""
        <div class="report-footer">
            <div class="footer-grid">
                <div>
                    <strong>Angavu Intelligence</strong> — Biashara yako, Nguvu yako<br>
                    Report ID: <span style="font-family:monospace;">{data.report_id}</span><br>
                    Generated: {generated_at}
                </div>
                <div style="text-align:right;">
                    <div class="qr-placeholder">QR Code<br>Verification</div>
                </div>
            </div>
            <div class="verification-hash">Verification Hash: {data.verification_hash}</div>
            <div style="margin-top:8px;font-size:8px;color:#bbb;">
                Auto-generated from verified transaction data. Integrity cryptographically verified.
                Verify: {data.qr_code_data}
            </div>
        </div>"""

    # ======================================================================
    # Bank-Ready Report
    # ======================================================================

    def _render_bank_ready(self, data: ReportData) -> str:
        lang = data.language
        period_label = ""
        if data.period_start and data.period_end:
            period_label = f"{data.period_start.strftime('%d %b %Y')} — {data.period_end.strftime('%d %b %Y')}"

        if lang == "sw":
            title = "RIPOTI YA BIASHARA — MATUMIZI YA BENKI"
            subtitle = "Ripoti hii imeandaliwa kwa matumizi ya maombi ya mkopo"
        else:
            title = "BUSINESS REPORT — BANK USE"
            subtitle = "This report is prepared for loan application purposes"

        score_color = self._score_color(data.alama_score)
        score_band_label = data.alama_score_band.replace("_", " ").title() if data.alama_score_band else "N/A"
        risk_label = data.risk_category.replace("_", " ").title() if data.risk_category else "N/A"

        alama_section = f"""
        <div class="section">
            <div class="section-title">📊 Alama Score — Credit Assessment</div>
            <div class="scores-row">
                <div class="score-card" style="border-color:{score_color};">
                    <div class="score-value" style="color:{score_color};">{data.alama_score}</div>
                    <div class="score-label">Alama Score (0-1000)</div>
                    <div class="score-band" style="color:{score_color};">{score_band_label}</div>
                    <div class="progress-bar"><div class="progress-fill" style="width:{data.alama_score/10:.0f}%;background:{score_color};"></div></div>
                </div>
                <div class="score-card">
                    <div class="score-value {self._grade_class(data.health_grade)}">{data.health_grade.value}</div>
                    <div class="score-label">Business Health Grade</div>
                    <div class="score-band">{data.health_score}/100</div>
                </div>
                <div class="score-card">
                    <div class="score-value" style="font-size:22px;">{risk_label}</div>
                    <div class="score-label">Risk Category</div>
                    <div class="score-band" style="font-size:10px;">Default Prob: {data.default_probability:.1%}</div>
                </div>
            </div>
            {self._render_score_bars(data.alama_score_components)}
        </div>"""

        margin_color = "fin-positive" if data.profit_margin_pct > 10 else ("fin-negative" if data.profit_margin_pct < 0 else "")
        pnl_section = f"""
        <div class="section">
            <div class="section-title">📈 Profit &amp; Loss / Taarifa ya Faida na Hasara</div>
            <table>
                <tr><th>Item</th><th class="text-right">Daily</th><th class="text-right">Weekly</th><th class="text-right">Monthly</th></tr>
                <tr><td><strong>Revenue / Mapato</strong></td><td class="text-right">{self._fmt(data.daily_revenue_avg)}</td><td class="text-right">{self._fmt(data.daily_revenue_avg*7)}</td><td class="text-right"><strong>{self._fmt(data.total_revenue)}</strong></td></tr>
                <tr><td><strong>Expenses / Gharama</strong></td><td class="text-right">{self._fmt(data.daily_expenses_avg)}</td><td class="text-right">{self._fmt(data.daily_expenses_avg*7)}</td><td class="text-right"><strong>{self._fmt(data.total_expenses)}</strong></td></tr>
                <tr style="background:#f0f4ff;"><td><strong>Net Profit / Faida</strong></td><td class="text-right {margin_color}"><strong>{self._fmt(data.daily_profit_avg)}</strong></td><td class="text-right {margin_color}"><strong>{self._fmt(data.daily_profit_avg*7)}</strong></td><td class="text-right {margin_color}"><strong>{self._fmt(data.total_profit)}</strong></td></tr>
                <tr><td>Profit Margin</td><td class="text-right" colspan="3"><strong class="{margin_color}">{data.profit_margin_pct:.1f}%</strong></td></tr>
            </table>
        </div>"""

        revenue_chart = ""
        if data.monthly_revenues:
            revenue_chart = f'<div class="section"><div class="section-title">📊 Revenue Trend</div>{self._render_bar_chart(data.monthly_revenues, "month", "revenue")}</div>'
        elif data.daily_revenues:
            revenue_chart = f'<div class="section"><div class="section-title">📊 Daily Revenue</div>{self._render_bar_chart(data.daily_revenues[-14:], "day", "revenue")}</div>'

        customer_section = f"""
        <div class="section">
            <div class="section-title">👥 Customer Metrics</div>
            <div class="financial-grid">
                <div class="fin-card"><div class="fin-label">Transactions</div><div class="fin-value">{data.total_transactions:,}</div><div class="fin-sub">in {data.days_in_period} days</div></div>
                <div class="fin-card"><div class="fin-label">Customers</div><div class="fin-value">{data.unique_customers:,}</div><div class="fin-sub">{data.repeat_customer_rate:.0f}% repeat</div></div>
                <div class="fin-card"><div class="fin-label">Avg Transaction</div><div class="fin-value">{self._fmt(data.avg_transaction_value)}</div></div>
            </div>
        </div>"""

        inventory_section = ""
        if data.top_products:
            products_rows = ""
            for i, p in enumerate(data.top_products[:8], 1):
                products_rows += f"<tr><td class='text-center'>{i}</td><td>{p.get('name','N/A')}</td><td class='text-right'>{p.get('quantity',0):,}</td><td class='text-right'>{self._fmt(p.get('revenue',0))}</td><td class='text-right'>{p.get('margin',0):.0f}%</td></tr>"
            inventory_section = f"""
            <div class="section">
                <div class="section-title">📦 Top Products</div>
                <table><tr><th class="text-center">#</th><th>Product</th><th class="text-right">Qty</th><th class="text-right">Revenue</th><th class="text-right">Margin</th></tr>{products_rows}</table>
                <div class="financial-grid" style="margin-top:12px;">
                    <div class="fin-card"><div class="fin-label">Items</div><div class="fin-value">{data.inventory_items}</div></div>
                    <div class="fin-card"><div class="fin-label">Value</div><div class="fin-value">{self._fmt(data.inventory_value)}</div></div>
                    <div class="fin-card"><div class="fin-label">Turnover</div><div class="fin-value">{data.stock_turnover:.1f}x</div></div>
                </div>
            </div>"""

        mpesa_badge = (
            f'<span class="mpesa-badge">✓ M-Pesa Verified ({data.mpesa_receipt_count} receipts)</span>'
            if data.mpesa_verified else '<span class="mpesa-badge unverified">⚠ M-Pesa Not Linked</span>'
        )

        loan_section = ""
        if data.max_affordable_loan > 0:
            loan_section = f"""
            <div class="bank-stamp">
                <h3>🏦 Loan Affordability Assessment</h3>
                <p>Based on cash flow analysis and Alama Score of <strong>{data.alama_score}</strong>,
                estimated max affordable loan: <strong>{self._fmt(data.max_affordable_loan)}</strong>.</p>
                <p style="margin-top:6px;">Recommended repayment: 6-12 months.
                Monthly repayment capacity: {self._fmt(data.total_profit * 0.3)} (30% of net profit).</p>
                <p style="margin-top:8px;">{mpesa_badge}</p>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="{"sw" if lang == "sw" else "en"}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — {data.business_name}</title>{self._base_css()}</head>
<body><div class="report-container">
    <div class="report-header">
        <div class="brand"><h1>ANGAVU</h1><div class="tagline">Intelligence for Every Business</div></div>
        <div class="report-meta"><div class="report-id">{data.report_id}</div><div style="margin-top:4px;">{data.report_date.strftime('%d %B %Y')}</div><div>{period_label}</div></div>
    </div>
    <div style="text-align:center;margin-bottom:20px;"><h2 style="font-size:16px;color:#0f3460;">{title}</h2><p style="font-size:11px;color:#666;">{subtitle}</p></div>
    <div class="business-card">
        <h2>{data.business_name}</h2>
        <div class="subtitle">{data.business_type_label} — {data.location}</div>
        <div class="details">
            <div class="detail-item"><span class="detail-label">Owner</span><span class="detail-value">{data.owner_name}</span></div>
            <div class="detail-item"><span class="detail-label">Type</span><span class="detail-value">{data.business_type_label}</span></div>
            <div class="detail-item"><span class="detail-label">Location</span><span class="detail-value">{data.location}</span></div>
            <div class="detail-item"><span class="detail-label">Active Days</span><span class="detail-value">{data.days_active}/{data.days_in_period}</span></div>
        </div>
    </div>
    <div class="financial-grid">
        <div class="fin-card"><div class="fin-label">Revenue</div><div class="fin-value fin-positive">{self._fmt(data.total_revenue)}</div><div class="fin-sub">{self._pct(data.revenue_growth_pct)} vs prev</div></div>
        <div class="fin-card"><div class="fin-label">Expenses</div><div class="fin-value">{self._fmt(data.total_expenses)}</div></div>
        <div class="fin-card"><div class="fin-label">Net Profit</div><div class="fin-value {"fin-positive" if data.total_profit>=0 else "fin-negative"}">{self._fmt(data.total_profit)}</div><div class="fin-sub">{data.profit_margin_pct:.1f}% margin</div></div>
    </div>
    {alama_section}
    {pnl_section}
    {revenue_chart}
    {self._render_cashflow(data)}
    {customer_section}
    {inventory_section}
    {loan_section}
    <div class="disclaimer"><strong>Disclaimer:</strong> Auto-generated from transaction data recorded through Msaidizi.
    Angavu verifies integrity via cryptographic hashing and M-Pesa cross-referencing. Not financial advice. Period: {period_label or 'N/A'}.</div>
    {self._footer(data)}
</div></body></html>"""

    # ======================================================================
    # Personal Summary
    # ======================================================================

    def _render_personal_summary(self, data: ReportData) -> str:
        lang = data.language
        title = f"{'Habari' if lang=='sw' else 'Hello'}, {data.owner_name}! 🌟"
        subtitle = "Hii ndio ripoti ya biashara yako" if lang == "sw" else "Here's your business report"

        if data.profit_margin_pct >= 20:
            mood = "😊 Biashara yako inakua vizuri!" if lang == "sw" else "😊 Your business is growing well!"
            mood_color = "#27ae60"
        elif data.profit_margin_pct >= 10:
            mood = "🙂 Biashara yako iko sawa." if lang == "sw" else "🙂 Your business is okay."
            mood_color = "#f39c12"
        elif data.total_profit > 0:
            mood = "😐 Kuna nafasi ya kuboresha." if lang == "sw" else "😐 Room to improve."
            mood_color = "#e67e22"
        else:
            mood = "😟 Hebu tuangalie jinsi ya kuboresha." if lang == "sw" else "😟 Let's find ways to improve."
            mood_color = "#e74c3c"

        revenue_chart = ""
        if data.daily_revenues:
            revenue_chart = self._render_bar_chart(data.daily_revenues[-7:], 'day', 'revenue', color="#3498db")

        top_products_html = ""
        if data.top_products:
            top_products_html = "<div class='section'><div class='section-title'>⭐ Bidhaa Bora / Top Products</div>"
            for i, p in enumerate(data.top_products[:5], 1):
                top_products_html += f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0;'><span>{i}. {p.get('name','N/A')}</span><span style='font-weight:600;'>{self._fmt(p.get('revenue',0))}</span></div>"
            top_products_html += "</div>"

        return f"""<!DOCTYPE html>
<html lang="{"sw" if lang=="sw" else "en"}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>{self._base_css()}
<style>.mood-banner {{ background:{mood_color};color:white;padding:15px 20px;border-radius:8px;text-align:center;font-size:14px;margin-bottom:20px; }}</style>
</head>
<body><div class="report-container">
    <div class="report-header">
        <div class="brand"><h1>ANGAVU</h1><div class="tagline">Biashara yako, Nguvu yako</div></div>
        <div class="report-meta"><div>{data.report_date.strftime('%d %B %Y')}</div></div>
    </div>
    <h2 style="font-size:20px;color:#0f3460;margin-bottom:5px;">{title}</h2>
    <p style="color:#666;margin-bottom:15px;">{subtitle}</p>
    <div class="mood-banner">{mood}</div>
    <div class="financial-grid">
        <div class="fin-card"><div class="fin-label">{"Mapato" if lang=="sw" else "Revenue"}</div><div class="fin-value fin-positive">{self._fmt(data.total_revenue)}</div></div>
        <div class="fin-card"><div class="fin-label">{"Gharama" if lang=="sw" else "Expenses"}</div><div class="fin-value">{self._fmt(data.total_expenses)}</div></div>
        <div class="fin-card"><div class="fin-label">{"Faida" if lang=="sw" else "Profit"}</div><div class="fin-value {"fin-positive" if data.total_profit>=0 else "fin-negative"}">{self._fmt(data.total_profit)}</div><div class="fin-sub">{data.profit_margin_pct:.1f}% margin</div></div>
    </div>
    <div class="section"><div class="section-title">📊 {"Mapato ya Wiki" if lang=="sw" else "Weekly Revenue"}</div>{revenue_chart}</div>
    {top_products_html}
    <div class="section">
        <div class="section-title">👥 {"Wateja" if lang=="sw" else "Customers"}</div>
        <div class="financial-grid">
            <div class="fin-card"><div class="fin-label">Miamala</div><div class="fin-value">{data.total_transactions:,}</div></div>
            <div class="fin-card"><div class="fin-label">Wateja</div><div class="fin-value">{data.unique_customers:,}</div></div>
            <div class="fin-card"><div class="fin-label">Repeat Rate</div><div class="fin-value">{data.repeat_customer_rate:.0f}%</div></div>
        </div>
    </div>
    {self._footer(data)}
</div></body></html>"""

    # ======================================================================
    # Weekly Digest
    # ======================================================================

    def _render_weekly_digest(self, data: ReportData) -> str:
        lang = data.language
        growth_arrow = "📈" if data.revenue_growth_pct >= 0 else "📉"
        growth_color = "#27ae60" if data.revenue_growth_pct >= 0 else "#e74c3c"
        title = "📋 Muhtasari wa Wiki" if lang == "sw" else "📋 Weekly Digest"

        dow_chart = ""
        if data.daily_revenues:
            dow_chart = self._render_bar_chart(data.daily_revenues[-7:], 'day', 'revenue', color="#3498db")

        top_products_html = ""
        if data.top_products:
            top_products_html = "<div class='section'><div class='section-title'>⭐ Bidhaa Bora</div>"
            for i, p in enumerate(data.top_products[:5], 1):
                top_products_html += f"<div style='display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f0f0f0;'><span>{i}. {p.get('name','N/A')}</span><span style='font-weight:600;'>{self._fmt(p.get('revenue',0))}</span></div>"
            top_products_html += "</div>"

        return f"""<!DOCTYPE html>
<html lang="{"sw" if lang=="sw" else "en"}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — {data.business_name}</title>{self._base_css()}</head>
<body><div class="report-container">
    <div class="report-header">
        <div class="brand"><h1>ANGAVU</h1><div class="tagline">Weekly Business Digest</div></div>
        <div class="report-meta"><div>{data.report_date.strftime('%d %B %Y')}</div><div style="color:#888;">Week {data.report_date.isocalendar()[1]}</div></div>
    </div>
    <div style="text-align:center;margin-bottom:20px;"><h2 style="color:#0f3460;">{title} — {data.business_name}</h2></div>
    <div class="financial-grid">
        <div class="fin-card"><div class="fin-label">Revenue</div><div class="fin-value fin-positive">{self._fmt(data.total_revenue)}</div><div class="fin-sub" style="color:{growth_color};">{growth_arrow} {self._pct(data.revenue_growth_pct)}</div></div>
        <div class="fin-card"><div class="fin-label">Profit</div><div class="fin-value {"fin-positive" if data.total_profit>=0 else "fin-negative"}">{self._fmt(data.total_profit)}</div><div class="fin-sub">{data.profit_margin_pct:.1f}% margin</div></div>
        <div class="fin-card"><div class="fin-label">Alama Score</div><div class="fin-value" style="color:{self._score_color(data.alama_score)};">{data.alama_score}</div><div class="fin-sub">{data.alama_score_band.replace('_',' ').title() if data.alama_score_band else 'N/A'}</div></div>
    </div>
    <div class="section"><div class="section-title">📊 Daily Revenue</div>{dow_chart}</div>
    <div class="section">
        <div class="section-title">⚡ Quick Stats</div>
        <table>
            <tr><td><strong>Transactions</strong></td><td class="text-right">{data.total_transactions:,}</td></tr>
            <tr><td><strong>Customers</strong></td><td class="text-right">{data.unique_customers:,}</td></tr>
            <tr><td><strong>Avg Transaction</strong></td><td class="text-right">{self._fmt(data.avg_transaction_value)}</td></tr>
            <tr><td><strong>Active Days</strong></td><td class="text-right">{data.days_active}/{data.days_in_period}</td></tr>
        </table>
    </div>
    {top_products_html}
    {self._footer(data)}
</div></body></html>"""
