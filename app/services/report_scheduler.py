"""
Report Scheduler — Msaidizi / Biashara AI

Handles automatic scheduling and delivery of reports via WhatsApp.
Uses cron-like scheduling with per-user customization.

Report Delivery Schedule:
- Daily (Ripoti ya Leo): Every evening at user's preferred time (default 7 PM)
- Weekly (Ripoti ya Wiki): Every Sunday evening
- Monthly (Ripoti ya Mwezi): 1st of every month
- Semi-annual (Ripoti ya Nusu Mwaka): January 1st and July 1st
- Annual (Ripoti ya Mwaka): January 1st

Integration Points:
- OpenWA for WhatsApp message delivery
- Msaidizi database for transaction data
- ReportGenerator for report formatting
- User preferences for language and timing

The scheduler is designed to be run as a background service or
triggered by a cron job (e.g., every 15 minutes) to check for
due reports.
"""

from __future__ import annotations

import json
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from pathlib import Path

from .report_generator import (
    ReportGenerator,
    UserProfile,
    DailyData,
    WeeklyData,
    MonthlyDataAgg,
    TransactionData,
    InventoryItem,
)
from .health_score import BusinessMetrics
from .comparison_engine import PeerBusiness

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("msaidizi.scheduler")


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

class ReportType(Enum):
    """Types of reports that can be scheduled."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"


class DeliveryStatus(Enum):
    """Status of a report delivery."""
    PENDING = "pending"
    GENERATING = "generating"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


# Maximum retry attempts for failed deliveries
MAX_RETRIES = 3
RETRY_DELAY_MINUTES = 5

# Default report times (hour in 24h format)
DEFAULT_DAILY_HOUR = 19      # 7 PM
DEFAULT_WEEKLY_HOUR = 18     # 6 PM Sunday
DEFAULT_MONTHLY_HOUR = 9     # 9 AM 1st of month
DEFAULT_SEMIANNUAL_HOUR = 9  # 9 AM Jan 1 / Jul 1
DEFAULT_ANNUAL_HOUR = 10     # 10 AM Jan 1


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ScheduledReport:
    """A scheduled report for a specific user."""
    user_id: str
    report_type: ReportType
    scheduled_time: datetime
    status: DeliveryStatus = DeliveryStatus.PENDING
    retry_count: int = 0
    last_attempt: Optional[datetime] = None
    delivery_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class DeliveryLog:
    """Log entry for a report delivery."""
    delivery_id: str
    user_id: str
    report_type: ReportType
    timestamp: datetime
    status: DeliveryStatus
    message_length: int = 0
    error_message: Optional[str] = None
    generation_time_ms: int = 0
    delivery_time_ms: int = 0


@dataclass
class SchedulerState:
    """Persistent state of the scheduler."""
    last_daily_check: Optional[datetime] = None
    last_weekly_check: Optional[datetime] = None
    last_monthly_check: Optional[datetime] = None
    last_semiannual_check: Optional[datetime] = None
    last_annual_check: Optional[datetime] = None
    pending_reports: List[ScheduledReport] = field(default_factory=list)
    delivery_log: List[DeliveryLog] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Data Access Interface
# ---------------------------------------------------------------------------

class DataAccessInterface:
    """Interface for accessing Msaidizi data.

    This is an abstract interface. The actual implementation depends
    on the database backend (PostgreSQL, SQLite, etc.).

    Implement this interface to connect to your specific data source.
    """

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile by ID.

        Args:
            user_id: User identifier.

        Returns:
            UserProfile if found, None otherwise.
        """
        raise NotImplementedError

    def get_all_active_users(self) -> List[UserProfile]:
        """Get all active users who should receive reports.

        Returns:
            List of active UserProfile objects.
        """
        raise NotImplementedError

    def get_daily_data(self, user_id: str, target_date: date) -> DailyData:
        """Get aggregated daily data for a user.

        Args:
            user_id: User identifier.
            target_date: The date to get data for.

        Returns:
            DailyData with aggregated transactions.
        """
        raise NotImplementedError

    def get_weekly_data(self, user_id: str, week_end: date) -> WeeklyData:
        """Get aggregated weekly data for a user.

        Args:
            user_id: User identifier.
            week_end: End date of the week (Sunday).

        Returns:
            WeeklyData with aggregated daily data.
        """
        raise NotImplementedError

    def get_monthly_data(self, user_id: str, year: int, month: int) -> MonthlyDataAgg:
        """Get aggregated monthly data for a user.

        Args:
            user_id: User identifier.
            year: Year.
            month: Month (1-12).

        Returns:
            MonthlyDataAgg with aggregated data.
        """
        raise NotImplementedError

    def get_inventory_alerts(self, user_id: str) -> List[InventoryItem]:
        """Get items with low stock for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of InventoryItem with low stock.
        """
        raise NotImplementedError

    def get_peer_data(
        self, business_type: str, market: str, region: str
    ) -> List[PeerBusiness]:
        """Get anonymized peer business data for comparison.

        Args:
            business_type: Type of business.
            market: Market name.
            region: Region name.

        Returns:
            List of PeerBusiness for comparison.
        """
        raise NotImplementedError

    def get_transactions(
        self, user_id: str, start_date: date, end_date: date
    ) -> List[TransactionData]:
        """Get raw transactions for a date range.

        Args:
            user_id: User identifier.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            List of TransactionData.
        """
        raise NotImplementedError

    def save_delivery_log(self, log: DeliveryLog) -> None:
        """Save a delivery log entry.

        Args:
            log: The delivery log to save.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# WhatsApp Delivery Interface
# ---------------------------------------------------------------------------

class WhatsAppDeliveryInterface:
    """Interface for sending WhatsApp messages via OpenWA.

    This is an abstract interface. Implement it to connect to your
    OpenWA instance or other WhatsApp API.
    """

    def send_message(self, phone: str, message: str) -> bool:
        """Send a WhatsApp text message.

        Args:
            phone: Phone number (with country code, e.g., "+254712345678").
            message: Message text (supports WhatsApp formatting).

        Returns:
            True if sent successfully, False otherwise.
        """
        raise NotImplementedError

    def send_message_with_link(self, phone: str, message: str, link: str) -> bool:
        """Send a WhatsApp message with a link preview.

        Args:
            phone: Phone number.
            message: Message text.
            link: URL to include.

        Returns:
            True if sent successfully, False otherwise.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock Data Access (for testing)
