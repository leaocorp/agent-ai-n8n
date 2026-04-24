"""Central message processor — orchestrates the entire pipeline.

Receives a parsed WebhookPayload and runs:
block_check → debounce → agent → history → send

Usage:
    processor = MessageProcessor(block_manager=..., ...)
    await processor.process(payload)
"""
from __future__ import annotations

import asyncio
import re
import structlog
from execution.config import Config
from execution.instagram_receiver import WebhookPayload, InstagramReceiver

logger = structlog.get_logger()


class MessageProcessor:
    """Orchestrates message processing from webhook to reply."""

    def __init__(
        self,
        block_manager: object,
        debounce_stacker: object,
        agent_invoker: object,
        chat_history: object,
        instagram_receiver: object,
        instagram_sender: object,
        config: Config,
    ) -> None:
        self._block = block_manager
        self._debounce = debounce_stacker
        self._agent = agent_invoker
        self._history = chat_history
        self._receiver = instagram_receiver
        self._sender = instagram_sender
        self._config = config

    async def process(self, payload: WebhookPayload) -> None:
        """Run the full pipeline for a single webhook payload."""
        sender_id = payload.sender_id
        log = logger.bind(sender=sender_id, mid=payload.message_mid)

        # 1. Handle echoes — activate block, save to history, exit
        if payload.is_echo:
            # Check if this exact message ID was just sent by our bot
            is_our_bot = await self._block.is_bot_message_id(payload.message_mid)
            
            if is_our_bot:
                log.info("bot_echo_ignored", mid=payload.message_mid)
            else:
                log.info("human_echo_detected", mid=payload.message_mid)
                await self._block.activate_echo_block(payload.recipient_id)
                if payload.text:
                    await self._history.save_ai_message(payload.recipient_id, payload.text)
                    await self._block.activate_handoff_block(payload.recipient_id)
            return

        # 2. Check blocklist
        if self._block.is_sender_blocked(sender_id):
            log.info("sender_blocked")
            return

        # 3. Check dedup
        if await self._block.is_message_duplicate(payload.message_mid):
            log.info("message_duplicate")
            return

        # 4. Check human takeover
        if await self._block.is_human_takeover_active(sender_id):
            log.info("human_takeover_active")
            await self._history.save_human_message(sender_id, payload.text or "")
            return

        # 5. Exploração: tenta resolver @username do remetente via Graph API (fire-and-forget)
        asyncio.ensure_future(
            InstagramReceiver.fetch_sender_username(sender_id, self._config.meta_page_access_token)
        )

        # 6. Resolve message text (download media if needed)
        message_text = payload.text or ""
        if payload.attachment_url and payload.attachment_type in ("audio", "image"):
            log.info("downloading_media", type=payload.attachment_type)
            media_bytes = await self._receiver.download_media(payload.attachment_url)
            message_text = f"[{payload.attachment_type} recebido: {len(media_bytes)} bytes]"

        if not message_text:
            log.info("empty_message_skipped")
            return

        # 7. Debounce — push and check if first arrival
        msg_data = {
            "mensagem": message_text,
            "id_msg": payload.message_mid,
            "timestamp": str(payload.timestamp),
        }
        is_first = await self._debounce.push_message(sender_id, msg_data)

        if not is_first:
            log.info("debounce_appended_only")
            return

        # 7. Wait for more messages to accumulate
        await asyncio.sleep(self._debounce.debounce_seconds)

        # 8. Collect all stacked messages
        concatenated = await self._debounce.collect_messages(sender_id)
        log.info("messages_collected", text_length=len(concatenated))

        # 9. Save human message to history
        await self._history.save_human_message(sender_id, concatenated)

        # 10. Invoke the agent
        agent_response = await self._agent.invoke(concatenated, sender_id)
        log.info("agent_responded", response_length=len(agent_response))

        # 11. Check for VAZIO — skip sending if the agent decided to stay silent
        if re.search(r"\bVAZIO\b", agent_response, re.IGNORECASE):
            log.info("vazio_detected_skipping_reply")
            return

        # 12. Save AI response to history
        await self._history.save_ai_message(sender_id, agent_response)

        # 13. Send the reply via Instagram
        sent_ids = await self._sender.send_reply(sender_id, agent_response)

        # 14. Mark dedup for each sent message
        for mid in sent_ids:
            await self._block.mark_message_sent(mid)

        log.info("processing_complete", sent_messages=len(sent_ids))
