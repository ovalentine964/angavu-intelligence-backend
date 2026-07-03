"""Test configuration for autonomous operations tests.

Sets required environment variables before any app modules are imported.
"""

import os

# Set required env vars before any app imports
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-32-chars-min!")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars-min!")
os.environ.setdefault("OPENWA_WEBHOOK_SECRET", "test-webhook-secret-16c")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
