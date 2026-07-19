"""
Tests for the reports API.

Tests cover:
- Daily report generation
- Weekly report generation
- Advice report generation
- Quick summary endpoint
- Access control (users can only see own reports)
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.database import Base, async_session_factory, engine
from app.main import app
from app.models.transaction import Transaction
from app.models.user import User
from app.utils.crypto import encrypt_value, hash_phone


@pytest_asyncio.fixture
async def client():
    """Create test client."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def user_with_transactions():
    """Create a test user with some transactions."""
    phone = "+254712345678"
    user_id = uuid.uuid4()

    async with async_session_factory() as session:
        user = User(
            id=user_id,
            phone_hash=hash_phone(phone),
            phone_encrypted=encrypt_value(phone),
            business_type="dukawallah",
            language="sw",
            device_id="test-device-001",
            consent_data_sharing=True,
        )
        session.add(user)

        # Add transactions for today and this week
        now = datetime.now(UTC)
        transactions = [
            Transaction(
                user_id=user_id,
                transaction_type="SALE",
                item="sukari",
                item_category="food",
                quantity=5.0,
                unit_price=100.0,
                amount=500.0,
                profit=100.0,
                payment_method="cash",
                timestamp=now - timedelta(hours=i),
            )
            for i in range(5)
        ] + [
            Transaction(
                user_id=user_id,
                transaction_type="PURCHASE",
                item="mafuta",
                amount=300.0,
                timestamp=now - timedelta(hours=3),
            ),
            Transaction(
                user_id=user_id,
                transaction_type="EXPENSE",
                item="transport",
                amount=100.0,
                timestamp=now - timedelta(hours=4),
            ),
        ]

        for txn in transactions:
            session.add(txn)

        await session.commit()

    return user_id, phone


@pytest_asyncio.fixture
def auth_headers(user_with_transactions):
    """Create auth headers."""
    from app.api.auth import create_access_token

    user_id, _ = user_with_transactions
    token = create_access_token({"sub": str(user_id), "phone_hash": "test"})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_daily_report(client, user_with_transactions, auth_headers):
    """Test daily report generation."""
    user_id, _ = user_with_transactions

    response = await client.get(
        f"/api/v1/reports/{user_id}/daily",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_id)
    assert "summary" in data
    assert data["summary"]["total_sales"] > 0
    assert data["summary"]["transaction_count"] > 0
    assert "top_products" in data
    assert "language" in data


@pytest.mark.asyncio
async def test_weekly_report(client, user_with_transactions, auth_headers):
    """Test weekly report generation."""
    user_id, _ = user_with_transactions

    response = await client.get(
        f"/api/v1/reports/{user_id}/weekly",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_id)
    assert "summary" in data
    assert "trends" in data
    assert "week_start" in data
    assert "week_end" in data


@pytest.mark.asyncio
async def test_advice_report(client, user_with_transactions, auth_headers):
    """Test advice report generation."""
    user_id, _ = user_with_transactions

    response = await client.get(
        f"/api/v1/reports/{user_id}/advice",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_id)
    assert "health_score" in data
    assert 0 <= data["health_score"] <= 100
    assert "health_label" in data
    assert "advice" in data
    assert isinstance(data["advice"], list)


@pytest.mark.asyncio
async def test_quick_summary(client, user_with_transactions, auth_headers):
    """Test quick summary endpoint."""
    user_id, _ = user_with_transactions

    response = await client.get(
        f"/api/v1/reports/{user_id}/summary",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "metrics" in data
    assert isinstance(data["summary"], str)


@pytest.mark.asyncio
async def test_report_access_control(client, user_with_transactions, auth_headers):
    """Test that users can only access their own reports."""
    other_user_id = str(uuid.uuid4())

    response = await client.get(
        f"/api/v1/reports/{other_user_id}/daily",
        headers=auth_headers,
    )

    assert response.status_code == 403
