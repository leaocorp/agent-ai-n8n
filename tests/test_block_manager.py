"""Tests for the 3-layer block manager."""
import pytest
from tests.conftest import FakeRedisClient
from execution.block_manager import BlockManager
from execution.config import Config


@pytest.fixture
def block_mgr(fake_redis: FakeRedisClient, test_config: Config) -> BlockManager:
    return BlockManager(redis=fake_redis, config=test_config)


@pytest.mark.asyncio
async def test_message_not_duplicate_initially(block_mgr: BlockManager) -> None:
    assert await block_mgr.is_message_duplicate("mid_123") is False


@pytest.mark.asyncio
async def test_message_duplicate_after_marking(block_mgr: BlockManager) -> None:
    await block_mgr.mark_message_sent("mid_123")
    assert await block_mgr.is_message_duplicate("mid_123") is True


@pytest.mark.asyncio
async def test_no_human_takeover_initially(block_mgr: BlockManager) -> None:
    assert await block_mgr.is_human_takeover_active("sender_1") is False


@pytest.mark.asyncio
async def test_echo_block_activates(block_mgr: BlockManager) -> None:
    await block_mgr.activate_echo_block("recipient_1")
    assert await block_mgr.is_human_takeover_active("recipient_1") is True


@pytest.mark.asyncio
async def test_handoff_block_activates(block_mgr: BlockManager) -> None:
    await block_mgr.activate_handoff_block("recipient_2")
    assert await block_mgr.is_human_takeover_active("recipient_2") is True


@pytest.mark.asyncio
async def test_sender_in_blocklist(block_mgr: BlockManager) -> None:
    assert block_mgr.is_sender_blocked("blocked_id_1") is True
    assert block_mgr.is_sender_blocked("normal_id") is False
