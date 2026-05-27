"""Integration tests for the EvolutionPipeline with mock LLM (T6).

Tests the full pipeline flow end-to-end without real LLM calls.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from skill_evolution.config import Config
from skill_evolution.core.auditor import Auditor
from skill_evolution.core.comparator import Comparator
from skill_evolution.core.explorer import Explorer
from skill_evolution.core.patcher import Patcher
from skill_evolution.core.pipeline import EvolutionPipeline, EvolutionReport, RoundReport
from skill_evolution.evaluation.evaluator import EvalResult, KeywordEvaluator
from skill_evolution.runner.executor import TaskExecutor, TaskOutcome
from skill_evolution.skill.schema import Skill
from tests.conftest import (
    AUDITOR_FAIL,
    AUDITOR_PASS,
    COMPARATOR_NO_SIGNALS,
    COMPARATOR_ONE_SIGNAL,
    PATCHER_RESPONSE,
    MockLLM,
    make_explorer_response,
)


def _make_skill() -> Skill:
    return Skill.from_markdown(
        "---\nname: test-skill\nversion: 1\ndomain: testing\n---\n\n"
        "# Test Skill\n\nThis is a test skill for integration testing.\n"
    )


def _build_pipeline(
    tmp_path: Path,
    responder=None,
    audit_enabled: bool = True,
) -> EvolutionPipeline:
    """Build an EvolutionPipeline with a MockLLM injected everywhere."""
    config = Config(
        workspace_dir=tmp_path,
        evolution={"num_strategies": 2, "num_rounds": 1},
        audit={"enabled": audit_enabled},
    )
    llm = MockLLM(responder=responder, default="default mock response")
    pipeline = EvolutionPipeline.__new__(EvolutionPipeline)
    pipeline.config = config
    pipeline._workspace = tmp_path
    pipeline.llm = llm
    pipeline.explorer = Explorer(llm, workspace=tmp_path)
    pipeline.executor = TaskExecutor(llm)
    pipeline.comparator = Comparator(llm, workspace=tmp_path)
    pipeline.patcher = Patcher(llm, workspace=tmp_path)
    pipeline.auditor = Auditor(MockLLM(responder=responder, default="default mock"), workspace=tmp_path)
    pipeline.evaluator = KeywordEvaluator()
    return pipeline


class TestRoundReport:
    def test_round_report_fields(self):
        r = RoundReport(
            round_num=1,
            strategies_generated=8,
            trajectories_total=8,
            trajectories_success=5,
            trajectories_failure=3,
            signals_extracted=2,
            audit_passed=True,
            changelog="Updated body",
            cost_estimate=0.05,
        )
        assert r.round_num == 1
        assert r.strategies_generated == 8
        assert r.trajectories_success == 5

    def test_round_report_defaults(self):
        r = RoundReport(
            round_num=1,
            strategies_generated=0,
            trajectories_total=0,
            trajectories_success=0,
            trajectories_failure=0,
            signals_extracted=0,
            audit_passed=True,
        )
        assert r.changelog == ""
        assert r.cost_estimate == 0.0


class TestEvolutionReport:
    def test_empty_report_summary(self):
        r = EvolutionReport(skill_name="test")
        s = r.summary()
        assert "test" in s
        assert "Rounds completed: 0" in s

    def test_report_with_rounds(self):
        r = EvolutionReport(
            skill_name="my-skill",
            rounds=[
                RoundReport(1, 4, 4, 3, 1, 2, True, "changes", 0.01),
                RoundReport(2, 4, 4, 4, 0, 0, True, "", 0.02),
            ],
            total_cost=0.03,
        )
        s = r.summary()
        assert "my-skill" in s
        assert "Round 1" in s
        assert "Round 2" in s
        assert "$0.0300" in s

    def test_report_na_success_rate(self):
        r = EvolutionReport(
            skill_name="test",
            rounds=[RoundReport(1, 0, 0, 0, 0, 0, True)],
        )
        assert "N/A" in r.summary()


class TestPipelineInit:
    def test_default_evaluator_is_keyword(self, tmp_path: Path):
        config = Config(workspace_dir=tmp_path)
        with patch("skill_evolution.core.pipeline.create_llm") as mock_create:
            mock_create.return_value = MockLLM()
            pipeline = EvolutionPipeline(config, workspace=tmp_path)
            assert isinstance(pipeline.evaluator, KeywordEvaluator)

    def test_custom_evaluator_class(self, tmp_path: Path):
        config = Config(
            workspace_dir=tmp_path,
            evolution={
                "evaluator_class": "skill_evolution.evaluation.evaluator.KeywordEvaluator"
            },
        )
        with patch("skill_evolution.core.pipeline.create_llm") as mock_create:
            mock_create.return_value = MockLLM()
            pipeline = EvolutionPipeline(config, workspace=tmp_path)
            assert isinstance(pipeline.evaluator, KeywordEvaluator)


class TestPipelineNoSignals:
    """Pipeline round where comparator finds no signals — skill should be unchanged."""

    def test_no_signals_round(self, tmp_path: Path):
        call_count = {"n": 0}

        def responder(system: str, prompt: str) -> str:
            call_count["n"] += 1
            if "diverse strategies" in prompt.lower() or "generate exactly" in prompt.lower():
                return make_explorer_response(2)
            if "compare" in system.lower() or "delta signal" in system.lower():
                return COMPARATOR_NO_SIGNALS
            return "Executed task successfully"

        pipeline = _build_pipeline(tmp_path, responder=responder, audit_enabled=False)
        skill = _make_skill()
        original_hash = skill.content_hash

        result_skill, report = asyncio.run(
            pipeline.evolve(skill, ["Write a test function"])
        )
        assert report.skill_name == "test-skill"
        assert len(report.rounds) == 1
        assert report.rounds[0].signals_extracted == 0
        assert result_skill.content_hash == original_hash


class TestPipelineWithSignals:
    """Pipeline round where comparator finds signals and patcher applies them."""

    def test_signals_applied_audit_pass(self, tmp_path: Path):
        def responder(system: str, prompt: str) -> str:
            if "diverse strategies" in prompt.lower() or "generate exactly" in prompt.lower():
                return make_explorer_response(2)
            if "delta signals to apply" in prompt.lower():
                return PATCHER_RESPONSE
            if "audit this skill" in prompt.lower():
                return AUDITOR_PASS
            if "compare" in system.lower() or "delta signal" in system.lower():
                return COMPARATOR_ONE_SIGNAL
            return "Executed task successfully"

        pipeline = _build_pipeline(tmp_path, responder=responder, audit_enabled=True)
        skill = _make_skill()
        original_hash = skill.content_hash

        result_skill, report = asyncio.run(
            pipeline.evolve(skill, ["Implement error handling"])
        )
        assert len(report.rounds) == 1
        assert report.rounds[0].signals_extracted >= 1
        assert report.rounds[0].audit_passed is True
        assert result_skill.content_hash != original_hash
        assert "error handling" in result_skill.body.lower()

    def test_signals_applied_audit_fail_rollback(self, tmp_path: Path):
        def responder(system: str, prompt: str) -> str:
            if "diverse strategies" in prompt.lower() or "generate exactly" in prompt.lower():
                return make_explorer_response(2)
            if "delta signals to apply" in prompt.lower():
                return PATCHER_RESPONSE
            if "audit this skill" in prompt.lower():
                return AUDITOR_FAIL
            if "compare" in system.lower() or "delta signal" in system.lower():
                return COMPARATOR_ONE_SIGNAL
            return "Executed task successfully"

        pipeline = _build_pipeline(tmp_path, responder=responder, audit_enabled=True)
        skill = _make_skill()
        original_hash = skill.content_hash

        result_skill, report = asyncio.run(
            pipeline.evolve(skill, ["Implement error handling"])
        )
        assert len(report.rounds) == 1
        assert report.rounds[0].audit_passed is False
        assert result_skill.content_hash == original_hash


class TestPipelineMultipleRounds:
    def test_two_rounds(self, tmp_path: Path):
        config = Config(
            workspace_dir=tmp_path,
            evolution={"num_strategies": 2, "num_rounds": 2},
            audit={"enabled": False},
        )

        def responder(system: str, prompt: str) -> str:
            if "diverse strategies" in prompt.lower() or "generate exactly" in prompt.lower():
                return make_explorer_response(2)
            if "delta signals to apply" in prompt.lower():
                return PATCHER_RESPONSE
            if "compare" in system.lower() or "delta signal" in system.lower():
                return COMPARATOR_ONE_SIGNAL
            return "Executed task"

        llm = MockLLM(responder=responder)
        pipeline = EvolutionPipeline.__new__(EvolutionPipeline)
        pipeline.config = config
        pipeline._workspace = tmp_path
        pipeline.llm = llm
        pipeline.explorer = Explorer(llm, workspace=tmp_path)
        pipeline.executor = TaskExecutor(llm)
        pipeline.comparator = Comparator(llm, workspace=tmp_path)
        pipeline.patcher = Patcher(llm, workspace=tmp_path)
        pipeline.auditor = Auditor(MockLLM(responder=responder), workspace=tmp_path)
        pipeline.evaluator = KeywordEvaluator()

        skill = _make_skill()
        result_skill, report = asyncio.run(
            pipeline.evolve(skill, ["Add logging"])
        )
        assert len(report.rounds) == 2
        assert report.total_cost >= 0.0

    def test_budget_exhaustion_stops_early(self, tmp_path: Path):
        config = Config(
            workspace_dir=tmp_path,
            evolution={"num_strategies": 2, "num_rounds": 5, "budget_usd": 0.0001},
            audit={"enabled": False},
        )

        def responder(system: str, prompt: str) -> str:
            if "diverse strategies" in prompt.lower() or "generate exactly" in prompt.lower():
                return make_explorer_response(2)
            if "compare" in system.lower() or "delta signal" in system.lower():
                return COMPARATOR_NO_SIGNALS
            return "x" * 10000  # long response to burn tokens

        llm = MockLLM(responder=responder)
        pipeline = EvolutionPipeline.__new__(EvolutionPipeline)
        pipeline.config = config
        pipeline._workspace = tmp_path
        pipeline.llm = llm
        pipeline.explorer = Explorer(llm, workspace=tmp_path)
        pipeline.executor = TaskExecutor(llm)
        pipeline.comparator = Comparator(llm, workspace=tmp_path)
        pipeline.patcher = Patcher(llm, workspace=tmp_path)
        pipeline.auditor = Auditor(MockLLM(responder=responder), workspace=tmp_path)
        pipeline.evaluator = KeywordEvaluator()

        skill = _make_skill()
        _, report = asyncio.run(
            pipeline.evolve(skill, ["test"])
        )
        assert len(report.rounds) < 5


class TestPipelineAuditFindingsToSignals:
    def test_converts_fail_findings(self):
        from skill_evolution.core.auditor import AuditFinding, AuditReport, AuditSeverity

        report = AuditReport(
            findings=[
                AuditFinding("overfitting", AuditSeverity.FAIL, "Too specific", "Generalize"),
                AuditFinding("consistency", AuditSeverity.WARNING, "Minor issue", "Align"),
                AuditFinding("hardcoding", AuditSeverity.PASS, "OK", ""),
            ],
            overall=AuditSeverity.FAIL,
            summary="Issues found",
        )
        signals = EvolutionPipeline._audit_findings_to_signals(report)
        assert len(signals) == 2
        assert signals[0].category == "wrong_approach"
        assert signals[0].confidence == 0.9
        assert signals[1].category == "edge_case"
        assert signals[1].confidence == 0.6


class TestExecutorIntegration:
    """Integration tests for TaskExecutor with mock LLM."""

    def test_successful_execution(self):
        from skill_evolution.core.explorer import Strategy

        llm = MockLLM(default="Here is the complete solution with all steps.")
        executor = TaskExecutor(llm)
        strategy = Strategy(id=1, name="Direct", description="Direct approach", approach="Step 1")

        trajectory = asyncio.run(
            executor.execute("Write a function", "# Skill", strategy)
        )
        assert trajectory.response == "Here is the complete solution with all steps."
        assert trajectory.outcome == TaskOutcome.PARTIAL
        assert trajectory.tokens_used > 0
        assert llm.usage.calls == 1

    def test_execution_error_handled(self):
        from skill_evolution.core.explorer import Strategy

        async def failing_complete(system, messages, temperature=0.7, max_tokens=4096):
            raise RuntimeError("API timeout")

        llm = MockLLM()
        llm.complete = failing_complete
        executor = TaskExecutor(llm)
        strategy = Strategy(id=1, name="Fail", description="", approach="")

        trajectory = asyncio.run(
            executor.execute("test", "skill", strategy)
        )
        assert trajectory.outcome == TaskOutcome.FAILURE
        assert "API timeout" in trajectory.outcome_reason


class TestExplorerIntegration:
    """Integration tests for Explorer with mock LLM."""

    def test_generates_strategies(self):
        llm = MockLLM(default=make_explorer_response(3))
        explorer = Explorer(llm)
        strategies = asyncio.run(
            explorer.generate_strategies("Write a test", "# Skill", k=3)
        )
        assert len(strategies) == 3
        assert strategies[0].name == "Strategy-1"
        assert strategies[2].name == "Strategy-3"

    def test_empty_response_returns_no_strategies(self):
        llm = MockLLM(default="No strategies here.")
        explorer = Explorer(llm)
        strategies = asyncio.run(
            explorer.generate_strategies("task", "skill", k=2)
        )
        assert strategies == []


class TestComparatorIntegration:
    """Integration tests for Comparator async methods with mock LLM."""

    def _make_trajectory(self, outcome: TaskOutcome, response: str = "test") -> "Trajectory":
        from skill_evolution.core.explorer import Strategy
        from skill_evolution.runner.executor import Trajectory

        return Trajectory(
            task_description="test task",
            strategy=Strategy(1, "S1", "desc", "approach"),
            skill_text="skill",
            response=response,
            outcome=outcome,
            outcome_reason="test",
        )

    def test_empty_trajectories_returns_empty(self):
        llm = MockLLM()
        comparator = Comparator(llm)
        signals = asyncio.run(comparator.compare([], "skill text"))
        assert signals == []
        assert llm.usage.calls == 0

    def test_contrastive_analysis(self):
        llm = MockLLM(default=COMPARATOR_ONE_SIGNAL)
        comparator = Comparator(llm)
        trajectories = [
            self._make_trajectory(TaskOutcome.SUCCESS),
            self._make_trajectory(TaskOutcome.FAILURE),
        ]
        signals = asyncio.run(comparator.compare(trajectories, "skill text"))
        assert len(signals) == 1
        assert signals[0].category == "missing_knowledge"

    def test_all_success_efficiency_analysis(self):
        llm = MockLLM(default=COMPARATOR_NO_SIGNALS)
        comparator = Comparator(llm)
        trajectories = [
            self._make_trajectory(TaskOutcome.SUCCESS),
            self._make_trajectory(TaskOutcome.SUCCESS),
        ]
        signals = asyncio.run(comparator.compare(trajectories, "skill text"))
        assert signals == []

    def test_all_failure_analysis(self):
        llm = MockLLM(default=COMPARATOR_ONE_SIGNAL)
        comparator = Comparator(llm)
        trajectories = [
            self._make_trajectory(TaskOutcome.FAILURE),
            self._make_trajectory(TaskOutcome.FAILURE),
        ]
        signals = asyncio.run(comparator.compare(trajectories, "skill text"))
        assert len(signals) >= 1


class TestPatcherIntegration:
    """Integration tests for Patcher with mock LLM."""

    def test_patch_applies_signals(self):
        from skill_evolution.core.comparator import DeltaSignal

        llm = MockLLM(default=PATCHER_RESPONSE)
        patcher = Patcher(llm)
        skill = _make_skill()
        signals = [
            DeltaSignal("missing_knowledge", "Add X", "evidence", 0.8, "body"),
        ]
        updated, changelog = asyncio.run(patcher.patch(skill, signals))
        assert "error handling" in updated.body.lower()
        assert "edge cases" in updated.appendix.lower()
        assert "Added" in changelog

    def test_patch_no_signals(self):
        llm = MockLLM()
        patcher = Patcher(llm)
        skill = _make_skill()
        updated, changelog = asyncio.run(patcher.patch(skill, []))
        assert updated.content_hash == skill.content_hash
        assert "No changes" in changelog


class TestAuditorIntegration:
    """Integration tests for Auditor with mock LLM."""

    def test_audit_pass(self):
        llm = MockLLM(default=AUDITOR_PASS)
        auditor = Auditor(llm)
        skill = _make_skill()
        report = asyncio.run(auditor.audit(skill))
        assert report.passed is True
        assert len(report.findings) == 2

    def test_audit_fail(self):
        llm = MockLLM(default=AUDITOR_FAIL)
        auditor = Auditor(llm)
        skill = _make_skill()
        report = asyncio.run(auditor.audit(skill))
        assert report.passed is False
