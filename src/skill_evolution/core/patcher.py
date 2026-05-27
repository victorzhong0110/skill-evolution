"""Skill Patcher — applies targeted updates based on delta signals.

Key design principle: LOCAL PATCHES, not global rewrites.
Only modify what the signals indicate, preserve everything else.
"""

from __future__ import annotations

from pathlib import Path

from skill_evolution.core.comparator import DeltaSignal
from skill_evolution.llm.base import LLMBackend
from skill_evolution.meta_skills.loader import load_meta_skill
from skill_evolution.skill.schema import Skill


_FALLBACK_PROMPT = """\
You are a precision skill editor. You receive a skill document and a set of delta signals \
(improvement instructions). Your job is to apply TARGETED, MINIMAL patches.

CRITICAL RULES:
1. Only modify what the signals require — preserve all other content
2. For "body" signals: modify the core skill content
3. For "appendix" signals: add reinforcement notes to the appendix section \
   (the skill content is correct, agents just need reminders to follow it)
4. Never remove correct information — only add, refine, or correct
5. Keep the same writing style and structure as the original
6. If signals conflict, prioritize higher-confidence signals
"""

_OUTPUT_FORMAT = """
Output the complete updated skill in two clearly labeled sections:

===UPDATED_BODY===
<the complete updated body text>

===UPDATED_APPENDIX===
<the complete updated appendix text>

===CHANGELOG===
- <what you changed and why, one line per change>
"""


class Patcher:
    """Applies delta signals to evolve a skill document."""

    def __init__(self, llm: LLMBackend, workspace: Path | None = None):
        self.llm = llm
        base_prompt = load_meta_skill("skill_patch", _FALLBACK_PROMPT, workspace)
        self._system_prompt = base_prompt + _OUTPUT_FORMAT

    async def patch(self, skill: Skill, signals: list[DeltaSignal]) -> tuple[Skill, str]:
        """Apply delta signals to a skill. Returns (updated_skill, changelog)."""
        if not signals:
            return skill, "No changes — no signals to apply."

        # Sort signals: higher confidence first
        sorted_signals = sorted(signals, key=lambda s: s.confidence, reverse=True)

        signals_text = "\n\n".join(
            f"Signal {i+1} (confidence: {s.confidence:.2f}, target: {s.affects}):\n"
            f"  Category: {s.category}\n"
            f"  Description: {s.description}\n"
            f"  Evidence: {s.evidence}"
            for i, s in enumerate(sorted_signals)
        )

        prompt = f"""\
## Current Skill Body
{skill.body}

## Current Skill Appendix
{skill.appendix if skill.appendix else "(empty)"}

## Delta Signals to Apply
{signals_text}

Apply these signals as targeted patches. Remember: minimal changes, preserve everything else."""

        resp = await self.llm.ask(prompt=prompt, system=self._system_prompt, temperature=0.3)
        return self._parse_patched_skill(resp.content, skill)

    def _parse_patched_skill(self, text: str, original: Skill) -> tuple[Skill, str]:
        """Parse LLM output into an updated Skill + changelog."""
        new_body = original.body
        new_appendix = original.appendix
        changelog = ""

        if "===UPDATED_BODY===" in text:
            body_section = text.split("===UPDATED_BODY===")[1]
            if "===UPDATED_APPENDIX===" in body_section:
                body_section = body_section.split("===UPDATED_APPENDIX===")[0]
            elif "===CHANGELOG===" in body_section:
                body_section = body_section.split("===CHANGELOG===")[0]
            new_body = body_section.strip()

        if "===UPDATED_APPENDIX===" in text:
            appendix_section = text.split("===UPDATED_APPENDIX===")[1]
            if "===CHANGELOG===" in appendix_section:
                appendix_section = appendix_section.split("===CHANGELOG===")[0]
            new_appendix = appendix_section.strip()

        if "===CHANGELOG===" in text:
            changelog = text.split("===CHANGELOG===")[1].strip()

        updated = Skill(
            metadata=original.metadata.model_copy(),
            body=new_body,
            appendix=new_appendix,
        )
        return updated, changelog
