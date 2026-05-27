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


class TestMetaSkillOutputPath:
    def test_creates_directory(self, config: Config, workspace: Path):
        evolver = MetaSkillEvolver(config, workspace=workspace)
        path = evolver._meta_skill_output_path("strategy_generation")
        assert path.parent.exists()
        assert path.name == "strategy_generation.md"

    def test_returns_workspace_path(self, config: Config, workspace: Path):
        evolver = MetaSkillEvolver(config, workspace=workspace)
        path = evolver._meta_skill_output_path("test")
        assert str(workspace) in str(path)


class TestGeneratePlaceholder:
    def test_returns_empty_string(self, config: Config):
        from skill_evolution.meta_skills.testing.models import EvalCase
        case = EvalCase(id="t", meta_skill="x", description="d", input_data={}, expected={})
        result = MetaSkillEvolver._generate_placeholder_output("x", case)
        assert result == ""


class TestPrintScoreTable:
    def test_runs_without_error(self):
        from skill_evolution.skill.regression_gate import GateVerdict
        verdict = GateVerdict(
            passed=True,
            improved=["case-1"],
            regressed=["case-3"],
            unchanged=["case-2"],
            summary="test",
        )
        MetaSkillEvolver._print_score_table(
            {"case-1": 0.5, "case-2": 0.7, "case-3": 0.9},
            {"case-1": 0.8, "case-2": 0.7, "case-3": 0.6},
            verdict,
        )

    def test_handles_new_cases(self):
        from skill_evolution.skill.regression_gate import GateVerdict
        verdict = GateVerdict(
            passed=True, new_cases=["case-new"], summary="test",
        )
        MetaSkillEvolver._print_score_table(
            {"case-1": 0.5},
            {"case-1": 0.5, "case-new": 0.8},
            verdict,
        )


class TestFallbackPrompt:
    def test_unknown_meta_skill_prompt(self, config: Config):
        from skill_evolution.meta_skills.testing.models import EvalCase
        evolver = MetaSkillEvolver(config)
        case = EvalCase(
            id="t", meta_skill="unknown_type", description="d",
            input_data={"some": "data"}, expected={},
        )
        prompt = evolver._build_test_prompt("unknown_type", case)
        assert "Execute this test case" in prompt


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

    def test_default_version_is_none(self):
        from skill_evolution.skill.regression_gate import GateVerdict
        result = MetaEvolveResult(
            target="test",
            accepted=False,
            baseline_scores={},
            candidate_scores={},
            gate_verdict=GateVerdict(passed=False, summary="FAIL"),
        )
        assert result.version is None
