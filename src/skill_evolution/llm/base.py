"""Abstract LLM interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Unified response from any LLM backend."""

    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_reason: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TokenUsageTracker:
    """Tracks cumulative token usage and estimated cost."""

    total_input: int = 0
    total_output: int = 0
    calls: int = 0
    _cost_per_input_mtok: float = 3.0  # Default: Claude Sonnet pricing
    _cost_per_output_mtok: float = 15.0

    def record(self, resp: LLMResponse) -> None:
        self.total_input += resp.input_tokens
        self.total_output += resp.output_tokens
        self.calls += 1

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.total_input * self._cost_per_input_mtok / 1_000_000
            + self.total_output * self._cost_per_output_mtok / 1_000_000
        )

    def summary(self) -> str:
        return (
            f"Calls: {self.calls} | "
            f"Tokens: {self.total_input:,} in + {self.total_output:,} out | "
            f"Est. cost: ${self.estimated_cost_usd:.4f}"
        )


class LLMBackend(ABC):
    """Abstract base for LLM backends."""

    def __init__(self) -> None:
        self.usage = TokenUsageTracker()

    @abstractmethod
    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a completion request and return unified response."""
        ...

    async def ask(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Convenience: single-turn question."""
        messages = [{"role": "user", "content": prompt}]
        return await self.complete(system, messages, temperature, max_tokens)
