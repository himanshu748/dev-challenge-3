from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.settings import Settings


class HireIQError(Exception):
    def __init__(self, detail: str, *, status_code: int = 500, extra: Optional[dict[str, Any]] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.extra = extra or {}


class AnthropicMCPClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.anthropic_base_url,
            timeout=settings.request_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def run_workflow(
        self,
        *,
        prompt: str,
        max_tokens: int,
        allowed_tools: list[str],
        system_prompt: str,
    ) -> dict[str, Any]:
        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": self.settings.anthropic_beta,
            "content-type": "application/json",
        }
        payload = {
            "model": self.settings.anthropic_model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "mcp_servers": [
                {
                    "type": "url",
                    "name": "notion",
                    "url": self.settings.notion_mcp_url,
                    "authorization_token": self.settings.notion_token,
                    "tool_configuration": {
                        "enabled": True,
                        "allowed_tools": allowed_tools,
                    },
                }
            ],
        }

        try:
            response = await self._client.post("/messages", json=payload, headers=headers)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise HireIQError("Anthropic request timed out.", status_code=504) from exc
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_message(exc.response)
            raise HireIQError(
                f"Anthropic API error: {detail}",
                status_code=502,
                extra={"provider_status_code": exc.response.status_code},
            ) from exc
        except httpx.HTTPError as exc:
            raise HireIQError("Anthropic request failed before a response was returned.", status_code=502) from exc

        return response.json()

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or "Unknown error"

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
        return response.text or "Unknown error"
