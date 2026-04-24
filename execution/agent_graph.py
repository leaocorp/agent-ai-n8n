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
    tools = [_build_encaminhamento_tool(deps.config)]

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
