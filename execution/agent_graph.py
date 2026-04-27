"""LangGraph agent — conversational AI with Gemini primary + GPT fallback.

Builds a ReAct-style agent with:
- System prompt loaded from directives/system_prompts/
- Tool: encaminhamento (forwards leads to team webhook)
- Fallback: Gemini → GPT-5-mini

Usage:
    deps = AgentDependencies(config=cfg, system_prompt=prompt_text)
    graph = build_agent_graph(deps)
    result = await graph.ainvoke({"messages": [HumanMessage(content="Oi")]})
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog
from langchain_core.messages import SystemMessage, BaseMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from execution.config import Config

logger = structlog.get_logger()


@dataclass
class AgentDependencies:
    """All dependencies the agent graph needs to be built."""

    config: Config
    system_prompt: str


def _build_encaminhamento_tool(config: Config) -> object:
    """Create the 'encaminhamento' tool for lead forwarding."""

    @tool
    async def encaminhamento(
        nome: str,
        identificador: str,
        motivo: str,
        resumo_curto: str,
        id_instagram: str = "",
    ) -> str:
        """Encaminha o lead para a equipe de atendimento.

        Args:
            nome: Nome do interessado
            identificador: WhatsApp (só números) ou 'instagram'
            motivo: 'agendamento' ou 'ebook'
            resumo_curto: 1-2 linhas com o que a paciente quer melhorar
            id_instagram: ID do Instagram do paciente
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    config.encaminhamento_url,
                    json={
                        "nome": nome,
                        "identificador": identificador,
                        "motivo": motivo,
                        "resumo_curto": resumo_curto,
                        "id_instagram": id_instagram,
                        "origem": "Dr. Antonio",
                    },
                )
                response.raise_for_status()
                logger.info("encaminhamento_sent", nome=nome, motivo=motivo)
                return "Lead encaminhado com sucesso para a equipe."
        except Exception as exc:
            logger.error("encaminhamento_failed", error=str(exc))
            return f"Erro ao encaminhar: {exc}"

    return encaminhamento


def _build_get_service_detail_tool(config: Config) -> object:
    """Create the 'get_service_detail' tool."""

    @tool
    async def get_service_detail(p_service_ia_id: str) -> str:
        """Retorna os detalhes de um serviço, que são: Preço, Profissionais, Instruções de preparação.

        ATENÇÃO: O que deve ser passado não é o nome do serviço e sim o ID (service_ia_id).
        Utilize a ferramenta de listar serviços caso não saiba o ID para encontrá-lo.

        Args:
            p_service_ia_id: O ID do serviço (em formato texto/string).
        """
        import httpx
        import structlog
        
        logger = structlog.get_logger()
        
        try:
            # Montando a URL do RPC do Supabase baseada na sua configuração
            url = f"{config.supabase_url}/rest/v1/rpc/get_service_with_professionals_by_ia_id"
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    url,
                    headers={
                        "apikey": config.supabase_key,
                        "Authorization": f"Bearer {config.supabase_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        # O ID do estabelecimento é fixo e vem das suas configurações
                        "p_establishment_id": config.establishment_id, 
                        # O ID do serviço é a IA que vai preencher
                        "p_service_ia_id": p_service_ia_id
                    }
                )
                response.raise_for_status()

                # Pegamos o JSON de resposta do Supabase
                dados_servico = response.json()
                
                logger.info("get_service_detail_success", service_id=p_service_ia_id)
                
                # Retornamos os dados em formato de texto para o LLM ler e interpretar
                return str(dados_servico)
                
        except httpx.HTTPStatusError as exc:
            logger.error("get_service_detail_http_error", status_code=exc.response.status_code, error=exc.response.text)
            return "Erro: Não foi possível encontrar os detalhes deste serviço. Verifique se o ID está correto."
        except Exception as exc:
            logger.error("get_service_detail_failed", error=str(exc))
            return "Erro interno ao buscar os detalhes do serviço."

    return get_service_detail

def _build_get_timer_for_service_tool(config: Config) -> object:
    """Create the 'get_timer_for_service' tool."""

    @tool
    async def get_timer_for_service(p_service_ia_ids: str, p_start_date: str) -> str:
        """Trás os horários disponíveis do(s) serviço(s), no intervalo de 7 dias a partir da data inicial.
        Só pode ser feita a pesquisa de mais de um serviço se TODOS tiverem o campo "can_be_combined" como true.

        Args:
            p_service_ia_ids: Lista dos uuids dos serviços para ser pesquisado. SEMPRE deve seguir o formato: "{uuid-do-serviço1,uuid-do-serviço2}".
            p_start_date: Data de início da pesquisa de horários, formato YYYY-MM-DD.
        """
        import httpx
        import structlog
        
        logger = structlog.get_logger()
        
        try:
            url = f"{config.supabase_url}/rest/v1/rpc/find_available_slots_v5"
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    url,
                    headers={
                        "apikey": config.supabase_key,
                        "Authorization": f"Bearer {config.supabase_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        # O n8n fixou em 7 dias de pesquisa
                        "p_days_ahead": 7, 
                        # ID do estabelecimento vem direto da configuração
                        "p_establishment_id": config.establishment_id,
                        # Parâmetros passados pela IA
                        "p_service_ia_ids": p_service_ia_ids,
                        "p_start_date": p_start_date
                    }
                )
                response.raise_for_status()
                
                dados_horarios = response.json()
                
                logger.info("get_timer_for_service_success", start_date=p_start_date)
                
                return str(dados_horarios)
                
        except httpx.HTTPStatusError as exc:
            logger.error("get_timer_for_service_http_error", status_code=exc.response.status_code, error=exc.response.text)
            return "Erro: Não foi possível buscar os horários disponíveis. Verifique se a data e os IDs dos serviços estão corretos."
        except Exception as exc:
            logger.error("get_timer_for_service_failed", error=str(exc))
            return "Erro interno ao buscar os horários disponíveis na agenda."

    return get_timer_for_service

