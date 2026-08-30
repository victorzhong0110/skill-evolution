"""Tests for train/held-out task loading (skill-up / skill-creator formats)."""

from __future__ import annotations

import json
from pathlib import Path

from skill_evolution.evaluation.tasks import load_task_specs


def test_plain_text(tmp_path: Path):
    path = tmp_path / "tasks.txt"
    path.write_text("Task one\nTask two\n# skip\n")
    specs = load_task_specs(path)
    assert [s.prompt for s in specs] == ["Task one", "Task two"]
    assert all(s.split == "train" for s in specs)


def test_json_array(tmp_path: Path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(["Alpha", "Beta"]))
    specs = load_task_specs(path)
    assert [s.prompt for s in specs] == ["Alpha", "Beta"]


def test_train_held_out_object(tmp_path: Path):
    path = tmp_path / "tasks.json"
    path.write_text(
        json.dumps(
            {
                "train": [
                    {"id": "t1", "prompt": "Count files", "required": ["Total Files"]},
                ],
                "held_out": [
                    {"id": "h1", "prompt": "Count lines", "required": ["Total Lines"]},
                ],
            }
        )
    )
    specs = load_task_specs(path)
    assert [s.id for s in specs] == ["t1", "h1"]
    assert specs[0].split == "train"
    assert specs[1].split == "held_out"
    assert specs[0].has_criteria


def test_skill_creator_evals_marks_last_third_held_out(tmp_path: Path):
    path = tmp_path / "evals.json"
    path.write_text(
        json.dumps(
            {
                "skill_name": "code-stats",
                "evals": [
                    {
                        "id": 1,
                        "prompt": "Analyze this repo",
                        "expectations": ["Output contains 'Files by Extension' section"],
                    },
                    {"id": 2, "prompt": "Second", "expectations": ["Output contains 'Total Files'"]},
                    {"id": 3, "prompt": "Third", "expectations": ["Output contains 'Total Lines'"]},
                ],
            }
        )
    )
    specs = load_task_specs(path)
    assert len(specs) == 3
    assert specs[0].split == "train"
    assert specs[1].split == "train"
    assert specs[2].split == "held_out"
    assert "Files by Extension" in specs[0].required


def test_bundled_code_stats_tasks():
    root = Path(__file__).resolve().parents[1]
    specs = load_task_specs(root / "examples" / "code-stats" / "tasks.json")
    assert [s.split for s in specs] == ["train", "train", "held_out"]
    assert all(s.has_criteria for s in specs)

    evals = load_task_specs(root / "examples" / "code-stats" / "evals.json")
    assert evals[-1].split == "held_out"
    assert "Files by Extension" in evals[0].required


def test_bundled_frontend_design_package():
    from skill_evolution.skill.schema import Skill

    root = Path(__file__).resolve().parents[1]
    skill = Skill.from_path(root / "examples" / "frontend-design")
    assert skill.metadata.name == "frontend-design"
    assert "distinctive" in skill.metadata.description.lower()
    specs = load_task_specs(root / "examples" / "frontend-design" / "tasks.json")
    assert specs[-1].split == "held_out"
    assert "palette" in specs[0].required
