from __future__ import annotations

import logging
from typing import Any, Optional

from huggingface_hub import AsyncInferenceClient

from app.core.settings import Settings

log = logging.getLogger("hireiq.hf")


class HireIQError(Exception):
    def __init__(
        self,
        detail: str,
        *,
        status_code: int = 500,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.extra = extra or {}


class HFService:
    """Async HuggingFace client for recruiting content generation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._hf = AsyncInferenceClient(
            model=settings.hf_model,
            token=settings.hf_api_key,
            timeout=settings.request_timeout_seconds,
        )

    async def close(self) -> None:
        await self._hf.close()

    async def generate_text(
        self, system: str, user_msg: str, *, max_tokens: int = 4096
    ) -> str:
        """Generate text via HuggingFace AsyncInferenceClient (streaming)."""
        if not self.settings.hf_api_key:
            raise HireIQError(
                "HF_API_KEY is not configured. Add it to .env before running AI-backed workflows.",
                status_code=400,
            )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]
        out = ""
        async for chunk in await self._hf.chat_completion(
            messages=messages, max_tokens=max_tokens, stream=True
        ):
            if chunk.choices:
                d = chunk.choices[0].delta
                if d.content:
                    out += d.content
        if not out.strip():
            raise HireIQError(
                "HuggingFace model returned no text response.", status_code=502
            )
        return out
