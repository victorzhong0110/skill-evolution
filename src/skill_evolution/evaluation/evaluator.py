"""TaskEvaluator protocol and built-in evaluators.

Replaces unreliable self-assessment with external evaluation.
The pipeline calls evaluate() after each task execution to determine
the outcome independently of the executing LLM.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from skill_evolution.runner.executor import TaskOutcome


@dataclass
class EvalResult:
    """Result of evaluating a single task execution."""

    outcome: TaskOutcome
    reason: str
    score: float = 0.0  # 0.0-1.0 continuous score


@runtime_checkable
class TaskEvaluator(Protocol):
    """External evaluator for task execution outputs.

    Implementations receive the task input and the LLM's raw output,
    then return an independent assessment. This breaks the self-bootstrap
    loop where the LLM rates its own output.
    """

    def evaluate(self, task_input: str, task_output: str) -> EvalResult: ...


class KeywordEvaluator:
    """Evaluates output by checking for required/forbidden keywords.

    A simple structural evaluator that doesn't use LLM calls,
    avoiding the evaluation circularity problem entirely.
    """

    def __init__(
        self,
        required: list[str] | None = None,
        forbidden: list[str] | None = None,
    ):
        self._required = required or []
        self._forbidden = forbidden or []

    def evaluate(self, task_input: str, task_output: str) -> EvalResult:
        output_lower = task_output.lower()
        missing = [kw for kw in self._required if kw.lower() not in output_lower]
        found_forbidden = [kw for kw in self._forbidden if kw.lower() in output_lower]

        if missing and found_forbidden:
            return EvalResult(
                outcome=TaskOutcome.FAILURE,
                reason=f"Missing: {missing}; Forbidden present: {found_forbidden}",
                score=0.0,
            )
        if missing:
            hit_ratio = 1 - len(missing) / len(self._required)
            outcome = TaskOutcome.PARTIAL if hit_ratio > 0.5 else TaskOutcome.FAILURE
            return EvalResult(
                outcome=outcome,
                reason=f"Missing keywords: {missing}",
                score=hit_ratio,
            )
        if found_forbidden:
            return EvalResult(
                outcome=TaskOutcome.PARTIAL,
                reason=f"Forbidden keywords present: {found_forbidden}",
                score=0.5,
            )
        return EvalResult(
            outcome=TaskOutcome.SUCCESS,
            reason="All required keywords present, no forbidden keywords",
            score=1.0,
        )


class GroundTruthEvaluator:
    """Evaluates output against expected ground-truth patterns.

    Uses regex patterns to check if the output matches expected content.
    Each pattern contributes equally to the final score.
    """

    def __init__(self, expected_patterns: list[str] | None = None):
        self._patterns = [re.compile(p, re.IGNORECASE) for p in (expected_patterns or [])]

    def evaluate(self, task_input: str, task_output: str) -> EvalResult:
        if not self._patterns:
            return EvalResult(
                outcome=TaskOutcome.PARTIAL,
                reason="No ground-truth patterns configured",
                score=0.5,
            )

        matches = sum(1 for p in self._patterns if p.search(task_output))
        score = matches / len(self._patterns)

        if score >= 0.8:
            outcome = TaskOutcome.SUCCESS
        elif score >= 0.4:
            outcome = TaskOutcome.PARTIAL
        else:
            outcome = TaskOutcome.FAILURE

        return EvalResult(
            outcome=outcome,
            reason=f"Matched {matches}/{len(self._patterns)} expected patterns",
            score=score,
        )


def load_evaluator_class(class_path: str) -> type[TaskEvaluator]:
    """Load an evaluator class from a dotted module path.

    Example: "skill_evolution.evaluation.evaluator.GroundTruthEvaluator"
    """
    module_path, _, class_name = class_path.rpartition(".")
    if not module_path:
        raise ValueError(f"Invalid evaluator class path: {class_path!r} (need 'module.ClassName')")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not (isinstance(cls, type) and issubclass(cls, TaskEvaluator)):
        raise TypeError(f"{class_path!r} is not a TaskEvaluator subclass")
    return cls
