"""Tests for bridge_auto_respond.py — regression coverage for classify_request,
DEFAULT_STRATEGY parsing, and topic template validity."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
META_SKILLS_DIR = ROOT / "src" / "skill_evolution" / "meta_skills"

sys.path.insert(0, str(SCRIPTS_DIR))
import bridge_auto_respond as bar  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from skill_evolution.core.explorer import Explorer, Strategy  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_meta_skill_text(name: str) -> str:
    """Load raw text of a meta-skill markdown file."""
    path = META_SKILLS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def _make_request(system: str, user_content: str = "") -> dict:
    return {
        "system": system,
        "messages": [{"content": user_content}],
    }


# ── 1. classify_request: all 5 types via real meta-skill prompts ────────────

class TestClassifyWithRealMetaSkills:
    """Verify classify_request identifies all 5 types using actual meta-skill
    system prompts loaded from src/skill_evolution/meta_skills/*.md."""

    def test_strategy_generation(self):
        system = _load_meta_skill_text("strategy_generation")
        req = _make_request(system)
        assert bar.classify_request(req) == "strategy_generation"

    def test_strategy_generation_via_user_message(self):
        req = _make_request(
            system="You help with strategies.",
            user_content="Generate exactly 3 diverse strategies for this task.",
        )
        assert bar.classify_request(req) == "strategy_generation"

    def test_comparator(self):
        system = _load_meta_skill_text("trajectory_comparison")
        req = _make_request(system)
        assert bar.classify_request(req) == "comparator"

    def test_patcher(self):
        system = _load_meta_skill_text("skill_patch")
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"

    def test_auditor(self):
        system = _load_meta_skill_text("skill_audit")
        req = _make_request(system)
        assert bar.classify_request(req) == "auditor"

    def test_executor(self):
        system = "You are an AI agent executing a task. Follow the strategy."
        req = _make_request(system)
        assert bar.classify_request(req) == "executor"

    def test_executor_via_execution_trace(self):
        system = "Produce an execution trace of your work."
        req = _make_request(system)
        assert bar.classify_request(req) == "executor"


# ── 2. Patcher must NOT be misclassified as comparator ──────────────────────

class TestPatcherNotMisclassified:
    """Regression: the patcher system prompt contains 'delta signals' which
    previously matched the comparator check.  Patcher must win."""

    def test_patcher_with_real_prompt(self):
        system = _load_meta_skill_text("skill_patch")
        assert "delta signal" in system.lower(), (
            "Precondition: patcher prompt must mention 'delta signal'"
        )
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"

    def test_patcher_with_delta_signal_and_patch_keyword(self):
        system = "Apply patch based on delta signals from comparison."
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"

    def test_comparator_requires_no_patch_keyword(self):
        system = "Analyze delta signals between trajectories."
        req = _make_request(system)
        assert bar.classify_request(req) == "comparator"

    def test_precision_skill_editor_routes_to_patcher(self):
        system = "You are a precision skill editor."
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"

    def test_updated_body_marker_routes_to_patcher(self):
        system = "Output in ===UPDATED_BODY=== format."
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"


# ── 3. DEFAULT_STRATEGY parses into 3 valid strategies ─────────────────────

class TestDefaultStrategyParsing:
    """DEFAULT_STRATEGY must use ===STRATEGY N=== markers and parse into
    exactly 3 Strategy objects via Explorer._parse_strategies."""

    def test_has_strategy_markers(self):
        for i in range(1, 4):
            assert f"===STRATEGY {i}===" in bar.DEFAULT_STRATEGY

    def test_parses_into_three_strategies(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.DEFAULT_STRATEGY)
        assert len(strategies) == 3

    def test_parsed_strategies_have_names(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.DEFAULT_STRATEGY)
        for s in strategies:
            assert s.name, f"Strategy {s.id} has no name"
            assert s.name != f"Strategy {s.id}", (
                f"Strategy {s.id} fell back to default name"
            )

    def test_parsed_strategies_have_descriptions(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.DEFAULT_STRATEGY)
        for s in strategies:
            assert s.description, f"Strategy {s.id} has no description"

    def test_parsed_strategies_have_approaches(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.DEFAULT_STRATEGY)
        for s in strategies:
            assert s.approach, f"Strategy {s.id} has no approach"


# ── 4. All 7 topic templates parse correctly ────────────────────────────────

EXPECTED_TOPICS = [
    "dedup",
    "credibility",
    "opinion_vs_event",
    "scoring_formula",
    "noise_floor",
    "source_independence",
    "priority_events",
]


class TestTopicTemplates:
    """Each of the 7 topic templates must be present in STRATEGY_TEMPLATES
    and parse into exactly 3 strategies via Explorer._parse_strategies."""

    @pytest.mark.parametrize("topic", EXPECTED_TOPICS)
    def test_template_exists(self, topic: str):
        assert topic in bar.STRATEGY_TEMPLATES

    @pytest.mark.parametrize("topic", EXPECTED_TOPICS)
    def test_template_has_strategy_markers(self, topic: str):
        text = bar.STRATEGY_TEMPLATES[topic]
        for i in range(1, 4):
            assert f"===STRATEGY {i}===" in text, (
                f"Topic '{topic}' missing ===STRATEGY {i}=== marker"
            )

    @pytest.mark.parametrize("topic", EXPECTED_TOPICS)
    def test_template_parses_into_three_strategies(self, topic: str):
        explorer = Explorer.__new__(Explorer)
        text = bar.STRATEGY_TEMPLATES[topic]
        strategies = explorer._parse_strategies(text)
        assert len(strategies) == 3, (
            f"Topic '{topic}' parsed into {len(strategies)} strategies, expected 3"
        )

    @pytest.mark.parametrize("topic", EXPECTED_TOPICS)
    def test_template_strategies_have_names(self, topic: str):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.STRATEGY_TEMPLATES[topic])
        for s in strategies:
            assert s.name and s.name != f"Strategy {s.id}", (
                f"Topic '{topic}' strategy {s.id} missing a real name"
            )

    def test_no_unexpected_templates(self):
        assert set(bar.STRATEGY_TEMPLATES.keys()) == set(EXPECTED_TOPICS)
