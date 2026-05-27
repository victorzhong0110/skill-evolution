"""Contrastive Trajectory Comparator.

Compares successful and failed trajectories to extract delta signals —
what specifically made the difference between success and failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skill_evolution.llm.base import LLMBackend
from skill_evolution.meta_skills.loader import load_meta_skill
from skill_evolution.runner.executor import TaskOutcome, Trajectory


@dataclass
class DeltaSignal:
    """A single improvement signal extracted from trajectory comparison."""

    category: str  # "missing_knowledge", "wrong_approach", "edge_case", "efficiency"
    description: str  # What the delta is
    evidence: str  # Concrete evidence from trajectories
    confidence: float  # 0-1, how confident we are this is a real signal
    affects: str  # "body" or "appendix" (EmbodiSkill-inspired targeting)


_FALLBACK_PROMPT = """\
You are a skill improvement analyst. You compare successful and failed task execution \
trajectories to identify what made the difference.

Your job is to extract DELTA SIGNALS — specific, actionable pieces of knowledge that, \
if added to or modified in the skill document, would turn failures into successes.

For each signal, classify it:
- missing_knowledge: The skill lacks information the agent needed
- wrong_approach: The skill recommends an approach that doesn't work
- edge_case: The skill doesn't handle a specific scenario
- efficiency: The skill works but is wasteful (too many steps, too verbose)

Also classify WHERE the fix should go (inspired by EmbodiSkill):
- body: The core skill content needs to change (skill defect)
- appendix: The skill is correct but agents don't follow it (execution lapse — add reinforcement)
"""

_OUTPUT_FORMAT = """
Output format:
===SIGNAL 1===
Category: <category>
Affects: <body|appendix>
Confidence: <0.0-1.0>
Description: <what needs to change>
Evidence: <specific quotes/observations from trajectories>

===SIGNAL 2===
...

===END===
If no meaningful signals found, output ===NO_SIGNALS===
"""


class Comparator:
    """Extracts improvement signals by comparing successful vs failed trajectories."""

    def __init__(self, llm: LLMBackend, workspace: Path | None = None):
        self.llm = llm
        base_prompt = load_meta_skill("trajectory_comparison", _FALLBACK_PROMPT, workspace)
        self._system_prompt = base_prompt + _OUTPUT_FORMAT

    async def compare(
        self,
        trajectories: list[Trajectory],
        skill_text: str,
    ) -> list[DeltaSignal]:
        """Compare trajectories and extract delta signals."""
        successes = [t for t in trajectories if t.outcome == TaskOutcome.SUCCESS]
        failures = [t for t in trajectories if t.outcome != TaskOutcome.SUCCESS]

        if not failures:
            # All succeeded — look for efficiency improvements only
            return await self._analyze_efficiency(successes, skill_text)

        if not successes:
            # All failed — analyze failure patterns
            return await self._analyze_failures(failures, skill_text)

        # The core case: compare successful vs failed
        return await self._contrastive_analysis(successes, failures, skill_text)

    async def _contrastive_analysis(
        self,
        successes: list[Trajectory],
        failures: list[Trajectory],
        skill_text: str,
    ) -> list[DeltaSignal]:
        """Core contrastive comparison between successes and failures."""
        # Build comparison prompt
        success_summaries = "\n\n".join(
            f"### Successful Trajectory (Strategy: {t.strategy.name})\n"
            f"Outcome reason: {t.outcome_reason}\n"
            f"Response excerpt:\n{t.response[:2000]}"
            for t in successes[:3]  # Limit to avoid token explosion
        )
        failure_summaries = "\n\n".join(
            f"### Failed Trajectory (Strategy: {t.strategy.name})\n"
            f"Outcome reason: {t.outcome_reason}\n"
            f"Response excerpt:\n{t.response[:2000]}"
            for t in failures[:3]
        )

        prompt = f"""\
## Current Skill Document
{skill_text}

## Successful Trajectories
{success_summaries}

## Failed Trajectories
{failure_summaries}

Compare the successful and failed trajectories. What specific knowledge or approach \
differences led to success vs failure? Extract delta signals for improving the skill."""

        resp = await self.llm.ask(prompt=prompt, system=self._system_prompt, temperature=0.4)
        return self._parse_signals(resp.content)

    async def _analyze_failures(
        self,
        failures: list[Trajectory],
        skill_text: str,
    ) -> list[DeltaSignal]:
        """When all attempts failed, analyze common failure patterns."""
        failure_summaries = "\n\n".join(
            f"### Failed Trajectory (Strategy: {t.strategy.name})\n"
            f"Outcome reason: {t.outcome_reason}\n"
            f"Response excerpt:\n{t.response[:2000]}"
            for t in failures[:4]
        )

        prompt = f"""\
## Current Skill Document
{skill_text}

## All Trajectories Failed
{failure_summaries}

All strategies failed. Analyze the common failure patterns and identify what the skill \
is missing or getting wrong. Extract delta signals."""

        resp = await self.llm.ask(prompt=prompt, system=self._system_prompt, temperature=0.4)
        return self._parse_signals(resp.content)

    async def _analyze_efficiency(
        self,
        successes: list[Trajectory],
        skill_text: str,
    ) -> list[DeltaSignal]:
        """When all succeeded, look for efficiency improvements."""
        summaries = "\n\n".join(
            f"### Trajectory (Strategy: {t.strategy.name})\n"
            f"Tokens used: {t.tokens_used}\n"
            f"Response excerpt:\n{t.response[:1500]}"
            for t in successes[:4]
        )

        prompt = f"""\
## Current Skill Document
{skill_text}

## All Trajectories Succeeded
{summaries}

All strategies succeeded. Look for efficiency improvements — could the skill be more \
concise? Are there redundant instructions? Could agents solve tasks with fewer steps? \
Extract optimization signals."""

        resp = await self.llm.ask(prompt=prompt, system=self._system_prompt, temperature=0.4)
        return self._parse_signals(resp.content)

    def _parse_signals(self, text: str) -> list[DeltaSignal]:
        """Parse LLM output into DeltaSignal objects."""
        if "===NO_SIGNALS===" in text:
            return []

        signals = []
        blocks = text.split("===SIGNAL")
        for block in blocks[1:]:
            if "===END===" in block:
                block = block[:block.index("===END===")]

            category = "missing_knowledge"
            affects = "body"
            confidence = 0.5
            description = ""
            evidence = ""

            for line in block.split("\n"):
                stripped = line.strip()
                if stripped.startswith("Category:"):
                    category = stripped[len("Category:"):].strip().lower()
                elif stripped.startswith("Affects:"):
                    affects = stripped[len("Affects:"):].strip().lower()
                elif stripped.startswith("Confidence:"):
                    try:
                        confidence = float(stripped[len("Confidence:"):].strip())
                    except ValueError:
                        confidence = 0.5
                elif stripped.startswith("Description:"):
                    description = stripped[len("Description:"):].strip()
                elif stripped.startswith("Evidence:"):
                    evidence = stripped[len("Evidence:"):].strip()

            if description:
                signals.append(DeltaSignal(
                    category=category,
                    description=description,
                    evidence=evidence,
                    confidence=min(max(confidence, 0.0), 1.0),
                    affects=affects if affects in ("body", "appendix") else "body",
                ))

        return signals
