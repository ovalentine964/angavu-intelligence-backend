"""
Conftest for autonomous revenue operations tests.

Sets up minimal environment variables so the app config
can be loaded without a full .env file.
"""

import os

# Set minimal env vars for testing
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing!")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")
os.environ.setdefault("OPENWA_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("CLICKHOUSE_URL", "")
os.environ.setdefault("NVIDIA_API_KEY", "test-key")
os.environ.setdefault("ENVIRONMENT", "test")
