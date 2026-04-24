"""Tests for the central message processor orchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from execution.message_processor import MessageProcessor
from execution.instagram_receiver import WebhookPayload
from execution.config import Config


@pytest.fixture
def test_payload() -> WebhookPayload:
    return WebhookPayload(
        sender_id="patient_1",
        recipient_id="page_1",
        message_mid="mid_test",
        timestamp=1700000000000,
        text="Olá doutor",
    )


@pytest.fixture
def echo_payload() -> WebhookPayload:
    return WebhookPayload(
        sender_id="page_1",
        recipient_id="patient_1",
        message_mid="mid_echo",
        timestamp=1700000000000,
        text="Respondido manualmente",
        is_echo=True,
    )


@pytest.mark.asyncio
async def test_echo_activates_block(test_config: Config) -> None:
    block_mgr = AsyncMock()
    block_mgr.is_sender_blocked.return_value = False
    block_mgr.is_bot_message_id.return_value = False  # simula echo humano, não do bot
    processor = MessageProcessor(
        block_manager=block_mgr,
        debounce_stacker=AsyncMock(),
        agent_invoker=AsyncMock(),
        chat_history=AsyncMock(),
        instagram_receiver=MagicMock(),
        instagram_sender=AsyncMock(),
        config=test_config,
    )
    payload = WebhookPayload(
        sender_id="page_1", recipient_id="patient_1",
        message_mid="mid_echo", timestamp=0, text="test", is_echo=True,
    )
    await processor.process(payload)
    block_mgr.activate_echo_block.assert_called_once()


@pytest.mark.asyncio
async def test_blocked_sender_is_skipped(test_config: Config) -> None:
    block_mgr = AsyncMock()
    block_mgr.is_sender_blocked.return_value = True
    debounce = AsyncMock()
    processor = MessageProcessor(
        block_manager=block_mgr,
        debounce_stacker=debounce,
        agent_invoker=AsyncMock(),
        chat_history=AsyncMock(),
        instagram_receiver=MagicMock(),
        instagram_sender=AsyncMock(),
        config=test_config,
    )
    payload = WebhookPayload(
        sender_id="blocked_id", recipient_id="page_1",
        message_mid="mid_blocked", timestamp=0, text="Hey",
    )
    await processor.process(payload)
    debounce.push_message.assert_not_called()


@pytest.mark.asyncio
async def test_vazio_response_skips_send(test_config: Config) -> None:
    block_mgr = AsyncMock()
    block_mgr.is_sender_blocked.return_value = False
    block_mgr.is_message_duplicate.return_value = False
    block_mgr.is_human_takeover_active.return_value = False

    debounce = AsyncMock()
    debounce.push_message.return_value = True
    debounce.collect_messages.return_value = "kkk"
    debounce.debounce_seconds = 0

    agent = AsyncMock()
    agent.invoke.return_value = "VAZIO"

    sender = AsyncMock()

    processor = MessageProcessor(
        block_manager=block_mgr,
        debounce_stacker=debounce,
        agent_invoker=agent,
        chat_history=AsyncMock(),
        instagram_receiver=MagicMock(),
        instagram_sender=sender,
        config=test_config,
    )
    payload = WebhookPayload(
        sender_id="s1", recipient_id="r1", message_mid="mid1", timestamp=0, text="kkk",
    )
    await processor.process(payload)
    sender.send_reply.assert_not_called()
