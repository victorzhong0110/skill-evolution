"""Tests for the RegressionGate (T8)."""

from __future__ import annotations

import pytest

from skill_evolution.skill.regression_gate import GateVerdict, check_regression


class TestCheckRegression:
    def test_no_regression_all_improved(self):
        baseline = {"case-1": 0.6, "case-2": 0.5}
        candidate = {"case-1": 0.8, "case-2": 0.7}
        verdict = check_regression(baseline, candidate)
        assert verdict.passed
        assert set(verdict.improved) == {"case-1", "case-2"}
        assert verdict.regressed == []

    def test_regression_blocks(self):
        baseline = {"case-1": 0.8, "case-2": 0.9}
        candidate = {"case-1": 0.7, "case-2": 0.95}
        verdict = check_regression(baseline, candidate)
        assert not verdict.passed
        assert "case-1" in verdict.regressed
        assert "case-2" in verdict.improved

    def test_no_change_passes(self):
        scores = {"a": 0.5, "b": 0.8}
        verdict = check_regression(scores, dict(scores))
        assert verdict.passed
        assert set(verdict.unchanged) == {"a", "b"}
        assert verdict.improved == []
        assert verdict.regressed == []

    def test_tolerance_allows_small_drop(self):
        baseline = {"a": 0.80}
        candidate = {"a": 0.76}
        verdict = check_regression(baseline, candidate, tolerance=0.05)
        assert verdict.passed
        assert "a" in verdict.unchanged

    def test_tolerance_blocks_large_drop(self):
        baseline = {"a": 0.80}
        candidate = {"a": 0.70}
        verdict = check_regression(baseline, candidate, tolerance=0.05)
        assert not verdict.passed
        assert "a" in verdict.regressed

    def test_new_cases_tracked(self):
        baseline = {"existing": 0.7}
        candidate = {"existing": 0.7, "new-case": 0.9}
        verdict = check_regression(baseline, candidate)
        assert verdict.passed
        assert "new-case" in verdict.new_cases

    def test_missing_candidate_case_is_regression(self):
        baseline = {"a": 0.8, "b": 0.7}
        candidate = {"a": 0.9}
        verdict = check_regression(baseline, candidate)
        assert not verdict.passed
        assert "b" in verdict.regressed

    def test_empty_baseline_all_new(self):
        verdict = check_regression({}, {"a": 0.5, "b": 0.8})
        assert verdict.passed
        assert set(verdict.new_cases) == {"a", "b"}

    def test_both_empty_passes(self):
        verdict = check_regression({}, {})
        assert verdict.passed

    def test_summary_format(self):
        baseline = {"a": 0.5, "b": 0.8}
        candidate = {"a": 0.7, "b": 0.6}
        verdict = check_regression(baseline, candidate)
        assert verdict.summary.startswith("FAIL")
        assert "regressed" in verdict.summary

    def test_summary_pass(self):
        verdict = check_regression({"a": 0.5}, {"a": 0.8})
        assert verdict.summary.startswith("PASS")
