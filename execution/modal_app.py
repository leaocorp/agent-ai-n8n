"""Modal App definition — Image, Secrets, endpoint, and background worker.

This is the entry point for `modal serve` (dev) and `modal deploy` (prod).

Usage:
    modal serve execution/modal_app.py     # Development
    modal deploy execution/modal_app.py    # Production
"""
from __future__ import annotations

import modal
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse, JSONResponse

app = modal.App("agent-ai-dr-antonio")



image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]",
    "langchain>=0.3.0",
    "langchain-google-genai>=2.0.0",
    "langchain-openai>=0.3.0",
    "langgraph>=0.2.0",
    "redis>=5.0.0",
    "supabase>=2.0.0",
    "httpx>=0.27.0",
    "structlog>=24.0.0",
    "python-dotenv>=1.0.0",
).add_local_dir("execution", remote_path="/root/execution").add_local_dir("directives", remote_path="/root/directives")

secrets = modal.Secret.from_name("agent-ai-secrets")


@app.function(image=image, secrets=[secrets])
async def process_message(body: dict) -> None:
    """Background worker — runs the full processing pipeline."""
    import structlog
    from execution.config import get_config
    from execution.redis_client import RedisClient
    from execution.supabase_client import SupabaseClient
    from execution.block_manager import BlockManager
    from execution.debounce_stacker import DebounceStacker
    from execution.instagram_receiver import InstagramReceiver
    from execution.instagram_sender import InstagramSender
    from execution.chat_history_writer import ChatHistoryWriter
    from execution.agent_graph import build_agent_graph, load_system_prompt, AgentDependencies
    from execution.message_processor import MessageProcessor
    import redis.asyncio as aioredis
    from supabase import create_client

    logger = structlog.get_logger()

    try:
        cfg = get_config()

        payload = InstagramReceiver.parse_webhook(body)
        if payload is None:
            logger.warning("unparseable_payload")
            return

        redis_conn = aioredis.from_url(cfg.redis_url)
        redis_client = RedisClient(connection=redis_conn)

        supabase_native = create_client(cfg.supabase_url, cfg.supabase_key)
        supabase_client = SupabaseClient(connection=supabase_native)

        block_mgr = BlockManager(redis=redis_client, config=cfg)
        debounce = DebounceStacker(redis=redis_client, debounce_seconds=cfg.debounce_seconds)
        history = ChatHistoryWriter(supabase=supabase_client, config=cfg)
        sender = InstagramSender(config=cfg, block_manager=block_mgr)
        receiver = InstagramReceiver()

        system_prompt = load_system_prompt()
        deps = AgentDependencies(config=cfg, system_prompt=system_prompt)
        graph = build_agent_graph(deps)

        class AgentInvoker:
            async def invoke(self, text: str, sender_id: str) -> str:
                messages = await history.load_as_langchain_messages(sender_id)
                from langchain_core.messages import HumanMessage
                messages.append(HumanMessage(content=text))
                result = await graph.ainvoke({"messages": messages})
                ai_msg = result["messages"][-1]
                
                content = ai_msg.content
                if isinstance(content, list):
                    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
                return str(content)

        processor = MessageProcessor(
            block_manager=block_mgr,
            debounce_stacker=debounce,
            agent_invoker=AgentInvoker(),
            chat_history=history,
            instagram_receiver=receiver,
            instagram_sender=sender,
            config=cfg,
        )

        await processor.process(payload)

    except Exception as exc:
        logger.error("process_message_failed", error=str(exc), exc_info=True)
    finally:
        if 'redis_conn' in dir():
            await redis_conn.aclose()


@app.function(image=image, secrets=[secrets])
@modal.fastapi_endpoint(method="GET")
async def webhook_get(request: Request) -> Response:
    """Meta webhook verification endpoint."""
    from execution.config import get_config
    from execution.webhook_handler import verify_webhook

    cfg = get_config()
    params = dict(request.query_params)
    challenge = verify_webhook(params, cfg)

    if challenge:
        return PlainTextResponse(content=challenge, status_code=200)
    return PlainTextResponse(content="Forbidden", status_code=403)


@app.function(image=image, secrets=[secrets])
@modal.fastapi_endpoint(method="POST")
async def webhook_post(request: Request) -> Response:
    """Instagram webhook POST handler — returns 200 immediately, processes in background."""
    body = await request.json()

    from execution.webhook_handler import parse_post_body
    if not parse_post_body(body):
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    await process_message.spawn.aio(body)

    return JSONResponse(content={"status": "ok"}, status_code=200)
