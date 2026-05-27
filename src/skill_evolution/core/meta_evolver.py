"""MetaSkillEvolver — orchestrates the meta-skill evolution cycle.

Cycle for one target meta-skill:
  1. Snapshot current meta-skill as baseline
  2. Score baseline against its test suite
  3. Evolve the meta-skill (treat it as a regular skill through the pipeline)
  4. Score candidate against same test suite
  5. Regression gate: compare candidate vs baseline scores
  6. Accept (overwrite meta-skill file) or rollback (keep baseline)
"""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from skill_evolution.config import Config
from skill_evolution.core.changelog import ChangelogEntry, append_changelog
from skill_evolution.core.pipeline import EvolutionPipeline
from skill_evolution.llm import create_llm
from skill_evolution.meta_skills.loader import load_meta_skill
from skill_evolution.meta_skills.testing.loader import load_builtin_suite, load_test_suite
from skill_evolution.meta_skills.testing.models import EvalCase
from skill_evolution.meta_skills.testing.scoring import get_scorer, score_meta_skill
from skill_evolution.skill.regression_gate import GateVerdict, check_regression
from skill_evolution.skill.schema import Skill
from skill_evolution.skill.versioning import SkillVersionManager

logger = logging.getLogger(__name__)
console = Console()

_META_SKILLS_DIR = Path(__file__).parent.parent / "meta_skills"


@dataclass
class MetaEvolveResult:
    """Result of one meta-skill evolution cycle."""

    target: str
    accepted: bool
    baseline_scores: dict[str, float]
    candidate_scores: dict[str, float]
    gate_verdict: GateVerdict
    version: int | None = None


