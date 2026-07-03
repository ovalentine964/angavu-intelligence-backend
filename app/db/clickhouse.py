"""
ClickHouse client for analytical queries on 600M+ records.

Used for:
- Time-series queries (prices, transactions over time)
- Aggregate analytics (GDP, inflation, employment)
- Dashboard queries (real-time metrics)
- Report generation (historical analysis)

ClickHouse is 30-200x faster than PostgreSQL for these queries.
"""

import logging
from typing import Any, Optional

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Module-level singleton
_client: Optional[AsyncClient] = None


async def get_clickhouse() -> AsyncClient:
    """
    Get or create the ClickHouse async client singleton.

    Returns an AsyncClient connected to the configured ClickHouse instance.
    Raises RuntimeError if ClickHouse is not configured.
    """
    global _client
    if _client is not None:
        return _client

    if not settings.has_clickhouse:
        raise RuntimeError(
            "ClickHouse is not configured. Set CLICKHOUSE_URL and CLICKHOUSE_PASSWORD."
        )

    _client = await clickhouse_connect.get_async_client(
        host=settings.CLICKHOUSE_URL.replace("http://", "").replace("https://", "").split(":")[0],
        port=int(settings.CLICKHOUSE_URL.split(":")[-1]) if ":" in settings.CLICKHOUSE_URL.split("//")[-1] else 8123,
        database=settings.CLICKHOUSE_DATABASE,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
    )
    logger.info("clickhouse_connected", database=settings.CLICKHOUSE_DATABASE)
    return _client


async def close_clickhouse() -> None:
    """Close the ClickHouse client connection. Called on shutdown."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("clickhouse_connection_closed")


class ClickHouseClient:
    """
    High-level ClickHouse client for analytical queries.

    Wraps the clickhouse-connect async client with convenience methods
    for the Angavu Intelligence analytics workloads.

    Usage:
        ch = ClickHouseClient()
        rows = await ch.query("SELECT count() FROM transactions WHERE date >= '2026-01-01'")
        await ch.insert("transactions", [{"id": 1, "amount": 500, "date": "2026-07-01"}])
    """

    async def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Execute a SELECT query and return results as a list of dicts.

        Args:
            sql: ClickHouse SQL query (can use {param:Type} placeholders)
            params: Query parameters for parameterized queries

        Returns:
            List of row dicts with column names as keys

        Example:
            rows = await ch.query(
                "SELECT region, avg(income) FROM workers WHERE year = {year:UInt16} GROUP BY region",
                params={"year": 2026}
            )
        """
        client = await get_clickhouse()
        result = await client.query(sql, parameters=params or {})
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    async def query_df(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """
        Execute a query and return results as a Polars DataFrame.

        Falls back to constructing from query() results.
        """
        import polars as pl

        rows = await self.query(sql, params)
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows)

    async def insert(self, table: str, data: list[dict[str, Any]], column_names: list[str] | None = None) -> None:
        """
        Insert rows into a ClickHouse table.

        Args:
            table: Target table name
            data: List of row dicts to insert
            column_names: Optional explicit column order. If None, inferred from first row.

        Example:
            await ch.insert("transactions", [
                {"id": 1, "amount": 500, "region": "nairobi", "date": "2026-07-01"},
                {"id": 2, "amount": 300, "region": "mombasa", "date": "2026-07-01"},
            ])
        """
        if not data:
            return

        client = await get_clickhouse()
        if column_names is None:
            column_names = list(data[0].keys())

        # Extract values in column order
        rows = [[row.get(col) for col in column_names] for row in data]
        await client.insert(table, rows, column_names=column_names)
        logger.info("clickhouse_insert", table=table, rows=len(data))

    async def create_table(self, table: str, schema: str, engine: str = "MergeTree()") -> None:
        """
        Create a ClickHouse table if it doesn't exist.

        Args:
            table: Table name
            schema: Column definitions (e.g. "id UInt64, amount Float64, date Date")
            engine: ClickHouse table engine (default: MergeTree())

        Example:
            await ch.create_table(
                "daily_aggregates",
                "date Date, region String, total_income Float64, worker_count UInt32",
                engine="MergeTree() ORDER BY (date, region)"
            )
        """
        client = await get_clickhouse()
        ddl = f"CREATE TABLE IF NOT EXISTS {table} ({schema}) ENGINE = {engine}"
        await client.command(ddl)
        logger.info("clickhouse_table_created", table=table)

    async def command(self, sql: str) -> None:
        """Execute a non-SELECT command (DDL, ALTER, OPTIMIZE, etc.)."""
        client = await get_clickhouse()
        await client.command(sql)

    async def health_check(self) -> bool:
        """Check if ClickHouse is reachable."""
        try:
            client = await get_clickhouse()
            result = await client.query("SELECT 1")
            return result.result_rows[0][0] == 1
        except Exception as e:
            logger.warning("clickhouse_health_check_failed", error=str(e))
            return False
