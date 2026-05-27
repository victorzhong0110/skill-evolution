"""Data models for meta-skill test suites.

EvalCase: a single test case (input + expected output characteristics).
ScoreResult: the result of scoring one case.
SuiteResult: aggregate results across an entire test suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    """A single test case for a meta-skill."""

    id: str
    meta_skill: str
    description: str
    input_data: dict[str, Any]
    expected: dict[str, Any]
    tags: list[str] = Field(default_factory=list)

    def to_jsonl_line(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_jsonl_line(cls, line: str) -> EvalCase:
        return cls.model_validate_json(line)


class ScoreResult(BaseModel):
    """Result of scoring one EvalCase."""

    case_id: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)


class SuiteResult(BaseModel):
    """Aggregate results for a full test suite run."""

    meta_skill: str
    total: int
    passed: int
    failed: int
    mean_score: float
    results: list[ScoreResult]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0


def write_cases_jsonl(cases: list[EvalCase], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(case.to_jsonl_line() + "\n")


def read_cases_jsonl(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                cases.append(EvalCase.from_jsonl_line(stripped))
            except Exception as exc:
                raise ValueError(
                    f"Invalid EvalCase at {path}:{line_num}: {exc}"
                ) from exc
    return cases
