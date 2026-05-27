"""Tests for MetaSkillEvolver (T9)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skill_evolution.config import Config
from skill_evolution.core.meta_evolver import MetaSkillEvolver, MetaEvolveResult
from skill_evolution.skill.schema import Skill


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def config() -> Config:
    return Config()


class TestMetaSkillEvolverInit:
    def test_creates_with_defaults(self, config: Config):
        evolver = MetaSkillEvolver(config)
        assert evolver.config is config

    def test_workspace_override(self, config: Config, workspace: Path):
        evolver = MetaSkillEvolver(config, workspace=workspace)
        assert evolver._workspace == workspace


class TestLoadMetaSkill:
    def test_loads_builtin(self, config: Config):
        evolver = MetaSkillEvolver(config)
        skill = evolver._load_meta_skill_as_skill("strategy_generation")
        assert "strategy" in skill.body.lower()

    def test_loads_workspace_override(self, config: Config, workspace: Path):
        meta_dir = workspace / "meta_skills"
        meta_dir.mkdir(parents=True)
        custom = Skill(body="Custom meta-skill content here.")
        custom.save(meta_dir / "strategy_generation.md")

        evolver = MetaSkillEvolver(config, workspace=workspace)
        skill = evolver._load_meta_skill_as_skill("strategy_generation")
        assert "Custom meta-skill" in skill.body

    def test_missing_raises(self, config: Config, workspace: Path):
        evolver = MetaSkillEvolver(config, workspace=workspace)
        with pytest.raises(FileNotFoundError, match="not found"):
            evolver._load_meta_skill_as_skill("nonexistent_meta_skill")


class TestScoreBaseline:
    def test_returns_score_map(self, config: Config):
        evolver = MetaSkillEvolver(config)
        scores = evolver.score_baseline("strategy_generation")
        assert isinstance(scores, dict)
        assert len(scores) > 0
        assert all(isinstance(v, float) for v in scores.values())


class TestTasksFromCases:
    def test_generates_tasks(self, config: Config):
        evolver = MetaSkillEvolver(config)
        from skill_evolution.meta_skills.testing.loader import load_builtin_suite
        cases = load_builtin_suite("strategy_generation")
        tasks = evolver._tasks_from_cases(cases)
        assert len(tasks) == min(5, len(cases))
        assert all("scenario" in t.lower() for t in tasks)


class TestBuildTestPrompt:
    def test_strategy_generation_prompt(self, config: Config):
        evolver = MetaSkillEvolver(config)
        from skill_evolution.meta_skills.testing.models import EvalCase
        case = EvalCase(
            id="test", meta_skill="strategy_generation",
            description="test", input_data={"task": "do X", "skill_text": "You are Y", "k": 3},
            expected={"k": 3},
        )
        prompt = evolver._build_test_prompt("strategy_generation", case)
        assert "do X" in prompt
        assert "You are Y" in prompt
        assert "3" in prompt

    def test_trajectory_comparison_prompt(self, config: Config):
        evolver = MetaSkillEvolver(config)
        from skill_evolution.meta_skills.testing.models import EvalCase
        case = EvalCase(
            id="test", meta_skill="trajectory_comparison",
            description="test",
            input_data={
                "skill_text": "Skill",
                "success_response": "OK",
                "failure_response": "FAIL",
            },
            expected={},
        )
        prompt = evolver._build_test_prompt("trajectory_comparison", case)
        assert "OK" in prompt
        assert "FAIL" in prompt
        assert "delta signals" in prompt.lower()


class TestMetaEvolveResult:
    def test_dataclass_fields(self):
        from skill_evolution.skill.regression_gate import GateVerdict
        result = MetaEvolveResult(
            target="strategy_generation",
            accepted=True,
            baseline_scores={"a": 0.5},
            candidate_scores={"a": 0.8},
            gate_verdict=GateVerdict(passed=True, summary="PASS: 1 improved"),
            version=2,
        )
        assert result.accepted
        assert result.version == 2
