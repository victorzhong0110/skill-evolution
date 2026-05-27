"""Tests for CLI task loading and config resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_evolution.cli import _load_config, _load_tasks


class TestLoadTasks:
    def test_load_plain_text(self, tmp_path: Path):
        task_file = tmp_path / "tasks.txt"
        task_file.write_text("Task one\nTask two\n\n# Comment\nTask three\n")

        tasks = _load_tasks(str(task_file))
        assert tasks == ["Task one", "Task two", "Task three"]

    def test_load_json_array(self, tmp_path: Path):
        task_file = tmp_path / "tasks.json"
        task_file.write_text(json.dumps(["Alpha", "Beta", "Gamma"]))

        tasks = _load_tasks(str(task_file))
        assert tasks == ["Alpha", "Beta", "Gamma"]

    def test_load_skips_empty_lines(self, tmp_path: Path):
        task_file = tmp_path / "tasks.txt"
        task_file.write_text("\n\n  \nReal task\n  \n")

        tasks = _load_tasks(str(task_file))
        assert tasks == ["Real task"]


class TestLoadConfig:
    def test_returns_defaults_when_no_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = _load_config(None)
        assert cfg.llm.provider == "claude"

    def test_loads_explicit_path(self, tmp_path: Path):
        from skill_evolution.config import Config

        cfg = Config()
        path = tmp_path / "custom.yaml"
        cfg.save(path)

        loaded = _load_config(str(path))
        assert loaded.llm.provider == "claude"
