"""Skill document schema — the core data structure for evolvable skills."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SkillMetadata(BaseModel):
    """Metadata block parsed from YAML front matter."""

    name: str = "untitled"
    version: int = 0
    domain: str = "general"
    author: str = "skill-evolution"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evolved_at: str | None = None
    parent_hash: str | None = None  # Hash of the version this was evolved from
    tags: list[str] = Field(default_factory=list)
    evolution_round: int = 0


class Skill(BaseModel):
    """A complete skill document with metadata, body, and optional appendix.

    Format on disk (Markdown with YAML front matter):

        ---
        name: code-review
        version: 3
        domain: engineering
        ...
        ---

        # Body
        Core rules and knowledge for this skill.

        # Appendix
        Reinforcement notes from execution lapse signals.
    """

    metadata: SkillMetadata = Field(default_factory=SkillMetadata)
    body: str = ""  # Core skill content
    appendix: str = ""  # Reinforcement notes (EmbodiSkill-inspired)

    @property
    def content_hash(self) -> str:
        """SHA-256 of body + appendix for change detection."""
        raw = f"{self.body}\n---\n{self.appendix}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    @property
    def full_text(self) -> str:
        """Render as the prompt text an agent would receive."""
        parts = [self.body.strip()]
        if self.appendix.strip():
            parts.append(f"\n\n## Important Reminders\n\n{self.appendix.strip()}")
        return "\n".join(parts)

    def to_markdown(self) -> str:
        """Serialize to Markdown with YAML front matter."""
        meta_dict = self.metadata.model_dump(mode="json", exclude_none=True)
        front_matter = yaml.dump(meta_dict, default_flow_style=False, sort_keys=False).strip()
        sections = [f"---\n{front_matter}\n---\n"]
        if self.body.strip():
            sections.append(f"\n{self.body.strip()}\n")
        if self.appendix.strip():
            sections.append(f"\n## Appendix\n\n{self.appendix.strip()}\n")
        return "\n".join(sections)

    @classmethod
    def from_markdown(cls, text: str) -> Skill:
        """Parse a Markdown skill file with optional YAML front matter."""
        metadata = SkillMetadata()
        body = text
        appendix = ""

        # Extract YAML front matter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if fm_match:
            try:
                meta_raw = yaml.safe_load(fm_match.group(1)) or {}
                metadata = SkillMetadata.model_validate(meta_raw)
            except Exception:
                logger.warning("Malformed YAML front matter, using defaults", exc_info=True)
            body = text[fm_match.end():]

        # Split body and appendix
        appendix_match = re.split(r"\n##\s*(?:Appendix|Important Reminders)\s*\n", body, maxsplit=1)
        if len(appendix_match) == 2:
            body, appendix = appendix_match

        return cls(metadata=metadata, body=body.strip(), appendix=appendix.strip())

    @classmethod
    def from_file(cls, path: Path) -> Skill:
        """Load skill from a Markdown file."""
        return cls.from_markdown(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        """Save skill to a Markdown file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
