"""Tests for meta-skill testing infrastructure (T7a, T7b, T7c)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_evolution.meta_skills.testing.models import (
    EvalCase,
    ScoreResult,
    SuiteResult,
    read_cases_jsonl,
    write_cases_jsonl,
)
from skill_evolution.meta_skills.testing.loader import (
    list_builtin_suites,
    load_builtin_suite,
    load_test_suite,
)
from skill_evolution.meta_skills.testing.scoring import (
    StrategyGenerationScorer,
    TrajectoryComparisonScorer,
    get_scorer,
    score_meta_skill,
)


# ── T7a: Models ──────────────────────────────────────────────────────


class TestEvalCase:
    def test_roundtrip_jsonl(self):
        case = EvalCase(
            id="test-1",
            meta_skill="strategy_generation",
            description="test case",
            input_data={"task": "do something", "k": 4},
            expected={"k": 4},
            tags=["happy_path"],
        )
        line = case.to_jsonl_line()
        restored = EvalCase.from_jsonl_line(line)
        assert restored == case

    def test_jsonl_is_valid_json(self):
        case = EvalCase(
            id="test-2",
            meta_skill="test",
            description="desc",
            input_data={},
            expected={},
        )
        parsed = json.loads(case.to_jsonl_line())
        assert parsed["id"] == "test-2"

    def test_default_tags_empty(self):
        case = EvalCase(
            id="x", meta_skill="m", description="d",
            input_data={}, expected={},
        )
        assert case.tags == []


class TestScoreResult:
    def test_score_bounds(self):
        r = ScoreResult(case_id="x", score=0.75, passed=True, reason="ok")
        assert 0.0 <= r.score <= 1.0

    def test_score_out_of_bounds_rejected(self):
        with pytest.raises(Exception):
            ScoreResult(case_id="x", score=1.5, passed=True, reason="ok")


class TestSuiteResult:
    def test_pass_rate(self):
        sr = SuiteResult(
            meta_skill="test", total=4, passed=3, failed=1,
            mean_score=0.75, results=[],
        )
        assert sr.pass_rate == 0.75

    def test_pass_rate_zero_total(self):
        sr = SuiteResult(
            meta_skill="test", total=0, passed=0, failed=0,
            mean_score=0.0, results=[],
        )
        assert sr.pass_rate == 0.0


class TestJsonlReadWrite:
    def test_roundtrip(self, tmp_path: Path):
        cases = [
            EvalCase(
                id=f"c-{i}", meta_skill="test", description=f"case {i}",
                input_data={"n": i}, expected={"val": i},
            )
            for i in range(3)
        ]
        path = tmp_path / "suite.jsonl"
        write_cases_jsonl(cases, path)
        loaded = read_cases_jsonl(path)
        assert loaded == cases

    def test_empty_lines_skipped(self, tmp_path: Path):
        path = tmp_path / "sparse.jsonl"
        case = EvalCase(
            id="x", meta_skill="m", description="d",
            input_data={}, expected={},
        )
        path.write_text(f"\n{case.to_jsonl_line()}\n\n")
        loaded = read_cases_jsonl(path)
        assert len(loaded) == 1

    def test_invalid_json_raises(self, tmp_path: Path):
        path = tmp_path / "bad.jsonl"
        path.write_text("not valid json\n")
        with pytest.raises(ValueError, match="Invalid EvalCase"):
            read_cases_jsonl(path)


# ── T7b: Loader ──────────────────────────────────────────────────────


class TestLoader:
    def test_load_test_suite(self, tmp_path: Path):
        case = EvalCase(
            id="l-1", meta_skill="test", description="loader test",
            input_data={}, expected={},
        )
        path = tmp_path / "suite.jsonl"
        write_cases_jsonl([case], path)
        loaded = load_test_suite(path)
        assert len(loaded) == 1
        assert loaded[0].id == "l-1"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_test_suite(tmp_path / "nonexistent.jsonl")

    def test_empty_suite_raises(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        path.write_text("\n\n")
        with pytest.raises(ValueError, match="empty"):
            load_test_suite(path)

    def test_load_builtin_strategy_generation(self):
        cases = load_builtin_suite("strategy_generation")
        assert len(cases) >= 5
        assert all(c.meta_skill == "strategy_generation" for c in cases)

    def test_load_builtin_trajectory_comparison(self):
        cases = load_builtin_suite("trajectory_comparison")
        assert len(cases) >= 5
        assert all(c.meta_skill == "trajectory_comparison" for c in cases)

    def test_list_builtin_suites(self):
        suites = list_builtin_suites()
        assert "strategy_generation" in suites
        assert "trajectory_comparison" in suites

    def test_builtin_suites_have_adversarial_cases(self):
        for name in ["strategy_generation", "trajectory_comparison"]:
            cases = load_builtin_suite(name)
            adversarial = [c for c in cases if "adversarial" in c.tags]
            assert len(adversarial) >= 1, f"{name} missing adversarial cases"

    def test_builtin_suites_have_edge_cases(self):
        for name in ["strategy_generation", "trajectory_comparison"]:
            cases = load_builtin_suite(name)
            edge = [c for c in cases if "edge_case" in c.tags]
            assert len(edge) >= 1, f"{name} missing edge cases"


# ── T7c: Scoring ─────────────────────────────────────────────────────


def _make_case(meta_skill: str, expected: dict | None = None, **kw) -> EvalCase:
    return EvalCase(
        id="test", meta_skill=meta_skill, description="test",
        input_data=kw.get("input_data", {}),
        expected=expected or {},
    )


class TestStrategyGenerationScorer:
    def test_perfect_output(self):
        scorer = StrategyGenerationScorer()
        case = _make_case("strategy_generation", expected={"k": 2})
        output = (
            "===STRATEGY 1===\n"
            "Name: Conservative Review\n"
            "Description: Follow the skill literally\n"
            "Approach:\n1. Read the skill\n2. Apply each rule\n\n"
            "===STRATEGY 2===\n"
            "Name: Exploratory Approach\n"
            "Description: Go beyond the skill\n"
            "Approach:\n1. Start with general knowledge\n2. Cross-reference skill\n"
        )
        result = scorer.score(case, output)
        assert result.passed
        assert result.score >= 0.8

    def test_wrong_count(self):
        scorer = StrategyGenerationScorer()
        case = _make_case("strategy_generation", expected={"k": 4})
        output = (
            "===STRATEGY 1===\n"
            "Name: Only One\n"
            "Description: Just one strategy\n"
            "Approach:\nDo the thing\n"
        )
        result = scorer.score(case, output)
        assert result.score < 1.0
        assert "Expected 4" in result.reason

    def test_missing_names(self):
        scorer = StrategyGenerationScorer()
        case = _make_case("strategy_generation", expected={"k": 2})
        output = (
            "===STRATEGY 1===\n"
            "Approach:\nDo something thoroughly step by step\n\n"
            "===STRATEGY 2===\n"
            "Approach:\nDo something differently and explore more options\n"
        )
        result = scorer.score(case, output)
        assert not result.details.get("all_named", True)

    def test_duplicate_strategies_penalized(self):
        scorer = StrategyGenerationScorer()
        case = _make_case("strategy_generation", expected={"k": 2})
        same_block = "Name: Same\nDescription: Same desc\nApproach:\nDo the exact same thing step by step carefully"
        output = f"===STRATEGY 1===\n{same_block}\n\n===STRATEGY 2===\n{same_block}\n"
        result = scorer.score(case, output)
        assert not result.details.get("strategies_distinct", True)

    def test_empty_output(self):
        scorer = StrategyGenerationScorer()
        case = _make_case("strategy_generation", expected={"k": 3})
        result = scorer.score(case, "")
        assert result.score < 0.5
        assert not result.passed


class TestTrajectoryComparisonScorer:
    def test_perfect_signals(self):
        scorer = TrajectoryComparisonScorer()
        case = _make_case("trajectory_comparison", expected={"min_signals": 1})
        output = (
            "===SIGNAL 1===\n"
            "Category: missing_knowledge\n"
            "Affects: body\n"
            "Confidence: 0.85\n"
            "Description: Skill lacks pagination handling guidance\n"
            "Evidence: Successful trajectory handled cursor pagination while failed one did not\n"
            "===END===\n"
        )
        result = scorer.score(case, output)
        assert result.passed
        assert result.score >= 0.8

    def test_no_signals_when_expected(self):
        scorer = TrajectoryComparisonScorer()
        case = _make_case("trajectory_comparison", expected={"expect_signals": True})
        result = scorer.score(case, "===NO_SIGNALS===")
        assert not result.passed
        assert result.score == 0.0

    def test_no_signals_when_not_expected(self):
        scorer = TrajectoryComparisonScorer()
        case = _make_case("trajectory_comparison", expected={"expect_signals": False})
        result = scorer.score(case, "===NO_SIGNALS===")
        assert result.passed

    def test_invalid_category(self):
        scorer = TrajectoryComparisonScorer()
        case = _make_case("trajectory_comparison", expected={"min_signals": 1})
        output = (
            "===SIGNAL 1===\n"
            "Category: totally_made_up\n"
            "Affects: body\n"
            "Confidence: 0.5\n"
            "Description: Something wrong\n"
            "Evidence: Saw it happen\n"
            "===END===\n"
        )
        result = scorer.score(case, output)
        assert not result.details.get("valid_categories", True)

    def test_confidence_out_of_range(self):
        scorer = TrajectoryComparisonScorer()
        case = _make_case("trajectory_comparison", expected={"min_signals": 1})
        output = (
            "===SIGNAL 1===\n"
            "Category: edge_case\n"
            "Affects: appendix\n"
            "Confidence: 5.0\n"
            "Description: Edge case found\n"
            "Evidence: Observed in testing\n"
            "===END===\n"
        )
        result = scorer.score(case, output)
        assert not result.details.get("valid_confidence", True)

    def test_empty_output(self):
        scorer = TrajectoryComparisonScorer()
        case = _make_case("trajectory_comparison", expected={"min_signals": 1})
        result = scorer.score(case, "")
        assert not result.passed


class TestGetScorer:
    def test_known_scorers(self):
        assert isinstance(get_scorer("strategy_generation"), StrategyGenerationScorer)
        assert isinstance(get_scorer("trajectory_comparison"), TrajectoryComparisonScorer)

    def test_unknown_scorer_raises(self):
        with pytest.raises(KeyError, match="No scorer"):
            get_scorer("nonexistent_skill")


class TestScoreMetaSkill:
    def test_full_suite_run(self):
        cases = [
            _make_case("strategy_generation", expected={"k": 2}),
            _make_case("strategy_generation", expected={"k": 2}),
        ]
        cases[0].id = "c1"
        cases[1].id = "c2"

        good_output = (
            "===STRATEGY 1===\n"
            "Name: Approach A\nDescription: First way\nApproach:\nDo it the first way step by step\n\n"
            "===STRATEGY 2===\n"
            "Name: Approach B\nDescription: Second way\nApproach:\nDo it the completely different second way\n"
        )
        result = score_meta_skill(
            "strategy_generation",
            cases,
            output_fn=lambda _: good_output,
        )
        assert result.total == 2
        assert result.meta_skill == "strategy_generation"
        assert result.mean_score > 0
