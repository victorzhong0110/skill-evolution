"""Anthropic Claude backend."""

from __future__ import annotations

import os

from anthropic import AsyncAnthropic

from skill_evolution.llm.base import LLMBackend, LLMResponse
from skill_evolution.llm.http_retry import (
    DEFAULT_BACKOFF_S,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_S,
    call_with_retry,
    clamp_max_retries,
)


class ClaudeBackend(LLMBackend):
    """Claude via Anthropic HTTP API, with bounded retries and a request timeout.

    SDK retries are disabled (``max_retries=0`` on the client) so only this
    layer retries — timeout / 429 / 5xx, up to ``max_retries`` extra attempts.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_s: float = DEFAULT_BACKOFF_S,
    ):
        super().__init__(model=model)
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = clamp_max_retries(max_retries)
        self.retry_backoff_s = retry_backoff_s
        self.client = AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            timeout=timeout_s,
            max_retries=0,
        )

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        async def _once() -> LLMResponse:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system if system else [],
                messages=messages,
            )
            return LLMResponse(
                content=resp.content[0].text if resp.content else "",
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                model=self.model,
                stop_reason=resp.stop_reason or "",
            )

        result = await call_with_retry(
            _once,
            max_retries=self.max_retries,
            backoff_s=self.retry_backoff_s,
        )
        self.usage.record(result)
        return result
