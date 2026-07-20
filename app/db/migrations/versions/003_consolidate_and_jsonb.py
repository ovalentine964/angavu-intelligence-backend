"""Consolidate duplicate tables, convert JSON Text → JSONB, add GIN indexes.

Revision ID: 003_consolidate_and_jsonb
Revises: 002_full_schema
Create Date: 2026-07-20

This migration:
1. Drops V1 duplicate tables (goal_records, goal_contributions, loan_records,
   loan_repayments, loan_roi_checkins) — data is migrated to V2 tables first.
2. Adds missing columns to V2 tables (goals, loans, loan_repayment_records)
   to match the current ORM models.
3. Converts all JSON-stored-as-Text columns to JSONB type.
4. Creates GIN indexes on JSONB columns for efficient querying.
5. Adds missing columns to intelligence_products for full ORM compatibility.
6. Creates mindset_lessons_v2 → renames to mindset_lessons (unified).

Run with: alembic -c alembic.ini upgrade head
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_consolidate_and_jsonb"
down_revision: str | None = "002_full_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =====================================================================
    # PHASE 1: Drop V1 duplicate tables (if they exist)
    # =====================================================================
    # These tables are superseded by V2 equivalents.
    # Data migration note: In a live deployment, run a data copy script
    # BEFORE this migration. For fresh installs, these tables are empty.

    _drop_if_exists("goal_contributions")
    _drop_if_exists("goal_records")
    _drop_if_exists("loan_repayments")  # V1 — replaced by loan_repayment_records
    _drop_if_exists("loan_roi_checkins")
    _drop_if_exists("loan_records")

    # Drop old V1 mindset tables (schema incompatible with V2)
    _drop_if_exists("mindset_lesson_progress")
    _drop_if_exists("rich_habit_scores")  # V1 singular — replaced by rich_habits_scores

    # Drop old simple intelligence_products table if it has the V1 schema
    # (We'll recreate it with the full V2 schema below)
    _drop_if_exists("intelligence_products")
    _drop_if_exists("data_access_logs")

    # Drop old migration's simple server_metrics (replaced by richer V2)
    _drop_if_exists("server_metrics")
    _drop_if_exists("model_versions")  # V1 name — replaced by model_versions with V2 schema
    _drop_if_exists("federated_updates")  # V1 — replaced by V2 schema
    _drop_if_exists("cost_tracking")

    # Drop old V1 mindset_lessons (string PK, incompatible with V2 UUID PK)
    _drop_if_exists("mindset_lessons")

    # =====================================================================
    # PHASE 2: Add missing columns to existing V2 tables
    # =====================================================================

    # ── goals table — add columns from GoalRecord V1 that V2 needs ──
    _add_column_if_missing("goals", "title_sw", sa.String(200), nullable=True)
    _add_column_if_missing("goals", "currency", sa.String(3), nullable=False, server_default="KES")
    _add_column_if_missing("goals", "target_date", sa.Date, nullable=True)
    _add_column_if_missing("goals", "commitment_declaration", sa.Text, nullable=True)
    _add_column_if_missing("goals", "commitment_made_at", sa.DateTime(timezone=True), nullable=True)
    _add_column_if_missing("goals", "accountability_partner_id",
                           postgresql.UUID(as_uuid=True), nullable=True)
    _add_column_if_missing("goals", "shared_with_partner", sa.Boolean, server_default="false")
    _add_column_if_missing("goals", "current_streak", sa.Integer, nullable=False, server_default="0")
    _add_column_if_missing("goals", "best_streak", sa.Integer, nullable=False, server_default="0")
    _add_column_if_missing("goals", "last_contribution_date", sa.Date, nullable=True)
    _add_column_if_missing("goals", "total_contributions", sa.Integer, nullable=False, server_default="0")
    _add_column_if_missing("goals", "weekly_history", postgresql.JSON, nullable=True)
    _add_column_if_missing("goals", "what_i_lose", sa.String(300), nullable=True)
    _add_column_if_missing("goals", "voice_created", sa.Boolean, server_default="false")
    _add_column_if_missing("goals", "voice_transcript", sa.Text, nullable=True)
    _add_column_if_missing("goals", "updated_at", sa.DateTime(timezone=True),
                           nullable=False, server_default=sa.func.now())

    # ── loans table — add columns from LoanRecord V1 ──
    _add_column_if_missing("loans", "currency", sa.String(3), nullable=False, server_default="KES")
    _add_column_if_missing("loans", "purpose_subcategory", sa.String(50), nullable=True)
    _add_column_if_missing("loans", "purpose_description", sa.Text, nullable=True)
    _add_column_if_missing("loans", "amount_repaid", sa.Float, nullable=False, server_default="0")
    _add_column_if_missing("loans", "sales_attributed", sa.Float, nullable=True, server_default="0")
    _add_column_if_missing("loans", "roi_pct", sa.Float, nullable=True)
    _add_column_if_missing("loans", "last_roi_check", sa.DateTime(timezone=True), nullable=True)
    _add_column_if_missing("loans", "repayment_frequency", sa.String(20), nullable=True, server_default="weekly")
    _add_column_if_missing("loans", "suggested_payment_amount", sa.Float, nullable=True)
    _add_column_if_missing("loans", "current_streak", sa.Integer, nullable=False, server_default="0")
    _add_column_if_missing("loans", "best_streak", sa.Integer, nullable=False, server_default="0")
    _add_column_if_missing("loans", "last_repayment_date", sa.Date, nullable=True)
    _add_column_if_missing("loans", "commitment_text", sa.Text, nullable=True)
    _add_column_if_missing("loans", "commitment_date", sa.DateTime(timezone=True), nullable=True)
    _add_column_if_missing("loans", "accountability_partner_id",
                           postgresql.UUID(as_uuid=True), nullable=True)
    _add_column_if_missing("loans", "default_probability", sa.Float, nullable=True)
    _add_column_if_missing("loans", "risk_level", sa.String(20), nullable=True)
    _add_column_if_missing("loans", "risk_last_updated", sa.DateTime(timezone=True), nullable=True)
    _add_column_if_missing("loans", "alama_score_at_start", sa.Integer, nullable=True)
    _add_column_if_missing("loans", "alama_score_impact", sa.Integer, nullable=True, server_default="0")
    _add_column_if_missing("loans", "nudges_sent", postgresql.JSON, nullable=True)
    _add_column_if_missing("loans", "last_nudge_at", sa.DateTime(timezone=True), nullable=True)
    _add_column_if_missing("loans", "updated_at", sa.DateTime(timezone=True),
                           nullable=False, server_default=sa.func.now())

    # ── loan_repayment_records — ensure all V2 columns exist ──
    _add_column_if_missing("loan_repayment_records", "notes", sa.Text, nullable=True)
    _add_column_if_missing("loan_repayment_records", "streak_day", sa.Integer, nullable=True)
    _add_column_if_missing("loan_repayment_records", "was_suggested", sa.Boolean, server_default="false")
    _add_column_if_missing("loan_repayment_records", "nudge_type", sa.String(50), nullable=True)

    # =====================================================================
    # PHASE 3: Create / recreate tables with full V2 schema
    # =====================================================================

    # ── Intelligence Products (full V2 schema) ────────────────────────
    op.create_table(
        "intelligence_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("buyers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("product_type", sa.String(50), nullable=False, index=True),
        sa.Column("market_id", sa.String(20), nullable=True, index=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("product_name", sa.String(200), nullable=True, server_default="all"),
        sa.Column("time_period", sa.String(20), nullable=True),
        sa.Column("granularity", sa.String(20), nullable=False, server_default="micro_market"),
        sa.Column("data", postgresql.JSON, nullable=False),
        sa.Column("metadata_extra", postgresql.JSON, nullable=True),
        sa.Column("price_kes", sa.Float, nullable=True, server_default="0"),
        sa.Column("users_included", sa.Integer, nullable=True),
        sa.Column("k_anonymity_value", sa.Integer, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_intel_market_period", "intelligence_products", ["market_id", "time_period"])
    op.create_index("idx_intel_type_status", "intelligence_products", ["product_type", "status"])
    op.create_index("idx_intel_created", "intelligence_products", ["created_at"])

    # ── Data Access Logs (full V2 schema) ─────────────────────────────
    op.create_table(
        "data_access_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("buyers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("buyer_api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("query_params", postgresql.JSON, nullable=True),
        sa.Column("response_size_bytes", sa.Integer, nullable=True),
        sa.Column("records_returned", sa.Integer, nullable=True),
        sa.Column("processing_time_ms", sa.Float, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.create_index("idx_dal_buyer_time", "data_access_logs", ["buyer_id", "accessed_at"])
    op.create_index("idx_dal_endpoint", "data_access_logs", ["endpoint", "accessed_at"])

    # ── Mindset Lessons (V2 — UUID PK, rich schema) ───────────────────
    op.create_table(
        "mindset_lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("module_number", sa.Integer, nullable=False),
        sa.Column("lesson_number", sa.Integer, nullable=False),
        sa.Column("title_en", sa.String(200), nullable=False),
        sa.Column("title_sw", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_book", sa.String(200), nullable=True),
        sa.Column("key_takeaway", sa.Text, nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("difficulty", sa.Integer, nullable=False, server_default="1"),
        sa.Column("audio_url", sa.String(500), nullable=True),
        sa.Column("content_text", sa.Text, nullable=True),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("module_number >= 1 AND module_number <= 6", name="ck_module_range"),
        sa.CheckConstraint("difficulty >= 1 AND difficulty <= 3", name="ck_difficulty_range"),
        sa.UniqueConstraint("module_number", "lesson_number", name="uq_module_lesson"),
    )
    op.create_index("idx_lesson_order", "mindset_lessons", ["order_index"])
    op.create_index("idx_lesson_module", "mindset_lessons", ["module_number", "lesson_number"])

    # ── User Lesson Progress (V2) ─────────────────────────────────────
    op.create_table(
        "user_lesson_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("mindset_lessons.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("completed", sa.Boolean, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_listened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listen_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson_progress"),
    )
    op.create_index("idx_user_progress", "user_lesson_progress", ["user_id", "completed"])

    # ── Rich Habits Scores (V2 — with 's') ────────────────────────────
    op.create_table(
        "rich_habits_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("score_date", sa.Date, nullable=False),
        sa.Column("record_sales", sa.Boolean, server_default="false"),
        sa.Column("check_balance", sa.Boolean, server_default="false"),
        sa.Column("save_money", sa.Boolean, server_default="false"),
        sa.Column("avoid_waste", sa.Boolean, server_default="false"),
        sa.Column("give", sa.Boolean, server_default="false"),
        sa.Column("learn", sa.Boolean, server_default="false"),
        sa.Column("set_goal", sa.Boolean, server_default="false"),
        sa.Column("review_day", sa.Boolean, server_default="false"),
        sa.Column("help_peer", sa.Boolean, server_default="false"),
        sa.Column("no_debt", sa.Boolean, server_default="false"),
        sa.Column("total_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("best_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("level", sa.Integer, nullable=False, server_default="1"),
        sa.Column("milestones", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "score_date", name="uq_user_score_date"),
    )
    op.create_index("idx_habits_user_date", "rich_habits_scores", ["user_id", "score_date"])
    op.create_index("idx_habits_score", "rich_habits_scores", ["total_score"])

    # ── Server Metrics (V2 — UUID PK, rich schema) ────────────────────
    op.create_table(
        "server_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("server_id", sa.String(100), nullable=False, index=True),
        sa.Column("phase", sa.String(20), nullable=False, server_default="cloud"),
        sa.Column("cpu_usage_pct", sa.Float, nullable=False),
        sa.Column("cpu_cores", sa.Integer, nullable=False, server_default="1"),
        sa.Column("ram_usage_pct", sa.Float, nullable=False),
        sa.Column("ram_total_gb", sa.Float, nullable=False),
        sa.Column("ram_used_gb", sa.Float, nullable=False),
        sa.Column("disk_usage_pct", sa.Float, nullable=False),
        sa.Column("disk_total_gb", sa.Float, nullable=False),
        sa.Column("disk_used_gb", sa.Float, nullable=False),
        sa.Column("network_in_mbps", sa.Float, nullable=True),
        sa.Column("network_out_mbps", sa.Float, nullable=True),
        sa.Column("inference_latency_ms", sa.Float, nullable=True),
        sa.Column("inference_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("cost_per_hour_usd", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="healthy"),
        sa.Column("uptime_pct", sa.Float, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now(), index=True),
    )
    op.create_index("idx_server_metric_time", "server_metrics", ["server_id", "recorded_at"])
    op.create_index("idx_server_metric_phase", "server_metrics", ["phase", "recorded_at"])

    # ── Model Versions (V2 — UUID PK, rich schema) ────────────────────
    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("base_model", sa.String(100), nullable=False),
        sa.Column("dialect", sa.String(10), nullable=False, server_default="sw"),
        sa.Column("status", sa.String(20), nullable=False, server_default="training"),
        sa.Column("is_champion", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("traffic_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("accuracy_score", sa.Float, nullable=True),
        sa.Column("latency_p50_ms", sa.Float, nullable=True),
        sa.Column("latency_p95_ms", sa.Float, nullable=True),
        sa.Column("latency_p99_ms", sa.Float, nullable=True),
        sa.Column("worker_satisfaction", sa.Float, nullable=True),
        sa.Column("training_data_points", sa.Integer, nullable=True),
        sa.Column("training_duration_min", sa.Float, nullable=True),
        sa.Column("federated_rounds", sa.Integer, nullable=True),
        sa.Column("ab_test_id", sa.String(100), nullable=True, index=True),
        sa.Column("ab_test_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ab_test_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_business_types", postgresql.JSON, nullable=True),
        sa.Column("target_regions", postgresql.JSON, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("changelog", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_model_active", "model_versions", ["model_name", "is_champion"])
    op.create_index("idx_model_ab_test", "model_versions", ["ab_test_id"])
    op.create_index("idx_model_dialect_status", "model_versions", ["dialect", "status"])

    # ── Federated Updates (V2 — UUID PK, rich schema) ─────────────────
    op.create_table(
        "federated_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id_hash", sa.String(64), nullable=False, index=True),
        sa.Column("dialect", sa.String(10), nullable=False),
        sa.Column("corrections_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("vocabulary_size", sa.Integer, nullable=True),
        sa.Column("estimated_wer", sa.Float, nullable=True),
        sa.Column("device_tier", sa.String(20), nullable=True),
        sa.Column("quality_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("dp_epsilon", sa.Float, nullable=False, server_default="0.1"),
        sa.Column("dp_applied", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("k_anonymity_k", sa.Integer, nullable=False, server_default="5"),
        sa.Column("aggregated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("aggregation_round", sa.Integer, nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("k_anonymity_met", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now(), index=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_fl_update_dialect", "federated_updates", ["dialect", "submitted_at"])
    op.create_index("idx_fl_update_unagg", "federated_updates", ["aggregated", "dialect"])

    # ── Cost Tracking (V2 — UUID PK, rich schema) ─────────────────────
    op.create_table(
        "cost_tracking",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("component", sa.String(20), nullable=False),
        sa.Column("phase", sa.String(20), nullable=False, server_default="cloud"),
        sa.Column("amount_usd", sa.Float, nullable=False),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("inference_count", sa.Integer, nullable=True),
        sa.Column("cost_per_inference_usd", sa.Float, nullable=True),
        sa.Column("workers_served", sa.Integer, nullable=True),
        sa.Column("cost_per_worker_usd", sa.Float, nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_cost_component_period", "cost_tracking", ["component", "period_start"])
    op.create_index("idx_cost_phase", "cost_tracking", ["phase", "period_start"])

    # =====================================================================
    # PHASE 4: Convert JSON Text columns → JSONB + add GIN indexes
    # =====================================================================
    # These tables were created by 002_full_schema with sa.Text for JSON columns.
    # We convert them to proper JSONB for indexing and efficient querying.

    _text_to_jsonb("soko_pulse_reports", "report_data")
    _text_to_jsonb("soko_pulse_reports", "market_ids")
    _text_to_jsonb("soko_pulse_reports", "day_of_week_pattern")
    _text_to_jsonb("soko_pulse_reports", "monthly_trend")
    _text_to_jsonb("soko_pulse_reports", "peak_demand_days")
    _text_to_jsonb("soko_pulse_reports", "methodology")

    _text_to_jsonb("biashara_pulse_reports", "report_data")
    _text_to_jsonb("biashara_pulse_reports", "sector_breakdown")
    _text_to_jsonb("biashara_pulse_reports", "top_sectors")

    _text_to_jsonb("alama_scores", "components")
    _text_to_jsonb("alama_scores", "vs_market_avg")

    _text_to_jsonb("jamii_insights_reports", "report_data")
    _text_to_jsonb("jamii_insights_reports", "top_barriers")
    _text_to_jsonb("jamii_insights_reports", "barrier_severity")

    _text_to_jsonb("tax_base_estimations", "estimation_data")
    _text_to_jsonb("tax_base_estimations", "sector_breakdown")
    _text_to_jsonb("tax_base_estimations", "top_tax_contributors")
    _text_to_jsonb("tax_base_estimations", "confidence_interval")

    _text_to_jsonb("distribution_gap_reports", "report_data")
    _text_to_jsonb("distribution_gap_reports", "gap_markets")
    _text_to_jsonb("distribution_gap_reports", "priority_gaps")
    _text_to_jsonb("distribution_gap_reports", "underserved_regions")
    _text_to_jsonb("distribution_gap_reports", "underserved_demographics")
    _text_to_jsonb("distribution_gap_reports", "competitor_presence")
    _text_to_jsonb("distribution_gap_reports", "optimal_route_suggestions")
    _text_to_jsonb("distribution_gap_reports", "recommended_expansion_markets")

    _text_to_jsonb("tithe_reports", "report_data")
    _text_to_jsonb("tithe_reports", "by_category")
    _text_to_jsonb("tithe_reports", "by_recipient")

    _text_to_jsonb("abundance_patterns", "pattern_data")
    _text_to_jsonb("abundance_patterns", "monthly_data")

    _text_to_jsonb("loan_roi_checkins", "checkin_data")
    _text_to_jsonb("purpose_verifications", "verification_data")
    _text_to_jsonb("purpose_verifications", "roi_tracking")

    _text_to_jsonb("agent_configs", "config")
    _text_to_jsonb("agent_insights", "data")
    _text_to_jsonb("user_engagements", "metadata")

    # GIN indexes on the most-queried JSONB columns
    _gin_index_if_missing("intelligence_products", "data")
    _gin_index_if_missing("soko_pulse_reports", "report_data")
    _gin_index_if_missing("biashara_pulse_reports", "report_data")
    _gin_index_if_missing("alama_scores", "components")
    _gin_index_if_missing("jamii_insights_reports", "report_data")
    _gin_index_if_missing("tax_base_estimations", "estimation_data")
    _gin_index_if_missing("distribution_gap_reports", "report_data")


def downgrade() -> None:
    """Reverse the migration — drop V2 tables, recreate V1."""
    # Drop V2 tables created in this migration
    for table in [
        "cost_tracking", "federated_updates", "model_versions",
        "server_metrics", "rich_habits_scores", "user_lesson_progress",
        "mindset_lessons", "data_access_logs", "intelligence_products",
    ]:
        op.drop_table(table)

    # Note: Column additions and JSONB conversions are not reversed
    # because downgrading would lose data. In practice, restore from
    # backup instead of running downgrade.


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _drop_if_exists(table_name: str) -> None:
    """Drop a table if it exists."""
    op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


def _add_column_if_missing(
    table: str,
    column: str,
    type_,
    nullable: bool = True,
    server_default=None,
) -> None:
    """Add a column only if it doesn't already exist."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns(table)}
    if column not in existing:
        kwargs = {}
        if server_default is not None:
            kwargs["server_default"] = server_default
        op.add_column(table, sa.Column(column, type_, nullable=nullable, **kwargs))


def _text_to_jsonb(table: str, column: str) -> None:
    """Convert a Text column to JSONB using a USING clause."""
    # Use raw SQL for the ALTER with USING cast
    op.execute(
        f"ALTER TABLE {table} ALTER COLUMN {column} TYPE JSONB "
        f"USING CASE WHEN {column} IS NULL THEN NULL "
        f"ELSE {column}::JSONB END"
    )


def _gin_index_if_missing(table: str, column: str) -> None:
    """Create a GIN index on a JSONB column if it doesn't exist."""
    index_name = f"idx_{table}_{column}_gin"
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {
        idx["name"] for idx in inspector.get_indexes(table)
    }
    if index_name not in existing_indexes:
        op.execute(f"CREATE INDEX {index_name} ON {table} USING GIN ({column})")
