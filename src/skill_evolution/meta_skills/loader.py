"""Load meta-skill prompts from Markdown files.

Resolution order:
  1. Workspace override: {workspace}/meta_skills/{name}.md
  2. Built-in: {package}/meta_skills/{name}.md
  3. Hardcoded fallback passed by the caller

This lets users evolve meta-skills in their workspace without
touching the installed package, while keeping a safe fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path

from skill_evolution.skill.schema import Skill

logger = logging.getLogger(__name__)

_BUILTIN_DIR = Path(__file__).parent


def load_meta_skill(
    name: str,
    fallback: str,
    workspace: Path | None = None,
) -> str:
    """Load a meta-skill's body text as a system prompt.

    Args:
        name: File stem without extension (e.g. "strategy_generation")
        fallback: Hardcoded prompt to use if the file is missing or empty
        workspace: Optional workspace directory for user overrides

    Returns:
        The meta-skill body text, ready to use as a system prompt.
    """
    candidates: list[Path] = []
    if workspace:
        candidates.append(workspace / "meta_skills" / f"{name}.md")
    candidates.append(_BUILTIN_DIR / f"{name}.md")

    for path in candidates:
        if not path.is_file():
            continue
        try:
            skill = Skill.from_file(path)
            if skill.full_text.strip():
                logger.debug("Loaded meta-skill '%s' from %s", name, path)
                return skill.full_text
        except Exception:
            logger.warning("Failed to parse meta-skill '%s' from %s", name, path, exc_info=True)

    logger.debug("Using hardcoded fallback for meta-skill '%s'", name)
    return fallback
