"""Thin async wrapper over a Redis connection.

Owns the interface so the rest of the project never touches `redis` directly.

Usage:
    client = RedisClient(connection=redis_conn)
    await client.set("key", "value", ttl=30)
"""
from __future__ import annotations

from typing import Any, Protocol
import structlog

logger = structlog.get_logger()


class RedisConnection(Protocol):
    """Protocol for Redis connection — allows fakes in tests."""

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def rpush(self, key: str, value: str) -> int: ...
    async def lrange(self, key: str, start: int, stop: int) -> list[str]: ...
    async def llen(self, key: str) -> int: ...


class RedisClient:
    """Async Redis client wrapper with structured logging."""

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    async def get(self, key: str) -> str | None:
        """Get a value by key. Returns None if not found."""
        result = await self._conn.get(key)
        logger.debug("redis_get", key=key, found=result is not None)
        return result

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Set a key with optional TTL in seconds."""
        await self._conn.set(key, value, ex=ttl)
        logger.debug("redis_set", key=key, ttl=ttl)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        await self._conn.delete(key)
        logger.debug("redis_delete", key=key)

    async def rpush(self, key: str, value: str) -> int:
        """Append value to a list. Returns new list length."""
        length = await self._conn.rpush(key, value)
        logger.debug("redis_rpush", key=key, new_length=length)
        return length

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        """Get list elements from start to stop (-1 for all)."""
        items = await self._conn.lrange(key, start, stop)
        logger.debug("redis_lrange", key=key, count=len(items))
        return items

    async def llen(self, key: str) -> int:
        """Get the length of a list."""
        length = await self._conn.llen(key)
        return length
