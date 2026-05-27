"""Factory for creating LLM backends from config."""

from __future__ import annotations

from skill_evolution.config import LLMConfig
from skill_evolution.llm.base import LLMBackend


def create_llm(config: LLMConfig | None = None) -> LLMBackend:
    """Create an LLM backend from config."""
    if config is None:
        from skill_evolution.config import LLMConfig
        config = LLMConfig()

    if config.provider == "bridge":
        from skill_evolution.llm.bridge_backend import BridgeBackend
        return BridgeBackend(model=config.model)
    elif config.provider == "cli":
        from skill_evolution.llm.cli_backend import CliLLMBackend
        return CliLLMBackend(model=config.model)
    elif config.provider == "claude":
        from skill_evolution.llm.claude_backend import ClaudeBackend
        return ClaudeBackend(model=config.model, api_key=config.api_key)
    elif config.provider == "openai":
        from skill_evolution.llm.openai_backend import OpenAIBackend
        return OpenAIBackend(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