class MetaSkillEvolver:
    """Orchestrates meta-skill evolution with regression safety."""

    def __init__(self, config: Config, workspace: Path | None = None):
        self.config = config
        self._workspace = workspace or config.workspace_dir

    def _load_meta_skill_as_skill(self, name: str) -> Skill:
        """Load a meta-skill markdown file as a Skill object."""
        workspace_path = self._workspace / "meta_skills" / f"{name}.md"
        if workspace_path.exists():
            return Skill.from_file(workspace_path)
        builtin_path = _META_SKILLS_DIR / f"{name}.md"
        if builtin_path.exists():
            return Skill.from_file(builtin_path)
        raise FileNotFoundError(f"Meta-skill not found: {name}")

    def _meta_skill_output_path(self, name: str) -> Path:
        """Where to write the evolved meta-skill."""
        workspace_path = self._workspace / "meta_skills" / f"{name}.md"
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        return workspace_path

    def _load_test_cases(
        self, name: str, suite_path: Path | None = None
    ) -> list[EvalCase]:
        """Load test cases — custom path or built-in suite."""
        if suite_path:
            return load_test_suite(suite_path)
        return load_builtin_suite(name)

    def score_baseline(
        self,
        name: str,
        suite_path: Path | None = None,
    ) -> dict[str, float]:
        """Score the current meta-skill against its test suite.

        Runs the scorer with the current meta-skill's output format
        expectations. Returns a {case_id: score} map.
        """
        cases = self._load_test_cases(name, suite_path)
        scorer = get_scorer(name)
        scores: dict[str, float] = {}
        for case in cases:
            placeholder_output = self._generate_placeholder_output(name, case)
            result = scorer.score(case, placeholder_output)
            scores[case.id] = result.score
        return scores

    def run_test_suite(
        self,
        name: str,
        skill_text: str,
        suite_path: Path | None = None,
    ) -> dict[str, float]:
        """Score a meta-skill's text against its test suite.

        This produces output by running the meta-skill text through
        the LLM, then scoring the result structurally.

        Safe to call from both sync and async contexts.
        """
        cases = self._load_test_cases(name, suite_path)
        llm = create_llm(self.config.llm)

        def output_fn(case: EvalCase) -> str:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            coro = llm.ask(
                prompt=self._build_test_prompt(name, case),
                system=skill_text,
                temperature=0.5,
            )
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=180).content
            return asyncio.run(coro).content

        suite_result = score_meta_skill(name, cases, output_fn)
        return {r.case_id: r.score for r in suite_result.results}

    async def evolve(
        self,
        target: str,
        tasks: list[str] | None = None,
        suite_path: Path | None = None,
        dry_run: bool = False,
        tolerance: float = 0.0,
    ) -> MetaEvolveResult:
        """Run a full meta-skill evolution cycle.

        Args:
            target: Meta-skill name (e.g., "strategy_generation")
            tasks: Task descriptions for evolution. If None, auto-generates
                   from test cases.
            suite_path: Optional custom test suite JSONL path
            dry_run: If True, don't write changes to disk
            tolerance: Allowed score drop before regression gate fails
        """
        console.print(f"\n[bold cyan]Meta-evolving: {target}[/bold cyan]")

        # 1. Load current meta-skill
        skill = self._load_meta_skill_as_skill(target)
        cases = self._load_test_cases(target, suite_path)
        vm = SkillVersionManager(self._workspace, f"meta-{target}")

        # 2. Score baseline
        console.print("[dim]Scoring baseline...[/dim]")
        baseline_scores = self.run_test_suite(target, skill.full_text, suite_path)
        console.print(f"  Baseline mean: {_mean(baseline_scores):.2f}")

        # Snapshot baseline with scores
        baseline_version = vm.snapshot(
            skill, notes="Baseline before meta-evolution", scores=baseline_scores
        )

        # 3. Evolve the meta-skill (treat as a regular skill)
        console.print("[dim]Evolving meta-skill...[/dim]")
        evolution_tasks = tasks or self._tasks_from_cases(cases)

        pipeline = EvolutionPipeline(self.config, workspace=self._workspace)
        candidate_skill, report = await pipeline.evolve(
            copy.deepcopy(skill), evolution_tasks
        )

        # 4. Score candidate
        console.print("[dim]Scoring candidate...[/dim]")
        candidate_scores = self.run_test_suite(
            target, candidate_skill.full_text, suite_path
        )
        console.print(f"  Candidate mean: {_mean(candidate_scores):.2f}")

        # 5. Regression gate
        console.print("[dim]Running regression gate...[/dim]")
        verdict = check_regression(baseline_scores, candidate_scores, tolerance)
        verdict_color = "green" if verdict.passed else "red"
        console.print(f"  Gate: [{verdict_color}]{verdict.summary}[/{verdict_color}]")

        if verdict.improved or verdict.regressed:
            self._print_score_table(baseline_scores, candidate_scores, verdict)

        # 6. Accept or rollback
        accepted = verdict.passed and candidate_skill.content_hash != skill.content_hash
        version = None

        if accepted and not dry_run:
            output_path = self._meta_skill_output_path(target)
            candidate_skill.save(output_path)
            version = vm.snapshot(
                candidate_skill,
                notes=f"Evolved: {verdict.summary}",
                scores=candidate_scores,
            )
            console.print(f"[green]Accepted: meta-skill updated (v{version})[/green]")
        elif accepted and dry_run:
            console.print("[yellow]Dry run: would accept (no files written)[/yellow]")
        elif not verdict.passed:
            console.print("[yellow]Rejected: regression detected, keeping baseline[/yellow]")
        else:
            console.print("[dim]No meaningful changes produced[/dim]")

        # Log to changelog
        if not dry_run:
            action = "accepted" if accepted else "rejected"
            entry = ChangelogEntry(
                meta_skill=target,
                action=action,
                baseline_mean=_mean(baseline_scores),
                candidate_mean=_mean(candidate_scores),
                delta=_mean(candidate_scores) - _mean(baseline_scores),
                improved=verdict.improved,
                regressed=verdict.regressed,
                version=version,
                summary=verdict.summary,
            )
            append_changelog(self._workspace, entry)

        return MetaEvolveResult(
            target=target,
            accepted=accepted,
            baseline_scores=baseline_scores,
            candidate_scores=candidate_scores,
            gate_verdict=verdict,
            version=version,
        )

    def _tasks_from_cases(self, cases: list[EvalCase]) -> list[str]:
        """Generate evolution tasks from test case descriptions."""
        return [
            f"Handle this scenario: {case.description}"
            for case in cases[:5]
        ]

    def _build_test_prompt(self, name: str, case: EvalCase) -> str:
        """Build a prompt for testing a meta-skill against one case."""
        data = case.input_data
        if name == "strategy_generation":
            k = data.get("k", 4)
            return (
                f"## Skill Document\n{data.get('skill_text', '')}\n\n"
                f"## Task\n{data.get('task', '')}\n\n"
                f"Generate exactly {k} diverse strategies.\n\n"
                f"You MUST use this exact output format:\n"
                f"===STRATEGY 1===\n"
                f"Name: <short name>\n"
                f"Description: <1-2 sentence summary>\n"
                f"Approach:\n"
                f"<detailed step-by-step approach>\n\n"
                f"===STRATEGY 2===\n"
                f"..."
            )
        elif name == "trajectory_comparison":
            return (
                f"## Current Skill Document\n{data.get('skill_text', '')}\n\n"
                f"## Successful Trajectory\n{data.get('success_response', '')}\n\n"
                f"## Failed Trajectory\n{data.get('failure_response', '')}\n\n"
                "Compare these trajectories and extract delta signals.\n\n"
                "You MUST use this exact output format:\n"
                "===SIGNAL 1===\n"
                "Category: <missing_knowledge|wrong_approach|edge_case|efficiency>\n"
                "Affects: <body|appendix>\n"
                "Confidence: <0.0-1.0>\n"
                "Description: <what needs to change>\n"
                "Evidence: <specific observations from trajectories>\n\n"
                "===SIGNAL 2===\n"
                "...\n\n"
                "===END===\n"
                "If no meaningful signals found, output ===NO_SIGNALS==="
            )
        return f"Execute this test case:\n{case.model_dump_json(indent=2)}"

    @staticmethod
    def _print_score_table(
        baseline: dict[str, float],
        candidate: dict[str, float],
        verdict: GateVerdict,
    ) -> None:
        """Print a Rich table comparing per-case baseline vs candidate scores."""
        table = Table(title="Score Comparison", show_lines=True)
        table.add_column("Case", style="bold")
        table.add_column("Baseline", justify="right")
        table.add_column("Candidate", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("Status")

        all_keys = sorted(set(baseline) | set(candidate))
        for key in all_keys:
            b = baseline.get(key, 0.0)
            c = candidate.get(key, 0.0)
            d = c - b
            if key in verdict.improved:
                status = "[green]+[/green]"
                delta_style = "green"
            elif key in verdict.regressed:
                status = "[red]-[/red]"
                delta_style = "red"
            else:
                status = "[dim]=[/dim]"
                delta_style = "dim"
            table.add_row(
                key,
                f"{b:.2f}",
                f"{c:.2f}",
                f"[{delta_style}]{d:+.2f}[/{delta_style}]",
                status,
            )

        b_mean = _mean(baseline)
        c_mean = _mean(candidate)
        d_mean = c_mean - b_mean
        mean_style = "green" if d_mean > 0 else "red" if d_mean < 0 else "dim"
        table.add_row(
            "[bold]Mean[/bold]",
            f"[bold]{b_mean:.2f}[/bold]",
            f"[bold]{c_mean:.2f}[/bold]",
            f"[bold {mean_style}]{d_mean:+.2f}[/bold {mean_style}]",
            "",
        )
        console.print(table)

    @staticmethod
    def _generate_placeholder_output(name: str, case: EvalCase) -> str:
        """Generate a minimal placeholder output for baseline scoring.

        Used when we can't call the LLM (e.g., score_baseline without
        LLM access). Returns empty string — scorer handles gracefully.
        """
        return ""


def _mean(scores: dict[str, float]) -> float:
    vals = list(scores.values())
    return sum(vals) / len(vals) if vals else 0.0
