"""Evolution changelog — structured record of each evolution cycle."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class ChangelogEntry(BaseModel):
    """One entry in the evolution changelog."""

    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    meta_skill: str
    action: str  # "accepted", "rejected", "baseline"
    baseline_mean: float = 0.0
    candidate_mean: float = 0.0
    delta: float = 0.0
    improved: list[str] = Field(default_factory=list)
    regressed: list[str] = Field(default_factory=list)
    version: int | None = None
    summary: str = ""


def append_changelog(workspace: Path, entry: ChangelogEntry) -> Path:
    """Append a changelog entry to the workspace's changelog.jsonl."""
    path = workspace / "changelog.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")
    return path


def read_changelog(workspace: Path) -> list[ChangelogEntry]:
    """Read all changelog entries."""
    path = workspace / "changelog.jsonl"
    if not path.exists():
        return []
    entries: list[ChangelogEntry] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                entries.append(ChangelogEntry.model_validate_json(stripped))
    return entries


def read_changelog_for_skill(workspace: Path, meta_skill: str) -> list[ChangelogEntry]:
    """Read changelog entries filtered to one meta-skill."""
    return [e for e in read_changelog(workspace) if e.meta_skill == meta_skill]
