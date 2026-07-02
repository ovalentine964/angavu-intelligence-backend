"""
Data Center Roadmap Service

Tracks progress towards building Africa's first data center
for the informal economy.

Every worker's usage contributes to the data center fund.
Every intelligence product sold brings us closer.
Every new worker makes the data center more valuable.

Phase 1: Cloud (Oracle free tier) → $0/month
Phase 2: Home server + solar → $2K-5K
Phase 3: Mini DC → $15K-30K
Phase 4: Containerized DC → $50K-200K
Phase 5: Pan-African DC network → $500K+
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Phase(IntEnum):
    CLOUD = 1
    HOME_SERVER = 2
    MINI_DC = 3
    DATA_CENTER = 4
    PAN_AFRICAN_NETWORK = 5


PHASE_THRESHOLDS: dict[int, dict] = {
    Phase.CLOUD: {
        "name": "Cloud (Oracle Free Tier)",
        "min_workers": 0,
        "min_monthly_revenue_usd": 0,
        "infra_budget_usd": 0,
        "capacity": "1,000 concurrent users",
        "latency_target_ms": 200,
        "cost_monthly_usd": 0,
        "description": "Oracle Cloud Free Tier — 4 OCPU, 24GB RAM, 200GB storage.",
        "worker_benefits": [
            "Voice bookkeeping (saves 5+ hrs/week)",
            "Daily profit reports",
            "Restock alerts",
            "Market price checks",
        ],
    },
    Phase.HOME_SERVER: {
        "name": "Home Server (ARM + Solar)",
        "min_workers": 1_000,
        "min_monthly_revenue_usd": 5_000,
        "infra_budget_usd": 6_200,
        "capacity": "10,000 concurrent users",
        "latency_target_ms": 100,
        "cost_monthly_usd": 120,
        "description": "Ampere Altra ARM server, 3-5 kW solar array, fiber + 4G backup.",
        "worker_benefits": [
            "2x faster response times (local processing)",
            "Better credit scoring accuracy",
            "More workers = better market data",
            "Reduced dependency on cloud provider",
        ],
    },
    Phase.MINI_DC: {
        "name": "Mini Data Center",
        "min_workers": 10_000,
        "min_monthly_revenue_usd": 55_000,
        "infra_budget_usd": 24_500,
        "capacity": "100,000 concurrent users",
        "latency_target_ms": 50,
        "cost_monthly_usd": 400,
        "description": "3-5 ARM servers, 10-20 kW solar, 50-100 kWh battery bank.",
        "worker_benefits": [
            "Real-time market intelligence",
            "Predictive analytics (price forecasting)",
            "Community benchmarks",
            "AI-powered business recommendations",
        ],
    },
    Phase.DATA_CENTER: {
        "name": "Data Center",
        "min_workers": 50_000,
        "min_monthly_revenue_usd": 200_000,
        "infra_budget_usd": 93_000,
        "capacity": "1,000,000+ concurrent users",
        "latency_target_ms": 20,
        "cost_monthly_usd": 1_000,
        "description": "20-50 ARM servers, 30-100 kW solar, full redundancy.",
        "worker_benefits": [
            "Continental market intelligence",
            "Cross-border trade optimization",
            "Real-time GDP/inflation data",
            "Pan-African business opportunities",
        ],
    },
    Phase.PAN_AFRICAN_NETWORK: {
        "name": "Pan-African DC Network",
        "min_workers": 200_000,
        "min_monthly_revenue_usd": 1_000_000,
        "infra_budget_usd": 500_000,
        "capacity": "10,000,000+ concurrent users",
        "latency_target_ms": 10,
        "cost_monthly_usd": 5_000,
        "description": "3-5 containerized DCs across Kenya, Nigeria, Tanzania, Uganda, Ethiopia.",
        "worker_benefits": [
            "Sub-10ms latency from any African city",
            "Continental trade intelligence",
            "Cross-border payment optimization",
            "Full offline-first with edge compute",
        ],
    },
}

# Revenue allocation percentages by phase
INFRA_ALLOCATION_PCT = {
    Phase.CLOUD: 0.10,
    Phase.HOME_SERVER: 0.15,
    Phase.MINI_DC: 0.20,
    Phase.DATA_CENTER: 0.15,
    Phase.PAN_AFRICAN_NETWORK: 0.10,
}


@dataclass
class RoadmapState:
    """Persisted state for the infrastructure roadmap."""

    current_phase: int = Phase.CLOUD
    total_infra_fund_usd: float = 0.0
    total_workers: int = 0
    monthly_revenue_usd: float = 0.0
    monthly_infra_allocation_usd: float = 0.0
    phase_started_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "current_phase": self.current_phase,
            "total_infra_fund_usd": self.total_infra_fund_usd,
            "total_workers": self.total_workers,
            "monthly_revenue_usd": self.monthly_revenue_usd,
            "monthly_infra_allocation_usd": self.monthly_infra_allocation_usd,
            "phase_started_at": self.phase_started_at,
            "updated_at": self.updated_at,
        }


class DataCenterRoadmap:
    """
    Tracks progress towards building Africa's first data center
    for the informal economy.

    Usage:
        roadmap = DataCenterRoadmap()
        phase = roadmap.get_current_phase()
        progress = roadmap.get_progress_to_next_phase()
        contribution = roadmap.get_worker_contribution("worker_123")
    """

    def __init__(self, state_path: Optional[str] = None):
        self._state_path = Path(state_path) if state_path else None
        self._state = self._load_state()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_worker_id(worker_id: str) -> str:
        """Sanitize worker_id to prevent path traversal attacks."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', worker_id):
            raise ValueError(f"Invalid worker_id: {worker_id}")
        return worker_id

    def _load_state(self) -> RoadmapState:
        if self._state_path and self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text())
                return RoadmapState(**data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Failed to load roadmap state from %s: %s", self._state_path, e)
                pass
        return RoadmapState(
            current_phase=Phase.CLOUD,
            phase_started_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _save_state(self) -> None:
        if self._state_path:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(self._state.to_dict(), indent=2))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_metrics(
        self,
        total_workers: int,
        monthly_revenue_usd: float,
        *,
        persist: bool = True,
    ) -> dict:
        """
        Update the roadmap with current business metrics.
        Automatically evaluates phase transitions.
        """
        self._state.total_workers = total_workers
        self._state.monthly_revenue_usd = monthly_revenue_usd
        allocation_pct = INFRA_ALLOCATION_PCT.get(self._state.current_phase, 0.10)
        self._state.monthly_infra_allocation_usd = monthly_revenue_usd * allocation_pct
        self._state.total_infra_fund_usd += self._state.monthly_infra_allocation_usd
        self._state.updated_at = datetime.now(timezone.utc).isoformat()

        # Check for phase transition
        transition = self._maybe_advance_phase()

        if persist:
            self._save_state()

        return {
            "state": self._state.to_dict(),
            "transition": transition,
        }

    def get_current_phase(self) -> dict:
        """What phase are we in based on revenue and worker count?"""
        phase_id = self._state.current_phase
        phase_info = PHASE_THRESHOLDS[phase_id]

        return {
            "phase_id": phase_id,
            "phase_name": phase_info["name"],
            "description": phase_info["description"],
            "capacity": phase_info["capacity"],
            "latency_target_ms": phase_info["latency_target_ms"],
            "cost_monthly_usd": phase_info["cost_monthly_usd"],
            "worker_benefits": phase_info["worker_benefits"],
            "workers": self._state.total_workers,
            "monthly_revenue_usd": self._state.monthly_revenue_usd,
            "infra_fund_usd": self._state.total_infra_fund_usd,
            "phase_started_at": self._state.phase_started_at,
            "updated_at": self._state.updated_at,
        }

    def get_progress_to_next_phase(self) -> dict:
        """How close are we to the next phase?"""
        current = self._state.current_phase
        if current >= Phase.PAN_AFRICAN_NETWORK:
            return {
                "current_phase": current,
                "next_phase": None,
                "next_phase_name": None,
                "progress_pct": 100.0,
                "message": "You've reached the final phase — pan-African data center network!",
                "barriers": [],
            }

        next_phase = current + 1
        next_info = PHASE_THRESHOLDS[next_phase]

        # Progress based on workers, revenue, and fund
        worker_progress = min(
            100.0,
            (self._state.total_workers / max(next_info["min_workers"], 1)) * 100,
        )
        revenue_progress = min(
            100.0,
            (self._state.monthly_revenue_usd / max(next_info["min_monthly_revenue_usd"], 1)) * 100,
        )
        fund_progress = min(
            100.0,
            (self._state.total_infra_fund_usd / max(next_info["infra_budget_usd"], 1)) * 100,
        )

        # Overall progress is the minimum — all criteria must be met
        overall = min(worker_progress, revenue_progress, fund_progress)

        barriers = []
        if worker_progress < 100:
            workers_needed = next_info["min_workers"] - self._state.total_workers
            barriers.append({
                "type": "workers",
                "current": self._state.total_workers,
                "target": next_info["min_workers"],
                "gap": max(0, workers_needed),
                "progress_pct": round(worker_progress, 1),
            })
        if revenue_progress < 100:
            revenue_needed = next_info["min_monthly_revenue_usd"] - self._state.monthly_revenue_usd
            barriers.append({
                "type": "monthly_revenue",
                "current_usd": self._state.monthly_revenue_usd,
                "target_usd": next_info["min_monthly_revenue_usd"],
                "gap_usd": max(0, revenue_needed),
                "progress_pct": round(revenue_progress, 1),
            })
        if fund_progress < 100:
            fund_needed = next_info["infra_budget_usd"] - self._state.total_infra_fund_usd
            barriers.append({
                "type": "infra_fund",
                "current_usd": self._state.total_infra_fund_usd,
                "target_usd": next_info["infra_budget_usd"],
                "gap_usd": max(0, fund_needed),
                "progress_pct": round(fund_progress, 1),
            })

        return {
            "current_phase": current,
            "current_phase_name": PHASE_THRESHOLDS[current]["name"],
            "next_phase": next_phase,
            "next_phase_name": next_info["name"],
            "next_phase_description": next_info["description"],
            "next_phase_benefits": next_info["worker_benefits"],
            "progress_pct": round(overall, 1),
            "breakdown": {
                "workers": round(worker_progress, 1),
                "revenue": round(revenue_progress, 1),
                "fund": round(fund_progress, 1),
            },
            "barriers": barriers,
            "message": self._progress_message(overall, next_info["name"]),
        }

    def get_worker_contribution(self, worker_id: str) -> dict:
        """
        How much has this worker contributed to the data center fund?

        In a production system this would query the transaction DB.
        For now we estimate based on average worker economics.
        """
        worker_id = self._sanitize_worker_id(worker_id)
        # Average worker economics from critical-mass-value.md
        avg_data_value_per_month_usd = 3.75  # KES 500
        infra_allocation_pct = INFRA_ALLOCATION_PCT.get(self._state.current_phase, 0.10)
        contribution_per_month_usd = avg_data_value_per_month_usd * infra_allocation_pct

        return {
            "worker_id": worker_id,
            "estimated_monthly_data_value_usd": avg_data_value_per_month_usd,
            "infra_allocation_pct": infra_allocation_pct,
            "estimated_monthly_contribution_usd": round(contribution_per_month_usd, 2),
            "estimated_monthly_contribution_kes": round(contribution_per_month_usd * 135, 0),
            "note": "Contribution is estimated from average worker economics. "
                    "Actual contribution tracked per-worker in production.",
            "message": (
                f"Your transactions this month contribute ~KES "
                f"{round(contribution_per_month_usd * 135)} to building "
                f"Africa's data infrastructure."
            ),
        }

    def get_infrastructure_metrics(self) -> dict:
        """Current infrastructure performance: latency, uptime, cost/worker."""
        phase_info = PHASE_THRESHOLDS[self._state.current_phase]
        workers = max(self._state.total_workers, 1)

        return {
            "phase": phase_info["name"],
            "latency_target_ms": phase_info["latency_target_ms"],
            "cost_monthly_usd": phase_info["cost_monthly_usd"],
            "cost_per_worker_usd": round(phase_info["cost_monthly_usd"] / workers, 4),
            "capacity": phase_info["capacity"],
            "uptime_target_pct": 99.5 if self._state.current_phase >= Phase.MINI_DC else 99.0,
            "vs_cloud": {
                "oracle_cost_per_user_month_usd": 0.012,
                "our_cost_per_user_month_usd": round(phase_info["cost_monthly_usd"] / workers, 4),
                "savings_pct": round(
                    max(0, (1 - phase_info["cost_monthly_usd"] / max(workers * 0.012, 0.001))) * 100, 1
                ),
            },
        }

    def get_phase_benefits(self, phase: int) -> dict:
        """What benefits does this phase bring to workers?"""
        if phase not in PHASE_THRESHOLDS:
            return {"error": f"Invalid phase {phase}. Valid: 1-5"}

        info = PHASE_THRESHOLDS[phase]
        is_current = phase == self._state.current_phase
        is_future = phase > self._state.current_phase
        is_past = phase < self._state.current_phase

        status = "current" if is_current else ("future" if is_future else "completed")

        return {
            "phase_id": phase,
            "phase_name": info["name"],
            "status": status,
            "description": info["description"],
            "capacity": info["capacity"],
            "latency_target_ms": info["latency_target_ms"],
            "cost_monthly_usd": info["cost_monthly_usd"],
            "worker_benefits": info["worker_benefits"],
            "min_workers_required": info["min_workers"],
            "min_monthly_revenue_usd": info["min_monthly_revenue_usd"],
            "infra_budget_usd": info["infra_budget_usd"],
        }

    def get_all_phases(self) -> dict:
        """Full roadmap overview with all phases."""
        phases = []
        for phase_id in sorted(PHASE_THRESHOLDS.keys()):
            phases.append(self.get_phase_benefits(phase_id))

        return {
            "current_phase": self._state.current_phase,
            "total_infra_fund_usd": self._state.total_infra_fund_usd,
            "total_workers": self._state.total_workers,
            "phases": phases,
            "timeline": {
                "phase_1_start": "2026-06",
                "phase_2_target": "2027-01",
                "phase_3_target": "2028-01",
                "phase_4_target": "2029-01",
                "phase_5_target": "2030-01",
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_advance_phase(self) -> Optional[dict]:
        """Check if we've met the criteria for the next phase."""
        current = self._state.current_phase
        if current >= Phase.PAN_AFRICAN_NETWORK:
            return None

        next_phase = current + 1
        next_info = PHASE_THRESHOLDS[next_phase]

        workers_met = self._state.total_workers >= next_info["min_workers"]
        revenue_met = self._state.monthly_revenue_usd >= next_info["min_monthly_revenue_usd"]
        fund_met = self._state.total_infra_fund_usd >= next_info["infra_budget_usd"]

        if workers_met and revenue_met and fund_met:
            old_phase = self._state.current_phase
            self._state.current_phase = next_phase
            self._state.phase_started_at = datetime.now(timezone.utc).isoformat()
            return {
                "transitioned": True,
                "from_phase": old_phase,
                "to_phase": next_phase,
                "to_phase_name": next_info["name"],
                "message": f"🚀 Phase transition: {PHASE_THRESHOLDS[old_phase]['name']} → {next_info['name']}!",
            }

        return None

    @staticmethod
    def _progress_message(pct: float, next_name: str) -> str:
        if pct >= 90:
            return f"Almost there! {next_name} is within reach."
        if pct >= 60:
            return f"Strong progress towards {next_name}. Keep growing!"
        if pct >= 30:
            return f"Building towards {next_name}. Every worker counts."
        return f"Early days — {next_name} is the long-term goal."
