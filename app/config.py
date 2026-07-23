"""
Angavu Intelligence Backend — Configuration

Architecture: arch_backend.md
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://msaidizi:msaidizi@localhost:5432/msaidizi"
    REDIS_URL: str = "redis://localhost:6379/0"
    CLICKHOUSE_URL: str = "http://localhost:8123"
    
    # Security
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "RS256"
    JWT_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    # Federated Learning
    FL_MIN_PARTICANTS: int = 5
    FL_PRIVACY_EPSILON: float = 0.1
    FL_PRIVACY_DELTA: float = 1e-5
    
    # Rate Limiting
    RATE_LIMIT_SYNC: str = "100/hour"
    RATE_LIMIT_REPORTS: str = "200/hour"
    RATE_LIMIT_INTELLIGENCE: str = "50/hour"
    RATE_LIMIT_BUYER: str = "1000/hour"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
