"""Tests for CLI task loading, config resolution, and meta-skill commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from skill_evolution.cli import _load_config, _load_tasks, main


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


class TestMetaCommands:
    def test_meta_evolve_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["meta-evolve", "--help"])
        assert result.exit_code == 0
        assert "--target" in result.output
        assert "--dry-run" in result.output
        assert "--tolerance" in result.output

    def test_meta_test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["meta-test", "--help"])
        assert result.exit_code == 0
        assert "--target" in result.output

    def test_meta_snapshot_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["meta-snapshot", "--help"])
        assert result.exit_code == 0
        assert "--target" in result.output

    def test_meta_snapshot_empty(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "meta-snapshot", "--target", "strategy_generation",
            "--workspace", str(tmp_path / "ws"),
        ])
        assert result.exit_code == 0
        assert "No snapshots" in result.output
