"""Skill version management — snapshot, diff, and rollback."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from skill_evolution.skill.schema import Skill


class VersionEntry(BaseModel):
    """A single version snapshot."""

    version: int
    content_hash: str
    timestamp: str
    evolution_round: int = 0
    file_name: str = ""
    notes: str = ""


class SkillVersionManager:
    """Manages version history for a skill within a workspace directory.

    Layout:
        workspace/
          skills/
            <skill-name>/
              current.md       <- latest version
              history/
                v001.md
                v002.md
                ...
              versions.json    <- version index
    """

    def __init__(self, workspace: Path, skill_name: str):
        self.skill_dir = workspace / "skills" / skill_name
        self.history_dir = self.skill_dir / "history"
        self.current_path = self.skill_dir / "current.md"
        self.index_path = self.skill_dir / "versions.json"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> list[VersionEntry]:
        if self.index_path.exists():
            data = json.loads(self.index_path.read_text())
            return [VersionEntry.model_validate(e) for e in data]
        return []

    def _save_index(self, entries: list[VersionEntry]) -> None:
        data = [e.model_dump(mode="json") for e in entries]
        self.index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def snapshot(self, skill: Skill, notes: str = "") -> int:
        """Save a snapshot of the current skill state. Returns new version number."""
        entries = self._load_index()
        new_version = len(entries) + 1

        # Update skill metadata
        skill.metadata.version = new_version
        skill.metadata.evolved_at = datetime.now(timezone.utc).isoformat()
        if entries:
            skill.metadata.parent_hash = entries[-1].content_hash

        # Save to history
        file_name = f"v{new_version:03d}.md"
        history_path = self.history_dir / file_name
        skill.save(history_path)

        # Update current
        skill.save(self.current_path)

        # Update index
        entry = VersionEntry(
            version=new_version,
            content_hash=skill.content_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
            evolution_round=skill.metadata.evolution_round,
            file_name=file_name,
            notes=notes,
        )
        entries.append(entry)
        self._save_index(entries)

        return new_version

    def load_current(self) -> Skill | None:
        """Load the current (latest) skill version."""
        if self.current_path.exists():
            return Skill.from_file(self.current_path)
        return None

    def load_version(self, version: int) -> Skill | None:
        """Load a specific historical version."""
        file_name = f"v{version:03d}.md"
        path = self.history_dir / file_name
        if path.exists():
            return Skill.from_file(path)
        return None

    def rollback(self, version: int) -> Skill | None:
        """Rollback to a specific version (copies it as current, doesn't delete history)."""
        skill = self.load_version(version)
        if skill:
            skill.save(self.current_path)
        return skill

    def history(self) -> list[VersionEntry]:
        """Get full version history."""
        return self._load_index()

    def diff_summary(self, v1: int, v2: int) -> dict[str, Any]:
        """Compare two versions at a high level."""
        s1 = self.load_version(v1)
        s2 = self.load_version(v2)
        if not s1 or not s2:
            return {"error": "Version not found"}

        return {
            "from_version": v1,
            "to_version": v2,
            "body_changed": s1.body != s2.body,
            "appendix_changed": s1.appendix != s2.appendix,
            "body_length_delta": len(s2.body) - len(s1.body),
            "appendix_length_delta": len(s2.appendix) - len(s1.appendix),
        }
