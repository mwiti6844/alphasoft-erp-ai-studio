from __future__ import annotations

from typing import Any

import httpx


class LaravelToolClient:
    def __init__(self, base_url: str, shared_secret: str, timeout_seconds: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.shared_secret = shared_secret
        self.timeout_seconds = timeout_seconds

    async def execute_tool(
        self,
        *,
        runtime_session_id: str,
        domain: str,
        tenant_id: str,
        user_id: int,
        session_id: int,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/api/internal/ai/mcp/tools/call",
                headers={
                    "x-ai-runtime-token": self.shared_secret,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={
                    "runtime_session_id": runtime_session_id,
                    "domain": domain,
                    "name": tool_name,
                    "arguments": tool_input,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "session_id": session_id,
                },
            )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "data" in payload:
            data = payload["data"]
            if isinstance(data, dict) and "output" in data and isinstance(data["output"], dict):
                return data["output"]
            if isinstance(data, dict):
                return data
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("Laravel returned a non-object tool response")

    async def list_tools(
        self,
        *,
        runtime_session_id: str,
        domain: str,
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/api/internal/ai/mcp/tools/list",
                headers={
                    "x-ai-runtime-token": self.shared_secret,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={
                    "runtime_session_id": runtime_session_id,
                    "domain": domain,
                },
            )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict) and isinstance(data.get("tools"), list):
            return data["tools"]
        return []