# ---------------------------------------------------------------------------

class MockDataAccess(DataAccessInterface):
    """Mock data access for testing and development.

    Generates realistic sample data for a food vendor in Gikomba, Nairobi.
    """

    def __init__(self):
        self._users = {
            "user_001": UserProfile(
                user_id="user_001",
                name="Valentine",
                business_name="Simba",
                business_type="food_vendor",
                location="Gikomba",
                language="sw",
                preferred_report_time="19:00",
                phone="+254712345678",
            ),
            "user_002": UserProfile(
                user_id="user_002",
                name="Grace",
                business_name="Nyota",
                business_type="mama_mboga",
                location="Eastleigh",
                language="sw",
                preferred_report_time="18:30",
                phone="+254798765432",
            ),
        }

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        return self._users.get(user_id)

    def get_all_active_users(self) -> List[UserProfile]:
        return list(self._users.values())

    def get_daily_data(self, user_id: str, target_date: date) -> DailyData:
        """Generate realistic daily data."""
        import random
        random.seed(hash(f"{user_id}_{target_date}"))

        base_sales = 3200
        sales = base_sales + random.randint(-800, 1200)
        purchases = int(sales * 0.65) + random.randint(-200, 200)
        sales_count = random.randint(8, 18)

        items = {
            "Mandazi": (random.randint(3, 8), random.randint(800, 2000)),
            "Chapati": (random.randint(2, 6), random.randint(500, 1500)),
            "Chai": (random.randint(3, 10), random.randint(300, 800)),
        }

        best_item = max(items.items(), key=lambda x: x[1][1])

        return DailyData(
            date=target_date,
            total_sales=sales,
            total_purchases=purchases,
            profit=sales - purchases,
            sales_count=sales_count,
            purchase_count=random.randint(1, 5),
            items_sold=items,
            best_item=best_item[0],
            best_item_revenue=best_item[1][1],
            best_item_qty=best_item[1][0],
        )

    def get_weekly_data(self, user_id: str, week_end: date) -> WeeklyData:
        """Generate realistic weekly data."""
        daily_data = []
        for i in range(7):
            day = week_end - timedelta(days=6 - i)
            daily_data.append(self.get_daily_data(user_id, day))

        total_sales = sum(d.total_sales for d in daily_data)
        total_purchases = sum(d.total_purchases for d in daily_data)

        # Aggregate items
        all_items: Dict[str, Tuple[int, float]] = {}
        for d in daily_data:
            for name, (qty, rev) in d.items_sold.items():
                if name in all_items:
                    old_qty, old_rev = all_items[name]
                    all_items[name] = (old_qty + qty, old_rev + rev)
                else:
                    all_items[name] = (qty, rev)

        top_items = sorted(
            [(name, qty, rev) for name, (qty, rev) in all_items.items()],
            key=lambda x: x[2],
            reverse=True,
        )

        best_day = max(daily_data, key=lambda d: d.total_sales)
        worst_day = min(daily_data, key=lambda d: d.total_sales)

        return WeeklyData(
            week_start=week_end - timedelta(days=6),
            week_end=week_end,
            daily_data=daily_data,
            total_sales=total_sales,
            total_purchases=total_purchases,
            profit=total_sales - total_purchases,
            total_transactions=sum(d.sales_count for d in daily_data),
            best_day=str(best_day.date),
            best_day_sales=best_day.total_sales,
            worst_day=str(worst_day.date),
            worst_day_sales=worst_day.total_sales,
            top_items=top_items,
            inventory_alerts=self.get_inventory_alerts(user_id),
        )

    def get_monthly_data(self, user_id: str, year: int, month: int) -> MonthlyDataAgg:
        """Generate realistic monthly data."""
        import calendar
        days_in_month = calendar.monthrange(year, month)[1]

        daily_data = []
        for day in range(1, days_in_month + 1):
            d = date(year, month, day)
            daily_data.append(self.get_daily_data(user_id, d))

        total_sales = sum(d.total_sales for d in daily_data)
        total_purchases = sum(d.total_purchases for d in daily_data)

        # Aggregate items
        all_items: Dict[str, Tuple[int, float]] = {}
        for d in daily_data:
            for name, (qty, rev) in d.items_sold.items():
                if name in all_items:
                    old_qty, old_rev = all_items[name]
                    all_items[name] = (old_qty + qty, old_rev + rev)
                else:
                    all_items[name] = (qty, rev)

        top_items = sorted(
            [(name, qty, rev) for name, (qty, rev) in all_items.items()],
            key=lambda x: x[2],
            reverse=True,
        )

        expense_categories = {
            "raw_materials": total_purchases * 0.67,
            "transport": total_purchases * 0.16,
            "rent": total_purchases * 0.10,
            "other": total_purchases * 0.07,
        }

        # Previous month (avoid infinite recursion)
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        # Generate previous month data directly without recursive get_monthly_data
        import calendar as cal
        prev_days = cal.monthrange(prev_year, prev_month)[1]
        prev_total_sales = int(total_sales * (0.92 + (hash(f"{user_id}_{prev_year}_{prev_month}") % 100) / 600))
        prev_total_purchases = int(prev_total_sales * 0.65)

        return MonthlyDataAgg(
            year=year,
            month=month,
            total_sales=total_sales,
            total_purchases=total_purchases,
            profit=total_sales - total_purchases,
            total_transactions=sum(d.sales_count for d in daily_data),
            active_days=len([d for d in daily_data if d.total_sales > 0]),
            daily_data=daily_data,
            top_items=top_items,
            expense_categories=expense_categories,
            previous_month_sales=prev_total_sales,
            previous_month_profit=prev_total_sales - prev_total_purchases,
        )

    def get_inventory_alerts(self, user_id: str) -> List[InventoryItem]:
        """Generate sample inventory alerts."""
        return [
            InventoryItem(
                item_name="Unga",
                current_stock=5,
                unit="kg",
                daily_usage_rate=2.5,
                restock_threshold=5,
                cost_per_unit=120,
            ),
            InventoryItem(
                item_name="Sukari",
                current_stock=3,
                unit="kg",
                daily_usage_rate=1.0,
                restock_threshold=3,
                cost_per_unit=150,
            ),
        ]

    def get_peer_data(
        self, business_type: str, market: str, region: str
    ) -> List[PeerBusiness]:
        """Generate anonymized peer data."""
        import random
        peers = []
        for i in range(25):
            peers.append(PeerBusiness(
                business_type=business_type,
                market=market,
                region=region,
                monthly_revenue=random.uniform(40000, 120000),
                monthly_expenses=random.uniform(25000, 80000),
                monthly_profit=random.uniform(10000, 40000),
                profit_margin=random.uniform(0.15, 0.45),
                monthly_transactions=random.randint(150, 500),
                unique_products=random.randint(2, 8),
                savings_rate=random.uniform(0, 0.20),
                growth_rate=random.uniform(-5, 25),
                active_days_ratio=random.uniform(0.6, 1.0),
                months_of_data=random.randint(3, 24),
            ))
        return peers

    def get_transactions(
        self, user_id: str, start_date: date, end_date: date
    ) -> List[TransactionData]:
        """Generate sample transactions."""
        return []

    def save_delivery_log(self, log: DeliveryLog) -> None:
        """Mock: just log to console."""
        logger.info(f"Delivery log: {log.delivery_id} - {log.status.value}")


