from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from execution.config import Config


class FakeRedisClient:
    """In-memory Redis substitute for tests."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._lists: dict[str, list[str]] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._lists.pop(key, None)

    async def rpush(self, key: str, value: str) -> int:
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].append(value)
        return len(self._lists[key])

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        return self._lists.get(key, [])[start:stop + 1] if stop != -1 else self._lists.get(key, [])[start:]

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))


class FakeSupabaseClient:
    """In-memory Supabase substitute for tests."""

    def __init__(self) -> None:
        self._rows: list[dict] = []

    async def insert(self, table: str, data: dict) -> dict:
        row = {"id": len(self._rows) + 1, **data}
        self._rows.append(row)
        return row

    async def select(self, table: str, filters: dict, limit: int = 50) -> list[dict]:
        results = [r for r in self._rows if all(r.get(k) == v for k, v in filters.items())]
        return results[-limit:]


@pytest.fixture
def fake_redis() -> FakeRedisClient:
    return FakeRedisClient()


@pytest.fixture
def fake_supabase() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def test_config() -> Config:
    return Config(
        meta_verify_token="test_token",
        meta_page_access_token="test_access_token",
        meta_page_id="17841400753420214",
        google_api_key="test_google_key",
        openai_api_key="test_openai_key",
        supabase_db_url="postgresql://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379",
        blocked_sender_ids=frozenset({"blocked_id_1"}),
        admin_sender_ids=frozenset({"1141940870875707"}),
    )
