"""ClickHouse connection management."""
from __future__ import annotations

from functools import lru_cache

import clickhouse_connect

from app.core import settings


@lru_cache
def get_clickhouse() -> clickhouse_connect.driver.Client:
    """Cached ClickHouse client."""
    url = settings.CLICKHOUSE_URL.replace("http://", "").replace("https://", "")
    host, port = url.split(":") if ":" in url else (url, "8123")
    return clickhouse_connect.get_client(
        host=host,
        port=int(port),
        database=settings.CLICKHOUSE_DATABASE,
    )
