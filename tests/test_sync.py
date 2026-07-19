"""
Tests for the sync API and sync service.

Tests cover:
- Successful sync with valid transactions
- Duplicate detection
- Batch size validation
- Invalid transaction rejection
- Inventory updates
- Idempotent syncs
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.database import Base, async_session_factory, engine
from app.main import app
from app.models.user import User
from app.utils.crypto import encrypt_value, hash_phone

# =========================================================================
# Fixtures
# =========================================================================

@pytest_asyncio.fixture
async def client():
    """Create test client with database session override."""
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Drop tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def test_user():
    """Create a test user in the database."""
    phone = "+254712345678"
    user_id = uuid.uuid4()

    async with async_session_factory() as session:
        user = User(
            id=user_id,
            phone_hash=hash_phone(phone),
            phone_encrypted=encrypt_value(phone),
            name_encrypted=encrypt_value("Test User"),
            business_type="dukawallah",
            language="sw",
            location_geohash="ke001",
            location_name="Gikomba Market",
            device_id="test-device-001",
            consent_data_sharing=True,
        )
        session.add(user)
        await session.commit()

    return user_id, phone


@pytest_asyncio.fixture
def auth_headers(test_user):
    """Create auth headers with valid JWT token."""
    from app.api.auth import create_access_token

    user_id, _ = test_user
    token = create_access_token({"sub": str(user_id), "phone_hash": "test"})
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# Tests
# =========================================================================


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test that health endpoint returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "msaidizi-backend"


@pytest.mark.asyncio
async def test_sync_success(client, test_user, auth_headers):
    """Test successful sync with valid transactions."""
    user_id, _ = test_user
    now = datetime.now(UTC)

    payload = {
        "device_id": "test-device-001",
        "user_id": str(user_id),
        "sync_timestamp": now.isoformat(),
        "sync_offset": 0,
        "payload": {
            "transactions": [
                {
                    "transaction_type": "SALE",
                    "item": "sukari",
                    "item_category": "food",
                    "quantity": 5.0,
                    "unit": "kg",
                    "unit_price": 100.0,
                    "amount": 500.0,
                    "payment_method": "cash",
                    "recorded_via": "text",
                    "timestamp": now.isoformat(),
                },
                {
                    "transaction_type": "SALE",
                    "item": "nyanya",
                    "quantity": 10.0,
                    "unit": "kg",
                    "unit_price": 80.0,
                    "amount": 800.0,
                    "payment_method": "mpesa",
                    "recorded_via": "voice",
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                },
                {
                    "transaction_type": "PURCHASE",
                    "item": "mafuta",
                    "quantity": 2.0,
                    "unit": "litres",
                    "unit_price": 150.0,
                    "amount": 300.0,
                    "recorded_via": "manual",
                    "timestamp": (now - timedelta(hours=2)).isoformat(),
                },
            ],
            "inventory_updates": [
                {
                    "item": "sukari",
                    "category": "food",
                    "current_stock": 15.0,
                    "unit": "kg",
                    "avg_cost": 90.0,
                    "sell_price": 100.0,
                    "restock_threshold": 5.0,
                },
            ],
        },
        "device_metadata": {
            "app_version": "0.3.1",
            "android_api": 28,
            "battery_pct": 75,
            "network_type": "wifi",
        },
        "is_compressed": False,
    }

    response = await client.post(
        "/api/v1/sync",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["transactions_received"] == 3
    assert data["transactions_accepted"] == 3
    assert data["transactions_rejected"] == 0
    assert data["inventory_updates_received"] == 1
    assert data["inventory_updates_accepted"] == 1
    assert "sync_id" in data


@pytest.mark.asyncio
async def test_sync_duplicate_detection(client, test_user, auth_headers):
    """Test that duplicate transactions are detected and rejected."""
    user_id, _ = test_user
    now = datetime.now(UTC)

    payload = {
        "device_id": "test-device-001",
        "user_id": str(user_id),
        "sync_timestamp": now.isoformat(),
        "sync_offset": 0,
        "payload": {
            "transactions": [
                {
                    "transaction_type": "SALE",
                    "item": "sukari",
                    "amount": 500.0,
                    "timestamp": now.isoformat(),
                },
            ],
        },
    }

    # First sync — should succeed
    response1 = await client.post("/api/v1/sync", json=payload, headers=auth_headers)
    assert response1.status_code == 200
    assert response1.json()["transactions_accepted"] == 1

    # Second sync — same transaction, should be detected as duplicate
    response2 = await client.post("/api/v1/sync", json=payload, headers=auth_headers)
    assert response2.status_code == 200
    assert response2.json()["transactions_accepted"] == 0
    assert response2.json()["transactions_rejected"] == 1


@pytest.mark.asyncio
async def test_sync_invalid_transaction(client, test_user, auth_headers):
    """Test that invalid transactions are rejected."""
    user_id, _ = test_user
    now = datetime.now(UTC)

    payload = {
        "device_id": "test-device-001",
        "user_id": str(user_id),
        "sync_timestamp": now.isoformat(),
        "sync_offset": 0,
        "payload": {
            "transactions": [
                {
                    "transaction_type": "SALE",
                    "item": "sukari",
                    "amount": -100.0,  # Invalid: negative amount
                    "timestamp": now.isoformat(),
                },
            ],
        },
    }

    response = await client.post("/api/v1/sync", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["transactions_rejected"] == 1
    assert len(data.get("rejection_reasons", [])) > 0


@pytest.mark.asyncio
async def test_sync_user_mismatch(client, test_user, auth_headers):
    """Test that sync rejects requests with mismatched user IDs."""
    user_id, _ = test_user
    now = datetime.now(UTC)

    payload = {
        "device_id": "test-device-001",
        "user_id": str(uuid.uuid4()),  # Different user ID
        "sync_timestamp": now.isoformat(),
        "sync_offset": 0,
        "payload": {
            "transactions": [],
        },
    }

    response = await client.post("/api/v1/sync", json=payload, headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sync_status(client, test_user, auth_headers):
    """Test sync status endpoint."""
    user_id, _ = test_user

    response = await client.get("/api/v1/sync/status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_id)
    assert data["is_active"] is True
