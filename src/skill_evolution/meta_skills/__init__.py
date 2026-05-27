"""Meta-skills — the prompts that drive the evolution pipeline.

Each meta-skill is a Markdown file with optional YAML front matter,
loaded at runtime so that evolved versions take effect immediately.
"""

from skill_evolution.meta_skills.loader import load_meta_skill

__all__ = ["load_meta_skill"]
