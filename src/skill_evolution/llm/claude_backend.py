"""Anthropic Claude backend."""

from __future__ import annotations

import os

from anthropic import AsyncAnthropic

from skill_evolution.llm.base import LLMBackend, LLMResponse


class ClaudeBackend(LLMBackend):
    """Claude via Anthropic API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str | None = None):
        super().__init__()
        self.model = model
        self.client = AsyncAnthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system if system else [],
            messages=messages,
        )
        result = LLMResponse(
            content=resp.content[0].text if resp.content else "",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=self.model,
            stop_reason=resp.stop_reason or "",
        )
        self.usage.record(result)
        return result
