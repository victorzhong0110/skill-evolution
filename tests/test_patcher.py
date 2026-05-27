"""Tests for the skill patcher — output parsing."""

from __future__ import annotations

import pytest

from skill_evolution.core.patcher import Patcher
from skill_evolution.skill.schema import Skill, SkillMetadata


class TestPatcherParsing:
    @pytest.fixture
    def original_skill(self) -> Skill:
        return Skill(
            metadata=SkillMetadata(name="test"),
            body="# Original\n\nOriginal body.",
            appendix="Original appendix.",
        )

    def test_parse_full_output(self, original_skill: Skill):
        text = """\
===UPDATED_BODY===
# Updated

Updated body with new rules.

===UPDATED_APPENDIX===
Updated appendix with reminders.

===CHANGELOG===
- Added new SQL injection detection rules
- Added reminder about parameterized queries
"""
        patcher = Patcher.__new__(Patcher)
        updated, changelog = patcher._parse_patched_skill(text, original_skill)

        assert "Updated body" in updated.body
        assert "Updated appendix" in updated.appendix
        assert "SQL injection" in changelog

    def test_parse_preserves_original_when_no_markers(self, original_skill: Skill):
        text = "Some response without proper markers."
        patcher = Patcher.__new__(Patcher)
        updated, changelog = patcher._parse_patched_skill(text, original_skill)

        assert updated.body == original_skill.body
        assert updated.appendix == original_skill.appendix
        assert changelog == ""

    def test_parse_body_only_update(self, original_skill: Skill):
        text = """\
===UPDATED_BODY===
# New body only

===CHANGELOG===
- Updated body
"""
        patcher = Patcher.__new__(Patcher)
        updated, changelog = patcher._parse_patched_skill(text, original_skill)

        assert "New body only" in updated.body
        assert updated.appendix == original_skill.appendix

    def test_updated_skill_has_original_metadata(self, original_skill: Skill):
        text = """\
===UPDATED_BODY===
New body

===UPDATED_APPENDIX===
New appendix

===CHANGELOG===
- Changed
"""
        patcher = Patcher.__new__(Patcher)
        updated, _ = patcher._parse_patched_skill(text, original_skill)

        assert updated.metadata.name == "test"
