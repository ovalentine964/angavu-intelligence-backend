"""
Database Models for Infrastructure Monitoring.

Tracks server health, model versions, federated learning updates,
and cost data across Biashara Intelligence's infrastructure.

Tables:
    - ServerMetric: CPU, RAM, disk, network metrics per server
    - ModelVersion: Registry of model versions and their status
    - FederatedUpdate: Individual federated learning submissions
    - CostTracking: Infrastructure cost tracking per component
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.database import Base


class ServerMetric(Base):
    """
    Server health metrics collected periodically.

    Each row is a single metric snapshot for one server at one point in time.
    Used for monitoring dashboards, alerting, and capacity planning.
    """

    __tablename__ = "server_metrics"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    server_id = Column(
        String(100),
        nullable=False,
        index=True,
        doc="Unique server identifier (e.g. 'oracle-cloud-1', 'home-server-arm')",
    )
    phase = Column(
        Enum("cloud", "home_server", "mini_dc", "data_center", "pan_african",
             name="infra_phase_enum"),
        nullable=False,
        default="cloud",
        doc="Infrastructure phase this server belongs to",
    )
    # CPU
    cpu_usage_pct = Column(Float, nullable=False, doc="CPU usage percentage (0-100)")
    cpu_cores = Column(Integer, nullable=False, default=1, doc="Number of CPU cores")
    # Memory
    ram_usage_pct = Column(Float, nullable=False, doc="RAM usage percentage (0-100)")
    ram_total_gb = Column(Float, nullable=False, doc="Total RAM in GB")
    ram_used_gb = Column(Float, nullable=False, doc="Used RAM in GB")
    # Disk
    disk_usage_pct = Column(Float, nullable=False, doc="Disk usage percentage (0-100)")
    disk_total_gb = Column(Float, nullable=False, doc="Total disk in GB")
    disk_used_gb = Column(Float, nullable=False, doc="Used disk in GB")
    # Network
    network_in_mbps = Column(Float, nullable=True, doc="Network inbound throughput in Mbps")
    network_out_mbps = Column(Float, nullable=True, doc="Network outbound throughput in Mbps")
    # Inference
    inference_latency_ms = Column(Float, nullable=True, doc="Average inference latency in ms")
    inference_count = Column(Integer, nullable=True, default=0, doc="Inferences served in this window")
    # Cost
    cost_per_hour_usd = Column(Float, nullable=True, doc="Running cost per hour in USD")
    # Status
    status = Column(
        Enum("healthy", "degraded", "down", name="server_status_enum"),
        nullable=False,
        default="healthy",
    )
    uptime_pct = Column(Float, nullable=True, doc="Uptime percentage over last 24h")

    recorded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("idx_server_metric_time", "server_id", "recorded_at"),
        Index("idx_server_metric_phase", "phase", "recorded_at"),
    )


class ModelVersion(Base):
    """
    Registry of AI model versions.

    Tracks which model version each worker segment is using,
    performance metrics, and enables A/B testing and rollback.
    """

    __tablename__ = "model_versions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    model_name = Column(
        String(200),
        nullable=False,
        doc="Model name (e.g. 'qwen-0.5b-fl-sw-v3')",
    )
    version = Column(
        String(50),
        nullable=False,
        doc="Semantic version string (e.g. 'v3.2.1')",
    )
    base_model = Column(
        String(100),
        nullable=False,
        doc="Base model (e.g. 'qwen-0.5b', 'llama-3.2-1b')",
    )
    dialect = Column(
        String(10),
        nullable=False,
        default="sw",
        doc="Target dialect/language code",
    )
    # Status
    status = Column(
        Enum("training", "staging", "active", "deprecated", "rolled_back",
             name="model_status_enum"),
        nullable=False,
        default="training",
    )
    # Deployment
    is_champion = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="True if this is the current production (champion) model",
    )
    traffic_pct = Column(
        Float,
        default=0.0,
        nullable=False,
        doc="Percentage of traffic routed to this model (for A/B testing)",
    )
    # Performance metrics
    accuracy_score = Column(Float, nullable=True, doc="Model accuracy on benchmark tasks")
    latency_p50_ms = Column(Float, nullable=True, doc="P50 inference latency in ms")
    latency_p95_ms = Column(Float, nullable=True, doc="P95 inference latency in ms")
    latency_p99_ms = Column(Float, nullable=True, doc="P99 inference latency in ms")
    worker_satisfaction = Column(Float, nullable=True, doc="Worker satisfaction score (0-5)")
    # Training metadata
    training_data_points = Column(Integer, nullable=True, doc="Number of data points used for training")
    training_duration_min = Column(Float, nullable=True, doc="Training duration in minutes")
    federated_rounds = Column(Integer, nullable=True, doc="Number of federated learning rounds")
    # A/B test
    ab_test_id = Column(
        String(100),
        nullable=True,
        index=True,
        doc="A/B test group this model belongs to",
    )
    ab_test_start = Column(DateTime(timezone=True), nullable=True)
    ab_test_end = Column(DateTime(timezone=True), nullable=True)

    # Worker segment targeting
    target_business_types = Column(
        JSONB,
        nullable=True,
        doc="Target business types (e.g. ['dukawallah', 'mama_mboga'])",
    )
    target_regions = Column(
        JSONB,
        nullable=True,
        doc="Target regions (geohash prefixes)",
    )

    # Metadata
    description = Column(Text, nullable=True)
    changelog = Column(Text, nullable=True, doc="What changed from previous version")

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deployed_at = Column(DateTime(timezone=True), nullable=True)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_model_active", "model_name", "is_champion"),
        Index("idx_model_ab_test", "ab_test_id"),
        Index("idx_model_dialect_status", "dialect", "status"),
    )


class FederatedUpdate(Base):
    """
    Individual federated learning update submissions.

    Stores metadata about each update for quality tracking,
    replay protection, and analytics. Actual gradients are
    stored in the aggregation service, not here.
    """

    __tablename__ = "federated_updates"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    device_id_hash = Column(
        String(64),
        nullable=False,
        index=True,
        doc="SHA-256 hash of device ID (one-way, cannot identify user)",
    )
    dialect = Column(
        String(10),
        nullable=False,
        doc="Dialect/language cluster assigned",
    )
    # Update metadata (no raw data)
    corrections_count = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of correction patterns in this update",
    )
    vocabulary_size = Column(Integer, nullable=True)
    estimated_wer = Column(Float, nullable=True, doc="Estimated word error rate")
    device_tier = Column(String(20), nullable=True, doc="Device capability tier")
    # Quality
    quality_score = Column(
        Float,
        nullable=False,
        default=0.5,
        doc="Quality validation score [0.0, 1.0]",
    )
    # Differential privacy
    dp_epsilon = Column(Float, nullable=False, default=0.1, doc="DP epsilon used")
    dp_applied = Column(Boolean, nullable=False, default=True, doc="Whether DP was applied")
    # K-anonymity
    k_anonymity_k = Column(Integer, nullable=False, default=5, doc="K-anonymity group size")
    # Aggregation
    aggregated = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether this update has been included in an aggregation round",
    )
    aggregation_round = Column(Integer, nullable=True, doc="Which aggregation round included this")
    model_version = Column(
        String(50),
        nullable=True,
        doc="Model version that resulted from this update",
    )
    # Privacy verification
    k_anonymity_met = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether k-anonymity threshold was met for this update's group",
    )

    submitted_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_fl_update_dialect", "dialect", "submitted_at"),
        Index("idx_fl_update_unagg", "aggregated", "dialect"),
    )


class CostTracking(Base):
    """
    Infrastructure cost tracking.

    Tracks costs per component (server, inference, storage, network)
    for budgeting, optimization, and investor reporting.
    """

    __tablename__ = "cost_tracking"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    component = Column(
        Enum("server", "inference", "storage", "network", "training", "other",
             name="cost_component_enum"),
        nullable=False,
        doc="Infrastructure component",
    )
    phase = Column(
        Enum("cloud", "home_server", "mini_dc", "data_center", "pan_african",
             name="cost_phase_enum"),
        nullable=False,
        default="cloud",
    )
    # Cost details
    amount_usd = Column(Float, nullable=False, doc="Cost amount in USD")
    # Inference-specific
    model_name = Column(String(200), nullable=True, doc="Model name (for inference costs)")
    inference_count = Column(Integer, nullable=True, doc="Number of inferences")
    cost_per_inference_usd = Column(Float, nullable=True, doc="Cost per inference in USD")
    # Worker metrics
    workers_served = Column(Integer, nullable=True, doc="Number of workers served")
    cost_per_worker_usd = Column(Float, nullable=True, doc="Cost per worker in USD")
    # Period
    period_start = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="Start of cost period",
    )
    period_end = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="End of cost period",
    )
    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_cost_component_period", "component", "period_start"),
        Index("idx_cost_phase", "phase", "period_start"),
    )
