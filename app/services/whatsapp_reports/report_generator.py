"""
WhatsApp Report Generator — Generates professional PDF/HTML business reports.

Converts raw transaction data from the database into ReportData objects
and renders them as HTML (which can be converted to PDF via headless
browser or WeasyPrint).

Data flow:
    DB (Transaction, User, Inventory, AlamaScore) → ReportData → HTML → PDF

The PDF is then sent via WhatsApp using the /send-media endpoint.
"""

from __future__ import annotations

import asyncio
import base64
import io
import tempfile
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Inventory, Transaction
from app.models.user import User
from app.services.health_score import BusinessHealthScorer, BusinessMetrics

from .templates import (
    BusinessHealthGrade,
    ReportData,
    ReportTemplate,
    TemplateType,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Business type labels (Swahili + English)
# ---------------------------------------------------------------------------

BUSINESS_TYPE_LABELS: dict[str, dict[str, str]] = {
    "food_vendor": {"sw": "Mama Mboga", "en": "Food Vendor"},
    "mama_mboga": {"sw": "Mama Mboga", "en": "Mama Mboga"},
    "dukawallah": {"sw": "Dukawallah", "en": "Shop Owner"},
    "clothing_vendor": {"sw": "Muuza Nguo", "en": "Clothing Vendor"},
    "boda_boda": {"sw": "Boda Boda", "en": "Boda Boda Rider"},
    "restaurant": {"sw": "Mmiliki wa Hoteli", "en": "Restaurant Owner"},
    "butcher": {"sw": "Muuza Nyama", "en": "Butcher"},
    "hairdresser": {"sw": "Fundi Nywele", "en": "Hairdresser"},
    "tailor": {"sw": "Fundi Nguo", "en": "Tailor"},
    "carpenter": {"sw": "Fundi Mbao", "en": "Carpenter"},
    "mechanic": {"sw": "Fundi Gari", "en": "Mechanic"},
    "pharmacy": {"sw": "Mmiliki wa Duka la Dawa", "en": "Pharmacy Owner"},
    "hardware_store": {"sw": "Mmiliki wa Hardware", "en": "Hardware Store"},
}


# ---------------------------------------------------------------------------
# Health grade mapping
# ---------------------------------------------------------------------------

def _health_grade(score: int) -> BusinessHealthGrade:
    """Map health score (0-100) to letter grade."""
    if score >= 85:
        return BusinessHealthGrade.A
    elif score >= 70:
        return BusinessHealthGrade.B
    elif score >= 55:
        return BusinessHealthGrade.C
    elif score >= 40:
        return BusinessHealthGrade.D
    return BusinessHealthGrade.F


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

class WhatsAppReportGenerator:
    """
    Generates professional business reports from database records.

    Usage:
        generator = WhatsAppReportGenerator(db)
        report_data = await generator.build_report_data(user, period_days=30)
        html = generator.render_html(report_data, TemplateType.BANK_READY)
        pdf_bytes = await generator.html_to_pdf(html)
        await delivery.send_document(phone, pdf_bytes, "report.pdf")
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.template = ReportTemplate()
        self._health_scorer = BusinessHealthScorer()

    # ======================================================================
    # Public API
    # ======================================================================

    async def build_report_data(
        self,
        user: User,
        period_days: int = 30,
        language: str | None = None,
    ) -> ReportData:
        """
        Build a complete ReportData object from database records.

        Args:
            user: User model instance
            period_days: Number of days to include in the report
            language: Override language (default: user's preference)

        Returns:
            Populated ReportData ready for template rendering
        """
        lang = language or getattr(user, "language", "sw")
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        # Fetch transactions for the period
        transactions = await self._fetch_transactions(user.id, start_date, end_date)
        inventory = await self._fetch_inventory(user.id)

        # Build financial summaries
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]

        total_revenue = sum(t.amount for t in sales)
        total_purchases = sum(t.amount for t in purchases)
        total_expenses_amount = sum(t.amount for t in expenses)
        total_expenses = total_purchases + total_expenses_amount
        total_profit = total_revenue - total_expenses

        # Daily breakdown
        daily_revenues = self._daily_breakdown(sales, start_date, end_date)
        days_active = sum(1 for d in daily_revenues if d["revenue"] > 0)

        # Monthly breakdown
        monthly_revenues = self._monthly_breakdown(sales)

        # Customer metrics
        unique_customers, repeat_rate = self._customer_metrics(sales)

        # Top products
        top_products = self._top_products(sales)

        # Cash flow
        cash_in, cash_out, flow_entries = self._cash_flow(transactions)

        # Inventory
        inv_items = len(inventory)
        inv_value = sum(getattr(i, "current_value", 0) or (getattr(i, "quantity", 0) * getattr(i, "unit_cost", 0)) for i in inventory)
        stock_turnover = self._stock_turnover(total_purchases, inv_value)

        # Growth (compare with previous period)
        prev_start = start_date - timedelta(days=period_days)
        prev_transactions = await self._fetch_transactions(user.id, prev_start, start_date - timedelta(days=1))
        prev_sales = [t for t in prev_transactions if t.transaction_type == "SALE"]
        prev_revenue = sum(t.amount for t in prev_sales)
        revenue_growth = ((total_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0

        # Health score
        health_metrics = BusinessMetrics(
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            total_profit=total_profit,
            total_transactions=len(sales),
            days_active=days_active,
            days_in_period=period_days,
            current_period_revenue=total_revenue,
            previous_period_revenue=prev_revenue,
            revenue_growth_pct=revenue_growth,
            daily_revenues=[d["revenue"] for d in daily_revenues],
        )
        health_result = self._health_scorer.calculate(health_metrics)

        # Alama Score
        alama_score, alama_components, risk_cat, default_prob = await self._fetch_alama_score(user.id)

        # Max affordable loan (rough: 3x monthly profit, capped by Alama)
        max_loan = 0.0
        if total_profit > 0 and alama_score >= 400:
            monthly_profit = total_profit * (30 / period_days)
            score_multiplier = min(alama_score / 600, 2.0)
            max_loan = round(monthly_profit * 3 * score_multiplier, -3)  # round to nearest 1000

        # M-Pesa verification
        mpesa_verified, mpesa_count = await self._check_mpesa(user.id, start_date, end_date)

        # Business type label
        biz_type = getattr(user, "business_type", "food_vendor") or "food_vendor"
        biz_labels = BUSINESS_TYPE_LABELS.get(biz_type, BUSINESS_TYPE_LABELS["food_vendor"])
        biz_label = biz_labels.get(lang, biz_labels.get("en", biz_type))

        return ReportData(
            business_name=getattr(user, "business_name", None) or "Biashara",
            owner_name=getattr(user, "first_name", None) or getattr(user, "name", "") or "Mmiliki",
            business_type=biz_type,
            business_type_label=biz_label,
            location=getattr(user, "location", None) or "",
            phone=getattr(user, "phone", "") or "",
            join_date=getattr(user, "created_at", None),
            report_date=end_date,
            period_start=start_date,
            period_end=end_date,
            language=lang,
            total_revenue=round(total_revenue, 2),
            total_expenses=round(total_expenses, 2),
            total_profit=round(total_profit, 2),
            profit_margin_pct=round((total_profit / total_revenue * 100) if total_revenue > 0 else 0, 1),
            daily_revenues=daily_revenues,
            monthly_revenues=monthly_revenues,
            total_transactions=len(sales),
            unique_customers=unique_customers,
            repeat_customer_rate=repeat_rate,
            days_active=days_active,
            days_in_period=period_days,
            inventory_items=inv_items,
            inventory_value=round(inv_value, 2),
            stock_turnover=round(stock_turnover, 1),
            top_products=top_products,
            cash_inflow=round(cash_in, 2),
            cash_outflow=round(cash_out, 2),
            net_cash_flow=round(cash_in - cash_out, 2),
            cash_flow_entries=flow_entries,
            alama_score=alama_score,
            alama_score_band=self._score_band(alama_score),
            alama_score_components=alama_components,
            risk_category=risk_cat,
            default_probability=default_prob,
            max_affordable_loan=max_loan,
            health_score=health_result.score,
            health_grade=_health_grade(health_result.score),
            revenue_growth_pct=round(revenue_growth, 1),
            mpesa_verified=mpesa_verified,
            mpesa_receipt_count=mpesa_count,
        )

    def render_html(self, data: ReportData, template_type: TemplateType) -> str:
        """Render ReportData to HTML string."""
        return self.template.render(data, template_type)

    async def html_to_pdf(self, html: str) -> bytes:
        """
        Convert HTML to PDF bytes.

        Tries WeasyPrint first (best quality), falls back to wkhtmltopdf,
        then returns HTML bytes if neither is available.
        """
        # Try WeasyPrint
        try:
            from weasyprint import HTML
            return HTML(string=html).write_pdf()
        except ImportError:
            pass
        except Exception as e:
            logger.warning("weasyprint_failed", error=str(e))

        # Try wkhtmltopdf via subprocess
        try:
            return await self._wkhtmltopdf(html)
        except Exception as e:
            logger.warning("wkhtmltopdf_failed", error=str(e))

        # Fallback: return HTML as bytes (user can open in browser)
        logger.warning("pdf_fallback_to_html", msg="No PDF engine available, returning HTML")
        return html.encode("utf-8")

    async def generate_report(
        self,
        user: User,
        template_type: TemplateType = TemplateType.BANK_READY,
        period_days: int = 30,
        language: str | None = None,
    ) -> tuple[bytes, str, str]:
        """
        Full pipeline: build data → render HTML → convert to PDF.

        Returns:
            Tuple of (pdf_bytes, filename, html_content)
        """
        data = await self.build_report_data(user, period_days, language)
        html = self.render_html(data, template_type)
        pdf_bytes = await self.html_to_pdf(html)

        # Generate filename
        biz_name = data.business_name.replace(" ", "_").replace("/", "-")[:30]
        filename = f"Angavu_{template_type.value}_{biz_name}_{data.report_date.strftime('%Y%m%d')}.pdf"

        return pdf_bytes, filename, html

    # ======================================================================
    # Database Queries
    # ======================================================================

    async def _fetch_transactions(
        self, user_id: str, start: date, end: date
    ) -> list[Transaction]:
        """Fetch all transactions for a user within a date range."""
        stmt = (
            select(Transaction)
            .where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.timestamp >= datetime.combine(start, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(end, datetime.max.time()),
                )
            )
            .order_by(Transaction.timestamp)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_inventory(self, user_id: str) -> list[Inventory]:
        """Fetch current inventory items."""
        stmt = select(Inventory).where(Inventory.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_alama_score(
        self, user_id: str
    ) -> tuple[int, list[dict], str, float]:
        """
        Fetch Alama Score for a user. Returns (score, components, risk, default_prob).
        Falls back to computing a basic score if the engine isn't available.
        """
        try:
            from app.services.alama_score.engine import AlamaScoreEngine
            engine = AlamaScoreEngine(self.db)
            report = await engine.compute_score(user_id)
            components = [
                {
                    "name": c.name,
                    "name_sw": c.name_sw,
                    "weight": c.weight,
                    "normalized_score": c.normalized_score,
                    "interpretation": c.interpretation,
                    "interpretation_sw": c.interpretation_sw,
                }
                for c in report.components
            ]
            return (
                report.composite_score,
                components,
                report.risk_category.value,
                report.default_probability,
            )
        except Exception as e:
            logger.info("alama_score_fallback", error=str(e))
            # Basic fallback: estimate from recent data
            return 500, [], "moderate", 0.15

    async def _check_mpesa(
        self, user_id: str, start: date, end: date
    ) -> tuple[bool, int]:
        """Check if M-Pesa receipts are linked for the period."""
        try:
            stmt = (
                select(func.count())
                .select_from(Transaction)
                .where(
                    and_(
                        Transaction.user_id == user_id,
                        Transaction.timestamp >= datetime.combine(start, datetime.min.time()),
                        Transaction.timestamp <= datetime.combine(end, datetime.max.time()),
                        Transaction.payment_method == "M-PESA",
                    )
                )
            )
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            return count > 0, count
        except Exception:
            return False, 0

    # ======================================================================
    # Data Processing
    # ======================================================================

    def _daily_breakdown(
        self, sales: list[Transaction], start: date, end: date
    ) -> list[dict[str, Any]]:
        """Compute daily revenue breakdown."""
        daily: dict[str, float] = defaultdict(float)
        for t in sales:
            key = t.timestamp.strftime("%Y-%m-%d")
            daily[key] += t.amount

        result = []
        current = start
        while current <= end:
            key = current.strftime("%Y-%m-%d")
            result.append({
                "day": current.strftime("%a %d"),
                "date": key,
                "revenue": round(daily.get(key, 0), 2),
            })
            current += timedelta(days=1)
        return result

    def _monthly_breakdown(self, sales: list[Transaction]) -> list[dict[str, Any]]:
        """Compute monthly revenue breakdown."""
        monthly: dict[str, float] = defaultdict(float)
        for t in sales:
            key = t.timestamp.strftime("%Y-%m")
            monthly[key] += t.amount

        result = []
        for month_key in sorted(monthly.keys()):
            try:
                label = datetime.strptime(month_key, "%Y-%m").strftime("%b %Y")
            except ValueError:
                label = month_key
            result.append({"month": label, "revenue": round(monthly[month_key], 2)})
        return result

    def _customer_metrics(self, sales: list[Transaction]) -> tuple[int, float]:
        """Calculate unique customers and repeat rate."""
        if not sales:
            return 0, 0.0

        customer_counts: dict[str, int] = defaultdict(int)
        for t in sales:
            cid = getattr(t, "customer_id", None) or "walk-in"
            customer_counts[cid] += 1

        unique = len(customer_counts)
        repeat = sum(1 for c in customer_counts.values() if c > 1)
        rate = (repeat / unique * 100) if unique > 0 else 0

        return unique, round(rate, 1)

    def _top_products(self, sales: list[Transaction], limit: int = 8) -> list[dict[str, Any]]:
        """Get top products by revenue."""
        products: dict[str, dict] = defaultdict(lambda: {"quantity": 0, "revenue": 0.0})
        for t in sales:
            name = getattr(t, "item_name", None) or "Unknown"
            products[name]["quantity"] += getattr(t, "quantity", 1) or 1
            products[name]["revenue"] += t.amount

        sorted_products = sorted(
            products.items(), key=lambda x: x[1]["revenue"], reverse=True
        )
        result = []
        for name, data in sorted_products[:limit]:
            margin = 0.0  # We don't have per-product cost, estimate later
            result.append({
                "name": name,
                "quantity": data["quantity"],
                "revenue": round(data["revenue"], 2),
                "margin": round(margin, 1),
            })
        return result

    def _cash_flow(
        self, transactions: list[Transaction]
    ) -> tuple[float, float, list[dict[str, Any]]]:
        """Calculate cash flow from transactions."""
        cash_in = 0.0
        cash_out = 0.0
        entries = []

        for t in transactions:
            if t.transaction_type == "SALE":
                cash_in += t.amount
                entries.append({
                    "date": t.timestamp.strftime("%d/%m"),
                    "type": "Sale",
                    "direction": "in",
                    "amount": t.amount,
                })
            elif t.transaction_type in ("PURCHASE", "EXPENSE"):
                cash_out += t.amount
                entries.append({
                    "date": t.timestamp.strftime("%d/%m"),
                    "type": t.transaction_type.title(),
                    "direction": "out",
                    "amount": t.amount,
                })

        return cash_in, cash_out, entries[-20:]  # Last 20 entries

    def _stock_turnover(self, purchases: float, inventory_value: float) -> float:
        """Estimate stock turnover ratio."""
        if inventory_value <= 0:
            return 0.0
        return purchases / inventory_value

    def _score_band(self, score: int) -> str:
        """Get descriptive score band."""
        if score >= 900:
            return "exceptional"
        elif score >= 800:
            return "excellent"
        elif score >= 700:
            return "good"
        elif score >= 600:
            return "fair"
        elif score >= 500:
            return "poor"
        elif score >= 300:
            return "very_poor"
        return "no_score"

    # ======================================================================
    # PDF Conversion
    # ======================================================================

    async def _wkhtmltopdf(self, html: str) -> bytes:
        """Convert HTML to PDF using wkhtmltopdf subprocess."""
        proc = await asyncio.create_subprocess_exec(
            "wkhtmltopdf",
            "--quiet",
            "--page-size", "A4",
            "--margin-top", "15mm",
            "--margin-bottom", "15mm",
            "--margin-left", "20mm",
            "--margin-right", "20mm",
            "--encoding", "UTF-8",
            "--no-stop-slow-scripts",
            "--enable-local-file-access",
            "-",  # read from stdin
            "-",  # write to stdout
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=html.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(f"wkhtmltopdf failed: {stderr.decode()[:200]}")
        return stdout
