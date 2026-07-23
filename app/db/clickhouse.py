"""
ClickHouse client — analytics engine for time-series and aggregate queries.

Architecture: arch_backend.md §3.4
"""
from typing import Any, Optional
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

_client = None


def get_clickhouse():
    """Get the ClickHouse HTTP client (lazy init)."""
    global _client
    if _client is None:
        try:
            from httpx import Client
            _client = Client(
                base_url=settings.CLICKHOUSE_URL,
                auth=(settings.CLICKHOUSE_USER, settings.CLICKHOUSE_PASSWORD),
                timeout=30.0,
            )
            logger.info("clickhouse_connected")
        except Exception as e:
            logger.warning("clickhouse_connection_failed", error=str(e))
            return None
    return _client


def close_clickhouse():
    """Close ClickHouse client."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("clickhouse_closed")


def query(sql: str, params: Optional[dict] = None) -> list[dict]:
    """Execute a ClickHouse query and return rows as dicts."""
    client = get_clickhouse()
    if client is None:
        return []
    try:
        response = client.post(
            "/",
            data=sql,
            params={**(params or {}), "default_format": "JSONEachRow"},
        )
        response.raise_for_status()
        lines = response.text.strip().split("\n")
        import json
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as e:
        logger.error("clickhouse_query_error", sql=sql[:200], error=str(e))
        return []


def execute(sql: str, params: Optional[dict] = None):
    """Execute a ClickHouse write (INSERT, CREATE, etc.)."""
    client = get_clickhouse()
    if client is None:
        return
    try:
        response = client.post("/", data=sql, params=params or {})
        response.raise_for_status()
    except Exception as e:
        logger.error("clickhouse_execute_error", sql=sql[:200], error=str(e))
        raise
