"""Instagram message receiver — parses webhook payloads and downloads media.

Handles text, audio, and image messages from Instagram's Graph API webhook.

Usage:
    payload = InstagramReceiver.parse_webhook(request_body)
    if payload and payload.attachment_url:
        content = await receiver.download_and_convert(payload)
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional
import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class WebhookPayload:
    """Parsed Instagram webhook message."""

    sender_id: str
    recipient_id: str
    message_mid: str
    timestamp: int
    text: Optional[str] = None
    is_echo: bool = False
    app_id: Optional[str] = None
    attachment_type: Optional[str] = None
    attachment_url: Optional[str] = None


class InstagramReceiver:
    """Parses and processes incoming Instagram webhook payloads."""

    @staticmethod
    def parse_webhook(body: dict) -> Optional[WebhookPayload]:
        """Extract message data from the Meta webhook body.

        Returns None if the payload has no processable message.
        """
        try:
            messaging = body["entry"][0]["messaging"][0]
            sender_id = messaging["sender"]["id"]
            recipient_id = messaging["recipient"]["id"]
            timestamp = messaging.get("timestamp", 0)

            message = messaging.get("message")
            if message is None:
                return None

            mid = message.get("mid", "")
            text = message.get("text")
            is_echo = message.get("is_echo", False)
            app_id = str(message.get("app_id")) if message.get("app_id") else None

            attachment_type: Optional[str] = None
            attachment_url: Optional[str] = None

            attachments = message.get("attachments", [])
            if attachments:
                first = attachments[0]
                attachment_type = first.get("type")
                attachment_url = first.get("payload", {}).get("url")

            return WebhookPayload(
                sender_id=sender_id,
                recipient_id=recipient_id,
                message_mid=mid,
                timestamp=timestamp,
                text=text,
                is_echo=is_echo,
                app_id=app_id,
                attachment_type=attachment_type,
                attachment_url=attachment_url,
            )
        except (KeyError, IndexError) as exc:
            logger.warning("webhook_parse_failed", error=str(exc), body_keys=list(body.keys()))
            return None

    @staticmethod
    async def download_media(url: str) -> bytes:
        """Download media binary from Instagram CDN."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
            logger.info("media_downloaded", url=url[:80], size_bytes=len(response.content))
            return response.content

    @staticmethod
    def media_to_base64(content: bytes) -> str:
        """Convert binary media to base64 string for LLM APIs."""
        return base64.b64encode(content).decode("utf-8")

    @staticmethod
    async def fetch_sender_username(
        sender_id: str,
        page_access_token: str,
        api_base: str = "https://graph.instagram.com/v22.0",
    ) -> dict[str, str | None]:
        """Try to fetch the Instagram username and name for a sender_id.

        The webhook only delivers a numeric IGSID. This makes an extra Graph API
        call to resolve it to a human-readable @username.

        Returns a dict with keys 'username' and 'name' (either may be None on failure).

        Usage (exploration/logging only — non-blocking):
            info = await InstagramReceiver.fetch_sender_username(sender_id, cfg.meta_page_access_token)
            logger.info("sender_resolved", **info)
        """
        url = f"{api_base}/{sender_id}"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    url,
                    params={"fields": "name,username", "access_token": page_access_token},
                )
                if response.status_code == 200:
                    data = response.json()
                    result = {
                        "username": data.get("username"),
                        "name": data.get("name"),
                        "sender_id": sender_id,
                    }
                    logger.info("sender_username_resolved", **result)
                    return result
                else:
                    logger.warning(
                        "sender_username_fetch_failed",
                        sender_id=sender_id,
                        status=response.status_code,
                        body=response.text[:200],
                    )
        except Exception as exc:
            logger.warning("sender_username_fetch_error", sender_id=sender_id, error=str(exc))
        return {"username": None, "name": None, "sender_id": sender_id}
