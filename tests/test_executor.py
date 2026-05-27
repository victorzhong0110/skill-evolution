"""Tests for the task executor."""

from __future__ import annotations

import pytest

from skill_evolution.runner.executor import TaskExecutor, TaskOutcome, Trajectory


class TestTrajectoryDefaults:
    def test_default_outcome_is_failure(self):
        t = Trajectory(
            task_description="test",
            strategy=None,  # type: ignore[arg-type]
            skill_text="test skill",
        )
        assert t.outcome == TaskOutcome.FAILURE

    def test_partial_outcome(self):
        t = Trajectory(
            task_description="test",
            strategy=None,  # type: ignore[arg-type]
            skill_text="test skill",
            outcome=TaskOutcome.PARTIAL,
            outcome_reason="Awaiting external evaluation",
        )
        assert t.outcome == TaskOutcome.PARTIAL
        assert "external" in t.outcome_reason.lower()

    def test_system_prompt_no_self_assessment(self):
        assert "===ASSESSMENT===" not in TaskExecutor.SYSTEM_PROMPT
