"""Skill document schema — Agent Skills directory or single Markdown file."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillMetadata(BaseModel):
    """Front matter. `name` + `description` match the Agent Skills spec."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str = "untitled"
    description: str = ""
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: str | None = Field(default=None, alias="allowed-tools")
    version: int = 0
    domain: str = "general"
    author: str = "victorzhong0110"
    target_model: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evolved_at: str | None = None
    parent_hash: str | None = None
    tags: list[str] = Field(default_factory=list)
    evolution_round: int = 0

    @field_validator("version", mode="before")
    @classmethod
    def _coerce_version(cls, value: object) -> int:
        if value is None or value == "":
            return 0
        if isinstance(value, int):
            return value
        text = str(value).strip()
        try:
            return int(text.split(".", maxsplit=1)[0])
        except ValueError:
            return 0

    @field_validator("name")
    @classmethod
    def _name_shape(cls, value: str) -> str:
        if value == "untitled":
            return value
        if len(value) > 64:
            logger.warning("Skill name longer than 64 characters: %s", value)
        if not _NAME_RE.match(value):
            logger.warning(
                "Skill name %r is not Agent Skills spec (lowercase, digits, single hyphens)",
                value,
            )
        return value


class Skill(BaseModel):
    """A skill: Markdown body + optional appendix, optionally a package directory.

    On disk this is either a single `.md` file or an Agent Skills directory:

        my-skill/
        ├── SKILL.md
        ├── scripts/
        └── references/
    """

    metadata: SkillMetadata = Field(default_factory=SkillMetadata)
    body: str = ""
    appendix: str = ""
    package_dir: Path | None = None
    script_paths: list[str] = Field(default_factory=list)
    reference_paths: list[str] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def content_hash(self) -> str:
        raw = f"{self.body}\n---\n{self.appendix}\n---\n{','.join(self.script_paths)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    @property
    def full_text(self) -> str:
        parts = [self.body.strip()]
        if self.appendix.strip():
            parts.append(f"\n\n## Important Reminders\n\n{self.appendix.strip()}")
        if self.script_paths:
            listed = "\n".join(f"- {p}" for p in self.script_paths)
            parts.append(
                "\n\n## Bundled scripts\n\n"
                "These scripts live next to SKILL.md. Prefer running them over re-implementing "
                f"the same logic.\n{listed}"
            )
        if self.reference_paths:
            listed = "\n".join(f"- {p}" for p in self.reference_paths)
            parts.append(f"\n\n## References (load on demand)\n{listed}")
        return "\n".join(parts)

    def to_markdown(self) -> str:
        meta_dict = self.metadata.model_dump(mode="json", exclude_none=True, by_alias=True)
        front_matter = yaml.dump(meta_dict, default_flow_style=False, sort_keys=False).strip()
        sections = [f"---\n{front_matter}\n---\n"]
        if self.body.strip():
            sections.append(f"\n{self.body.strip()}\n")
        if self.appendix.strip():
            sections.append(f"\n## Appendix\n\n{self.appendix.strip()}\n")
        return "\n".join(sections)

    @classmethod
    def from_markdown(cls, text: str, *, package_dir: Path | None = None) -> Skill:
        metadata = SkillMetadata()
        body = text
        appendix = ""

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if fm_match:
            try:
                meta_raw = yaml.safe_load(fm_match.group(1)) or {}
                metadata = SkillMetadata.model_validate(meta_raw)
            except Exception:
                logger.warning("Malformed YAML front matter, using defaults", exc_info=True)
            body = text[fm_match.end() :]

        appendix_match = re.split(r"\n##\s*(?:Appendix|Important Reminders)\s*\n", body, maxsplit=1)
        if len(appendix_match) == 2:
            body, appendix = appendix_match

        skill = cls(
            metadata=metadata,
            body=body.strip(),
            appendix=appendix.strip(),
            package_dir=package_dir,
        )
        if package_dir is not None:
            skill._attach_package_files(package_dir)
        return skill

    @classmethod
    def from_file(cls, path: Path) -> Skill:
        return cls.from_markdown(path.read_text(encoding="utf-8"))

    @classmethod
    def from_path(cls, path: Path) -> Skill:
        """Load a skill from a Markdown file or an Agent Skills directory."""
        path = Path(path)
        if path.is_dir():
            skill_md = path / "SKILL.md"
            if not skill_md.exists():
                raise FileNotFoundError(f"No SKILL.md in {path}")
            return cls.from_markdown(skill_md.read_text(encoding="utf-8"), package_dir=path)
        if path.name == "SKILL.md":
            return cls.from_markdown(path.read_text(encoding="utf-8"), package_dir=path.parent)
        return cls.from_file(path)

    def save(self, path: Path) -> None:
        path = Path(path)
        if path.suffix.lower() in {".md", ".markdown"}:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.to_markdown(), encoding="utf-8")
            return
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(self.to_markdown(), encoding="utf-8")
        self.package_dir = path

    def _attach_package_files(self, package_dir: Path) -> None:
        scripts = package_dir / "scripts"
        refs = package_dir / "references"
        if scripts.is_dir():
            self.script_paths = sorted(
                p.relative_to(package_dir).as_posix()
                for p in scripts.rglob("*")
                if p.is_file()
            )
        if refs.is_dir():
            self.reference_paths = sorted(
                p.relative_to(package_dir).as_posix()
                for p in refs.rglob("*")
                if p.is_file()
            )
