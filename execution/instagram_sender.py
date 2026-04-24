"""Instagram message sender — TYPING_ON, split, send, and tracking.

Mirrors the n8n "Code in JavaScript" split logic and the Loop Over Items
pattern: split by newline, send TYPING_ON, wait, send text, repeat.

Usage:
    sender = InstagramSender(config=cfg)
    await sender.send_reply(sender_id, "Oi!\nComo posso ajudar?")
"""
from __future__ import annotations

import asyncio
import re
import httpx
import structlog
from execution.config import Config

logger = structlog.get_logger()


class InstagramSender:
    """Sends messages to Instagram via Graph API with typing indicators."""

    def __init__(self, config: Config, block_manager: object = None) -> None:
        self._config = config
        self._block = block_manager
        self._base_url = f"{config.instagram_api_base}/{config.meta_page_id}/messages"

    @staticmethod
    def split_response(text: str) -> list[str]:
        """Split LLM response into message bubbles — mirrors n8n JS logic.

        Splits on newlines, strips whitespace, removes trailing dots.
        """
        parts = re.split(r"\n+", text)
        cleaned = [p.strip().rstrip(".") for p in parts if p.strip()]
        return cleaned

    async def send_typing(self, recipient_id: str) -> None:
        """Send TYPING_ON action to show typing indicator."""
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self._config.meta_page_access_token}"},
                json={"recipient": {"id": recipient_id}, "sender_action": "TYPING_ON"},
            )
        logger.debug("typing_sent", recipient=recipient_id)

    async def send_text(self, recipient_id: str, text: str) -> str | None:
        """Send a single text message. Returns message_id on success."""
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self._config.meta_page_access_token}"},
                json={"recipient": {"id": recipient_id}, "message": {"text": text}},
            )
            response.raise_for_status()
            data = response.json()
            message_id = data.get("message_id")
            
            # Instantly save to Redis to prevent race condition with incoming echo webhook
            if message_id and self._block:
                await self._block.save_bot_message_id(message_id)
                
            logger.info("message_sent", recipient=recipient_id, message_id=message_id)
            return message_id

    async def track_sent_message(self, message_id: str) -> None:
        """Notify the mensageria tracking system (fire-and-forget)."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    self._config.mensageria_url,
                    json={"id": message_id},
                )
            logger.debug("tracking_sent", message_id=message_id)
        except Exception as exc:
            logger.warning("tracking_failed", message_id=message_id, error=str(exc))

    async def send_reply(self, recipient_id: str, full_response: str) -> list[str]:
        """Split response and send as sequential bubbles with typing indicators.

        Returns list of sent message_ids.
        """
        parts = self.split_response(full_response)
        sent_ids: list[str] = []

        for part in parts:
            await self.send_typing(recipient_id)
            await asyncio.sleep(1)
            message_id = await self.send_text(recipient_id, part)
            if message_id:
                sent_ids.append(message_id)
                await self.track_sent_message(message_id)

        logger.info("reply_complete", recipient=recipient_id, bubbles=len(parts))
        return sent_ids
