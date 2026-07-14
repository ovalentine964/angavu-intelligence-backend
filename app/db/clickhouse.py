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
from pathlib import Path
from typing import Any, Optional

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Canonical table names ─────────────────────────────────────────────────────
# Import these everywhere to avoid typos and enable rename refactors.
TABLE_TRANSACTIONS_ANALYTICS = "transactions_analytics"
TABLE_ECONOMIC_INDICATORS    = "economic_indicators"
TABLE_MARKET_DATA            = "market_data"
TABLE_WORKER_ACTIVITY        = "worker_activity"

ALL_TABLES = [
    TABLE_TRANSACTIONS_ANALYTICS,
    TABLE_ECONOMIC_INDICATORS,
    TABLE_MARKET_DATA,
    TABLE_WORKER_ACTIVITY,
]

# ── Schema file path ─────────────────────────────────────────────────────────
_SCHEMA_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "database" / "schema" / "clickhouse.sql",
    Path("/app/database/schema/clickhouse.sql"),
    Path("database/schema/clickhouse.sql"),
]

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
        from app.db.clickhouse import ClickHouseClient, TABLE_TRANSACTIONS_ANALYTICS

        ch = ClickHouseClient()
        rows = await ch.query(
            "SELECT region, sum(amount) FROM transactions_analytics "
            "WHERE date >= '2026-01-01' GROUP BY region"
        )
        await ch.insert(TABLE_TRANSACTIONS_ANALYTICS, [
            {"date": "2026-07-01", "region": "nairobi", "product_category": "food",
             "volume": 100, "amount": 50000},
        ])
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

    async def ensure_schema(self) -> None:
        """
        Apply the ClickHouse schema SQL if tables don't exist.

        Called once on application startup. Reads database/schema/clickhouse.sql
        and executes each statement. Idempotent (uses IF NOT EXISTS).
        """
        schema_file = None
        for candidate in _SCHEMA_CANDIDATES:
            if candidate.exists():
                schema_file = candidate
                break

        if schema_file is None:
            logger.warning("clickhouse_schema_file_not_found", paths=[str(c) for c in _SCHEMA_CANDIDATES])
            return

        sql = schema_file.read_text(encoding="utf-8")
        statements = [s.strip() for s in sql.split(";") if s.strip()]

        applied = 0
        for stmt in statements:
            lines = [l for l in stmt.split("\n") if l.strip() and not l.strip().startswith("--")]
            clean = " ".join(lines).strip()
            if not clean:
                continue
            try:
                await self.command(clean)
                applied += 1
            except Exception as e:
                # ALTER TTL on empty table can warn — that's fine
                logger.debug("clickhouse_schema_stmt_skip", error=str(e), stmt=clean[:120])

        logger.info("clickhouse_schema_applied", statements=applied)

        # Verify expected tables exist
        client = await get_clickhouse()
        result = await client.query(
            "SELECT name FROM system.tables WHERE database = {db:String}",
            parameters={"db": settings.CLICKHOUSE_DATABASE},
        )
        existing = {row[0] for row in result.result_rows}
        missing = [t for t in ALL_TABLES if t not in existing]
        if missing:
            logger.error("clickhouse_tables_missing", tables=missing)
        else:
            logger.info("clickhouse_tables_verified", tables=ALL_TABLES)
