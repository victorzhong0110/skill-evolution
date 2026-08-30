"""Task executor — runs a task with a skill + strategy, records the trajectory.

Each execution is a fresh LLM call (SkillEvolver: deployment-driven feedback).
When the skill is an Agent Skills package with scripts/, the executor can run
those scripts in a sandboxed subprocess instead of asking the model to fake them.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from skill_evolution.core.explorer import Strategy
from skill_evolution.llm.base import LLMBackend


class TaskOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class Trajectory:
    """A complete record of one task execution attempt."""

    task_description: str
    strategy: Strategy
    skill_text: str
    response: str = ""
    outcome: TaskOutcome = TaskOutcome.FAILURE
    outcome_reason: str = ""
    tokens_used: int = 0
    error: str | None = None
    skill_used: bool = False
    scripts_run: list[str] = field(default_factory=list)


_SCRIPT_CALL = re.compile(
    r"===RUN_SCRIPT===\s*(?P<path>\S+)\s*(?:===ARGS===\s*(?P<args>.*?))?(?====RUN_SCRIPT===|===SKILL_USED===|\Z)",
    re.DOTALL,
)
_SKILL_USED = re.compile(r"===SKILL_USED===\s*(yes|no)", re.IGNORECASE)


class TaskExecutor:
    """Executes tasks using a fresh LLM instance with skill + strategy."""

    SYSTEM_PROMPT = """\
You are an AI agent executing a task. You have a skill document and a strategy to follow.

## Your Skill
{skill}

## Strategy to Follow
{strategy}

Execute the task step by step. Be thorough and precise.

If the skill lists bundled scripts, prefer running them over re-implementing the
same logic. To run a script, emit:

===RUN_SCRIPT===
scripts/example.py
===ARGS===
--flag value

You may emit at most three script calls. After you are done, end with:

===SKILL_USED=== yes
or
===SKILL_USED=== no

Use "yes" only if you actually followed the skill (invoked a bundled script, or
applied a named rule from the skill body). Silent bypass — answering from
parametric knowledge while ignoring the skill — must be marked "no".
"""

    def __init__(self, llm: LLMBackend, package_dir: Path | None = None):
        self.llm = llm
        self.package_dir = package_dir
        self.max_script_rounds = 3

    async def execute(
        self,
        task_description: str,
        skill_text: str,
        strategy: Strategy,
        package_dir: Path | None = None,
        script_paths: list[str] | None = None,
    ) -> Trajectory:
        """Execute a single task with a specific strategy."""
        pkg = package_dir or self.package_dir
        system = self.SYSTEM_PROMPT.format(
            skill=skill_text,
            strategy=f"{strategy.name}\n{strategy.approach}",
        )
        user_prompt = f"## Task\n{task_description}\n\nExecute this task now."
        scripts_run: list[str] = []
        script_outputs: list[str] = []
        tokens = 0
        transcript: list[str] = []

        try:
            for _ in range(self.max_script_rounds + 1):
                resp = await self.llm.ask(
                    prompt=user_prompt,
                    system=system,
                    temperature=0.3,
                    max_tokens=8192,
                )
                tokens += resp.total_tokens
                transcript.append(resp.content)
                calls = list(_SCRIPT_CALL.finditer(resp.content))
                if not calls or pkg is None:
                    break
                results: list[str] = []
                for match in calls:
                    rel = match.group("path").strip()
                    args = (match.group("args") or "").strip()
                    stdout, err = await _run_skill_script(pkg, rel, args)
                    scripts_run.append(rel)
                    block = f"===SCRIPT_RESULT {rel}===\n{stdout if stdout else err}"
                    results.append(block)
                    script_outputs.append(block)
                if not results:
                    break
                user_prompt = (
                    f"## Task\n{task_description}\n\n"
                    "Script results follow. Continue or finish the task.\n\n"
                    + "\n\n".join(results)
                )

            response = "\n\n".join(transcript + script_outputs)
            used_marker = _SKILL_USED.search(response)
            skill_used = bool(scripts_run)
            if used_marker:
                skill_used = used_marker.group(1).lower() == "yes" or skill_used
            elif script_paths:
                skill_used = skill_used or _mentions_any(response, script_paths)

            return Trajectory(
                task_description=task_description,
                strategy=strategy,
                skill_text=skill_text,
                response=response,
                outcome=TaskOutcome.PARTIAL,
                outcome_reason="Awaiting external evaluation",
                tokens_used=tokens,
                skill_used=skill_used,
                scripts_run=scripts_run,
            )
        except Exception as e:
            return Trajectory(
                task_description=task_description,
                strategy=strategy,
                skill_text=skill_text,
                outcome=TaskOutcome.FAILURE,
                outcome_reason=f"Execution error: {e}",
                error=str(e),
                skill_used=False,
            )


def _mentions_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return any(n.lower() in lower for n in needles if n)


async def _run_skill_script(package_dir: Path, rel_path: str, args: str) -> tuple[str, str]:
    """Run a script that lives under package_dir/scripts/. Returns (stdout, stderr)."""
    package_dir = package_dir.resolve()
    requested = Path(rel_path)
    if requested.is_absolute() or ".." in requested.parts:
        return "", f"Rejected script path: {rel_path}"
    script = (package_dir / requested).resolve()
    scripts_root = (package_dir / "scripts").resolve()
    try:
        script.relative_to(scripts_root)
    except ValueError:
        return "", f"Script must live under scripts/: {rel_path}"
    if not script.is_file():
        return "", f"Script not found: {rel_path}"

    cmd = _script_command(script, args)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(package_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=30)
    except TimeoutError:
        proc.kill()
        return "", f"Script timed out: {rel_path}"
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        return stdout, f"exit {proc.returncode}\n{stderr}"
    return stdout, stderr


def _script_command(script: Path, args: str) -> list[str]:
    extra = [part for part in args.split() if part] if args else []
    if script.suffix == ".py":
        return ["python3", str(script), *extra]
    if script.suffix in {".sh", ""} or os.access(script, os.X_OK):
        return ["bash", str(script), *extra]
    return ["python3", str(script), *extra]
