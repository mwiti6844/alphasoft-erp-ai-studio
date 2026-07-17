from __future__ import annotations

import httpx
import pytest

from app.clients.laravel import LaravelToolClient


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://laravel.test/api/internal/ai/mcp/tools/call")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_execute_tool_posts_mcp_tools_call_payload(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            calls.append({"url": url, "headers": headers, "json": json})
            return _FakeResponse(
                payload={
                    "data": {
                        "name": "inventory_balance",
                        "output": {"count": 2, "balances": []},
                        "summary": "2 rows",
                    },
                    "message": None,
                    "errors": None,
                }
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    client = LaravelToolClient(
        base_url="http://laravel.test",
        shared_secret="shared-secret",
        timeout_seconds=5,
    )

    output = await client.execute_tool(
        runtime_session_id="runtime-abc",
        domain="shop.localhost",
        tenant_id="tenant-1",
        user_id=42,
        session_id=7,
        tool_name="inventory_balance",
        tool_input={"search": "maize"},
    )

    assert output == {"count": 2, "balances": []}
    assert calls == [
        {
            "url": "http://laravel.test/api/internal/ai/mcp/tools/call",
            "headers": {
                "x-ai-runtime-token": "shared-secret",
                "accept": "application/json",
                "content-type": "application/json",
            },
            "json": {
                "runtime_session_id": "runtime-abc",
                "domain": "shop.localhost",
                "name": "inventory_balance",
                "arguments": {"search": "maize"},
                "tenant_id": "tenant-1",
                "user_id": 42,
                "session_id": 7,
            },
        }
    ]


@pytest.mark.asyncio
async def test_execute_tool_raises_on_http_error(monkeypatch: pytest.MonkeyPatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            return _FakeResponse(status_code=403, payload={"message": "Permission denied"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    client = LaravelToolClient(
        base_url="http://laravel.test",
        shared_secret="shared-secret",
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.execute_tool(
            runtime_session_id="runtime-abc",
            domain="shop.localhost",
            tenant_id="tenant-1",
            user_id=42,
            session_id=7,
            tool_name="inventory_balance",
            tool_input={},
        )
