"""Tests for debounce stacker — message accumulation logic."""
import pytest
import json
from tests.conftest import FakeRedisClient
from execution.debounce_stacker import DebounceStacker


@pytest.fixture
def stacker(fake_redis: FakeRedisClient) -> DebounceStacker:
    return DebounceStacker(redis=fake_redis, debounce_seconds=0)


@pytest.mark.asyncio
async def test_first_message_is_first_arrival(stacker: DebounceStacker) -> None:
    msg = {"mensagem": "Oi", "id_msg": "mid1", "timestamp": "2026-01-01T00:00:00"}
    is_first = await stacker.push_message("sender_1", msg)
    assert is_first is True


@pytest.mark.asyncio
async def test_second_message_is_not_first(stacker: DebounceStacker) -> None:
    msg1 = {"mensagem": "Oi", "id_msg": "mid1", "timestamp": "2026-01-01T00:00:00"}
    msg2 = {"mensagem": "Tudo bem?", "id_msg": "mid2", "timestamp": "2026-01-01T00:00:01"}
    await stacker.push_message("sender_1", msg1)
    is_first = await stacker.push_message("sender_1", msg2)
    assert is_first is False


@pytest.mark.asyncio
async def test_collect_returns_all_messages(stacker: DebounceStacker) -> None:
    msg1 = {"mensagem": "Oi", "id_msg": "mid1", "timestamp": "2026-01-01T00:00:00"}
    msg2 = {"mensagem": "Tudo bem?", "id_msg": "mid2", "timestamp": "2026-01-01T00:00:01"}
    await stacker.push_message("sender_1", msg1)
    await stacker.push_message("sender_1", msg2)
    collected = await stacker.collect_messages("sender_1")
    assert collected == "Oi\nTudo bem?"


@pytest.mark.asyncio
async def test_collect_clears_the_list(stacker: DebounceStacker) -> None:
    msg = {"mensagem": "Hello", "id_msg": "mid1", "timestamp": "2026-01-01T00:00:00"}
    await stacker.push_message("sender_1", msg)
    await stacker.collect_messages("sender_1")
    # After collecting, list should be empty
    is_first = await stacker.push_message("sender_1", msg)
    assert is_first is True
