"""Test suite loader — reads JSONL files into typed EvalCase lists."""

from __future__ import annotations

import logging
from pathlib import Path

from skill_evolution.meta_skills.testing.models import EvalCase, read_cases_jsonl

logger = logging.getLogger(__name__)

_BUILTIN_DIR = Path(__file__).parent.parent / "test_suites"


def load_test_suite(path: Path) -> list[EvalCase]:
    """Load a test suite from a JSONL file.

    Raises ValueError on schema errors, FileNotFoundError if missing.
    """
    if not path.exists():
        raise FileNotFoundError(f"Test suite not found: {path}")
    cases = read_cases_jsonl(path)
    if not cases:
        raise ValueError(f"Test suite is empty: {path}")
    logger.debug("Loaded %d cases from %s", len(cases), path)
    return cases


def load_builtin_suite(meta_skill_name: str) -> list[EvalCase]:
    """Load the built-in test suite for a meta-skill.

    Built-in suites live in meta_skills/test_suites/{name}.jsonl.
    """
    path = _BUILTIN_DIR / f"{meta_skill_name}.jsonl"
    return load_test_suite(path)


def list_builtin_suites() -> list[str]:
    """Return names of all available built-in test suites."""
    if not _BUILTIN_DIR.exists():
        return []
    return sorted(p.stem for p in _BUILTIN_DIR.glob("*.jsonl"))
