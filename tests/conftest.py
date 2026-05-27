"""Shared test fixtures — mock LLM backend for integration tests."""

from __future__ import annotations

from typing import Callable

import pytest

from skill_evolution.llm.base import LLMBackend, LLMResponse


class MockLLM(LLMBackend):
    """Deterministic LLM backend for testing.

    Accepts a responder function that maps (system, prompt) to a response string.
    Falls back to a default response if no responder is provided.
    """

    def __init__(
        self,
        responder: Callable[[str, str], str] | None = None,
        default: str = "Mock LLM response",
    ):
        super().__init__()
        self._responder = responder
        self._default = default

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        prompt = messages[-1]["content"] if messages else ""
        if self._responder:
            content = self._responder(system, prompt)
        else:
            content = self._default
        resp = LLMResponse(
            content=content,
            input_tokens=len(prompt) // 4,
            output_tokens=len(content) // 4,
            model="mock",
        )
        self.usage.record(resp)
        return resp


@pytest.fixture
def mock_llm():
    """Create a MockLLM with a default response."""
    return MockLLM()


def make_explorer_response(k: int = 4) -> str:
    """Generate a well-formed Explorer response with K strategies."""
    blocks = []
    for i in range(1, k + 1):
        blocks.append(
            f"===STRATEGY {i}===\n"
            f"Name: Strategy-{i}\n"
            f"Description: Test strategy number {i}\n"
            f"Approach:\n"
            f"1. Step one for strategy {i}\n"
            f"2. Step two for strategy {i}\n"
        )
    return "\n\n".join(blocks)


COMPARATOR_NO_SIGNALS = "===NO_SIGNALS==="

COMPARATOR_ONE_SIGNAL = """\
===SIGNAL 1===
Category: missing_knowledge
Affects: body
Confidence: 0.8
Description: Add error handling guidance
Evidence: Failed trajectories lacked error handling
===END===
"""

PATCHER_RESPONSE = """\
===UPDATED_BODY===
# Updated Skill

This skill has been improved with error handling guidance.

Always handle errors explicitly.

===UPDATED_APPENDIX===
Remember to check for edge cases.

===CHANGELOG===
- Added error handling guidance to body
"""

AUDITOR_PASS = """\
===CHECK: overfitting===
Severity: PASS
Description: No overfitting detected
Suggestion:

===CHECK: hardcoding===
Severity: PASS
Description: No hardcoded values
Suggestion:

===OVERALL===
Severity: PASS
Summary: Skill looks good.
"""

AUDITOR_FAIL = """\
===CHECK: overfitting===
Severity: FAIL
Description: Task-specific rules detected
Suggestion: Generalize the rules

===OVERALL===
Severity: FAIL
Summary: Skill has overfitting issues.
"""
