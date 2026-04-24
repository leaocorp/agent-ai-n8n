"""Three-layer block manager — dedup, echo, handoff.

Mirrors the n8n blocking logic exactly:
- Dedup: prevents reprocessing the same mid (TTL 30s)
- Echo: silences bot when human replied manually (TTL 180s)
- Handoff: silences bot when team took over (TTL 5h)

Usage:
    mgr = BlockManager(redis=redis_client, config=cfg)
    if await mgr.is_message_duplicate(mid):
        return
"""
from __future__ import annotations

import structlog
from execution.config import Config

logger = structlog.get_logger()


class BlockManager:
    """Manages Instagram conversation blocking state via Redis."""

    def __init__(self, redis: object, config: Config) -> None:
        self._redis = redis
        self._config = config

    async def is_message_duplicate(self, message_mid: str) -> bool:
        """Check if this message was already processed (dedup layer)."""
        result = await self._redis.get(message_mid)
        return result is not None

    async def mark_message_sent(self, message_mid: str) -> None:
        """Mark a message as sent to prevent reprocessing."""
        await self._redis.set(message_mid, "true", ttl=self._config.dedup_ttl)
        logger.info("dedup_marked", mid=message_mid, ttl=self._config.dedup_ttl)

    async def is_human_takeover_active(self, sender_id: str) -> bool:
        """Check if human takeover block is active (echo or handoff)."""
        key = f"{sender_id}_direct_dr_antonio_block"
        result = await self._redis.get(key)
        return result is not None

    async def activate_echo_block(self, recipient_id: str) -> None:
        """Block bot for 3 minutes after human replied manually."""
        key = f"{recipient_id}_direct_dr_antonio_block"
        await self._redis.set(key, "true", ttl=self._config.echo_block_ttl)
        logger.info("echo_block_activated", recipient=recipient_id, ttl=self._config.echo_block_ttl)

    async def activate_handoff_block(self, recipient_id: str) -> None:
        """Block bot for 5 hours after team handoff."""
        key = f"{recipient_id}_direct_dr_antonio_block"
        await self._redis.set(key, "true", ttl=self._config.handoff_block_ttl)
        logger.info("handoff_block_activated", recipient=recipient_id, ttl=self._config.handoff_block_ttl)

    def is_sender_blocked(self, sender_id: str) -> bool:
        """Check if sender is in the static blocklist."""
        return sender_id in self._config.blocked_sender_ids

    async def save_bot_message_id(self, message_id: str) -> None:
        """Save a message_id sent by the bot (TTL 30s) to recognize its echo later."""
        key = f"bot_msg:{message_id}"
        await self._redis.set(key, "true", ttl=30)

    async def is_bot_message_id(self, message_id: str) -> bool:
        """Check if a message_id was recently sent by the bot."""
        key = f"bot_msg:{message_id}"
        result = await self._redis.get(key)
        return result is not None
