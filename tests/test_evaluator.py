"""Tests for the TaskEvaluator protocol and built-in evaluators."""

from __future__ import annotations

import pytest

from skill_evolution.evaluation.evaluator import (
    EvalResult,
    GroundTruthEvaluator,
    KeywordEvaluator,
    TaskEvaluator,
    load_evaluator_class,
)
from skill_evolution.runner.executor import TaskOutcome


class TestKeywordEvaluator:
    def test_all_required_present(self):
        ev = KeywordEvaluator(required=["hello", "world"])
        result = ev.evaluate("task", "Hello World!")
        assert result.outcome == TaskOutcome.SUCCESS
        assert result.score == 1.0

    def test_missing_required(self):
        ev = KeywordEvaluator(required=["hello", "world", "foo"])
        result = ev.evaluate("task", "Hello World!")
        assert result.outcome == TaskOutcome.PARTIAL
        assert result.score == pytest.approx(2 / 3)

    def test_all_missing(self):
        ev = KeywordEvaluator(required=["alpha", "beta"])
        result = ev.evaluate("task", "no matches here")
        assert result.outcome == TaskOutcome.FAILURE
        assert result.score == 0.0

    def test_forbidden_present(self):
        ev = KeywordEvaluator(forbidden=["error", "bug"])
        result = ev.evaluate("task", "found an error in the code")
        assert result.outcome == TaskOutcome.PARTIAL
        assert "error" in result.reason.lower()

    def test_no_config(self):
        ev = KeywordEvaluator()
        result = ev.evaluate("task", "anything")
        assert result.outcome == TaskOutcome.SUCCESS

    def test_implements_protocol(self):
        assert isinstance(KeywordEvaluator(), TaskEvaluator)


class TestGroundTruthEvaluator:
    def test_all_patterns_match(self):
        ev = GroundTruthEvaluator(expected_patterns=[r"\d+ items", r"total: \d+"])
        result = ev.evaluate("task", "Found 5 items, total: 42")
        assert result.outcome == TaskOutcome.SUCCESS
        assert result.score == 1.0

    def test_no_patterns_match(self):
        ev = GroundTruthEvaluator(expected_patterns=[r"\d+ items", r"total: \d+"])
        result = ev.evaluate("task", "nothing here")
        assert result.outcome == TaskOutcome.FAILURE
        assert result.score == 0.0

    def test_partial_match(self):
        ev = GroundTruthEvaluator(expected_patterns=[r"hello", r"world", r"foo", r"bar", r"baz"])
        result = ev.evaluate("task", "hello world")
        assert result.outcome == TaskOutcome.PARTIAL

    def test_no_patterns_configured(self):
        ev = GroundTruthEvaluator()
        result = ev.evaluate("task", "anything")
        assert result.outcome == TaskOutcome.PARTIAL

    def test_implements_protocol(self):
        assert isinstance(GroundTruthEvaluator(), TaskEvaluator)


class TestLoadEvaluatorClass:
    def test_load_keyword_evaluator(self):
        cls = load_evaluator_class("skill_evolution.evaluation.evaluator.KeywordEvaluator")
        assert cls is KeywordEvaluator

    def test_load_ground_truth_evaluator(self):
        cls = load_evaluator_class("skill_evolution.evaluation.evaluator.GroundTruthEvaluator")
        assert cls is GroundTruthEvaluator

    def test_invalid_path(self):
        with pytest.raises(ValueError, match="Invalid evaluator class path"):
            load_evaluator_class("NoModule")

    def test_nonexistent_module(self):
        with pytest.raises(ModuleNotFoundError):
            load_evaluator_class("nonexistent.module.Evaluator")

    def test_not_evaluator_subclass(self):
        with pytest.raises(TypeError, match="not a TaskEvaluator"):
            load_evaluator_class("skill_evolution.config.Config")
