"""Tests for skill version management — snapshot, history, rollback."""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_evolution.skill.schema import Skill, SkillMetadata
from skill_evolution.skill.versioning import SkillVersionManager


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def skill() -> Skill:
    return Skill(
        metadata=SkillMetadata(name="test-skill", domain="testing"),
        body="# Test\n\nInitial body.",
    )


class TestSkillVersionManager:
    def test_snapshot_creates_files(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        version = vm.snapshot(skill, notes="initial")

        assert version == 1
        assert vm.current_path.exists()
        assert (vm.history_dir / "v001.md").exists()
        assert vm.index_path.exists()

    def test_snapshot_increments_version(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        v1 = vm.snapshot(skill, notes="v1")
        v2 = vm.snapshot(skill, notes="v2")
        v3 = vm.snapshot(skill, notes="v3")

        assert v1 == 1
        assert v2 == 2
        assert v3 == 3

    def test_history_returns_all_entries(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="first")
        vm.snapshot(skill, notes="second")

        entries = vm.history()
        assert len(entries) == 2
        assert entries[0].version == 1
        assert entries[0].notes == "first"
        assert entries[1].version == 2
        assert entries[1].notes == "second"

    def test_load_current(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="saved")

        loaded = vm.load_current()
        assert loaded is not None
        assert "Initial body" in loaded.body

    def test_load_current_returns_none_when_empty(self, workspace: Path):
        vm = SkillVersionManager(workspace, "test-skill")
        assert vm.load_current() is None

    def test_load_specific_version(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="v1")

        skill.body = "# Updated\n\nModified body."
        vm.snapshot(skill, notes="v2")

        v1 = vm.load_version(1)
        v2 = vm.load_version(2)
        assert v1 is not None
        assert "Initial body" in v1.body
        assert v2 is not None
        assert "Modified body" in v2.body

    def test_load_nonexistent_version_returns_none(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        assert vm.load_version(99) is None

    def test_rollback(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="v1")

        skill.body = "# Changed"
        vm.snapshot(skill, notes="v2")

        rolled_back = vm.rollback(1)
        assert rolled_back is not None

        current = vm.load_current()
        assert current is not None
        assert "Initial body" in current.body

    def test_rollback_nonexistent_returns_none(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        assert vm.rollback(99) is None

    def test_diff_summary(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="v1")

        skill.body = "# Changed body"
        skill.appendix = "New appendix"
        vm.snapshot(skill, notes="v2")

        diff = vm.diff_summary(1, 2)
        assert diff["body_changed"] is True
        assert diff["appendix_changed"] is True

    def test_diff_summary_missing_version(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        diff = vm.diff_summary(1, 2)
        assert "error" in diff

    def test_parent_hash_linked(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="v1")

        entries = vm.history()
        first_hash = entries[0].content_hash

        skill.body = "# Modified"
        vm.snapshot(skill, notes="v2")

        v2_skill = vm.load_version(2)
        assert v2_skill is not None
        assert v2_skill.metadata.parent_hash == first_hash

    def test_snapshot_with_scores(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        scores = {"case-1": 0.9, "case-2": 0.75}
        vm.snapshot(skill, notes="scored", scores=scores)

        retrieved = vm.get_scores(1)
        assert retrieved == scores

    def test_get_scores_empty_when_not_set(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="no scores")
        assert vm.get_scores(1) == {}

    def test_get_scores_nonexistent_version(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        assert vm.get_scores(99) == {}

    def test_get_baseline_scores(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="v1", scores={"a": 0.5})
        skill.body = "# Updated"
        vm.snapshot(skill, notes="v2", scores={"a": 0.8, "b": 0.6})

        baseline = vm.get_baseline_scores()
        assert baseline == {"a": 0.8, "b": 0.6}

    def test_get_baseline_scores_empty_history(self, workspace: Path):
        vm = SkillVersionManager(workspace, "test-skill")
        assert vm.get_baseline_scores() == {}

    def test_update_scores(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="v1")

        updated = vm.update_scores(1, {"x": 0.95})
        assert updated is True
        assert vm.get_scores(1) == {"x": 0.95}

    def test_update_scores_nonexistent(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        assert vm.update_scores(99, {"x": 0.5}) is False

    def test_scores_persist_across_reloads(self, workspace: Path, skill: Skill):
        vm = SkillVersionManager(workspace, "test-skill")
        vm.snapshot(skill, notes="v1", scores={"a": 0.7})

        vm2 = SkillVersionManager(workspace, "test-skill")
        assert vm2.get_scores(1) == {"a": 0.7}
