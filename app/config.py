"""
Application configuration using pydantic-settings.

All settings are loaded from environment variables with sensible defaults
for local development. See .env.example for the full list.
"""

import os
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Main application settings loaded from environment variables."""

    # === Application ===
    APP_NAME: str = "Angavu Intelligence"
    APP_ENV: str = "development"
    DEBUG: bool = False
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
    JWT_ALGORITHM: str = "RS256"
    JWT_PRIVATE_KEY: str = ""  # PEM-encoded RSA private key for RS256 signing
    JWT_PUBLIC_KEY: str = ""   # PEM-encoded RSA public key for RS256 verification
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_ISSUER: str = "angavu-intelligence"  # Token issuer claim
    JWT_AUDIENCE: str = "angavu-api"  # Token audience claim

    # === Encryption ===
    ENCRYPTION_KEY: str = ""
    DATA_ENCRYPTION_SALT: str = "msaidizi-salt-2026"

    # === Rate Limiting ===
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    # === Data Pipeline ===
    K_ANONYMITY_THRESHOLD: int = 10
    DIFFERENTIAL_PRIVACY_EPSILON: float = 0.1
    DIFFERENTIAL_PRIVACY_DELTA: float = 1e-5
    MAX_BATCH_SIZE: int = 200
    MAX_PAYLOAD_SIZE_KB: int = 200

    # === External Services ===
    OPENWA_URL: str = "http://localhost:3000"
    OPENWA_WEBHOOK_SECRET: str = ""
    ENABLE_WHATSAPP: bool = False  # Set to true to enable WhatsApp (OpenWA) integration

    # === Telegram Fallback Channel ===
    TELEGRAM_BOT_TOKEN: str = ""  # Bot token from @BotFather
    TELEGRAM_API_URL: str = ""  # Override for self-hosted Telegram Bot API
    ENABLE_TELEGRAM: bool = False  # Enable Telegram as fallback channel

    # === SMS Fallback Channel (Africa's Talking) ===
    AFRICASTALKING_API_KEY: str = ""
    AFRICASTALKING_USERNAME: str = ""
    AFRICASTALKING_SENDER_ID: str = "Msaidizi"
    ENABLE_SMS: bool = False  # Enable SMS as fallback channel

    # === Channel Failover ===
    CHANNEL_FAILOVER_ENABLED: bool = True  # Enable automatic channel failover
    CHANNEL_HEALTH_CHECK_INTERVAL: int = 60  # Seconds between health checks
    # NOTE: GROQ_API_KEY, DEEPSEEK_API_KEY, NVIDIA_NIM_API_KEY removed.
    # Angavu uses zero-cost on-device inference only.
    # No paid API keys are needed or accepted.

    # === LLM Service (local GGUF + API fallback) ===
    LLM_HOST: str = "localhost"          # llama.cpp server host ("llama-cpp" in Docker)
    LLM_PORT: int = 8080                  # llama.cpp server port
    LLM_MODEL_PATH: str = "qwen2.5-7b-q4_k_m"  # Model name/path on the server
    LLM_TEMPERATURE: float = 0.7          # Default temperature
    LLM_MAX_TOKENS: int = 512             # Default max tokens per completion
    LLM_TIMEOUT: float = 60.0             # Request timeout in seconds
    LLM_FALLBACK_ENABLED: bool = True     # Enable API fallback when local unavailable

    # === Verification / Branding URLs ===
    VERIFICATION_BASE_URL: str = "https://verify.msaidizi.co.ke"
    ANGAVU_DASHBOARD_URL: str = "https://angavu.ai"

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

    # === Agent Scaling ===
    # Controls max concurrent agents and event bus queue depth
    AGENT_MAX_CONCURRENT: int = 50         # Max agents running simultaneously
    AGENT_EVENT_QUEUE_DEPTH: int = 10_000  # Max events buffered per stream
    AGENT_POLL_INTERVAL: float = 1.0       # Seconds between agent event polls
    AGENT_SUBAGENT_MAX_CONCURRENCY: int = 10  # Max sub-agents per parent
    AGENT_SUBAGENT_MAX_DEPTH: int = 3      # Max nesting depth for sub-agents
    AGENT_TASK_TIMEOUT: float = 300.0      # Default task timeout in seconds

    # === Voice Pipeline (ASR / TTS) ===
    WHISPER_URL: str = "http://localhost:9002"  # Whisper ASR service URL
    WHISPER_MODEL: str = "base"                  # Whisper model size (tiny/base/small/medium/large)
    WHISPER_ASR_ENGINE: str = "openai_whisper"   # ASR engine backend
    PIPER_MODEL: str = "sw_CD-mbaza"              # Piper TTS model for Swahili
    PIPER_BINARY: str = "piper"                   # Piper binary path (or Docker service URL)
    VOICE_BACKEND: str = "whisper"                # "whisper" | "sherpa-onnx" | "faster-whisper"
    VOICE_SAMPLE_RATE: int = 16000                # Audio sample rate in Hz
    VOICE_MAX_DURATION_S: float = 120.0           # Max voice message duration (seconds)
    VOICE_TEMP_DIR: str = "/tmp/angavu-voice"     # Temp directory for audio processing
    SHERPA_ONNX_MODEL: str = ""                   # Path to sherpa-onnx model directory

    # === CORS ===
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

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
        # RS256 uses key pairs instead of shared secret
        algorithm = os.getenv("JWT_ALGORITHM", info.data.get("JWT_ALGORITHM", "RS256"))
        if algorithm == "RS256":
            return v  # RS256 doesn't need JWT_SECRET_KEY
        if not v or v.startswith("change-me"):
            raise ValueError("JWT_SECRET_KEY must be set to a unique secret (got default)")
        env = os.getenv("APP_ENV", info.data.get("APP_ENV", "development"))
        if env == "production" and len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v, info):
        if not v or v.startswith("CHANGE_ME") or v.startswith("change-me"):
            raise ValueError("SECRET_KEY must be set to a unique secret (got default)")
        env = os.getenv("APP_ENV", info.data.get("APP_ENV", "development"))
        if env == "production" and len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        return v

    @model_validator(mode="after")
    def validate_secrets_not_empty(self):
        """Cross-validate that secret keys are consistent with the chosen algorithm."""
        # If using HS256 (or any HMAC algorithm), JWT_SECRET_KEY MUST be set
        if self.JWT_ALGORITHM.startswith("HS") and not self.JWT_PRIVATE_KEY:
            if not self.JWT_SECRET_KEY:
                raise ValueError(
                    "JWT_SECRET_KEY must be set when JWT_ALGORITHM is "
                    f"{self.JWT_ALGORITHM} and JWT_PRIVATE_KEY is not provided"
                )
        # SECRET_KEY must never be empty in any environment
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY must not be empty")
        # RS256 requires both private and public keys
        if self.JWT_ALGORITHM == "RS256":
            if not self.JWT_PRIVATE_KEY:
                raise ValueError("JWT_PRIVATE_KEY must be set when using RS256")
            if not self.JWT_PUBLIC_KEY:
                raise ValueError("JWT_PUBLIC_KEY must be set when using RS256")
        # Production: ENCRYPTION_KEY must be set
        if self.APP_ENV == "production" and not self.ENCRYPTION_KEY:
            raise ValueError("ENCRYPTION_KEY must be set in production")
        return self

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
        # Skip validation when WhatsApp is disabled
        enable_whatsapp = os.getenv("ENABLE_WHATSAPP", info.data.get("ENABLE_WHATSAPP", "false"))
        if str(enable_whatsapp).lower() in ("false", "0", "no", ""):
            return v
        if not v or v == "change-me":
            raise ValueError("OPENWA_WEBHOOK_SECRET must be set when ENABLE_WHATSAPP=true (got default)")
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


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses lru_cache to ensure settings are loaded only once per process.
    Call this instead of instantiating Settings() directly.
    """
    return Settings()
