"""Application configuration using pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — reads from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Environment ───────────────────────────────────────────
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"

    # ── API ────────────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Angavu Intelligence Backend"
    VERSION: str = "1.0.0"
    ALLOWED_ORIGINS: list[str] = ["*"]
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Database ───────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://angavu:angavu_pass@localhost:5432/angavu"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30

    # ── ClickHouse ─────────────────────────────────────────────
    CLICKHOUSE_URL: str = "http://localhost:8123"
    CLICKHOUSE_DATABASE: str = "angavu_analytics"

    # ── Redis ──────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    CACHE_TTL_SECONDS: int = 300

    # ── LLM Providers ─────────────────────────────────────────
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_REASONER_MODEL: str = "deepseek-reasoner"
    DEEPSEEK_CHAT_MODEL: str = "deepseek-chat"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.1

    # ── Security ───────────────────────────────────────────────
    JWT_SECRET: str = "change-me-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    PQC_ENABLED: bool = False

    # ── Privacy / Guardrails ───────────────────────────────────
    K_ANONYMITY_THRESHOLD: int = 10
    DIFFERENTIAL_PRIVACY_EPSILON: float = 0.1
    DIFFERENTIAL_PRIVACY_DELTA: float = 1e-5
    MAX_QUERY_RESULT_ROWS: int = 10000

    # ── Memory ─────────────────────────────────────────────────
    SESSION_TTL_SECONDS: int = 3600
    DAILY_MEMORY_RETENTION_DAYS: int = 90
    PATTERN_MEMORY_RETENTION_DAYS: int = 365
    KNOWLEDGE_GRAPH_MAX_NODES: int = 100000

    # ── Superagent ─────────────────────────────────────────────
    OODA_LOOP_INTERVAL_SECONDS: int = 30
    MAX_CONCURRENT_CAPABILITIES: int = 4
    ORCHESTRATOR_TIMEOUT_SECONDS: int = 120

    # ── Paths ──────────────────────────────────────────────────
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    MODEL_ARTIFACTS_DIR: Path = Field(default=Path("/app/model_artifacts"))

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()


settings = get_settings()
