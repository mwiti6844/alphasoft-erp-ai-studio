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
        tenant_id: str,
        user_id: int,
        session_id: int,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/api/internal/ai/tools/{tool_name}/execute",
                headers={
                    "x-ai-runtime-token": self.shared_secret,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "input": tool_input,
                },
            )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("Laravel returned a non-object tool response")
