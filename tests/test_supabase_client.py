"""Tests for the Supabase client wrapper."""
import pytest
from execution.supabase_client import SupabaseClient


class FakePostgrestResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class FakePostgrestBuilder:
    def __init__(self, store: list[dict], table: str) -> None:
        self._store = store
        self._table = table
        self._filters: dict = {}
        self._order_col: str | None = None
        self._limit_val: int | None = None

    def select(self, columns: str = "*") -> "FakePostgrestBuilder":
        return self

    def eq(self, col: str, val: str) -> "FakePostgrestBuilder":
        self._filters[col] = val
        return self

    def order(self, col: str, desc: bool = False) -> "FakePostgrestBuilder":
        self._order_col = col
        return self

    def limit(self, n: int) -> "FakePostgrestBuilder":
        self._limit_val = n
        return self

    def insert(self, data: dict) -> "FakePostgrestBuilder":
        self._store.append(data)
        return self

    def execute(self) -> FakePostgrestResponse:
        filtered = [r for r in self._store if all(r.get(k) == v for k, v in self._filters.items())]
        if self._limit_val:
            filtered = filtered[-self._limit_val:]
        return FakePostgrestResponse(data=filtered)


class FakeSupabaseNativeClient:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict]] = {}

    def table(self, name: str) -> FakePostgrestBuilder:
        if name not in self._tables:
            self._tables[name] = []
        return FakePostgrestBuilder(self._tables[name], name)


@pytest.mark.asyncio
async def test_insert_and_select() -> None:
    native = FakeSupabaseNativeClient()
    client = SupabaseClient(connection=native)

    await client.insert("messages", {"session_id": "s1", "message": '{"type":"human"}'})
    rows = await client.select("messages", {"session_id": "s1"}, limit=10)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"
