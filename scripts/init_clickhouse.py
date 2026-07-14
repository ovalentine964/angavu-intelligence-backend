"""
ClickHouse Schema Initializer — Python variant.

Can be called from application startup or as a standalone script.
Reads database/schema/clickhouse.sql and executes it against ClickHouse.

Usage:
    python -m scripts.init_clickhouse               # standalone
    from scripts.init_clickhouse import run_schema   # import
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_schema_file() -> Path:
    """Locate the ClickHouse schema SQL file."""
    candidates = [
        Path(__file__).resolve().parent.parent / "database" / "schema" / "clickhouse.sql",
        Path("/app/database/schema/clickhouse.sql"),
        Path("database/schema/clickhouse.sql"),
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "ClickHouse schema file not found. Tried: "
        + ", ".join(str(c) for c in candidates)
    )


async def run_schema(
    host: str = "clickhouse",
    port: int = 8123,
    user: str = "admin",
    password: str = "",
    database: str = "biashara",
    schema_path: str | None = None,
    max_retries: int = 30,
    retry_interval: float = 2.0,
) -> None:
    """
    Apply the ClickHouse schema.

    Waits for ClickHouse to be ready, then executes the schema SQL.
    All CREATE statements use IF NOT EXISTS, so this is safe to run
    multiple times (idempotent).

    Args:
        host: ClickHouse hostname
        port: ClickHouse HTTP port
        user: ClickHouse username
        password: ClickHouse password
        database: ClickHouse database name
        schema_path: Path to the schema SQL file (auto-detected if None)
        max_retries: Max connection attempts
        retry_interval: Seconds between retries
    """
    import clickhouse_connect

    if schema_path:
        schema_file = Path(schema_path)
    else:
        schema_file = _find_schema_file()

    logger.info(
        "clickhouse_schema_init",
        host=host,
        port=port,
        user=user,
        database=database,
        schema=str(schema_file),
    )

    # Wait for ClickHouse
    client = None
    for attempt in range(1, max_retries + 1):
        try:
            client = await clickhouse_connect.get_async_client(
                host=host,
                port=port,
                database=database,
                username=user,
                password=password,
            )
            # Verify connectivity
            result = await client.query("SELECT 1")
            if result.result_rows[0][0] == 1:
                logger.info("clickhouse_ready", attempt=attempt)
                break
        except Exception as e:
            if attempt == max_retries:
                logger.error(
                    "clickhouse_not_ready",
                    attempts=max_retries,
                    error=str(e),
                )
                raise ConnectionError(
                    f"ClickHouse not ready after {max_retries} attempts: {e}"
                ) from e
            logger.debug(
                "clickhouse_retry",
                attempt=attempt,
                max=max_retries,
                error=str(e),
            )
            await asyncio.sleep(retry_interval)
            client = None

    # Execute schema
    sql = schema_file.read_text(encoding="utf-8")

    # Split on semicolons and execute each statement separately
    # (clickhouse-connect doesn't support multiquery in a single call)
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    applied = 0
    errors = 0
    for stmt in statements:
        # Skip comments-only blocks
        lines = [
            l for l in stmt.split("\n")
            if l.strip() and not l.strip().startswith("--")
        ]
        if not lines:
            continue

        clean_stmt = " ".join(lines).strip()
        if not clean_stmt:
            continue

        try:
            await client.command(clean_stmt)
            applied += 1
        except Exception as e:
            errors += 1
            # Log but continue — partial failures are acceptable
            # (e.g., ALTER TABLE on first run with no data is fine)
            logger.warning(
                "clickhouse_schema_stmt_error",
                error=str(e),
                statement=clean_stmt[:200],
            )

    logger.info(
        "clickhouse_schema_applied",
        statements=applied,
        errors=errors,
        database=database,
    )

    # Verify tables exist
    result = await client.query(
        "SELECT name FROM system.tables WHERE database = {db:String}",
        parameters={"db": database},
    )
    tables = [row[0] for row in result.result_rows]
    logger.info("clickhouse_tables", tables=tables)

    await client.close()


async def main():
    """CLI entrypoint."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    await run_schema(
        host=os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        user=os.environ.get("CLICKHOUSE_USER", "admin"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        database=os.environ.get("CLICKHOUSE_DATABASE", "biashara"),
    )


if __name__ == "__main__":
    asyncio.run(main())
