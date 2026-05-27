"""Task executor — runs a task with a skill + strategy, records the trajectory.

Each execution is done by a FRESH, independent LLM call (not the same instance
that generated the strategy), matching SkillEvolver's deployment-driven feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from skill_evolution.core.explorer import Strategy
from skill_evolution.llm.base import LLMBackend, LLMResponse


class TaskOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class Trajectory:
    """A complete record of one task execution attempt."""

    task_description: str
    strategy: Strategy
    skill_text: str
    response: str = ""
    outcome: TaskOutcome = TaskOutcome.FAILURE
    outcome_reason: str = ""
    tokens_used: int = 0
    error: str | None = None


class TaskExecutor:
    """Executes tasks using a fresh LLM instance with skill + strategy."""

    SYSTEM_PROMPT = """\
You are an AI agent executing a task. You have a skill document and a strategy to follow.

## Your Skill
{skill}

## Strategy to Follow
{strategy}

Execute the task step by step. Be thorough and precise.
At the end, provide a self-assessment:
===ASSESSMENT===
Outcome: SUCCESS | FAILURE | PARTIAL
Reason: <why you succeeded or failed>
"""

    def __init__(self, llm: LLMBackend):
        self.llm = llm

    async def execute(
        self,
        task_description: str,
        skill_text: str,
        strategy: Strategy,
    ) -> Trajectory:
        """Execute a single task with a specific strategy."""
        system = self.SYSTEM_PROMPT.format(
            skill=skill_text,
            strategy=f"{strategy.name}\n{strategy.approach}",
        )

        try:
            resp = await self.llm.ask(
                prompt=f"## Task\n{task_description}\n\nExecute this task now.",
                system=system,
                temperature=0.3,  # Lower temperature for consistent execution
                max_tokens=8192,
            )
            outcome, reason = self._parse_assessment(resp.content)

            return Trajectory(
                task_description=task_description,
                strategy=strategy,
                skill_text=skill_text,
                response=resp.content,
                outcome=outcome,
                outcome_reason=reason,
                tokens_used=resp.total_tokens,
            )
        except Exception as e:
            return Trajectory(
                task_description=task_description,
                strategy=strategy,
                skill_text=skill_text,
                outcome=TaskOutcome.FAILURE,
                outcome_reason=f"Execution error: {e}",
                error=str(e),
            )

    def _parse_assessment(self, text: str) -> tuple[TaskOutcome, str]:
        """Extract self-assessment from the execution output."""
        if "===ASSESSMENT===" not in text:
            # No self-assessment — try to infer
            return TaskOutcome.PARTIAL, "No self-assessment provided"

        assessment = text.split("===ASSESSMENT===")[-1].strip()
        outcome = TaskOutcome.PARTIAL
        reason = ""

        for line in assessment.split("\n"):
            stripped = line.strip()
            if stripped.startswith("Outcome:"):
                raw = stripped[len("Outcome:"):].strip().upper()
                if "SUCCESS" in raw:
                    outcome = TaskOutcome.SUCCESS
                elif "FAILURE" in raw:
                    outcome = TaskOutcome.FAILURE
                else:
                    outcome = TaskOutcome.PARTIAL
            elif stripped.startswith("Reason:"):
                reason = stripped[len("Reason:"):].strip()

        return outcome, reason
