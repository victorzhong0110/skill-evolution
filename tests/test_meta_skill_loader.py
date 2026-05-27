"""Tests for meta-skill loader — resolution order and fallback behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_evolution.meta_skills.loader import load_meta_skill


FALLBACK = "hardcoded fallback prompt"


class TestLoadMetaSkill:
    def test_loads_builtin_file(self):
        prompt = load_meta_skill("strategy_generation", FALLBACK)
        assert "Strategy" in prompt or "strategy" in prompt
        assert FALLBACK not in prompt

    def test_falls_back_when_file_missing(self):
        prompt = load_meta_skill("nonexistent_meta_skill", FALLBACK)
        assert prompt == FALLBACK

    def test_workspace_override_takes_priority(self, tmp_path: Path):
        meta_dir = tmp_path / "meta_skills"
        meta_dir.mkdir()
        (meta_dir / "strategy_generation.md").write_text(
            "---\nname: custom-strategy\n---\n\n# Custom Strategy\n\nWorkspace override content."
        )

        prompt = load_meta_skill("strategy_generation", FALLBACK, workspace=tmp_path)
        assert "Workspace override content" in prompt

    def test_builtin_used_when_workspace_file_absent(self, tmp_path: Path):
        prompt = load_meta_skill("strategy_generation", FALLBACK, workspace=tmp_path)
        assert "Strategy" in prompt or "strategy" in prompt
        assert FALLBACK not in prompt

    def test_fallback_on_empty_file(self, tmp_path: Path):
        meta_dir = tmp_path / "meta_skills"
        meta_dir.mkdir()
        (meta_dir / "empty.md").write_text("")

        prompt = load_meta_skill("empty", FALLBACK, workspace=tmp_path)
        assert prompt == FALLBACK

    def test_all_builtin_meta_skills_load(self):
        names = ["strategy_generation", "trajectory_comparison", "skill_audit", "skill_patch"]
        for name in names:
            prompt = load_meta_skill(name, FALLBACK)
            assert len(prompt) > 100, f"Meta-skill '{name}' loaded but seems too short"
            assert FALLBACK not in prompt
