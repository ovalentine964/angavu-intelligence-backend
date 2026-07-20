"""
API v1 — Domain-Organized Sub-Routers.

All /api/v1 endpoints are grouped into logical domains:

    /api/v1/auth/*          — Authentication & OTP
    /api/v1/intelligence/*  — Intelligence products, analysis, FL, reports
    /api/v1/finance/*       — Biashara sync, data sync, formal reports
    /api/v1/channels/*      — WhatsApp, triggers, channel health, webhooks
    /api/v1/agents/*        — Agent management, loops, model routing, harness
    /api/v1/dashboard/*     — Dashboard, policymaker, research
    /api/v1/infra/*         — Deployment, infrastructure, evolution, explainability
    /api/v1/worker/*        — Onboarding, features, stickiness, skills
    /api/v1/revenue-ops/*   — Autonomous revenue operations

Each domain module exposes a single ``domain_router`` that aggregates
the individual feature routers within that domain.
"""

from fastapi import APIRouter

from app.api.v1.auth import auth_router
from app.api.v1.intelligence import intelligence_router
from app.api.v1.finance import finance_router
from app.api.v1.channels import channels_router
from app.api.v1.agents import agents_router
from app.api.v1.dashboard import dashboard_router
from app.api.v1.infra import infra_router
from app.api.v1.worker import worker_router
from app.api.v1.autonomous import autonomous_router

# Master v1 router — includes all domain sub-routers
v1_router = APIRouter()
v1_router.include_router(auth_router)
v1_router.include_router(intelligence_router)
v1_router.include_router(finance_router)
v1_router.include_router(channels_router)
v1_router.include_router(agents_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(infra_router)
v1_router.include_router(worker_router)
v1_router.include_router(autonomous_router)
