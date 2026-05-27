"""Tests for LLM abstraction — factory and usage tracking."""

from __future__ import annotations

import pytest

from skill_evolution.config import LLMConfig
from skill_evolution.llm.base import LLMResponse, TokenUsageTracker
from skill_evolution.llm.factory import create_llm


class TestTokenUsageTracker:
    def test_initial_state(self):
        tracker = TokenUsageTracker()
        assert tracker.total_input == 0
        assert tracker.total_output == 0
        assert tracker.calls == 0
        assert tracker.estimated_cost_usd == 0.0

    def test_record_accumulates(self):
        tracker = TokenUsageTracker()
        tracker.record(LLMResponse(content="a", input_tokens=100, output_tokens=50))
        tracker.record(LLMResponse(content="b", input_tokens=200, output_tokens=100))

        assert tracker.total_input == 300
        assert tracker.total_output == 150
        assert tracker.calls == 2

    def test_cost_calculation(self):
        tracker = TokenUsageTracker(
            _cost_per_input_mtok=3.0,
            _cost_per_output_mtok=15.0,
        )
        tracker.record(LLMResponse(content="x", input_tokens=1_000_000, output_tokens=100_000))

        assert tracker.estimated_cost_usd == pytest.approx(3.0 + 1.5)

    def test_summary_format(self):
        tracker = TokenUsageTracker()
        tracker.record(LLMResponse(content="x", input_tokens=500, output_tokens=100))
        summary = tracker.summary()

        assert "Calls: 1" in summary
        assert "500" in summary
        assert "100" in summary


class TestLLMResponse:
    def test_total_tokens(self):
        resp = LLMResponse(content="hi", input_tokens=100, output_tokens=50)
        assert resp.total_tokens == 150


class TestFactory:
    def test_create_claude_backend(self):
        cfg = LLMConfig(provider="claude", model="claude-sonnet-4-20250514")
        backend = create_llm(cfg)
        assert backend.__class__.__name__ == "ClaudeBackend"

    def test_create_openai_backend(self):
        cfg = LLMConfig(provider="openai", model="gpt-4o")
        backend = create_llm(cfg)
        assert backend.__class__.__name__ == "OpenAIBackend"

    def test_unknown_provider_raises(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMConfig(provider="unknown")  # type: ignore

    def test_default_config(self):
        backend = create_llm()
        assert backend.__class__.__name__ == "ClaudeBackend"
