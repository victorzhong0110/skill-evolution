"""OpenAI-compatible backend (works with OpenAI, vLLM, Ollama, etc.)."""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from skill_evolution.llm.base import LLMBackend, LLMResponse


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible API backend."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        super().__init__(model=model)
        self.model = model
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OpenAIBackend requires an API key: pass api_key or set OPENAI_API_KEY. "
                "Failing at init so misconfiguration surfaces before any LLM spend."
            )
        self.client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url,
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

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        usage = resp.usage

        result = LLMResponse(
            content=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self.model,
            stop_reason=choice.finish_reason or "",
        )
        self.usage.record(result)
        return result
