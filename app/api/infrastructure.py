"""
Infrastructure Revenue Model & Status Dashboard

Shows workers how their usage drives data center growth.
Every transaction they record contributes to building Africa's
first data center for the informal economy.

The flywheel:
  Worker uses Msaidizi (Day 1 value)
    → More data generated
      → Better intelligence products
        → Buyers pay for intelligence
          → 10-20% allocated to infrastructure
            → Home server → Mini DC → Data Center
              → Better performance → More workers
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import Optional
import os

router = APIRouter(tags=["Infrastructure"])

# ---------------------------------------------------------------------------
# Infrastructure phase definitions
# ---------------------------------------------------------------------------

PHASES = {
    "cloud": {
        "id": 1,
        "name": "Cloud (Oracle Free Tier)",
        "status": "active",
        "started": "2026-06-01",
        "capacity": "1,000 concurrent users",
        "latency_target_ms": 200,
        "cost_monthly": 0,
        "description": "Oracle Cloud Free Tier — 4 OCPU, 24GB RAM, 200GB storage.",
        "worker_benefits": [
            "Voice bookkeeping (saves 5+ hrs/week)",
            "Daily profit reports",
            "Restock alerts",
            "Market price checks",
        ],
        "next_upgrade": "Home Server with ARM + solar power",
    },
    "home_server": {
        "id": 2,
        "name": "Home Server (ARM + Solar)",
        "status": "planned",
        "target_start": "2027-01-01",
        "capacity": "10,000 concurrent users",
        "latency_target_ms": 100,
        "cost_monthly": 120,
        "description": "Ampere Altra ARM server, 3-5 kW solar array, fiber + 4G backup.",
        "worker_benefits": [
            "Faster response times (local processing)",
            "Better credit scoring accuracy",
            "More workers = better market data",
            "Reduced dependency on cloud provider",
        ],
        "next_upgrade": "Mini Data Center (3-5 servers)",
    },
    "mini_dc": {
        "id": 3,
        "name": "Mini Data Center",
        "status": "planned",
        "target_start": "2028-01-01",
        "capacity": "100,000 concurrent users",
        "latency_target_ms": 50,
        "cost_monthly": 400,
        "description": "3-5 ARM servers, 10-20 kW solar, 50-100 kWh battery bank.",
        "worker_benefits": [
            "Real-time market intelligence",
            "Predictive analytics (price forecasting)",
            "Community benchmarks",
            "AI-powered business recommendations",
        ],
        "next_upgrade": "Containerized Data Center",
    },
    "data_center": {
        "id": 4,
        "name": "Data Center",
        "status": "planned",
        "target_start": "2029-01-01",
        "capacity": "1,000,000+ concurrent users",
        "latency_target_ms": 20,
        "cost_monthly": 1000,
        "description": "20-50 ARM servers, 30-100 kW solar, full redundancy.",
        "worker_benefits": [
            "Continental market intelligence",
            "Cross-border trade optimization",
            "Real-time GDP/inflation data",
            "Pan-African business opportunities",
        ],
        "next_upgrade": "Pan-African DC Network",
    },
    "pan_african_network": {
        "id": 5,
        "name": "Pan-African DC Network",
        "status": "vision",
        "target_start": "2030-01-01",
        "capacity": "10,000,000+ concurrent users",
        "latency_target_ms": 10,
        "cost_monthly": 5000,
        "description": "3-5 containerized data centers across Kenya, Nigeria, Tanzania, Uganda, Ethiopia.",
        "worker_benefits": [
            "Sub-10ms latency from any African city",
            "Continental trade intelligence",
            "Cross-border payment optimization",
            "Full offline-first with edge compute",
        ],
        "next_upgrade": None,
    },
}

# Revenue allocation model (year → config)
REVENUE_MODEL = [
    {
        "year": 1,
        "revenue_usd": 310_000,
        "infra_pct": 15,
        "infra_usd": 46_500,
        "what_it_buys": "Home server (ARM) + solar panels + battery bank",
        "phase": "home_server",
        "workers_target": 5_000,
    },
    {
        "year": 2,
        "revenue_usd": 1_200_000,
        "infra_pct": 20,
        "infra_usd": 240_000,
        "what_it_buys": "Mini DC (3-5 servers) + solar array + redundant internet",
        "phase": "mini_dc",
        "workers_target": 20_000,
    },
    {
        "year": 3,
        "revenue_usd": 3_500_000,
        "infra_pct": 15,
        "infra_usd": 525_000,
        "what_it_buys": "Containerized data center + full solar + cooling",
        "phase": "data_center",
        "workers_target": 50_000,
    },
    {
        "year": 4,
        "revenue_usd": 10_000_000,
        "infra_pct": 10,
        "infra_usd": 1_000_000,
        "what_it_buys": "DC expansion + multi-ISP redundancy + edge nodes",
        "phase": "data_center",
        "workers_target": 200_000,
    },
    {
        "year": 5,
        "revenue_usd": 25_000_000,
        "infra_pct": 10,
        "infra_usd": 2_500_000,
        "what_it_buys": "Pan-African DC network (Kenya, Nigeria, Tanzania, Uganda, Ethiopia)",
        "phase": "pan_african_network",
        "workers_target": 1_000_000,
    },
]


def _get_current_phase() -> dict:
    """Determine current infrastructure phase based on date and status."""
    # For now, we're in cloud phase
    return PHASES["cloud"]


def _calculate_flywheel_stats() -> dict:
    """Calculate how worker activity drives infrastructure growth."""
    return {
        "flywheel": {
            "description": (
                "Worker uses Msaidizi → Generates transaction data → "
                "Biashara Intelligence aggregates & sells → Revenue funds "
                "better infrastructure → Better performance attracts more workers"
            ),
            "stages": [
                {
                    "stage": "Worker Value (Day 1)",
                    "description": "Voice bookkeeping, profit reports, restock alerts",
                    "value_to_worker_kes_month": "3,000-8,000",
                },
                {
                    "stage": "Data Generation",
                    "description": "Each worker records 5-50 transactions/day",
                    "data_points_per_worker_day": "5-50",
                },
                {
                    "stage": "Intelligence Products",
                    "description": "Soko Pulse, Alama Score, Biashara Pulse, Jamii Insights",
                    "products_activated_at_workers": {
                        "soko_pulse": 1_000,
                        "alama_score": 5_000,
                        "biashara_pulse": 10_000,
                        "jamii_insights": 20_000,
                        "tax_base": 50_000,
                    },
                },
                {
                    "stage": "Revenue",
                    "description": "Intelligence buyers pay for aggregated, anonymized data",
                    "year_1_target_usd": 310_000,
                    "year_3_target_usd": 3_500_000,
                },
                {
                    "stage": "Infrastructure Investment",
                    "description": "10-20% of revenue allocated to data center buildout",
                    "year_1_infra_usd": 46_500,
                    "year_3_infra_usd": 525_000,
                },
                {
                    "stage": "Better Service",
                    "description": "Faster latency, more capacity, predictive analytics",
                    "latency_improvement_ms": "200 → 100 → 50 → 20 → 10",
                },
            ],
        }
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/v1/infrastructure/status")
async def infrastructure_status():
    """
    Infrastructure status dashboard.

    Shows workers how their usage drives infrastructure growth:
    - Current phase (Cloud/Home Server/Mini DC/DC)
    - Revenue allocated to infrastructure
    - Next milestone
    - Performance metrics (latency, uptime)
    - The flywheel: how worker value → data center
    """
    current = _get_current_phase()
    flywheel = _calculate_flywheel_stats()

    return {
        "current_phase": current,
        "next_phase": current.get("next_upgrade"),
        "revenue_model": REVENUE_MODEL,
        "flywheel": flywheel["flywheel"],
        "message": (
            "Every transaction you record in Msaidizi helps build Africa's "
            "first data center for the informal economy. Your data creates "
            "intelligence that funds better infrastructure — which means "
            "faster service, better credit access, and more opportunities for you."
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/infrastructure/phases")
async def infrastructure_phases():
    """List all infrastructure phases with worker benefits at each stage."""
    return {
        "phases": PHASES,
        "total_investment_5yr_usd": sum(r["infra_usd"] for r in REVENUE_MODEL),
        "total_workers_target_5yr": REVENUE_MODEL[-1]["workers_target"],
    }


@router.get("/api/v1/infrastructure/revenue-model")
async def infrastructure_revenue_model():
    """
    Infrastructure revenue allocation model.

    Shows how company revenue funds data center growth:
    - 10-20% of revenue → infrastructure
    - Cloud → Home Server → Mini DC → Data Center → Pan-African Network
    """
    total_revenue = sum(r["revenue_usd"] for r in REVENUE_MODEL)
    total_infra = sum(r["infra_usd"] for r in REVENUE_MODEL)

    return {
        "revenue_model": REVENUE_MODEL,
        "summary": {
            "total_5yr_revenue_usd": total_revenue,
            "total_5yr_infra_usd": total_infra,
            "avg_infra_pct": round(total_infra / total_revenue * 100, 1),
            "phases": [
                "Cloud → Home Server → Mini DC → Data Center → Pan-African Network"
            ],
        },
        "principle": (
            "Infrastructure is funded by revenue, not external investment. "
            "Workers generate data → Data creates intelligence → "
            "Intelligence generates revenue → Revenue builds infrastructure → "
            "Better infrastructure serves more workers."
        ),
    }


@router.get("/api/v1/infrastructure/worker-impact")
async def worker_impact():
    """
    How worker activity impacts infrastructure growth.

    Shows each worker that their usage directly contributes
    to building Africa's data infrastructure.
    """
    return {
        "your_impact": {
            "transactions_per_day": "10 (average)",
            "data_value_per_month_usd": 3.75,
            "infrastructure_contribution_per_month_usd": 0.56,
            "description": (
                "Your 10 daily transactions generate ~$3.75/month in intelligence "
                "value. Of that, ~$0.56 goes to building better infrastructure "
                "for you and 600M+ workers like you."
            ),
        },
        "collective_impact": {
            "at_1000_workers": {
                "transactions_per_day": 10_000,
                "unlocks": "Soko Pulse (real-time market prices)",
                "monthly_data_value_usd": 3_750,
            },
            "at_5000_workers": {
                "transactions_per_day": 50_000,
                "unlocks": "Alama Score (credit scoring)",
                "monthly_data_value_usd": 18_750,
            },
            "at_20000_workers": {
                "transactions_per_day": 200_000,
                "unlocks": "Jamii Insights (community intelligence)",
                "monthly_data_value_usd": 75_000,
            },
            "at_50000_workers": {
                "transactions_per_day": 500_000,
                "unlocks": "Tax Base Estimation (government intelligence)",
                "monthly_data_value_usd": 187_500,
            },
        },
        "message": (
            "You're not just recording transactions — you're building "
            "Africa's digital infrastructure. Every sale you log, every "
            "profit report you read, every restock alert that saves you "
            "money — it all feeds the flywheel that builds the data center "
            "that serves 600 million informal workers."
        ),
    }
