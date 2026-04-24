"""Tests for the Redis client wrapper."""
import pytest
from execution.redis_client import RedisClient


class FakeRedisConnection:
    """Simulates aioredis connection for unit tests."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._lists: dict[str, list[str]] = {}
        self._ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value
        if ex:
            self._ttls[key] = ex

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._lists.pop(key, None)

    async def rpush(self, key: str, value: str) -> int:
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].append(value)
        return len(self._lists[key])

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        lst = self._lists.get(key, [])
        if stop == -1:
            return lst[start:]
        return lst[start:stop + 1]

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))


@pytest.mark.asyncio
async def test_set_and_get() -> None:
    conn = FakeRedisConnection()
    client = RedisClient(connection=conn)
    await client.set("key1", "value1", ttl=30)
    result = await client.get("key1")
    assert result == "value1"


@pytest.mark.asyncio
async def test_rpush_and_lrange() -> None:
    conn = FakeRedisConnection()
    client = RedisClient(connection=conn)
    await client.rpush("list1", "msg_a")
    await client.rpush("list1", "msg_b")
    items = await client.lrange("list1", 0, -1)
    assert items == ["msg_a", "msg_b"]


@pytest.mark.asyncio
async def test_delete_removes_key() -> None:
    conn = FakeRedisConnection()
    client = RedisClient(connection=conn)
    await client.set("key2", "val")
    await client.delete("key2")
    result = await client.get("key2")
    assert result is None


@pytest.mark.asyncio
async def test_llen_returns_count() -> None:
    conn = FakeRedisConnection()
    client = RedisClient(connection=conn)
    assert await client.llen("empty") == 0
    await client.rpush("items", "a")
    await client.rpush("items", "b")
    assert await client.llen("items") == 2
