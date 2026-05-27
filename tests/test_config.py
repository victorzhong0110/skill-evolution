"""Tests for configuration loading and saving."""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_evolution.config import AuditConfig, Config, EvolutionConfig, LLMConfig


class TestLLMConfig:
    def test_defaults(self):
        cfg = LLMConfig()
        assert cfg.provider == "claude"
        assert "claude" in cfg.model
        assert cfg.temperature == 0.7
        assert cfg.api_key is None

    def test_openai_provider(self):
        cfg = LLMConfig(provider="openai", model="gpt-4o")
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"


class TestEvolutionConfig:
    def test_defaults(self):
        cfg = EvolutionConfig()
        assert cfg.num_strategies == 4
        assert cfg.num_rounds == 2
        assert cfg.budget_usd is None
        assert cfg.auto_snapshot is True

    def test_validation_bounds(self):
        with pytest.raises(Exception):
            EvolutionConfig(num_strategies=0)
        with pytest.raises(Exception):
            EvolutionConfig(num_strategies=9)
        with pytest.raises(Exception):
            EvolutionConfig(num_rounds=0)
        with pytest.raises(Exception):
            EvolutionConfig(num_rounds=11)


class TestConfig:
    def test_defaults(self):
        cfg = Config()
        assert cfg.llm.provider == "claude"
        assert cfg.evolution.num_rounds == 2
        assert cfg.audit.enabled is True

    def test_save_and_load(self, tmp_path: Path):
        original = Config(
            llm=LLMConfig(provider="openai", model="gpt-4o"),
            evolution=EvolutionConfig(num_rounds=5, num_strategies=6),
        )
        path = tmp_path / "config.yaml"
        original.save(path)

        loaded = Config.load(path)
        assert loaded.llm.provider == "openai"
        assert loaded.llm.model == "gpt-4o"
        assert loaded.evolution.num_rounds == 5
        assert loaded.evolution.num_strategies == 6

    def test_load_nonexistent_returns_defaults(self):
        cfg = Config.load(Path("/nonexistent/path.yaml"))
        assert cfg.llm.provider == "claude"

    def test_load_none_returns_defaults(self):
        cfg = Config.load(None)
        assert cfg.llm.provider == "claude"

    def test_audit_config_defaults(self):
        cfg = AuditConfig()
        assert "overfitting" in cfg.checks
        assert "hardcoding" in cfg.checks
        assert len(cfg.checks) == 5
