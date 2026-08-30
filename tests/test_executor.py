"""Tests for the task executor."""

from __future__ import annotations

import asyncio
from pathlib import Path

from skill_evolution.core.explorer import Strategy
from skill_evolution.runner.executor import (
    TaskExecutor,
    TaskOutcome,
    Trajectory,
    _run_skill_script,
)
from tests.conftest import MockLLM


class TestTrajectoryDefaults:
    def test_default_outcome_is_failure(self):
        t = Trajectory(
            task_description="test",
            strategy=None,  # type: ignore[arg-type]
            skill_text="test skill",
        )
        assert t.outcome == TaskOutcome.FAILURE

    def test_partial_outcome(self):
        t = Trajectory(
            task_description="test",
            strategy=None,  # type: ignore[arg-type]
            skill_text="test skill",
            outcome=TaskOutcome.PARTIAL,
            outcome_reason="Awaiting external evaluation",
        )
        assert t.outcome == TaskOutcome.PARTIAL
        assert "external" in t.outcome_reason.lower()

    def test_system_prompt_no_self_assessment(self):
        assert "===ASSESSMENT===" not in TaskExecutor.SYSTEM_PROMPT


class TestScriptSandbox:
    def _pkg(self, tmp_path: Path) -> Path:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "count.py").write_text("print('Total Files: 3')\n")
        return tmp_path

    def test_runs_bundled_script(self, tmp_path: Path):
        pkg = self._pkg(tmp_path)

        def responder(system: str, prompt: str) -> str:
            if "SCRIPT_RESULT" in prompt:
                return "Done. ===SKILL_USED=== yes"
            return "===RUN_SCRIPT===\nscripts/count.py\n===SKILL_USED=== yes"

        executor = TaskExecutor(MockLLM(responder=responder))
        strategy = Strategy(id=1, name="Direct", description="", approach="run the script")
        traj = asyncio.run(
            executor.execute(
                "count files",
                "# skill",
                strategy,
                package_dir=pkg,
                script_paths=["scripts/count.py"],
            )
        )
        assert traj.scripts_run == ["scripts/count.py"]
        assert "Total Files: 3" in traj.response
        assert traj.skill_used is True

    def test_rejects_parent_path(self, tmp_path: Path):
        pkg = self._pkg(tmp_path)
        stdout, err = asyncio.run(_run_skill_script(pkg, "../secret.py", ""))
        assert stdout == ""
        assert "Rejected" in err

    def test_rejects_path_outside_scripts(self, tmp_path: Path):
        pkg = self._pkg(tmp_path)
        (tmp_path / "outside.py").write_text("print('nope')\n")
        stdout, err = asyncio.run(_run_skill_script(pkg, "outside.py", ""))
        assert stdout == ""
        assert "scripts/" in err

