"""Shared fixtures and environment setup for all tests.

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
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_PRIVATE_KEY", "")

import numpy as np
import pytest


# ════════════════════════════════════════════════════════════════════
# Sample Data Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_transactions():
    """Realistic sample transaction data for a Kenyan dukawallah."""
    return [
        {"item": "sukari", "amount": 500, "type": "SALE", "timestamp": "2026-06-01T10:00:00Z"},
        {"item": "mchele", "amount": 1200, "type": "SALE", "timestamp": "2026-06-01T11:30:00Z"},
        {"item": "unga", "amount": 800, "type": "PURCHASE", "timestamp": "2026-06-02T09:00:00Z"},
        {"item": "nyanya", "amount": 300, "type": "SALE", "timestamp": "2026-06-02T14:00:00Z"},
        {"item": "mafuta", "amount": 1500, "type": "SALE", "timestamp": "2026-06-03T08:00:00Z"},
        {"item": "vitunguu", "amount": 200, "type": "SALE", "timestamp": "2026-06-03T16:00:00Z"},
        {"item": "sukari", "amount": 500, "type": "PURCHASE", "timestamp": "2026-06-04T10:00:00Z"},
        {"item": "mchele", "amount": 1200, "type": "SALE", "timestamp": "2026-06-04T12:00:00Z"},
        {"item": "soap", "amount": 150, "type": "SALE", "timestamp": "2026-06-05T09:00:00Z"},
        {"item": "paraffin", "amount": 400, "type": "SALE", "timestamp": "2026-06-05T17:00:00Z"},
    ]


@pytest.fixture
def sample_worker_profile():
    """Sample worker/business profile for credit scoring tests."""
    return {
        "worker_id": "worker_001",
        "business_name": "Mama Njeri's Duka",
        "location": "Nairobi, Eastlands",
        "geohash": "ke001abc123",
        "months_active": 18,
        "avg_monthly_revenue": 85000.0,
        "product_categories": ["food", "household"],
        "registration_date": "2025-01-15",
    }


@pytest.fixture
def sample_price_series():
    """Sample price time series for econometric tests."""
    np.random.seed(42)
    n = 100
    t = np.arange(n)
    # Realistic price series: trend + seasonality + noise
    trend = 50 + 0.1 * t
    seasonal = 5 * np.sin(2 * np.pi * t / 12)
    noise = np.random.randn(n) * 2
    return trend + seasonal + noise


@pytest.fixture
def sample_ols_data():
    """Sample data for OLS regression tests."""
    np.random.seed(42)
    n = 200
    X = np.random.randn(n, 3)
    beta_true = np.array([5.0, 2.0, -1.0, 0.5])  # intercept + 3 coefficients
    y = beta_true[0] + X @ beta_true[1:] + np.random.randn(n) * 0.5
    return X, y, beta_true
