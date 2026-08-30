"""Tests for Agent Skills directory loading."""

from __future__ import annotations

from pathlib import Path

from skill_evolution.skill.schema import Skill


def test_from_path_directory(tmp_path: Path):
    skill_dir = tmp_path / "frontend-design"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "scripts" / "tokens.py").write_text("print('ok')\n")
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: frontend-design\n"
        "description: Distinctive UI guidance. Use when building a new page.\n"
        "version: 1.0.0\n"
        "---\n\n"
        "# Frontend Design\n\n"
        "Ground the design in the subject.\n"
    )
    skill = Skill.from_path(skill_dir)
    assert skill.metadata.name == "frontend-design"
    assert "Distinctive UI" in skill.metadata.description
    assert skill.metadata.version == 1
    assert skill.script_paths == ["scripts/tokens.py"]
    assert "Bundled scripts" in skill.full_text
    assert skill.package_dir == skill_dir


def test_save_as_package(tmp_path: Path):
    skill = Skill.from_markdown(
        "---\nname: demo\ndescription: Demo skill for packaging.\n---\n\n# Body\n\nDo the thing.\n"
    )
    out = tmp_path / "demo"
    skill.save(out)
    assert (out / "SKILL.md").exists()
    loaded = Skill.from_path(out)
    assert loaded.metadata.name == "demo"
    assert "Do the thing" in loaded.body
