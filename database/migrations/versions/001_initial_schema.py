"""Initial schema - all core tables.

Revision ID: 001_initial
Revises: None
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from pgvector.sqlalchemy import Vector

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── Users & Auth ──────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("external_id", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("phone_hash", sa.String(64), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False, default="user"),
        sa.Column("status", sa.String(20), nullable=False, default="active"),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── Transactions (TimescaleDB hypertable) ─────────────────
    op.create_table(
        "transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, default="KES"),
        sa.Column("category", sa.String(50), nullable=False, index=True),
        sa.Column("subcategory", sa.String(50)),
        sa.Column("merchant_category", sa.String(50)),
        sa.Column("region", sa.String(100), index=True),
        sa.Column("lat", sa.Float),
        sa.Column("lon", sa.Float),
        sa.Column("channel", sa.String(20)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Market Data ───────────────────────────────────────────
    op.create_table(
        "market_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("signal_type", sa.String(50), nullable=False, index=True),
        sa.Column("region", sa.String(100), nullable=False, index=True),
        sa.Column("sector", sa.String(50), nullable=False, index=True),
        sa.Column("value", sa.Numeric(15, 4), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Credit Scores ─────────────────────────────────────────
    op.create_table(
        "credit_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("factors", JSONB, nullable=False),
        sa.Column("model_version", sa.String(20), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Intelligence Reports ──────────────────────────────────
    op.create_table(
        "intelligence_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_type", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("region", sa.String(100), index=True),
        sa.Column("sector", sa.String(50), index=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("data_points", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(1536)),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_intelligence_reports_embedding",
        "intelligence_reports",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )

    # ── Audit Log ─────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("action", sa.String(50), nullable=False, index=True),
        sa.Column("actor_id", UUID(as_uuid=True), index=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100)),
        sa.Column("details", JSONB, server_default="{}"),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # ── Data Sync State ───────────────────────────────────────
    op.create_table(
        "sync_state",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("device_id", sa.String(128), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sync_cursor", sa.String(256)),
        sa.Column("schema_version", sa.Integer, nullable=False, default=1),
        sa.Column("metadata", JSONB, server_default="{}"),
    )

    # ── Model Registry ────────────────────────────────────────
    op.create_table(
        "ml_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, index=True),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("model_type", sa.String(50), nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("artifact_path", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="staging"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_ml_model_name_version", "ml_models", ["name", "version"])


def downgrade() -> None:
    for table in [
        "ml_models", "sync_state", "audit_log", "intelligence_reports",
        "credit_scores", "market_signals", "transactions", "users",
    ]:
        op.drop_table(table)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS timescaledb")
    op.execute("DROP EXTENSION IF EXISTS vector")
