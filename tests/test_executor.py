"""Tests for the task executor — assessment parsing."""

from __future__ import annotations

import pytest

from skill_evolution.runner.executor import TaskExecutor, TaskOutcome


class TestAssessmentParsing:
    def test_parse_success(self):
        text = """\
I reviewed the code and found SQL injection.

===ASSESSMENT===
Outcome: SUCCESS
Reason: Identified all security issues in the code.
"""
        executor = TaskExecutor.__new__(TaskExecutor)
        outcome, reason = executor._parse_assessment(text)

        assert outcome == TaskOutcome.SUCCESS
        assert "security issues" in reason

    def test_parse_failure(self):
        text = """\
I was unable to complete the review.

===ASSESSMENT===
Outcome: FAILURE
Reason: Could not parse the code snippet.
"""
        executor = TaskExecutor.__new__(TaskExecutor)
        outcome, reason = executor._parse_assessment(text)

        assert outcome == TaskOutcome.FAILURE
        assert "parse" in reason

    def test_parse_partial(self):
        text = """\
Partial review.

===ASSESSMENT===
Outcome: PARTIAL
Reason: Only checked security, not performance.
"""
        executor = TaskExecutor.__new__(TaskExecutor)
        outcome, reason = executor._parse_assessment(text)

        assert outcome == TaskOutcome.PARTIAL

    def test_no_assessment_returns_partial(self):
        text = "Just some response without assessment markers."
        executor = TaskExecutor.__new__(TaskExecutor)
        outcome, reason = executor._parse_assessment(text)

        assert outcome == TaskOutcome.PARTIAL
        assert "No self-assessment" in reason
