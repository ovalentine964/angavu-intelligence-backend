"""Pydantic schemas for API request/response validation."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ── Base Schemas ───────────────────────────────────────────────

class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── User Schemas ───────────────────────────────────────────────

class UserCreate(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=128)
    phone_hash: str = Field(..., min_length=16, max_length=64)
    role: str = Field(default="user", pattern="^(user|analyst|admin)$")


class UserResponse(BaseModel):
    id: uuid.UUID
    external_id: str
    role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Transaction Schemas ────────────────────────────────────────

class TransactionCreate(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = Field(default="KES", min_length=3, max_length=3)
    category: str = Field(..., min_length=1, max_length=50)
    subcategory: str | None = None
    merchant_category: str | None = None
    region: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    channel: str | None = None
    recorded_at: datetime


class TransactionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: float
    currency: str
    category: str
    region: str | None
    recorded_at: datetime

    model_config = {"from_attributes": True}


# ── Intelligence Schemas ───────────────────────────────────────

class IntelligenceQuery(BaseModel):
    """Query for intelligence products."""
    report_type: str = Field(..., description="Intelligence product type")
    region: str | None = None
    sector: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = Field(default=10, ge=1, le=100)


class IntelligenceReportResponse(BaseModel):
    id: uuid.UUID
    report_type: str
    title: str
    content: dict
    region: str | None
    sector: str | None
    confidence: float
    data_points: int
    published_at: datetime

    model_config = {"from_attributes": True}


# ── Credit Score Schemas ───────────────────────────────────────

class CreditScoreRequest(BaseModel):
    user_id: uuid.UUID
    include_factors: bool = True


class CreditScoreResponse(BaseModel):
    score: int = Field(..., ge=300, le=850)
    tier: str
    factors: dict | None = None
    model_version: str
    valid_until: datetime


# ── Market Signal Schemas ──────────────────────────────────────

class MarketSignalCreate(BaseModel):
    signal_type: str
    region: str
    sector: str
    value: float
    confidence: float = Field(..., ge=0, le=1)
    sample_size: int = Field(..., ge=1)
    period_start: datetime
    period_end: datetime

    @field_validator("period_end")
    @classmethod
    def validate_period(cls, v: datetime, info) -> datetime:
        if "period_start" in info.data and v <= info.data["period_start"]:
            raise ValueError("period_end must be after period_start")
        return v


class MarketSignalResponse(BaseModel):
    id: uuid.UUID
    signal_type: str
    region: str
    sector: str
    value: float
    confidence: float
    sample_size: int
    period_start: datetime
    period_end: datetime

    model_config = {"from_attributes": True}


# ── Health / Status ────────────────────────────────────────────

class HealthCheck(BaseModel):
    status: str = "ok"
    version: str
    environment: str
    uptime_seconds: float
    services: dict[str, str]


# ── Superagent Schemas ─────────────────────────────────────────

class SuperagentRequest(BaseModel):
    """Request to the superagent orchestrator."""
    capability: str = Field(..., description="Which capability module to invoke")
    query: str = Field(..., min_length=1, max_length=10000)
    context: dict[str, Any] = Field(default_factory=dict)
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")


class SuperagentResponse(BaseModel):
    """Response from the superagent orchestrator."""
    request_id: uuid.UUID
    capability: str
    result: dict[str, Any]
    confidence: float
    processing_time_ms: float
    model_used: str
    guardrails_applied: list[str]