# ---------------------------------------------------------------------------
# Mock WhatsApp Delivery (for testing)
# ---------------------------------------------------------------------------

class MockWhatsAppDelivery(WhatsAppDeliveryInterface):
    """Mock WhatsApp delivery for testing.

    Prints messages to console instead of sending via WhatsApp.
    """

    def __init__(self):
        self.sent_messages: List[Tuple[str, str]] = []

    def send_message(self, phone: str, message: str) -> bool:
        self.sent_messages.append((phone, message))
        logger.info(f"[MOCK WhatsApp] To: {phone}")
        logger.info(f"[MOCK WhatsApp] Message ({len(message)} chars):")
        logger.info(message[:200] + "..." if len(message) > 200 else message)
        return True

    def send_message_with_link(self, phone: str, message: str, link: str) -> bool:
        full_message = f"{message}\n\n🔗 Ripoti kamili: {link}"
        return self.send_message(phone, full_message)


# ---------------------------------------------------------------------------
# Report Scheduler
# ---------------------------------------------------------------------------

class ReportScheduler:
    """Schedules and delivers reports to users via WhatsApp.

    The scheduler can be run in two modes:
    1. Polling mode: Call check_and_send_reports() periodically (e.g., every 15 min)
    2. Event mode: Call send_report_for_user() directly for specific events

    Usage:
        data_access = MyDataAccess()  # Your database implementation
        whatsapp = MyWhatsAppDelivery()  # Your OpenWA implementation
        scheduler = ReportScheduler(data_access, whatsapp)

        # Polling mode — run this every 15 minutes
        scheduler.check_and_send_reports()

        # Event mode — send a specific report
        scheduler.send_report_for_user("user_001", ReportType.DAILY)
    """

    def __init__(
        self,
        data_access: DataAccessInterface,
        whatsapp: WhatsAppDeliveryInterface,
        state_file: Optional[str] = None,
    ):
        """Initialize the scheduler.

        Args:
            data_access: Data access implementation.
            whatsapp: WhatsApp delivery implementation.
            state_file: Optional path to persist scheduler state.
        """
        self.data_access = data_access
        self.whatsapp = whatsapp
        self.generator = ReportGenerator()
        self.state = SchedulerState()
        self.state_file = state_file

        if state_file:
            self._load_state()

    # -------------------------------------------------------------------
    # Main Scheduling Loop
    # -------------------------------------------------------------------

    def check_and_send_reports(self) -> Dict[ReportType, int]:
        """Check for due reports and send them.

        This is the main entry point for polling mode. Call it
        periodically (e.g., every 15 minutes via cron).

        Returns:
            Dict of report_type → count of reports sent.
        """
        now = datetime.now()
        counts = {rt: 0 for rt in ReportType}

        users = self.data_access.get_all_active_users()
        logger.info(f"Checking reports for {len(users)} users at {now}")

        for user in users:
            try:
                # Check daily reports
                if self._is_daily_due(user, now):
                    success = self.send_report_for_user(user.user_id, ReportType.DAILY)
                    if success:
                        counts[ReportType.DAILY] += 1

                # Check weekly reports (Sunday)
                if now.weekday() == 6 and self._is_weekly_due(user, now):
                    success = self.send_report_for_user(user.user_id, ReportType.WEEKLY)
                    if success:
                        counts[ReportType.WEEKLY] += 1

                # Check monthly reports (1st of month)
                if now.day == 1 and self._is_monthly_due(user, now):
                    success = self.send_report_for_user(user.user_id, ReportType.MONTHLY)
                    if success:
                        counts[ReportType.MONTHLY] += 1

                # Check semi-annual reports (Jan 1 or Jul 1)
                if now.month in (1, 7) and now.day == 1:
                    if self._is_semiannual_due(user, now):
                        success = self.send_report_for_user(user.user_id, ReportType.SEMIANNUAL)
                        if success:
                            counts[ReportType.SEMIANNUAL] += 1

                # Check annual reports (Jan 1)
                if now.month == 1 and now.day == 1:
                    if self._is_annual_due(user, now):
                        success = self.send_report_for_user(user.user_id, ReportType.ANNUAL)
                        if success:
                            counts[ReportType.ANNUAL] += 1

            except Exception as e:
                logger.error(f"Error processing reports for {user.user_id}: {e}")

        self._save_state()
        logger.info(f"Reports sent: {counts}")
        return counts

    # -------------------------------------------------------------------
    # Send Specific Report
    # -------------------------------------------------------------------

    def send_report_for_user(
        self, user_id: str, report_type: ReportType
    ) -> bool:
        """Generate and send a specific report to a user.

        Args:
            user_id: User identifier.
            report_type: Type of report to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        import time as time_module

        # Get user profile
        profile = self.data_access.get_user_profile(user_id)
        if not profile:
            logger.error(f"User not found: {user_id}")
            return False

        # Generate report
        start_time = time_module.time()
        try:
            message = self._generate_report(profile, report_type)
        except Exception as e:
            logger.error(f"Error generating report for {user_id}: {e}")
            self._log_delivery(user_id, report_type, DeliveryStatus.FAILED, error=str(e))
            return False

        generation_time = int((time_module.time() - start_time) * 1000)

        if not message:
            logger.warning(f"Empty report generated for {user_id}")
            return False

        # Send via WhatsApp
        delivery_start = time_module.time()
        try:
            success = self.whatsapp.send_message(profile.phone, message)
        except Exception as e:
            logger.error(f"Error sending WhatsApp message to {profile.phone}: {e}")
            self._log_delivery(
                user_id, report_type, DeliveryStatus.FAILED,
                error=str(e), generation_time=generation_time
            )
            return False

        delivery_time = int((time_module.time() - delivery_start) * 1000)

        if success:
            self._log_delivery(
                user_id, report_type, DeliveryStatus.DELIVERED,
                message_length=len(message),
                generation_time=generation_time,
                delivery_time=delivery_time,
            )
            logger.info(
                f"Report sent: {report_type.value} to {profile.name} ({profile.phone}) "
                f"[{len(message)} chars, gen:{generation_time}ms, del:{delivery_time}ms]"
            )
            return True
        else:
            self._log_delivery(
                user_id, report_type, DeliveryStatus.FAILED,
                error="WhatsApp send failed",
                generation_time=generation_time,
            )
            return False

    # -------------------------------------------------------------------
    # Report Generation Dispatch
    # -------------------------------------------------------------------

    def _generate_report(
        self, profile: UserProfile, report_type: ReportType
    ) -> Optional[str]:
        """Generate a report message based on type.

        Args:
            profile: User profile.
            report_type: Type of report.

        Returns:
            Formatted WhatsApp message string, or None if error.
        """
        now = datetime.now()

        if report_type == ReportType.DAILY:
            return self._generate_daily(profile, now)

        elif report_type == ReportType.WEEKLY:
            return self._generate_weekly(profile, now)

        elif report_type == ReportType.MONTHLY:
            return self._generate_monthly(profile, now)

        elif report_type == ReportType.SEMIANNUAL:
            return self._generate_semiannual(profile, now)

        elif report_type == ReportType.ANNUAL:
            return self._generate_annual(profile, now)

        return None

    def _generate_daily(self, profile: UserProfile, now: datetime) -> str:
        """Generate daily report."""
        today = now.date()
        yesterday = today - timedelta(days=1)

        today_data = self.data_access.get_daily_data(profile.user_id, today)
        yesterday_data = self.data_access.get_daily_data(profile.user_id, yesterday)
        inventory_alerts = self.data_access.get_inventory_alerts(profile.user_id)

        # Calculate average daily sales (last 7 days)
        weekly_sales = []
        for i in range(7):
            d = today - timedelta(days=i)
            day_data = self.data_access.get_daily_data(profile.user_id, d)
            if day_data.total_sales > 0:
                weekly_sales.append(day_data.total_sales)
        avg_sales = sum(weekly_sales) / len(weekly_sales) if weekly_sales else 0

        return self.generator.generate_daily(
            profile=profile,
            today=today_data,
            yesterday=yesterday_data,
            avg_daily_sales=avg_sales,
            inventory_alerts=inventory_alerts,
        )

    def _generate_weekly(self, profile: UserProfile, now: datetime) -> str:
        """Generate weekly report."""
        # Week ends on Sunday (today)
        week_end = now.date()
        prev_week_end = week_end - timedelta(days=7)

        week_data = self.data_access.get_weekly_data(profile.user_id, week_end)
        prev_week_data = self.data_access.get_weekly_data(profile.user_id, prev_week_end)

        return self.generator.generate_weekly(
            profile=profile,
            week=week_data,
            previous_week=prev_week_data,
        )

    def _generate_monthly(self, profile: UserProfile, now: datetime) -> str:
        """Generate monthly report."""
        # Previous month (since we run on the 1st)
        if now.month == 1:
            report_year = now.year - 1
            report_month = 12
        else:
            report_year = now.year
            report_month = now.month - 1

        month_data = self.data_access.get_monthly_data(
            profile.user_id, report_year, report_month
        )

        # Get previous months for trend
        previous_months = []
        for i in range(1, 4):
            m = report_month - i
            y = report_year
            while m <= 0:
                m += 12
                y -= 1
            prev_data = self.data_access.get_monthly_data(profile.user_id, y, m)
            previous_months.append(prev_data)
        previous_months.reverse()

        inventory = self.data_access.get_inventory_alerts(profile.user_id)
        peer_data = self.data_access.get_peer_data(
            profile.business_type, profile.location, "Nairobi"
        )

        return self.generator.generate_monthly(
            profile=profile,
            month_data=month_data,
            previous_months=previous_months,
            inventory=inventory,
            peer_data=peer_data,
        )

    def _generate_semiannual(self, profile: UserProfile, now: datetime) -> str:
        """Generate semi-annual report."""
        monthly_data = []

        if now.month == 1:
            # July - December of previous year
            for m in range(7, 13):
                data = self.data_access.get_monthly_data(profile.user_id, now.year - 1, m)
                monthly_data.append(data)
        else:
            # January - June of current year
            for m in range(1, 7):
                data = self.data_access.get_monthly_data(profile.user_id, now.year, m)
                monthly_data.append(data)

        peer_data = self.data_access.get_peer_data(
            profile.business_type, profile.location, "Nairobi"
        )

        return self.generator.generate_semiannual(
            profile=profile,
            monthly_data_list=monthly_data,
            peer_data=peer_data,
        )

    def _generate_annual(self, profile: UserProfile, now: datetime) -> str:
        """Generate annual report."""
        year = now.year - 1  # Previous year

        monthly_data = []
        for m in range(1, 13):
            data = self.data_access.get_monthly_data(profile.user_id, year, m)
            monthly_data.append(data)

        # Previous year sales (for YoY comparison)
        prev_year_sales = 0
        try:
            prev_year_data = self.data_access.get_monthly_data(
                profile.user_id, year - 1, 12
            )
            # This is simplified — ideally aggregate full previous year
            prev_year_sales = prev_year_data.total_sales * 12
        except Exception:
            pass

        peer_data = self.data_access.get_peer_data(
            profile.business_type, profile.location, "Nairobi"
        )

        return self.generator.generate_annual(
            profile=profile,
            monthly_data_list=monthly_data,
            previous_year_sales=prev_year_sales,
            peer_data=peer_data,
        )

    # -------------------------------------------------------------------
    # Schedule Checking
    # -------------------------------------------------------------------

    def _is_daily_due(self, profile: UserProfile, now: datetime) -> bool:
        """Check if a daily report is due for a user.

        Args:
            profile: User profile.
            now: Current datetime.

        Returns:
            True if the daily report should be sent now.
        """
        # Parse preferred time
        try:
            hour, minute = map(int, profile.preferred_report_time.split(":"))
        except (ValueError, AttributeError):
            hour, minute = DEFAULT_DAILY_HOUR, 0

        # Check if we're within the delivery window (15 minutes)
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        window_start = scheduled - timedelta(minutes=15)
        window_end = scheduled + timedelta(minutes=15)

        if not (window_start <= now <= window_end):
            return False

        # Check if already sent today
        today_str = now.strftime("%Y-%m-%d")
        for log in self.state.delivery_log:
            if (
                log.user_id == profile.user_id
                and log.report_type == ReportType.DAILY
                and log.status == DeliveryStatus.DELIVERED
                and log.timestamp.strftime("%Y-%m-%d") == today_str
            ):
                return False

        return True

    def _is_weekly_due(self, profile: UserProfile, now: datetime) -> bool:
        """Check if a weekly report is due."""
        hour = DEFAULT_WEEKLY_HOUR
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        window = timedelta(minutes=30)

        if not (scheduled - window <= now <= scheduled + window):
            return False

        # Check if already sent this week
        week_start = now.date() - timedelta(days=now.weekday())
        for log in self.state.delivery_log:
            if (
                log.user_id == profile.user_id
                and log.report_type == ReportType.WEEKLY
                and log.status == DeliveryStatus.DELIVERED
                and log.timestamp.date() >= week_start
            ):
                return False

        return True

    def _is_monthly_due(self, profile: UserProfile, now: datetime) -> bool:
        """Check if a monthly report is due."""
        hour = DEFAULT_MONTHLY_HOUR
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        window = timedelta(hours=2)

        if not (scheduled - window <= now <= scheduled + window):
            return False

        # Check if already sent this month
        for log in self.state.delivery_log:
            if (
                log.user_id == profile.user_id
                and log.report_type == ReportType.MONTHLY
                and log.status == DeliveryStatus.DELIVERED
                and log.timestamp.month == now.month
                and log.timestamp.year == now.year
            ):
                return False

        return True

    def _is_semiannual_due(self, profile: UserProfile, now: datetime) -> bool:
        """Check if a semi-annual report is due."""
        hour = DEFAULT_SEMIANNUAL_HOUR
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        window = timedelta(hours=4)

        if not (scheduled - window <= now <= scheduled + window):
            return False

        # Check if already sent this half-year
        half = "H1" if now.month <= 6 else "H2"
        for log in self.state.delivery_log:
            if (
                log.user_id == profile.user_id
                and log.report_type == ReportType.SEMIANNUAL
                and log.status == DeliveryStatus.DELIVERED
                and log.timestamp.year == now.year
            ):
                log_half = "H1" if log.timestamp.month <= 6 else "H2"
                if log_half == half:
                    return False

        return True

    def _is_annual_due(self, profile: UserProfile, now: datetime) -> bool:
        """Check if an annual report is due."""
        hour = DEFAULT_ANNUAL_HOUR
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        window = timedelta(hours=6)

        if not (scheduled - window <= now <= scheduled + window):
            return False

        # Check if already sent this year
        for log in self.state.delivery_log:
            if (
                log.user_id == profile.user_id
                and log.report_type == ReportType.ANNUAL
                and log.status == DeliveryStatus.DELIVERED
                and log.timestamp.year == now.year
            ):
                return False

        return True

    # -------------------------------------------------------------------
    # Delivery Logging
    # -------------------------------------------------------------------

    def _log_delivery(
        self,
        user_id: str,
        report_type: ReportType,
        status: DeliveryStatus,
        message_length: int = 0,
        error: Optional[str] = None,
        generation_time: int = 0,
        delivery_time: int = 0,
    ) -> None:
        """Log a delivery attempt.

        Args:
            user_id: User identifier.
            report_type: Report type.
            status: Delivery status.
            message_length: Length of message sent.
            error: Error message if failed.
            generation_time: Time to generate report (ms).
            delivery_time: Time to deliver message (ms).
        """
        delivery_id = hashlib.md5(
            f"{user_id}_{report_type.value}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        log = DeliveryLog(
            delivery_id=delivery_id,
            user_id=user_id,
            report_type=report_type,
            timestamp=datetime.now(),
            status=status,
            message_length=message_length,
            error_message=error,
            generation_time_ms=generation_time,
            delivery_time_ms=delivery_time,
        )

        self.state.delivery_log.append(log)

        # Persist to database
        try:
            self.data_access.save_delivery_log(log)
        except Exception as e:
            logger.warning(f"Failed to persist delivery log: {e}")

        # Trim old logs (keep last 1000)
        if len(self.state.delivery_log) > 1000:
            self.state.delivery_log = self.state.delivery_log[-1000:]

    # -------------------------------------------------------------------
    # State Persistence
    # -------------------------------------------------------------------

    def _save_state(self) -> None:
        """Save scheduler state to file."""
        if not self.state_file:
            return

        try:
            state_data = {
                "last_daily_check": self.state.last_daily_check.isoformat() if self.state.last_daily_check else None,
                "last_weekly_check": self.state.last_weekly_check.isoformat() if self.state.last_weekly_check else None,
                "last_monthly_check": self.state.last_monthly_check.isoformat() if self.state.last_monthly_check else None,
                "delivery_count": len(self.state.delivery_log),
            }
            path = Path(self.state_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state_data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save scheduler state: {e}")

    def _load_state(self) -> None:
        """Load scheduler state from file."""
        if not self.state_file:
            return

        try:
            path = Path(self.state_file)
            if path.exists():
                data = json.loads(path.read_text())
                if data.get("last_daily_check"):
                    self.state.last_daily_check = datetime.fromisoformat(data["last_daily_check"])
                if data.get("last_weekly_check"):
                    self.state.last_weekly_check = datetime.fromisoformat(data["last_weekly_check"])
                if data.get("last_monthly_check"):
                    self.state.last_monthly_check = datetime.fromisoformat(data["last_monthly_check"])
                logger.info("Scheduler state loaded")
        except Exception as e:
            logger.warning(f"Failed to load scheduler state: {e}")

    # -------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------

    def get_delivery_stats(self) -> Dict[str, Any]:
        """Get delivery statistics.

        Returns:
            Dict with delivery stats.
        """
        logs = self.state.delivery_log
        if not logs:
            return {"total": 0, "delivered": 0, "failed": 0}

        total = len(logs)
        delivered = sum(1 for l in logs if l.status == DeliveryStatus.DELIVERED)
        failed = sum(1 for l in logs if l.status == DeliveryStatus.FAILED)

        # Average generation time
        gen_times = [l.generation_time_ms for l in logs if l.generation_time_ms > 0]
        avg_gen_time = sum(gen_times) / len(gen_times) if gen_times else 0

        # By report type
        by_type = {}
        for rt in ReportType:
            type_logs = [l for l in logs if l.report_type == rt]
            by_type[rt.value] = {
                "total": len(type_logs),
                "delivered": sum(1 for l in type_logs if l.status == DeliveryStatus.DELIVERED),
                "failed": sum(1 for l in type_logs if l.status == DeliveryStatus.FAILED),
            }

        return {
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "success_rate": f"{(delivered / total * 100):.1f}%" if total > 0 else "N/A",
            "avg_generation_time_ms": round(avg_gen_time),
            "by_type": by_type,
        }

    def preview_report(
        self, user_id: str, report_type: ReportType
    ) -> Optional[str]:
        """Preview a report without sending it.

        Useful for testing and debugging.

        Args:
            user_id: User identifier.
            report_type: Type of report.

        Returns:
            Formatted message string, or None if error.
        """
        profile = self.data_access.get_user_profile(user_id)
        if not profile:
            return None
        return self._generate_report(profile, report_type)
