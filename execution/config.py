from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Config:
    """Immutable application configuration."""

    # ==========================================
    # Meta / Instagram Configuration
    # ==========================================
    # Token de verificação usado na configuração inicial do webhook na Meta.
    meta_verify_token: str = ""
    # Token de acesso de longo prazo (Page Access Token) para chamar a Graph API.
    meta_page_access_token: str = ""
    # ID da página do Instagram (IG User ID) associado ao bot.
    meta_page_id: str = ""
    # ID do aplicativo da Meta no Facebook Developers (opcional, útil para lógicas de eco).
    meta_app_id: str = ""
    # URL base da Graph API da Meta (versão atualizada recomendada: v22.0).
    instagram_api_base: str = "https://graph.instagram.com/v22.0"

    # ==========================================
    # Modelos de Inteligência Artificial (LLMs)
    # ==========================================
    # Chave da API do Google AI Studio para usar os modelos Gemini.
    google_api_key: str = ""
    # Chave da API da OpenAI para modelos de fallback (ex: gpt-4o-mini).
    openai_api_key: str = ""
    # Modelo principal de alta velocidade e baixo custo.
    primary_model: str = "gemini-3-flash-preview"
    # Modelo reserva acionado automaticamente em caso de falha do principal.
    fallback_model: str = "gpt-5-mini"

    # ==========================================
    # Banco de Dados de Histórico (Supabase)
    # ==========================================
    # URL pública do projeto Supabase (REST API).
    supabase_url: str = ""
    # Chave anônima (anon key) ou de serviço (service role key) para acessar via REST.
    supabase_key: str = ""
    # String de conexão do banco Postgres (usada em algumas migrações ou conexões diretas).
    supabase_db_url: str = ""
    # Nome da tabela onde os históricos de chat (Human/AI) serão gravados.
    chat_history_table: str = "ias_chat_histories_drantonio"
    # Quantidade máxima de mensagens antigas carregadas para dar contexto ao modelo.
    context_window_length: int = 50

    # ==========================================
    # Cache e Gerenciamento de Estado (Redis)
    # ==========================================
    # URL de conexão do Redis (ex: redis://:senha@host:porta).
    redis_url: str = ""

    # ==========================================
    # Controle de Tempo (Debounce)
    # ==========================================
    # Segundos que o sistema aguarda novas mensagens antes de empacotar tudo e enviar para a IA.
    # Evita que a IA responda "Bom dia" separadamente da dúvida real do paciente.
    debounce_seconds: int = 15

    # ==========================================
    # Controle de Bloqueios (Tempo de Vida - TTL)
    # ==========================================
    # Segundos para manter IDs de mensagens cacheados (evita reprocessamento acidental).
    dedup_ttl: int = 30
    # Segundos de bloqueio após detectar um "eco" (atualmente não usado se o sistema identificar como eco da própria IA).
    echo_block_ttl: int = 180
    # Segundos que a IA deve silenciar caso um humano (atendente) envie uma mensagem (18000s = 5 horas).
    handoff_block_ttl: int = 18000

    # ==========================================
    # Listas de Controle de Acesso (ACL)
    # ==========================================
    # IDs de usuários (Instagram Scoped IDs) que o bot deve ignorar completamente.
    blocked_sender_ids: frozenset[str] = field(default_factory=frozenset)
    # IDs de administradores (podem executar comandos especiais se necessário).
    admin_sender_ids: frozenset[str] = field(default_factory=frozenset)

    # ==========================================
    # Integrações de Webhooks Externos (n8n / Outros)
    # ==========================================
    # Webhook acionado pela IA quando precisar encaminhar para agendamento manual.
    encaminhamento_url: str = "https://webhook.leaocorp.com.br/webhook/tool-encaminhamento-unita"
    # Webhook acionado silenciosamente (fire-and-forget) para rastrear envios bem-sucedidos na mensageria interna.
    mensageria_url: str = "https://webhook.leaocorp.com.br/webhook/send-by-ia-mensageria"


def get_config() -> Config:
    """Build Config from environment variables.

    Usage:
        cfg = get_config()
    """
    blocked = os.getenv("BLOCKED_SENDER_IDS", "")
    admin = os.getenv("ADMIN_SENDER_IDS", "")

    return Config(
        meta_verify_token=os.getenv("META_VERIFY_TOKEN", ""),
        meta_page_access_token=os.getenv("META_PAGE_ACCESS_TOKEN", ""),
        meta_page_id=os.getenv("META_PAGE_ID", "17841400753420214"),
        meta_app_id=os.getenv("META_APP_ID", ""),
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_key=os.getenv("SUPABASE_KEY", ""),
        supabase_db_url=os.getenv("SUPABASE_DB_URL", ""),
        redis_url=os.getenv("REDIS_URL", ""),
        blocked_sender_ids=frozenset(s.strip() for s in blocked.split(",") if s.strip()),
        admin_sender_ids=frozenset(s.strip() for s in admin.split(",") if s.strip()),
    )
