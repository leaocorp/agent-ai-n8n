"""Tests for the get_service_detail tool builder in execution.agent_graph."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest

from execution.agent_graph import _build_get_service_detail_tool
from execution.config import Config


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal stand-in for httpx.Response used by the tool."""

    def __init__(
        self,
        *,
        json_data: Any = None,
        status_code: int = 200,
        text: str = "",
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://fake")
            response = httpx.Response(self.status_code, text=self.text, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=response,
            )


class FakeAsyncClient:
    """Captures POST calls and returns a configured response."""

    def __init__(
        self,
        *,
        response: FakeResponse | None = None,
        raise_exc: Exception | None = None,
        timeout: int | float | None = None,
    ) -> None:
        self._response = response
        self._raise_exc = raise_exc
        self.timeout = timeout
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._response is not None
        return self._response


@pytest.fixture
def service_config(test_config: Config) -> Config:
    """A Config with the Supabase fields populated for tool testing."""
    return replace(
        test_config,
        supabase_url="https://project.supabase.co",
        supabase_key="anon-key-123",
        establishment_id="estab-42",
    )


def _patch_async_client(monkeypatch: pytest.MonkeyPatch, fake: FakeAsyncClient) -> None:
    """Make httpx.AsyncClient(...) return our fake regardless of kwargs."""

    def factory(*args: Any, **kwargs: Any) -> FakeAsyncClient:
        fake.timeout = kwargs.get("timeout", fake.timeout)
        return fake

    monkeypatch.setattr(httpx, "AsyncClient", factory)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_tool_has_expected_name_and_arg(service_config: Config) -> None:
    tool = _build_get_service_detail_tool(service_config)
    assert tool.name == "get_service_detail"
    # The tool advertises its single string argument to the LLM.
    schema = tool.args_schema.model_json_schema() if hasattr(tool, "args_schema") else {}
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    assert "p_service_ia_id" in properties


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_stringified_payload_on_success(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    payload = {
        "service_id": "svc-1",
        "name": "Limpeza de Pele",
        "price": 250.0,
        "professionals": [{"id": "p1", "name": "Dra. Ana"}],
    }
    fake = FakeAsyncClient(response=FakeResponse(json_data=payload))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    result = await tool.ainvoke({"p_service_ia_id": "svc-1"})

    assert result == str(payload)


@pytest.mark.asyncio
async def test_posts_to_correct_supabase_rpc_url(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    await tool.ainvoke({"p_service_ia_id": "svc-99"})

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == (
        "https://project.supabase.co/rest/v1/rpc/get_service_with_professionals_by_ia_id"
    )


@pytest.mark.asyncio
async def test_sends_required_headers(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    await tool.ainvoke({"p_service_ia_id": "svc-1"})

    headers = fake.calls[0]["headers"]
    assert headers["apikey"] == "anon-key-123"
    assert headers["Authorization"] == "Bearer anon-key-123"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_sends_establishment_id_and_service_id_in_body(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(json_data={}))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    await tool.ainvoke({"p_service_ia_id": "svc-77"})

    body = fake.calls[0]["json"]
    assert body == {
        "p_establishment_id": "estab-42",
        "p_service_ia_id": "svc-77",
    }
    # Body must be JSON-serializable — guard against accidental non-serializable values.
    json.dumps(body)


@pytest.mark.asyncio
async def test_uses_client_timeout(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(json_data={}))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    await tool.ainvoke({"p_service_ia_id": "svc-1"})

    assert fake.timeout == 10


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_user_friendly_message_on_http_error(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(status_code=404, text="not found"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    result = await tool.ainvoke({"p_service_ia_id": "missing-id"})

    assert "Erro" in result
    assert "ID está correto" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 500, 502, 503])
async def test_handles_various_http_error_codes(
    monkeypatch: pytest.MonkeyPatch,
    service_config: Config,
    status_code: int,
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(status_code=status_code, text="boom"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    result = await tool.ainvoke({"p_service_ia_id": "svc-x"})

    assert isinstance(result, str)
    assert result.startswith("Erro")


@pytest.mark.asyncio
async def test_returns_generic_error_on_network_failure(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    fake = FakeAsyncClient(raise_exc=httpx.ConnectError("conn refused"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    result = await tool.ainvoke({"p_service_ia_id": "svc-1"})

    assert result == "Erro interno ao buscar os detalhes do serviço."


@pytest.mark.asyncio
async def test_returns_generic_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    fake = FakeAsyncClient(raise_exc=httpx.ReadTimeout("timed out"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    result = await tool.ainvoke({"p_service_ia_id": "svc-1"})

    assert result == "Erro interno ao buscar os detalhes do serviço."


@pytest.mark.asyncio
async def test_returns_generic_error_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    fake = FakeAsyncClient(raise_exc=RuntimeError("kaboom"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    result = await tool.ainvoke({"p_service_ia_id": "svc-1"})

    assert result == "Erro interno ao buscar os detalhes do serviço."


@pytest.mark.asyncio
async def test_no_tool_exception_leaks_to_caller(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    """The tool must always return a string — never raise — so the agent loop survives."""
    fake = FakeAsyncClient(raise_exc=ValueError("malformed json"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(service_config)
    result = await tool.ainvoke({"p_service_ia_id": "svc-1"})
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_url_reflects_config_changes(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    other_cfg = replace(service_config, supabase_url="https://other.supabase.co")
    fake = FakeAsyncClient(response=FakeResponse(json_data={}))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(other_cfg)
    await tool.ainvoke({"p_service_ia_id": "svc-1"})

    assert fake.calls[0]["url"].startswith("https://other.supabase.co/")


@pytest.mark.asyncio
async def test_establishment_id_reflects_config_changes(
    monkeypatch: pytest.MonkeyPatch, service_config: Config
) -> None:
    other_cfg = replace(service_config, establishment_id="estab-999")
    fake = FakeAsyncClient(response=FakeResponse(json_data={}))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_service_detail_tool(other_cfg)
    await tool.ainvoke({"p_service_ia_id": "svc-1"})

    assert fake.calls[0]["json"]["p_establishment_id"] == "estab-999"
