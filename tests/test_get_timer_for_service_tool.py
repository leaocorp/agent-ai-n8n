"""Tests for the get_timer_for_service tool builder in execution.agent_graph."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest

from execution.agent_graph import _build_get_timer_for_service_tool
from execution.config import Config


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeResponse:
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
def timer_config(test_config: Config) -> Config:
    return replace(
        test_config,
        supabase_url="https://project.supabase.co",
        supabase_key="anon-key-123",
        establishment_id="estab-42",
    )


def _patch_async_client(monkeypatch: pytest.MonkeyPatch, fake: FakeAsyncClient) -> None:
    def factory(*args: Any, **kwargs: Any) -> FakeAsyncClient:
        fake.timeout = kwargs.get("timeout", fake.timeout)
        return fake

    monkeypatch.setattr(httpx, "AsyncClient", factory)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_tool_has_expected_name_and_args(timer_config: Config) -> None:
    tool = _build_get_timer_for_service_tool(timer_config)
    assert tool.name == "get_timer_for_service"
    schema = tool.args_schema.model_json_schema() if hasattr(tool, "args_schema") else {}
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    assert "p_service_ia_ids" in properties
    assert "p_start_date" in properties


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_stringified_payload_on_success(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    payload = [
        {"slot": "2026-05-01T09:00:00", "professional_id": "p1"},
        {"slot": "2026-05-01T10:00:00", "professional_id": "p1"},
    ]
    fake = FakeAsyncClient(response=FakeResponse(json_data=payload))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    result = await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )

    assert result == str(payload)


@pytest.mark.asyncio
async def test_posts_to_correct_supabase_rpc_url(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )

    assert len(fake.calls) == 1
    assert fake.calls[0]["url"] == (
        "https://project.supabase.co/rest/v1/rpc/find_available_slots_v5"
    )


@pytest.mark.asyncio
async def test_sends_required_headers(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )

    headers = fake.calls[0]["headers"]
    assert headers["apikey"] == "anon-key-123"
    assert headers["Authorization"] == "Bearer anon-key-123"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_body_has_all_four_required_params(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    await tool.ainvoke(
        {
            "p_service_ia_ids": "{uuid-1,uuid-2}",
            "p_start_date": "2026-05-15",
        }
    )

    body = fake.calls[0]["json"]
    assert body == {
        "p_days_ahead": 7,
        "p_establishment_id": "estab-42",
        "p_service_ia_ids": "{uuid-1,uuid-2}",
        "p_start_date": "2026-05-15",
    }
    json.dumps(body)


@pytest.mark.asyncio
async def test_days_ahead_is_hardcoded_to_seven(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    """Per the n8n contract, the search window is fixed at 7 days."""
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert fake.calls[0]["json"]["p_days_ahead"] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ids",
    [
        "{uuid-1}",
        "{uuid-1,uuid-2}",
        "{uuid-1,uuid-2,uuid-3}",
    ],
)
async def test_passes_service_ids_verbatim(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config, ids: str
) -> None:
    """The Postgres array literal format must be forwarded untouched."""
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    await tool.ainvoke({"p_service_ia_ids": ids, "p_start_date": "2026-05-01"})

    assert fake.calls[0]["json"]["p_service_ia_ids"] == ids


@pytest.mark.asyncio
async def test_uses_client_timeout(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert fake.timeout == 10


@pytest.mark.asyncio
async def test_handles_empty_slots_response(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    """A valid query with no available slots must still return a string, not raise."""
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    result = await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert result == str([])


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_user_friendly_message_on_http_error(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(status_code=400, text="bad request"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    result = await tool.ainvoke(
        {"p_service_ia_ids": "{bad}", "p_start_date": "not-a-date"}
    )

    assert result.startswith("Erro")
    # The message hints at the two likely culprits.
    assert "data" in result.lower()
    assert "id" in result.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 500, 502, 503])
async def test_handles_various_http_error_codes(
    monkeypatch: pytest.MonkeyPatch,
    timer_config: Config,
    status_code: int,
) -> None:
    fake = FakeAsyncClient(response=FakeResponse(status_code=status_code, text="boom"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    result = await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert isinstance(result, str)
    assert result.startswith("Erro")


@pytest.mark.asyncio
async def test_returns_generic_error_on_network_failure(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(raise_exc=httpx.ConnectError("conn refused"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    result = await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert result == "Erro interno ao buscar os horários disponíveis na agenda."


@pytest.mark.asyncio
async def test_returns_generic_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(raise_exc=httpx.ReadTimeout("timed out"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    result = await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert result == "Erro interno ao buscar os horários disponíveis na agenda."


@pytest.mark.asyncio
async def test_returns_generic_error_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(raise_exc=RuntimeError("kaboom"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    result = await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert result == "Erro interno ao buscar os horários disponíveis na agenda."


@pytest.mark.asyncio
async def test_no_tool_exception_leaks_to_caller(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    fake = FakeAsyncClient(raise_exc=ValueError("malformed json"))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(timer_config)
    result = await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_url_reflects_config_changes(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    other_cfg = replace(timer_config, supabase_url="https://other.supabase.co")
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(other_cfg)
    await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert fake.calls[0]["url"].startswith("https://other.supabase.co/")


@pytest.mark.asyncio
async def test_establishment_id_reflects_config_changes(
    monkeypatch: pytest.MonkeyPatch, timer_config: Config
) -> None:
    other_cfg = replace(timer_config, establishment_id="estab-999")
    fake = FakeAsyncClient(response=FakeResponse(json_data=[]))
    _patch_async_client(monkeypatch, fake)

    tool = _build_get_timer_for_service_tool(other_cfg)
    await tool.ainvoke(
        {"p_service_ia_ids": "{uuid-1}", "p_start_date": "2026-05-01"}
    )
    assert fake.calls[0]["json"]["p_establishment_id"] == "estab-999"
