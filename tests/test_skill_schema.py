"""Tests for skill schema — parsing, serialization, and content hashing."""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_evolution.skill.schema import Skill, SkillMetadata


class TestSkillMetadata:
    def test_defaults(self):
        meta = SkillMetadata()
        assert meta.name == "untitled"
        assert meta.version == 0
        assert meta.domain == "general"
        assert meta.tags == []

    def test_custom_values(self):
        meta = SkillMetadata(name="code-review", version=3, domain="engineering", tags=["test"])
        assert meta.name == "code-review"
        assert meta.version == 3
        assert meta.tags == ["test"]


class TestSkillParsing:
    MINIMAL_SKILL = """\
---
name: test-skill
version: 1
domain: testing
---

# Test Skill

This is the body content.
"""

    SKILL_WITH_APPENDIX = """\
---
name: with-appendix
version: 2
domain: testing
tags: [a, b]
---

# Body

Core content here.

## Appendix

Remember to check edge cases.
"""

    SKILL_NO_FRONTMATTER = """\
# Plain Skill

Just a body with no metadata.
"""

    def test_parse_minimal(self):
        skill = Skill.from_markdown(self.MINIMAL_SKILL)
        assert skill.metadata.name == "test-skill"
        assert skill.metadata.version == 1
        assert skill.metadata.domain == "testing"
        assert "Test Skill" in skill.body
        assert "body content" in skill.body
        assert skill.appendix == ""

    def test_parse_with_appendix(self):
        skill = Skill.from_markdown(self.SKILL_WITH_APPENDIX)
        assert skill.metadata.name == "with-appendix"
        assert skill.metadata.tags == ["a", "b"]
        assert "Core content" in skill.body
        assert "edge cases" in skill.appendix

    def test_parse_no_frontmatter(self):
        skill = Skill.from_markdown(self.SKILL_NO_FRONTMATTER)
        assert skill.metadata.name == "untitled"
        assert "Plain Skill" in skill.body

    def test_content_hash_deterministic(self):
        skill = Skill.from_markdown(self.MINIMAL_SKILL)
        h1 = skill.content_hash
        h2 = skill.content_hash
        assert h1 == h2
        assert len(h1) == 12

    def test_content_hash_changes_with_body(self):
        skill1 = Skill(body="version a")
        skill2 = Skill(body="version b")
        assert skill1.content_hash != skill2.content_hash

    def test_full_text_without_appendix(self):
        skill = Skill(body="# Rules\n\nDo X.")
        assert "Rules" in skill.full_text
        assert "Reminders" not in skill.full_text

    def test_full_text_with_appendix(self):
        skill = Skill(body="# Rules\n\nDo X.", appendix="Always check Y.")
        text = skill.full_text
        assert "Rules" in text
        assert "Important Reminders" in text
        assert "check Y" in text


class TestSkillSerialization:
    def test_roundtrip(self):
        original = Skill(
            metadata=SkillMetadata(name="roundtrip", version=5, domain="test", tags=["a"]),
            body="# Body\n\nContent here.",
            appendix="Remember this.",
        )
        markdown = original.to_markdown()
        restored = Skill.from_markdown(markdown)

        assert restored.metadata.name == "roundtrip"
        assert restored.metadata.version == 5
        assert "Content here" in restored.body
        assert "Remember this" in restored.appendix

    def test_save_and_load(self, tmp_path: Path):
        skill = Skill(
            metadata=SkillMetadata(name="disk-test", domain="test"),
            body="# Disk Test\n\nPersisted content.",
        )
        path = tmp_path / "skill.md"
        skill.save(path)

        loaded = Skill.from_file(path)
        assert loaded.metadata.name == "disk-test"
        assert "Persisted content" in loaded.body

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "skill.md"
        skill = Skill(body="nested")
        skill.save(path)
        assert path.exists()