def _build_get_timer_for_service_with_professional_tool(config: Config) -> object:
    """Create the 'get_timer_for_service_with_professional' tool."""

    @tool
    async def get_timer_for_service_with_professional(
        p_professional_id: str,
        p_service_ia_ids: str,
        p_start_date: str
    ) -> str:
        """Trás os horários disponíveis do(s) serviço(s), no intervalo de 7 dias a partir da data inicial, filtrado por um profissional específico.
        Só pode ser feita a pesquisa de mais de um serviço se TODOS tiverem o campo "can_be_combined" como true.

        Args:
            p_professional_id: UUID do profissional do serviço.
            p_service_ia_ids: Lista dos uuids dos serviços para ser pesquisado. SEMPRE deve seguir o formato: "{uuid-do-serviço1,uuid-do-serviço2}".
            p_start_date: Data de início da pesquisa de horários, formato YYYY-MM-DD.
        """
        import httpx
        import structlog
        
        logger = structlog.get_logger()
        
        try:
            url = f"{config.supabase_url}/rest/v1/rpc/find_available_slots_v5"
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    url,
                    headers={
                        "apikey": config.supabase_key,
                        "Authorization": f"Bearer {config.supabase_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        # Valor fixo do n8n
                        "p_days_ahead": 7,
                        # Valores extraídos da configuração
                        "p_establishment_id": config.establishment_id,
                        # Valores preenchidos pela Inteligência Artificial
                        "p_professional_id": p_professional_id,
                        "p_service_ia_ids": p_service_ia_ids,
                        "p_start_date": p_start_date
                    }
                )
                response.raise_for_status()
                
                dados_horarios = response.json()
                
                logger.info(
                    "get_timer_for_service_with_professional_success", 
                    professional_id=p_professional_id, 
                    start_date=p_start_date
                )
                
                return str(dados_horarios)
                
        except httpx.HTTPStatusError as exc:
            logger.error("get_timer_with_professional_http_error", status_code=exc.response.status_code, error=exc.response.text)
            return "Erro: Não foi possível buscar os horários disponíveis para este profissional. Verifique se os IDs e a data estão corretos."
        except Exception as exc:
            logger.error("get_timer_with_professional_failed", error=str(exc))
            return "Erro interno ao buscar os horários na agenda do profissional."

    return get_timer_for_service_with_professional

def _build_criar_agendamento_tool(config: Config) -> object:
    """Create the 'criar_agendamento' tool."""



def build_agent_graph(deps: AgentDependencies) -> object:
    """Build and compile the LangGraph ReAct agent.

    Returns a compiled graph ready for .invoke() or .ainvoke().
    """
    # Primary LLM: Gemini
    primary_llm = ChatGoogleGenerativeAI(
        model=deps.config.primary_model,
        google_api_key=deps.config.google_api_key,
        temperature=0.7,
    )

    # Fallback LLM: OpenAI
    fallback_llm = ChatOpenAI(
        model=deps.config.fallback_model,
        openai_api_key=deps.config.openai_api_key,
    )

    # Gemini with automatic fallback to GPT
    llm_with_fallback = primary_llm.with_fallbacks([fallback_llm])

    # Tools
    tools = [_build_encaminhamento_tool(deps.config),
            _build_get_service_detail_tool(deps.config),
            _build_get_timer_for_service_tool(deps.config),
            _build_get_timer_for_service_with_professional_tool(deps.config)]

    # Build the ReAct agent with system prompt
    graph = create_react_agent(
        model=llm_with_fallback,
        tools=tools,
        prompt=SystemMessage(content=deps.system_prompt),
    )

    logger.info("agent_graph_built", primary=deps.config.primary_model, fallback=deps.config.fallback_model)
    return graph


def load_system_prompt(prompt_path: str = "directives/system_prompts/dr_antonio_direct.md") -> str:
    """Load the system prompt from a markdown file.

    Usage:
        prompt = load_system_prompt()
    """
    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"System prompt not found at {path.absolute()}")
    return path.read_text(encoding="utf-8")
