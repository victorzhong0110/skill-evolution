"""LLM abstraction layer supporting Claude and OpenAI-compatible backends."""

from skill_evolution.llm.base import LLMBackend, LLMResponse
from skill_evolution.llm.factory import create_llm

__all__ = ["LLMBackend", "LLMResponse", "create_llm"]
