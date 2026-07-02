"""
Application configuration using pydantic-settings.

All settings are loaded from environment variables with sensible defaults
for local development. See .env.example for the full list.
"""

import os
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Main application settings loaded from environment variables."""

    # === Application ===
    APP_NAME: str = "Biashara Intelligence"
    APP_ENV: str = "development"
    DEBUG: bool = True
    ENABLE_DOCS: bool = False  # Explicit toggle; defaults off even in development
    SECRET_KEY: str = ""
    API_V1_PREFIX: str = "/api/v1"

    # === Database ===
    # Default to SQLite for zero-config micro deployment
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/biashara.db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800
    DATABASE_ECHO: bool = False

    # === Redis (empty = in-memory cache fallback) ===
    REDIS_URL: str = ""

    # === Authentication ===
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # === Encryption ===
    ENCRYPTION_KEY: str = ""
    DATA_ENCRYPTION_SALT: str = "msaidizi-salt-2026"

    # === Rate Limiting ===
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    # === Data Pipeline ===
    K_ANONYMITY_THRESHOLD: int = 10
    DIFFERENTIAL_PRIVACY_EPSILON: float = 1.0
    DIFFERENTIAL_PRIVACY_DELTA: float = 1e-5
    MAX_BATCH_SIZE: int = 200
    MAX_PAYLOAD_SIZE_KB: int = 200

    # === External Services ===
    OPENWA_URL: str = "http://localhost:3000"
    OPENWA_WEBHOOK_SECRET: str = ""
    GROQ_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # === ClickHouse (OLAP analytics) ===
    CLICKHOUSE_URL: str = "http://clickhouse:8123"
    CLICKHOUSE_DATABASE: str = "biashara"
    CLICKHOUSE_USER: str = "admin"
    CLICKHOUSE_PASSWORD: str = ""

    # === S3 Compatible Storage ===
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = "msaidizi-data"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "eu-west-1"

    # === Monitoring ===
    SENTRY_DSN: str = ""
    LOG_LEVEL: str = "INFO"

    # === CORS ===
    CORS_ORIGINS: List[str] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from JSON string or list."""
        if isinstance(v, str):
            # Handle comma-separated string
            if v.startswith("["):
                import json
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v, info):
        if not v or v.startswith("change-me"):
            raise ValueError("JWT_SECRET_KEY must be set to a unique secret (got default)")
        env = os.getenv("APP_ENV", info.data.get("APP_ENV", "development"))
        if env == "production" and len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v, info):
        if not v or v.startswith("CHANGE_ME"):
            raise ValueError("SECRET_KEY must be set to a unique secret (got default)")
        env = os.getenv("APP_ENV", info.data.get("APP_ENV", "development"))
        if env == "production" and len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        return v

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v, info):
        if not v or v.startswith("change-me"):
            raise ValueError("ENCRYPTION_KEY must be set to a unique key (got default)")
        env = os.getenv("APP_ENV", info.data.get("APP_ENV", "development"))
        if env == "production" and len(v) < 32:
            raise ValueError("ENCRYPTION_KEY must be at least 32 characters in production")
        return v

    @field_validator("OPENWA_WEBHOOK_SECRET")
    @classmethod
    def validate_webhook_secret(cls, v, info):
        if not v or v == "change-me":
            raise ValueError("OPENWA_WEBHOOK_SECRET must be set (got default)")
        env = os.getenv("APP_ENV", info.data.get("APP_ENV", "development"))
        if env == "production" and len(v) < 16:
            raise ValueError("OPENWA_WEBHOOK_SECRET must be at least 16 characters in production")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV == "production"

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite backend."""
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def has_redis(self) -> bool:
        """Check if Redis is configured."""
        return bool(self.REDIS_URL)

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")

    @property
    def has_clickhouse(self) -> bool:
        """Check if ClickHouse is configured."""
        return bool(self.CLICKHOUSE_URL and self.CLICKHOUSE_PASSWORD)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses lru_cache to ensure settings are loaded only once per process.
    Call this instead of instantiating Settings() directly.
    """
    return Settings()
