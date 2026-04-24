"""Webhook handler — GET verification + POST ingestion for Meta platform.

The GET endpoint handles Meta's webhook verification challenge.
The POST endpoint receives messages and spawns background processing.

Usage:
    Deployed via modal_app.py as a @modal.fastapi_endpoint.
"""
from __future__ import annotations

from typing import Optional
import structlog
from execution.config import Config

logger = structlog.get_logger()


def verify_webhook(params: dict, config: Config) -> Optional[str]:
    """Verify Meta webhook subscription (GET handler).

    Returns the challenge string if valid, None if rejected.
    """
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == config.meta_verify_token:
        logger.info("webhook_verified")
        return challenge

    logger.warning("webhook_verification_failed", mode=mode)
    return None


def parse_post_body(body: dict) -> bool:
    """Validate that the POST body is a valid Instagram webhook event.

    Returns True if the body contains processable Instagram messaging data.
    """
    if body.get("object") != "instagram":
        return False
    entries = body.get("entry", [])
    if not entries:
        return False
    return True
