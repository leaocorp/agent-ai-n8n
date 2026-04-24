"""Chat history reader/writer for ias_chat_histories_drAntonio.

Reads history as LangChain messages for the agent, writes human+ai messages
back after each interaction. Mirrors the n8n memoryPostgresChat behavior.

Usage:
    writer = ChatHistoryWriter(supabase=client, config=cfg)
    messages = await writer.load_as_langchain_messages("sender_id")
    await writer.save_human_message("sender_id", "Hello")
    await writer.save_ai_message("sender_id", "Hi there!")
"""
from __future__ import annotations

import json
import structlog
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from execution.config import Config

logger = structlog.get_logger()


class ChatHistoryWriter:
    """Read/write chat history in Supabase, compatible with n8n format."""

    def __init__(self, supabase: object, config: Config) -> None:
        self._supabase = supabase
        self._config = config

    def build_session_id(self, sender_id: str) -> str:
        """Build the session_id matching the n8n convention."""
        return f"{sender_id}_direct_drantonio"

    async def save_human_message(self, sender_id: str, content: str) -> None:
        """Save a human (patient) message to the history table."""
        session_id = self.build_session_id(sender_id)
        payload = json.dumps({
            "type": "human",
            "content": content,
            "additional_kwargs": {},
            "response_metadata": {},
            "invalid_tool_calls": [],
        })
        await self._supabase.insert(self._config.chat_history_table, {
            "session_id": session_id,
            "message": payload,
        })
        logger.info("chat_history_saved", type="human", sender=sender_id)

    async def save_ai_message(self, sender_id: str, content: str) -> None:
        """Save an AI (agent) response to the history table."""
        session_id = self.build_session_id(sender_id)
        payload = json.dumps({
            "type": "ai",
            "content": content,
            "additional_kwargs": {},
            "response_metadata": {},
            "invalid_tool_calls": [],
        })
        await self._supabase.insert(self._config.chat_history_table, {
            "session_id": session_id,
            "message": payload,
        })
        logger.info("chat_history_saved", type="ai", sender=sender_id)

    async def load_history(self, sender_id: str) -> list[dict]:
        """Load raw history dicts from Supabase."""
        session_id = self.build_session_id(sender_id)
        rows = await self._supabase.select(
            self._config.chat_history_table,
            {"session_id": session_id},
            limit=self._config.context_window_length,
        )
        results: list[dict] = []
        for row in rows:
            msg_data = row.get("message", "{}")
            if isinstance(msg_data, str):
                msg_data = json.loads(msg_data)
            results.append(msg_data)
        return results

    async def load_as_langchain_messages(self, sender_id: str) -> list[BaseMessage]:
        """Load history and convert to LangChain message objects."""
        raw_history = await self.load_history(sender_id)
        messages: list[BaseMessage] = []
        for entry in raw_history:
            msg_type = entry.get("type", "human")
            content = entry.get("content", "")
            if msg_type == "human":
                messages.append(HumanMessage(content=content))
            elif msg_type == "ai":
                messages.append(AIMessage(content=content))
        logger.info("chat_history_loaded", sender=sender_id, count=len(messages))
        return messages
