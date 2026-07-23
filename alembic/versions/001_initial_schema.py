"""Initial schema — users, transactions, intelligence, buyer, FL models.

Revision ID: 001
Revises:
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("worker_id_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone_encrypted", sa.Text, nullable=True),
        sa.Column("phone_hash", sa.String(64), nullable=True),
        sa.Column("language", sa.String(10), server_default="sw"),
        sa.Column("business_type", sa.String(50), server_default="unknown"),
        sa.Column("business_description", sa.Text, nullable=True),
        sa.Column("location_geohash", sa.String(10), nullable=True),
        sa.Column("device_id_hash", sa.String(64), nullable=True),
        sa.Column("consent_data_sharing", sa.Boolean, server_default="false"),
        sa.Column("consent_fl_participation", sa.Boolean, server_default="false"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("vector_clock", sa.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_user_geohash_active", "users", ["location_geohash", "is_active"])

    # OTP Codes
    op.create_table(
        "otp_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("phone_hash", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(20), server_default="login"),
        sa.Column("attempts", sa.Integer, server_default="0"),
        sa.Column("max_attempts", sa.Integer, server_default="5"),
        sa.Column("is_used", sa.Boolean, server_default="false"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_otp_phone", "otp_codes", ["phone_hash"])

    # Transactions
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(64), unique=True, nullable=True),
        sa.Column("tx_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="KES"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("product_name", sa.String(200), nullable=True),
        sa.Column("product_category", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Integer, server_default="1"),
        sa.Column("payment_method", sa.String(50), server_default="cash"),
        sa.Column("location_geohash", sa.String(10), nullable=True),
        sa.Column("vector_clock", sa.JSON, server_default="{}"),
        sa.Column("device_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_txn_user_date", "transactions", ["user_id", "created_at"])
    op.create_index("idx_txn_category_region", "transactions", ["product_category", "location_geohash"])

    # Inventory
    op.create_table(
        "inventory",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("product_category", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Integer, server_default="0"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("vector_clock", sa.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_inventory_user_product", "inventory", ["user_id", "product_name"])

    # Intelligence Products
    op.create_table(
        "intelligence_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_type", sa.String(50), nullable=False),
        sa.Column("region", sa.String(10), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), server_default="ready"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("data_points", sa.Integer, server_default="0"),
        sa.Column("confidence", sa.Integer, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_intel_type_region_cat", "intelligence_products", ["product_type", "region", "category"])
    op.create_index("idx_intel_status", "intelligence_products", ["status", "product_type"])

    # Buyer Organizations
    op.create_table(
        "buyer_organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("country", sa.String(2), server_default="KE"),
        sa.Column("contact_email", sa.String(255), unique=True, nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("metadata", sa.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # Buyer API Keys
    op.create_table(
        "buyer_api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("buyer_id", sa.String(36), sa.ForeignKey("buyer_organizations.id"), nullable=False),
        sa.Column("key_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("org_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Buyer Subscriptions
    op.create_table(
        "buyer_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("buyer_id", sa.String(36), sa.ForeignKey("buyer_organizations.id"), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("products", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("monthly_budget_usd", sa.Float, server_default="100.0"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # Buyer Usage Records
    op.create_table(
        "buyer_usage_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("buyer_id", sa.String(36), sa.ForeignKey("buyer_organizations.id"), nullable=False),
        sa.Column("product", sa.String(50), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=True),
        sa.Column("query_params", sa.JSON, nullable=True),
        sa.Column("response_size_bytes", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_usage_buyer_date", "buyer_usage_records", ["buyer_id", "created_at"])

    # FL Updates
    op.create_table(
        "fl_updates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id_hash", sa.String(64), nullable=False),
        sa.Column("dialect", sa.String(20), nullable=False),
        sa.Column("calibration_params", sa.JSON, nullable=True),
        sa.Column("correction_patterns", sa.JSON, nullable=True),
        sa.Column("adapter_deltas", sa.LargeBinary, nullable=True),
        sa.Column("sample_count", sa.Integer, server_default="1"),
        sa.Column("privacy_epsilon", sa.Float, server_default="0.1"),
        sa.Column("metadata", sa.JSON, server_default="{}"),
        sa.Column("processed", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_fl_update_dialect_processed", "fl_updates", ["dialect", "processed"])

    # FL Global Models
    op.create_table(
        "fl_global_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dialect", sa.String(20), nullable=False),
        sa.Column("version", sa.String(50), unique=True, nullable=False),
        sa.Column("calibration_params", sa.JSON, nullable=True),
        sa.Column("vocabulary_updates", sa.JSON, nullable=True),
        sa.Column("adapter_deltas", sa.LargeBinary, nullable=True),
        sa.Column("updates_included", sa.Integer, server_default="0"),
        sa.Column("dp_epsilon", sa.Float, server_default="0.1"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # FL Rounds
    op.create_table(
        "fl_rounds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dialect", sa.String(20), nullable=False),
        sa.Column("round_number", sa.Integer, nullable=False),
        sa.Column("clients_participated", sa.Integer, server_default="0"),
        sa.Column("clients_failed", sa.Integer, server_default="0"),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("fl_rounds")
    op.drop_table("fl_global_models")
    op.drop_table("fl_updates")
    op.drop_table("buyer_usage_records")
    op.drop_table("buyer_subscriptions")
    op.drop_table("buyer_api_keys")
    op.drop_table("buyer_organizations")
    op.drop_table("intelligence_products")
    op.drop_table("inventory")
    op.drop_table("transactions")
    op.drop_table("otp_codes")
    op.drop_table("users")
