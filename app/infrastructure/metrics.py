"""
Prometheus metrics — API and system metrics.

Architecture: arch_backend.md §3.7
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time
from contextlib import contextmanager

# ─── API Metrics ──────────────────────────────────────────────────────────────

API_REQUESTS = Counter(
    "angavu_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)

API_LATENCY = Histogram(
    "angavu_api_latency_seconds",
    "API request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ─── Sync Metrics ─────────────────────────────────────────────────────────────

SYNC_TRANSACTIONS = Counter(
    "angavu_sync_transactions_total",
    "Total transactions synced from devices",
)

SYNC_DURATION = Histogram(
    "angavu_sync_duration_seconds",
    "Sync request processing time",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ─── Intelligence Metrics ─────────────────────────────────────────────────────

INTEL_GENERATION = Histogram(
    "angavu_intelligence_generation_seconds",
    "Intelligence product generation time",
    ["product"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# ─── FL Metrics ───────────────────────────────────────────────────────────────

FL_ROUNDS = Counter(
    "angavu_fl_round_total",
    "Total FL aggregation rounds completed",
)

FL_CLIENTS_PER_ROUND = Histogram(
    "angavu_fl_clients_per_round",
    "Number of clients per FL round",
    buckets=[1, 2, 5, 10, 20, 50, 100],
)

# ─── System Metrics ───────────────────────────────────────────────────────────

ACTIVE_WORKERS = Gauge(
    "angavu_active_workers",
    "Currently active worker connections",
)

DB_QUERY_DURATION = Histogram(
    "angavu_db_query_duration_seconds",
    "Database query latency",
    ["table"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)


@contextmanager
def track_latency(histogram: Histogram, **labels):
    """Context manager to track latency for a histogram."""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        histogram.labels(**labels).observe(elapsed)


def get_metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
