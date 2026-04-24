"""Debounce stacker — accumulates rapid messages before sending to LLM.

Mirrors the n8n "empilhamento" pattern:
1. Push message to Redis list
2. If first arrival, caller should wait N seconds then collect
3. If not first arrival, caller exits silently

Usage:
    stacker = DebounceStacker(redis=client, debounce_seconds=2)
    is_first = await stacker.push_message(sender_id, msg_dict)
    if is_first:
        await asyncio.sleep(stacker.debounce_seconds)
        text = await stacker.collect_messages(sender_id)
"""
from __future__ import annotations

import json
import structlog

logger = structlog.get_logger()


class DebounceStacker:
    """Accumulates messages in Redis for debounced processing."""

    def __init__(self, redis: object, debounce_seconds: int = 2) -> None:
        self._redis = redis
        self.debounce_seconds = debounce_seconds

    def _key(self, sender_id: str) -> str:
        return f"empilhamento:{sender_id}"

    async def push_message(self, sender_id: str, message: dict) -> bool:
        """Push a message to the stack. Returns True if this is the first message."""
        key = self._key(sender_id)
        current_length = await self._redis.llen(key)
        await self._redis.rpush(key, json.dumps(message, ensure_ascii=False))
        is_first = current_length == 0
        logger.info("debounce_push", sender=sender_id, is_first=is_first, queue_size=current_length + 1)
        return is_first

    async def collect_messages(self, sender_id: str) -> str:
        """Read all stacked messages, delete the key, return concatenated text."""
        key = self._key(sender_id)
        raw_items = await self._redis.lrange(key, 0, -1)
        await self._redis.delete(key)

        texts: list[str] = []
        for raw in raw_items:
            parsed = json.loads(raw)
            texts.append(parsed.get("mensagem", ""))

        concatenated = "\n".join(t for t in texts if t)
        logger.info("debounce_collect", sender=sender_id, message_count=len(raw_items), text_length=len(concatenated))
        return concatenated
