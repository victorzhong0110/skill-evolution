"""OpenAI-compatible backend (works with OpenAI, vLLM, Ollama, etc.)."""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from skill_evolution.llm.base import LLMBackend, LLMResponse
from skill_evolution.llm.http_retry import (
    DEFAULT_BACKOFF_S,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_S,
    call_with_retry,
    clamp_max_retries,
)


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible API backend with bounded retries and a request timeout.

    SDK retries are disabled (``max_retries=0`` on the client) so only this
    layer retries — timeout / 429 / 5xx, up to ``max_retries`` extra attempts.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_s: float = DEFAULT_BACKOFF_S,
    ):
        super().__init__(model=model)
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = clamp_max_retries(max_retries)
        self.retry_backoff_s = retry_backoff_s
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OpenAIBackend requires an API key: pass api_key or set OPENAI_API_KEY. "
                "Failing at init so misconfiguration surfaces before any LLM spend."
            )
        self.client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url,
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
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        async def _once() -> LLMResponse:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = resp.choices[0]
            usage = resp.usage
            return LLMResponse(
                content=choice.message.content or "",
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                model=self.model,
                stop_reason=choice.finish_reason or "",
            )

        result = await call_with_retry(
            _once,
            max_retries=self.max_retries,
            backoff_s=self.retry_backoff_s,
        )
        self.usage.record(result)
        return result
