"""Thin wrapper over the Supabase Python client.

Owns the interface so the rest of the project never imports `supabase` directly.

Usage:
    client = SupabaseClient(connection=supabase_native)
    await client.insert("table", {"col": "val"})
    rows = await client.select("table", {"col": "val"}, limit=50)
"""
from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger()


class SupabaseClient:
    """Synchronous Supabase client wrapper with structured logging.

    Note: The official `supabase-py` client is synchronous under the hood,
    so we wrap it with async signatures for interface consistency.
    """

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    async def insert(self, table: str, data: dict) -> dict:
        """Insert a row into a table."""
        result = self._conn.table(table).insert(data).execute()
        logger.debug("supabase_insert", table=table, keys=list(data.keys()))
        return result.data[0] if result.data else data

    async def select(
        self, table: str, filters: dict, limit: int = 50
    ) -> list[dict]:
        """Select rows from a table with equality filters."""
        builder = self._conn.table(table).select("*")
        for col, val in filters.items():
            builder = builder.eq(col, val)
        builder = builder.order("id", desc=False).limit(limit)
        result = builder.execute()
        logger.debug("supabase_select", table=table, filters=filters, count=len(result.data))
        return result.data
