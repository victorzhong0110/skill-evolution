"""Configuration management for skill-evolution."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM backend configuration."""

    provider: Literal["claude", "openai"] = "claude"
    model: str = "claude-sonnet-4-20250514"
    api_key: str | None = None  # Falls back to env var
    base_url: str | None = None  # For OpenAI-compatible endpoints
    temperature: float = 0.7
    max_tokens: int = 4096


class EvolutionConfig(BaseModel):
    """Evolution loop configuration."""

    num_strategies: int = Field(default=4, ge=1, le=8, description="K: diverse strategies per round")
    num_rounds: int = Field(default=2, ge=1, le=10, description="R: evolution rounds")
    budget_usd: float | None = Field(default=None, description="Max spend in USD; None = unlimited")
    auto_snapshot: bool = Field(default=True, description="Auto-snapshot skill after each round")


class AuditConfig(BaseModel):
    """Audit settings."""

    enabled: bool = True
    checks: list[str] = Field(
        default_factory=lambda: [
            "overfitting",
            "hardcoding",
            "silent_bypass",
            "consistency",
            "generalizability",
        ]
    )


class Config(BaseModel):
    """Top-level configuration."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    workspace_dir: Path = Field(default=Path(".skill-evolution"))

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Load config from YAML file, falling back to defaults."""
        if path and path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls.model_validate(data)
        return cls()

    def save(self, path: Path) -> None:
        """Save current config to YAML."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)
