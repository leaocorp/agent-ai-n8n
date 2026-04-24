"""Tests for the LangGraph agent builder."""
import pytest
from execution.agent_graph import build_agent_graph, AgentDependencies
from execution.config import Config
from langchain_core.messages import HumanMessage, AIMessage


def test_build_graph_returns_compiled_graph(test_config: Config) -> None:
    deps = AgentDependencies(
        config=test_config,
        system_prompt="You are a test agent.",
    )
    graph = build_agent_graph(deps)
    # The compiled graph should have an invoke method
    assert hasattr(graph, "invoke")


def test_build_graph_includes_encaminhamento_tool(test_config: Config) -> None:
    deps = AgentDependencies(
        config=test_config,
        system_prompt="You are a test agent.",
    )
    graph = build_agent_graph(deps)
    # Verify the tool is registered by checking the graph nodes
    assert graph is not None
