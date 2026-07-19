"""
Worker Value Tracker

Tracks the value each worker gets from Msaidizi.

Value metrics:
- Time saved (voice bookkeeping vs manual)
- Money saved (better prices, less spoilage)
- Money earned (credit access, market intelligence)
- Stress reduced (automated tracking, alerts)

This data proves the platform works and justifies
the data center investment.

Workers must get 5-10x more value from Msaidizi than
the data they generate is worth to Angavu Intelligence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WorkerMetrics:
    """Cumulative value metrics for a single worker."""

    worker_id: str = ""
    hours_saved: float = 0.0
    money_saved_kes: float = 0.0
    money_earned_kes: float = 0.0
    transactions_recorded: int = 0
    days_active: int = 0
    first_active_at: str = ""
    last_active_at: str = ""

    # Granular breakdowns
    time_saved_voice_bookkeeping_hrs: float = 0.0
    money_saved_better_prices_kes: float = 0.0
    money_saved_less_spoilage_kes: float = 0.0
    money_saved_stockout_prevention_kes: float = 0.0
    money_earned_credit_access_kes: float = 0.0
    money_earned_market_intel_kes: float = 0.0
    money_earned_business_growth_kes: float = 0.0

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "hours_saved": round(self.hours_saved, 1),
            "money_saved_kes": round(self.money_saved_kes, 0),
            "money_earned_kes": round(self.money_earned_kes, 0),
            "total_value_kes": round(self.money_saved_kes + self.money_earned_kes, 0),
            "transactions_recorded": self.transactions_recorded,
            "days_active": self.days_active,
            "first_active_at": self.first_active_at,
            "last_active_at": self.last_active_at,
            "breakdown": {
                "time_saved": {
                    "voice_bookkeeping_hrs": round(self.time_saved_voice_bookkeeping_hrs, 1),
                    "total_hrs": round(self.hours_saved, 1),
                    "value_kes": round(self.hours_saved * 200, 0),  # KES 200/hr opportunity cost
                },
                "money_saved": {
                    "better_prices_kes": round(self.money_saved_better_prices_kes, 0),
                    "less_spoilage_kes": round(self.money_saved_less_spoilage_kes, 0),
                    "stockout_prevention_kes": round(self.money_saved_stockout_prevention_kes, 0),
                    "total_kes": round(self.money_saved_kes, 0),
                },
                "money_earned": {
                    "credit_access_kes": round(self.money_earned_credit_access_kes, 0),
                    "market_intelligence_kes": round(self.money_earned_market_intel_kes, 0),
                    "business_growth_kes": round(self.money_earned_business_growth_kes, 0),
                    "total_kes": round(self.money_earned_kes, 0),
                },
            },
        }


@dataclass
class AggregateMetrics:
    """Aggregate value metrics across all workers."""

    total_workers: int = 0
    active_workers_30d: int = 0
    total_hours_saved: float = 0.0
    total_money_saved_kes: float = 0.0
    total_money_earned_kes: float = 0.0
    total_value_delivered_kes: float = 0.0
    total_transactions: int = 0
    avg_value_per_worker_kes: float = 0.0
    avg_hours_saved_per_worker: float = 0.0
    value_to_data_ratio: float = 0.0  # worker value / data revenue

    def to_dict(self) -> dict:
        return {
            "total_workers": self.total_workers,
            "active_workers_30d": self.active_workers_30d,
            "total_hours_saved": round(self.total_hours_saved, 1),
            "total_money_saved_kes": round(self.total_money_saved_kes, 0),
            "total_money_earned_kes": round(self.total_money_earned_kes, 0),
            "total_value_delivered_kes": round(self.total_value_delivered_kes, 0),
            "total_value_delivered_usd": round(self.total_value_delivered_kes / 135, 0),
            "total_transactions": self.total_transactions,
            "avg_value_per_worker_kes": round(self.avg_value_per_worker_kes, 0),
            "avg_hours_saved_per_worker": round(self.avg_hours_saved_per_worker, 1),
            "value_to_data_ratio": round(self.value_to_data_ratio, 1),
            "value_first_status": (
                "healthy" if self.value_to_data_ratio >= 5.0
                else "developing" if self.value_to_data_ratio >= 2.0
                else "needs_improvement"
            ),
        }


# Default path for state persistence
_DEFAULT_STATE_DIR = Path(".openclaw/tmp/infrastructure")


class WorkerValueTracker:
    """
    Tracks the value each worker gets from Msaidizi.

    Usage:
        tracker = WorkerValueTracker()
        tracker.track_time_saved("worker_123", hours_saved=1.5)
        tracker.track_money_saved("worker_123", amount_saved=500, category="better_prices")
        summary = tracker.get_value_summary("worker_123")
        aggregate = tracker.get_aggregate_value()
    """

    # Valid categories for money_saved and money_earned
    _VALID_SAVED_CATEGORIES = {"better_prices", "less_spoilage", "stockout_prevention"}
    _VALID_EARNED_SOURCES = {"credit_access", "market_intelligence", "business_growth"}
    _VALID_TIME_SOURCES = {"voice_bookkeeping", "automated_reports"}
    _MAX_LIMIT = 1000

    def __init__(self, state_dir: str | None = None):
        self._state_dir = Path(state_dir) if state_dir else _DEFAULT_STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._workers: dict[str, WorkerMetrics] = {}
        self._load_all_workers_sync()

    # ------------------------------------------------------------------
    # Tracking methods
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_worker_id(worker_id: str) -> str:
        """Sanitize worker_id to prevent path traversal attacks."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', worker_id):
            raise ValueError(f"Invalid worker_id: {worker_id}")
        return worker_id

    def track_time_saved(
        self,
        worker_id: str,
        hours_saved: float,
        source: str = "voice_bookkeeping",
    ) -> dict:
        """
        Record time saved for a worker.

        Args:
            worker_id: Worker identifier
            hours_saved: Hours saved (e.g., 0.5 for 30 min)
            source: Source of time savings (voice_bookkeeping, automated_reports, etc.)
        """
        worker_id = self._sanitize_worker_id(worker_id)
        if hours_saved < 0:
            raise ValueError(f"hours_saved must be non-negative, got {hours_saved}")
        if source not in self._VALID_TIME_SOURCES:
            raise ValueError(f"Invalid source: {source}. Valid: {self._VALID_TIME_SOURCES}")
        worker = self._get_or_create(worker_id)
        worker.hours_saved += hours_saved
        if source == "voice_bookkeeping":
            worker.time_saved_voice_bookkeeping_hrs += hours_saved
        self._touch_worker(worker)
        self._save_worker(worker)

        return {
            "tracked": True,
            "worker_id": worker_id,
            "hours_saved": hours_saved,
            "source": source,
            "cumulative_hours_saved": round(worker.hours_saved, 1),
            "estimated_value_kes": round(worker.hours_saved * 200, 0),
        }

    def track_money_saved(
        self,
        worker_id: str,
        amount_saved: float,
        category: str = "better_prices",
    ) -> dict:
        """
        Record money saved for a worker.

        Args:
            worker_id: Worker identifier
            amount_saved: Amount saved in KES
            category: better_prices | less_spoilage | stockout_prevention
        """
        worker_id = self._sanitize_worker_id(worker_id)
        if amount_saved < 0:
            raise ValueError(f"amount_saved must be non-negative, got {amount_saved}")
        if category not in self._VALID_SAVED_CATEGORIES:
            raise ValueError(
                f"Invalid category: {category}. Valid: {self._VALID_SAVED_CATEGORIES}"
            )
        worker = self._get_or_create(worker_id)
        worker.money_saved_kes += amount_saved

        if category == "better_prices":
            worker.money_saved_better_prices_kes += amount_saved
        elif category == "less_spoilage":
            worker.money_saved_less_spoilage_kes += amount_saved
        elif category == "stockout_prevention":
            worker.money_saved_stockout_prevention_kes += amount_saved

        self._touch_worker(worker)
        self._save_worker(worker)

        return {
            "tracked": True,
            "worker_id": worker_id,
            "amount_saved_kes": amount_saved,
            "category": category,
            "cumulative_money_saved_kes": round(worker.money_saved_kes, 0),
        }

    def track_money_earned(
        self,
        worker_id: str,
        amount_earned: float,
        source: str = "market_intelligence",
    ) -> dict:
        """
        Record money earned for a worker.

        Args:
            worker_id: Worker identifier
            amount_earned: Amount earned in KES
            source: credit_access | market_intelligence | business_growth
        """
        worker_id = self._sanitize_worker_id(worker_id)
        if amount_earned < 0:
            raise ValueError(f"amount_earned must be non-negative, got {amount_earned}")
        if source not in self._VALID_EARNED_SOURCES:
            raise ValueError(
                f"Invalid source: {source}. Valid: {self._VALID_EARNED_SOURCES}"
            )
        worker = self._get_or_create(worker_id)
        worker.money_earned_kes += amount_earned

        if source == "credit_access":
            worker.money_earned_credit_access_kes += amount_earned
        elif source == "market_intelligence":
            worker.money_earned_market_intel_kes += amount_earned
        elif source == "business_growth":
            worker.money_earned_business_growth_kes += amount_earned

        self._touch_worker(worker)
        self._save_worker(worker)

        return {
            "tracked": True,
            "worker_id": worker_id,
            "amount_earned_kes": amount_earned,
            "source": source,
            "cumulative_money_earned_kes": round(worker.money_earned_kes, 0),
        }

    def record_transaction(self, worker_id: str) -> dict:
        """Increment transaction count for a worker."""
        worker_id = self._sanitize_worker_id(worker_id)
        worker = self._get_or_create(worker_id)
        worker.transactions_recorded += 1
        self._touch_worker(worker)
        self._save_worker(worker)

        return {
            "tracked": True,
            "worker_id": worker_id,
            "total_transactions": worker.transactions_recorded,
        }

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_value_summary(self, worker_id: str) -> dict:
        """Show how much value this worker has received."""
        worker_id = self._sanitize_worker_id(worker_id)
        worker = self._workers.get(worker_id)
        if not worker:
            return {
                "worker_id": worker_id,
                "status": "not_found",
                "message": "No data recorded for this worker yet.",
            }

        data = worker.to_dict()
        total_value = data["total_value_kes"]

        data["impact_statement"] = self._impact_statement(total_value, worker.hours_saved)
        data["value_comparison"] = {
            "your_value_per_month_kes": round(total_value / max(worker.days_active / 30, 1), 0),
            "average_platform_value_kes": 5_000,  # From critical-mass-value.md
            "data_revenue_generated_kes": round(worker.transactions_recorded * 0.28, 0),  # ~KES 0.28/txn
            "value_to_data_ratio": round(
                total_value / max(worker.transactions_recorded * 0.28, 1), 1
            ),
        }

        return data

    def get_aggregate_value(self) -> dict:
        """Aggregate value metrics across all workers."""
        agg = AggregateMetrics()

        for worker in self._workers.values():
            agg.total_workers += 1
            agg.total_hours_saved += worker.hours_saved
            agg.total_money_saved_kes += worker.money_saved_kes
            agg.total_money_earned_kes += worker.money_earned_kes
            agg.total_transactions += worker.transactions_recorded

            # Check if active in last 30 days
            if worker.last_active_at:
                try:
                    last = datetime.fromisoformat(worker.last_active_at)
                    if (datetime.now(UTC) - last).days <= 30:
                        agg.active_workers_30d += 1
                except ValueError:
                    pass

        agg.total_value_delivered_kes = agg.total_money_saved_kes + agg.total_money_earned_kes

        if agg.total_workers > 0:
            agg.avg_value_per_worker_kes = agg.total_value_delivered_kes / agg.total_workers
            agg.avg_hours_saved_per_worker = agg.total_hours_saved / agg.total_workers

        # Value-to-data ratio: worker value / data revenue
        # Data revenue ~KES 500/worker/month (from critical-mass-value.md)
        data_revenue = agg.total_workers * 500
        if data_revenue > 0:
            agg.value_to_data_ratio = agg.total_value_delivered_kes / data_revenue

        return agg.to_dict()

    def get_top_workers(self, limit: int = 10) -> list[dict]:
        """Get top workers by total value received."""
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        limit = min(limit, self._MAX_LIMIT)
        ranked = sorted(
            self._workers.values(),
            key=lambda w: w.money_saved_kes + w.money_earned_kes,
            reverse=True,
        )
        return [
            {
                "worker_id": w.worker_id,
                "total_value_kes": round(w.money_saved_kes + w.money_earned_kes, 0),
                "hours_saved": round(w.hours_saved, 1),
                "transactions": w.transactions_recorded,
                "days_active": w.days_active,
            }
            for w in ranked[:limit]
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create(self, worker_id: str) -> WorkerMetrics:
        if worker_id not in self._workers:
            self._workers[worker_id] = WorkerMetrics(
                worker_id=worker_id,
                first_active_at=datetime.now(UTC).isoformat(),
            )
        return self._workers[worker_id]

    def _touch_worker(self, worker: WorkerMetrics) -> None:
        now = datetime.now(UTC).isoformat()
        worker.last_active_at = now
        # Estimate days active from first_active_at
        try:
            first = datetime.fromisoformat(worker.first_active_at)
            worker.days_active = max(1, (datetime.now(UTC) - first).days)
        except ValueError:
            worker.days_active = 1

    def _save_worker(self, worker: WorkerMetrics) -> None:
        """Synchronous worker save. Use save_worker_async in async contexts."""
        # Double-check worker_id is safe (defense in depth)
        self._sanitize_worker_id(worker.worker_id)
        path = self._state_dir / f"worker_{worker.worker_id}.json"
        path.write_text(json.dumps(worker.to_dict(), indent=2))
        self._workers[worker.worker_id] = worker

    async def save_worker_async(self, worker: WorkerMetrics) -> None:
        """Async wrapper for worker save — offloads to thread pool."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._save_worker, worker)

    def _load_all_workers_sync(self) -> None:
        for path in self._state_dir.glob("worker_*.json"):
            try:
                data = json.loads(path.read_text())
                # Reconstruct WorkerMetrics from saved data
                breakdown = data.get("breakdown", {})
                ts = breakdown.get("time_saved", {})
                ms = breakdown.get("money_saved", {})
                me = breakdown.get("money_earned", {})

                self._workers[data["worker_id"]] = WorkerMetrics(
                    worker_id=data["worker_id"],
                    hours_saved=data.get("hours_saved", 0),
                    money_saved_kes=data.get("money_saved_kes", 0),
                    money_earned_kes=data.get("money_earned_kes", 0),
                    transactions_recorded=data.get("transactions_recorded", 0),
                    days_active=data.get("days_active", 0),
                    first_active_at=data.get("first_active_at", ""),
                    last_active_at=data.get("last_active_at", ""),
                    time_saved_voice_bookkeeping_hrs=ts.get("voice_bookkeeping_hrs", 0),
                    money_saved_better_prices_kes=ms.get("better_prices_kes", 0),
                    money_saved_less_spoilage_kes=ms.get("less_spoilage_kes", 0),
                    money_saved_stockout_prevention_kes=ms.get("stockout_prevention_kes", 0),
                    money_earned_credit_access_kes=me.get("credit_access_kes", 0),
                    money_earned_market_intel_kes=me.get("market_intelligence_kes", 0),
                    money_earned_business_growth_kes=me.get("business_growth_kes", 0),
                )
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning("Failed to load worker data from %s: %s", path.name, e)
                continue

    async def load_all_workers_async(self) -> None:
        """Async wrapper for loading all workers — offloads to thread pool."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_all_workers_sync)

    @staticmethod
    def _impact_statement(total_value_kes: float, hours_saved: float) -> str:
        if total_value_kes >= 50_000:
            return (
                f"Msaidizi has saved you {hours_saved:.0f} hours and delivered "
                f"KES {total_value_kes:,.0f} in value. You're a power user! 🌟"
            )
        if total_value_kes >= 10_000:
            return (
                f"Msaidizi has saved you {hours_saved:.0f} hours and delivered "
                f"KES {total_value_kes:,.0f} in value. Your business is growing!"
            )
        if total_value_kes >= 1_000:
            return (
                f"Msaidizi has saved you {hours_saved:.0f} hours and delivered "
                f"KES {total_value_kes:,.0f} in value. Keep recording to unlock more."
            )
        return (
            "You've just started with Msaidizi. Record your sales daily to see "
            "your business value grow!"
        )
