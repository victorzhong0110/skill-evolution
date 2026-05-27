"""Strategy Diversification Explorer.

Generates K diverse high-level strategies for solving a task,
ensuring each strategy takes a meaningfully different approach.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skill_evolution.llm.base import LLMBackend
from skill_evolution.meta_skills.loader import load_meta_skill


@dataclass
class Strategy:
    """A high-level approach for solving a task."""

    id: int
    name: str
    description: str
    approach: str  # Detailed step-by-step approach


_FALLBACK_PROMPT = """\
You are a strategy diversification expert. Given a task description and a skill document, \
generate {k} meaningfully different high-level strategies for solving the task.

Each strategy must:
1. Take a fundamentally different approach (not just reword the same idea)
2. Be concrete enough for an agent to follow
3. Leverage the skill document where relevant, but also explore beyond it

Output format (STRICTLY follow this):
===STRATEGY 1===
Name: <short name>
Description: <1-2 sentence summary>
Approach:
<detailed step-by-step approach>

===STRATEGY 2===
...
"""

_OUTPUT_FORMAT = """
Output format (STRICTLY follow this):
===STRATEGY 1===
Name: <short name>
Description: <1-2 sentence summary>
Approach:
<detailed step-by-step approach>

===STRATEGY 2===
...
"""


class Explorer:
    """Generates diverse strategies for a given task using an LLM."""

    def __init__(self, llm: LLMBackend, workspace: Path | None = None):
        self.llm = llm
        base_prompt = load_meta_skill("strategy_generation", _FALLBACK_PROMPT, workspace)
        self._system_prompt = base_prompt + _OUTPUT_FORMAT

    async def generate_strategies(
        self,
        task_description: str,
        skill_text: str,
        k: int = 4,
    ) -> list[Strategy]:
        """Generate K diverse strategies for solving a task."""
        prompt = f"""\
## Skill Document
{skill_text}

## Task
{task_description}

Generate exactly {k} diverse strategies."""

        system = self._system_prompt.replace("{k}", str(k))
        resp = await self.llm.ask(
            prompt=prompt,
            system=system,
            temperature=0.9,  # Higher temperature for diversity
        )
        return self._parse_strategies(resp.content)

    def _parse_strategies(self, text: str) -> list[Strategy]:
        """Parse LLM output into Strategy objects."""
        strategies = []
        blocks = text.split("===STRATEGY")
        for i, block in enumerate(blocks[1:], start=1):  # Skip first empty split
            lines = block.strip().split("\n")
            name = ""
            description = ""
            approach_lines = []
            in_approach = False

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("Name:"):
                    name = stripped[len("Name:"):].strip()
                elif stripped.startswith("Description:"):
                    description = stripped[len("Description:"):].strip()
                elif stripped.startswith("Approach:"):
                    in_approach = True
                elif in_approach:
                    approach_lines.append(line)

            strategies.append(Strategy(
                id=i,
                name=name or f"Strategy {i}",
                description=description,
                approach="\n".join(approach_lines).strip(),
            ))
        return strategies
