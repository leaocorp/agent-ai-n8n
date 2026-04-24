"""Tests for chat history read/write."""
import json
import pytest
from tests.conftest import FakeSupabaseClient
from execution.chat_history_writer import ChatHistoryWriter
from execution.config import Config


@pytest.fixture
def writer(fake_supabase: FakeSupabaseClient, test_config: Config) -> ChatHistoryWriter:
    return ChatHistoryWriter(supabase=fake_supabase, config=test_config)


@pytest.mark.asyncio
async def test_save_human_message(writer: ChatHistoryWriter) -> None:
    await writer.save_human_message("sender_1", "Olá doutor")
    history = await writer.load_history("sender_1")
    assert len(history) == 1
    assert history[0]["type"] == "human"
    assert history[0]["content"] == "Olá doutor"


@pytest.mark.asyncio
async def test_save_ai_message(writer: ChatHistoryWriter) -> None:
    await writer.save_ai_message("sender_1", "Como posso ajudar?")
    history = await writer.load_history("sender_1")
    assert len(history) == 1
    assert history[0]["type"] == "ai"


@pytest.mark.asyncio
async def test_load_history_returns_langchain_messages(writer: ChatHistoryWriter) -> None:
    await writer.save_human_message("sender_1", "Oi")
    await writer.save_ai_message("sender_1", "Olá!")
    messages = await writer.load_as_langchain_messages("sender_1")
    assert len(messages) == 2
    assert messages[0].__class__.__name__ == "HumanMessage"
    assert messages[1].__class__.__name__ == "AIMessage"


@pytest.mark.asyncio
async def test_session_id_format(writer: ChatHistoryWriter) -> None:
    session_id = writer.build_session_id("123456")
    assert session_id == "123456_direct_drantonio"
