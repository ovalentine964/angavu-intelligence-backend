"""Full schema migration — all tables for Angavu Intelligence.

Revision ID: 002_full_schema
Revises: 001_initial
Create Date: 2026-07-07

This migration creates the complete schema from all ORM models.
Run with: alembic -c alembic.ini upgrade head

Tables created:
  - users — Worker accounts (phone encrypted, location geohash only)
  - transactions — Business transactions (sale, purchase, expense)
  - inventory — Stock levels per worker
  - buyers — Intelligence product buyers
  - buyer_api_keys — API keys for buyer access
  - intelligence_products — Generated intelligence products
  - data_access_logs — Audit trail for data access
  - soko_pulse_reports — Market price intelligence
  - biashara_pulse_reports — Business health reports
  - alama_scores — Credit scoring
  - jamii_insights_reports — Community intelligence
  - tax_base_estimations — Government intelligence
  - distribution_gap_reports — FMCG distribution analysis
  - tithe_records — Giving/tithe tracking
  - tithe_reports — Tithe analysis reports
  - abundance_patterns — Giving pattern analysis
  - goal_records — Worker savings goals
  - goal_contributions — Goal progress entries
  - loan_records — Worker loans
  - loan_repayments — Loan repayment schedule
  - loan_roi_checkins — Loan ROI verification
  - mindset_lessons — Financial literacy content
  - mindset_lesson_progress — Lesson completion tracking
  - rich_habit_scores — Habit tracking
  - loans_v2 — Enhanced loan model
  - purpose_verifications — Loan purpose verification
  - goals_v2 — Enhanced goal model
  - goal_milestones — Goal milestone tracking
  - goal_progress_entries — Goal progress entries
  - server_metrics — Infrastructure monitoring
  - model_versions — ML model registry
  - federated_updates — Federated learning updates
  - cost_tracking — Infrastructure cost tracking
  - worker_types — Worker classification
  - agent_configs — Agent configuration
  - agent_insights — Generated insights
  - agent_recommendations — Agent recommendations
  - user_engagements — Gamification engagement
  - badges — Achievement badges
  - user_badges — Earned badges
  - user_levels — Level progression
  - streaks — Activity streaks
  - mindset_lessons_v2 — Enhanced lessons
  - user_lesson_progress — Lesson progress
  - affirmations — Daily affirmations
  - refresh_tokens — JWT refresh token rotation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_full_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables from ORM models."""

    # ─── Users ───────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_hash", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("phone_encrypted", sa.Text, nullable=False),
        sa.Column("name_encrypted", sa.Text, nullable=True),
        sa.Column("business_type", sa.String(20), nullable=False, server_default="dukawallah"),
        sa.Column("location_geohash", sa.String(12), nullable=True, index=True),
        sa.Column("location_name", sa.String(200), nullable=True),
        sa.Column("language", sa.String(5), nullable=False, server_default="sw"),
        sa.Column("channel", sa.String(20), nullable=False, server_default="whatsapp"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_id", sa.String(100), unique=True, nullable=True),
        sa.Column("app_version", sa.String(20), nullable=True),
        sa.Column("consent_data_sharing", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_user_location_active", "users", ["location_geohash", "is_active"])
    op.create_index("idx_user_business_type", "users", ["business_type", "is_active"])
    op.create_index("idx_user_channel", "users", ["channel", "is_active"])
    op.create_index("idx_user_sync", "users", ["last_sync_at"])

    # ─── Transactions ────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("transaction_type", sa.String(10), nullable=False, index=True),
        sa.Column("item", sa.String(200), nullable=True),
        sa.Column("item_category", sa.String(20), nullable=True, index=True),
        sa.Column("quantity", sa.Float, nullable=True, server_default="0"),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("unit_price", sa.Float, nullable=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("profit", sa.Float, nullable=True),
        sa.Column("payment_method", sa.String(10), nullable=True, server_default="cash"),
        sa.Column("customer_phone_hash", sa.String(64), nullable=True),
        sa.Column("mpesa_receipt", sa.String(50), nullable=True),
        sa.Column("recorded_via", sa.String(15), nullable=True, server_default="manual"),
        sa.Column("confidence_score", sa.Float, nullable=True, server_default="1.0"),
        sa.Column("source_text", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_id", sa.String(100), nullable=True),
        sa.Column("location_geohash", sa.String(12), nullable=True),
    )
    op.create_index("idx_txn_user_time", "transactions", ["user_id", "timestamp"])
    op.create_index("idx_txn_type_time", "transactions", ["transaction_type", "timestamp"])
    op.create_index("idx_txn_category_time", "transactions", ["item_category", "timestamp"])
    op.create_index("idx_txn_item", "transactions", ["item", "timestamp"])
    op.create_index("idx_txn_location", "transactions", ["location_geohash", "timestamp"])
    op.create_index("idx_txn_synced", "transactions", ["synced_at"])
    op.create_index("idx_txn_mpesa", "transactions", ["mpesa_receipt"])

    # ─── Inventory ───────────────────────────────────────────
    op.create_table(
        "inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("current_stock", sa.Float, nullable=False, server_default="0"),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("avg_cost", sa.Float, nullable=True),
        sa.Column("sell_price", sa.Float, nullable=True),
        sa.Column("restock_threshold", sa.Float, nullable=True, server_default="0"),
        sa.Column("last_restocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_inv_user_item", "inventory", ["user_id", "item"], unique=True)
    op.create_index("idx_inv_restock", "inventory", ["user_id", "current_stock"])

    # ─── Refresh Tokens ──────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("family_id", sa.String(64), nullable=False, index=True),
        sa.Column("jti", sa.String(64), nullable=False, unique=True),
        sa.Column("used", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_rt_family", "refresh_tokens", ["family_id", "revoked"])
    op.create_index("idx_rt_user", "refresh_tokens", ["user_id"])

    # ─── Buyers ──────────────────────────────────────────────
    op.create_table(
        "buyers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("organization", sa.String(200), nullable=True),
        sa.Column("buyer_type", sa.String(50), nullable=False, server_default="enterprise"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("contract_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contract_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "buyer_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buyers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ─── Intelligence Products ───────────────────────────────
    op.create_table(
        "intelligence_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_type", sa.String(50), nullable=False, index=True),
        sa.Column("market_id", sa.String(100), nullable=True, index=True),
        sa.Column("data", sa.Text, nullable=True),  # JSON
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "data_access_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("product_type", sa.String(50), nullable=False),
        sa.Column("market_id", sa.String(100), nullable=True),
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ip_address", sa.String(45), nullable=True),
    )

    # ─── FMCG Intelligence Reports ───────────────────────────
    op.create_table(
        "soko_pulse_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("market_id", sa.String(100), nullable=False, index=True),
        sa.Column("report_data", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "biashara_pulse_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("worker_type", sa.String(50), nullable=False, index=True),
        sa.Column("location_geohash", sa.String(12), nullable=True),
        sa.Column("report_data", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "alama_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("worker_id_hash", sa.String(64), nullable=False, index=True),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("components", sa.Text, nullable=True),  # JSON
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "jamii_insights_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("area_geohash", sa.String(12), nullable=False, index=True),
        sa.Column("report_data", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "tax_base_estimations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("area_geohash", sa.String(12), nullable=False, index=True),
        sa.Column("estimation_data", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "distribution_gap_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand", sa.String(100), nullable=False, index=True),
        sa.Column("report_data", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─── Worker Features (Tithe, Goals, Loans, Mindset) ──────
    op.create_table(
        "tithe_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("recipient", sa.String(200), nullable=True, server_default=""),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=True, server_default=""),
        sa.Column("notes", sa.Text, nullable=True, server_default=""),
        sa.Column("income_at_time", sa.Float, nullable=True, server_default="0"),
        sa.Column("input_method", sa.String(10), nullable=True, server_default="VOICE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "tithe_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("report_data", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "abundance_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("pattern_data", sa.Text, nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "goal_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("target_amount", sa.Float, nullable=False),
        sa.Column("current_amount", sa.Float, nullable=False, server_default="0"),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("weekly_target", sa.Float, nullable=True, server_default="0"),
        sa.Column("daily_target", sa.Float, nullable=True, server_default="0"),
        sa.Column("streak", sa.Integer, nullable=True, server_default="0"),
        sa.Column("best_streak", sa.Integer, nullable=True, server_default="0"),
        sa.Column("deeper_purpose", sa.Text, nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "goal_contributions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("goal_id", sa.Integer, sa.ForeignKey("goal_records.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("note", sa.Text, nullable=True, server_default=""),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "loan_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column("lender", sa.String(200), nullable=True, server_default=""),
        sa.Column("interest_rate", sa.Float, nullable=True, server_default="0"),
        sa.Column("total_due", sa.Float, nullable=True, server_default="0"),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repayment_frequency", sa.String(20), nullable=True, server_default="MONTHLY"),
        sa.Column("total_repaid", sa.Float, nullable=True, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "loan_repayments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("loan_id", sa.Integer, sa.ForeignKey("loan_records.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("penalty", sa.Float, nullable=True, server_default="0"),
    )

    op.create_table(
        "loan_roi_checkins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("loan_id", sa.Integer, nullable=False, index=True),
        sa.Column("checkin_data", sa.Text, nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "mindset_lessons",
        sa.Column("lesson_id", sa.String(50), primary_key=True),
        sa.Column("category", sa.String(50), nullable=False, index=True),
        sa.Column("title_sw", sa.String(200), nullable=False),
        sa.Column("title_en", sa.String(200), nullable=False),
        sa.Column("content_sw", sa.Text, nullable=False),
        sa.Column("content_en", sa.Text, nullable=False),
        sa.Column("source_book", sa.String(200), nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=True, server_default="150"),
        sa.Column("sort_order", sa.Integer, nullable=True, server_default="0"),
    )

    op.create_table(
        "mindset_lesson_progress",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("lesson_id", sa.String(50), nullable=False, index=True),
        sa.Column("delivered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "rich_habit_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("habit_id", sa.String(50), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ─── Enhanced Loans (V2) ─────────────────────────────────
    op.create_table(
        "loans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column("lender", sa.String(200), nullable=True),
        sa.Column("interest_rate", sa.Float, nullable=True, server_default="0"),
        sa.Column("total_due", sa.Float, nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "loan_repayments_v2",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("loan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
    )

    op.create_table(
        "purpose_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("loan_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("verification_data", sa.Text, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─── Enhanced Goals (V2) ─────────────────────────────────
    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("target_amount", sa.Float, nullable=False),
        sa.Column("current_amount", sa.Float, nullable=False, server_default="0"),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("deeper_purpose", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "goal_milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("percentage", sa.Float, nullable=False),
        sa.Column("reached_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "goal_progress_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─── Infrastructure / Monitoring ─────────────────────────
    op.create_table(
        "server_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("metric_name", sa.String(100), nullable=False, index=True),
        sa.Column("metric_value", sa.Float, nullable=False),
        sa.Column("labels", sa.Text, nullable=True),  # JSON
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_name", sa.String(100), nullable=False, index=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("dialect", sa.String(20), nullable=True),
        sa.Column("metrics", sa.Text, nullable=True),  # JSON
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "federated_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dialect", sa.String(20), nullable=False, index=True),
        sa.Column("update_data", sa.Text, nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "cost_tracking",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(50), nullable=False, index=True),
        sa.Column("amount_usd", sa.Float, nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─── Agent Models ────────────────────────────────────────
    op.create_table(
        "worker_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("worker_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.5"),
        sa.Column("classified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "agent_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_name", sa.String(100), nullable=False, unique=True),
        sa.Column("config", sa.Text, nullable=True),  # JSON
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "agent_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_name", sa.String(100), nullable=False, index=True),
        sa.Column("insight_type", sa.String(50), nullable=False),
        sa.Column("data", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "agent_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_name", sa.String(100), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("recommendation", sa.Text, nullable=False),
        sa.Column("priority", sa.Integer, nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─── Gamification / Stickiness ───────────────────────────
    op.create_table(
        "user_engagements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("points", sa.Integer, nullable=True, server_default="0"),
        sa.Column("metadata", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "badges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("points_required", sa.Integer, nullable=True, server_default="0"),
    )

    op.create_table(
        "user_badges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("badge_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("earned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "user_levels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "streaks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("streak_type", sa.String(50), nullable=False),
        sa.Column("current_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("best_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_active_date", sa.String(10), nullable=True),
    )

    # ─── Mindset V2 ──────────────────────────────────────────
    op.create_table(
        "mindset_lessons_v2",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lesson_id", sa.String(50), nullable=False, unique=True),
        sa.Column("category", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_book", sa.String(200), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True, server_default="150"),
        sa.Column("sort_order", sa.Integer, nullable=True, server_default="0"),
    )

    op.create_table(
        "user_lesson_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("lesson_id", sa.String(50), nullable=False, index=True),
        sa.Column("delivered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "rich_habits_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("habit_id", sa.String(50), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "affirmations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("text_sw", sa.Text, nullable=False),
        sa.Column("text_en", sa.Text, nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    """Drop all tables in reverse order."""
    tables = [
        "affirmations", "rich_habits_scores", "user_lesson_progress",
        "mindset_lessons_v2", "streaks", "user_levels", "user_badges",
        "badges", "user_engagements", "agent_recommendations",
        "agent_insights", "agent_configs", "worker_types",
        "cost_tracking", "federated_updates", "model_versions",
        "server_metrics", "goal_progress_entries", "goal_milestones",
        "goals", "purpose_verifications", "loan_repayments_v2",
        "loans", "rich_habit_scores", "mindset_lesson_progress",
        "mindset_lessons", "loan_roi_checkins", "loan_repayments",
        "loan_records", "goal_contributions", "goal_records",
        "abundance_patterns", "tithe_reports", "tithe_records",
        "distribution_gap_reports", "tax_base_estimations",
        "jamii_insights_reports", "alama_scores",
        "biashara_pulse_reports", "soko_pulse_reports",
        "data_access_logs", "intelligence_products",
        "buyer_api_keys", "buyers", "refresh_tokens",
        "inventory", "transactions", "users",
    ]
    for table in tables:
        op.drop_table(table)
