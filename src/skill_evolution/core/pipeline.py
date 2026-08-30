"""Evolution Pipeline — orchestrates the full skill evolution loop.

Flow per round:
  1. Explorer: generate K diverse strategies
  2. Executor: run each strategy on each task (independent agents)
  3. Evaluator: externally evaluate each trajectory (replaces self-assessment)
  4. Comparator: compare successes vs failures, extract delta signals
  5. Patcher: apply targeted patches to the skill (on a deep copy)
  6. Auditor: independent review; if FAIL, rollback + feed findings as DeltaSignals

This loops for R rounds or until budget is exhausted.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from skill_evolution.config import Config
from skill_evolution.core.auditor import Auditor, AuditReport, AuditSeverity
from skill_evolution.core.comparator import Comparator, DeltaSignal
from skill_evolution.core.explorer import Explorer, Strategy
from skill_evolution.core.patcher import Patcher
from skill_evolution.core.prompt_safety import ensure_prompt_safe
from skill_evolution.evaluation.evaluator import (
    KeywordEvaluator,
    PerTaskEvaluator,
    TaskEvaluator,
    UnconfiguredEvaluatorError,
    load_evaluator_class,
)
from skill_evolution.evaluation.tasks import TaskSpec, normalize_tasks
from skill_evolution.llm import create_llm
from skill_evolution.runner.executor import TaskExecutor, TaskOutcome, Trajectory
from skill_evolution.skill.regression_gate import check_regression
from skill_evolution.skill.schema import Skill
from skill_evolution.skill.versioning import SkillVersionManager

FOLLOW_SKILL = Strategy(
    id=0,
    name="follow-skill",
    description="Follow the skill as written",
    approach=(
        "Execute the task by following the skill document exactly. "
        "Run bundled scripts when they apply."
    ),
)

logger = logging.getLogger(__name__)

console = Console()


@dataclass
class RoundReport:
    """Report for one evolution round."""

    round_num: int
    strategies_generated: int
    trajectories_total: int
    trajectories_success: int
    trajectories_failure: int
    signals_extracted: int
    audit_passed: bool
    changelog: str = ""
    cost_estimate: float = 0.0
    held_out_passed: bool = True
    gate_summary: str = ""


@dataclass
class EvolutionReport:
    """Full evolution report across all rounds."""

    skill_name: str
    rounds: list[RoundReport] = field(default_factory=list)
    initial_hash: str = ""
    final_hash: str = ""
    total_cost: float = 0.0

    def summary(self) -> str:
        lines = [f"Evolution Report: {self.skill_name}"]
        lines.append(f"Rounds completed: {len(self.rounds)}")
        for r in self.rounds:
            success_rate = (
                f"{r.trajectories_success}/{r.trajectories_total}"
                if r.trajectories_total > 0
                else "N/A"
            )
            lines.append(
                f"  Round {r.round_num}: "
                f"success={success_rate}, signals={r.signals_extracted}, "
                f"audit={'PASS' if r.audit_passed else 'FAIL'}"
                + (f", held-out={r.gate_summary}" if r.gate_summary else "")
            )
        lines.append(f"Total estimated cost: ${self.total_cost:.4f}")
        return "\n".join(lines)


class EvolutionPipeline:
    """Main orchestrator for skill evolution."""

    def __init__(self, config: Config, workspace: Path | None = None):
        self.config = config
        self._workspace = workspace or config.workspace_dir
        self.llm = create_llm(config.llm)
        self.explorer = Explorer(self.llm, workspace=self._workspace)
        self.executor = TaskExecutor(self.llm)
        self.comparator = Comparator(self.llm, workspace=self._workspace)
        self.patcher = Patcher(self.llm, workspace=self._workspace)
        self.auditor = Auditor(create_llm(config.llm), workspace=self._workspace)
        self.evaluator = self._create_evaluator()

    def _create_evaluator(self) -> TaskEvaluator:
        """Instantiate the configured TaskEvaluator."""
        class_path = self.config.evolution.evaluator_class
        if class_path is None:
            return KeywordEvaluator()
        cls = load_evaluator_class(class_path)
        return cls()

    async def evolve(
        self,
        skill: Skill,
        tasks: list[str] | list[TaskSpec],
        workspace: Path | None = None,
    ) -> tuple[Skill, EvolutionReport]:
        """Run the full evolution loop.

        Args:
            skill: Initial skill document
            tasks: Task prompts, or TaskSpec objects with train/held-out splits
            workspace: Directory for version snapshots (optional)

        Returns:
            (evolved_skill, evolution_report)
        """
        specs = normalize_tasks(tasks)
        self._ensure_scorable(specs)
        ensure_prompt_safe(skill.body, source="skill body")
        ensure_prompt_safe(skill.appendix, source="skill appendix")
        for spec in specs:
            ensure_prompt_safe(spec.prompt, source=f"tasks[{spec.id}]")

        ws = workspace or self.config.workspace_dir
        vm = SkillVersionManager(ws, skill.metadata.name)

        # Warn if evolution model differs from skill's target model
        if skill.metadata.target_model:
            llm_name = getattr(self.llm, "model", "") or ""
            if skill.metadata.target_model.lower() not in llm_name.lower():
                console.print(
                    f"[bold yellow]⚠ Model mismatch: skill target_model='{skill.metadata.target_model}' "
                    f"but evolution LLM='{llm_name}'. "
                    f"Scoring behaviors may diverge.[/bold yellow]"
                )

        # Snapshot initial version
        vm.snapshot(skill, notes="Initial version before evolution")
        report = EvolutionReport(
            skill_name=skill.metadata.name,
            initial_hash=skill.content_hash,
        )

        current_skill = skill
        num_rounds = self.config.evolution.num_rounds
        k = self.config.evolution.num_strategies

        for round_num in range(1, num_rounds + 1):
            console.print(f"\n[bold cyan]━━━ Round {round_num}/{num_rounds} ━━━[/bold cyan]")

            # Budget check
            if self._over_budget():
                console.print("[yellow]Budget exhausted. Stopping evolution.[/yellow]")
                break

            round_report = await self._run_round(
                current_skill, specs, k, round_num
            )
            report.rounds.append(round_report)

            # If the round produced an updated skill, use it
            if round_report.changelog:
                current_skill.metadata.evolution_round = round_num
                if self.config.evolution.auto_snapshot:
                    vm.snapshot(current_skill, notes=f"Round {round_num}: {round_report.changelog[:200]}")
                console.print(f"[green]Skill updated and snapshotted (v{current_skill.metadata.version})[/green]")

        report.final_hash = current_skill.content_hash
        report.total_cost = self.llm.usage.estimated_cost_usd

        console.print("\n[bold green]Evolution complete![/bold green]")
        console.print(self.llm.usage.summary())

        return current_skill, report

    def _ensure_scorable(self, tasks: list[TaskSpec]) -> None:
        fallback = self.evaluator
        unconfigured = isinstance(fallback, KeywordEvaluator) and not fallback.is_configured
        if unconfigured and not any(task.has_criteria for task in tasks):
            raise UnconfiguredEvaluatorError(
                "Refusing to evolve: the evaluator has no scoring criteria and no task "
                "lists required/forbidden/expected_patterns. An empty KeywordEvaluator "
                "marks every trajectory SUCCESS and starves contrastive learning. "
                "Use a JSON task file with criteria, or set evolution.evaluator_class."
            )

    async def _run_round(
        self,
        skill: Skill,
        tasks: list[TaskSpec],
        k: int,
        round_num: int,
    ) -> RoundReport:
        """Execute one evolution round."""
        train = [t for t in tasks if t.split == "train"]
        held_out = [t for t in tasks if t.split == "held_out"]
        if not train:
            train = list(tasks)

        console.print("[dim]Generating diverse strategies...[/dim]")
        all_trajectories: list[Trajectory] = []
        scorer = PerTaskEvaluator(self.evaluator)

        for task_idx, task in enumerate(train):
            console.print(f"  Task {task_idx + 1}/{len(train)}: {task.prompt[:60]}...")
            strategies = await self.explorer.generate_strategies(
                task_description=task.prompt,
                skill_text=skill.full_text,
                k=k,
            )
            console.print(f"    Generated {len(strategies)} strategies")

            for strat in strategies:
                trajectory = await self.executor.execute(
                    task_description=task.prompt,
                    skill_text=skill.full_text,
                    strategy=strat,
                    package_dir=skill.package_dir,
                    script_paths=skill.script_paths,
                )
                try:
                    result = scorer.evaluate_task(task, trajectory.response)
                    trajectory.outcome = result.outcome
                    trajectory.outcome_reason = result.reason
                except Exception as exc:
                    logger.warning("Evaluator failed for task %s strategy %s: %s", task.id, strat.name, exc)
                    trajectory.outcome = TaskOutcome.FAILURE
                    trajectory.outcome_reason = f"Evaluator error: {exc}"

                all_trajectories.append(trajectory)
                icon = "✓" if trajectory.outcome == TaskOutcome.SUCCESS else "✗"
                used = "invoked" if trajectory.skill_used else "bypass"
                console.print(f"    [{strat.name}] {icon} {trajectory.outcome.value} ({used})")

        console.print("[dim]Comparing trajectories...[/dim]")
        signals = await self.comparator.compare(all_trajectories, skill.full_text)
        console.print(f"  Extracted {len(signals)} delta signals")

        unused = sum(1 for t in all_trajectories if not t.skill_used)
        if unused and unused == len(all_trajectories):
            signals.append(DeltaSignal(
                category="wrong_approach",
                description="Silent bypass: every trajectory ignored the skill at runtime.",
                evidence=f"{unused}/{len(all_trajectories)} runs did not invoke the skill.",
                confidence=0.85,
                affects="body",
            ))

        for s in signals:
            console.print(f"    [{s.affects}] {s.category} (conf={s.confidence:.2f}): {s.description[:80]}")

        changelog = ""
        audit_passed = True
        held_out_passed = True
        gate_summary = ""
        if signals:
            console.print("[dim]Applying patches...[/dim]")
            original_len = len(skill.body)
            skill_snapshot = copy.deepcopy(skill)
            updated_skill, changelog = await self.patcher.patch(skill_snapshot, signals)
            console.print(f"  Changes applied:\n{changelog[:500]}")

            if (
                len(updated_skill.body) > original_len * 1.25
                and "DELETE" not in changelog.upper()
            ):
                console.print("  [yellow]Patch grew >25% with no DELETE — adding shrinkage signal[/yellow]")
                signals.append(DeltaSignal(
                    category="redundancy",
                    description="Skill grew without deleting unused content.",
                    evidence=changelog[:300],
                    confidence=0.7,
                    affects="body",
                ))

            if self.config.audit.enabled:
                console.print("[dim]Running independent audit...[/dim]")
                audit_report = await self.auditor.audit(updated_skill, trajectories=all_trajectories)
                audit_passed = audit_report.passed
                severity_color = "green" if audit_passed else "red"
                console.print(
                    f"  Audit: [{severity_color}]{audit_report.overall.value}[/{severity_color}] "
                    f"— {audit_report.summary}"
                )
            else:
                audit_report = None

            if audit_passed and self.config.evolution.held_out_gate and held_out:
                console.print("[dim]Scoring held-out split...[/dim]")
                baseline = await self._score_tasks(skill, held_out)
                candidate = await self._score_tasks(updated_skill, held_out)
                verdict = check_regression(
                    baseline, candidate, self.config.evolution.gate_tolerance
                )
                held_out_passed = verdict.passed
                gate_summary = verdict.summary
                console.print(f"  Held-out gate: {verdict.summary}")
                if not held_out_passed:
                    console.print("  [yellow]Held-out regression — rolling back patch[/yellow]")

            if audit_passed and held_out_passed:
                skill.body = updated_skill.body
                skill.appendix = updated_skill.appendix
                skill.metadata.description = updated_skill.metadata.description
            else:
                console.print("  [yellow]Rolling back patch, feeding findings as signals[/yellow]")
                changelog = ""
                if audit_report is not None and not audit_passed:
                    audit_signals = self._audit_findings_to_signals(audit_report)
                    signals.extend(audit_signals)
                    logger.info(
                        "Round %d audit failed: rolled back patch, generated %d feedback signals",
                        round_num, len(audit_signals),
                    )

        successes = sum(1 for t in all_trajectories if t.outcome == TaskOutcome.SUCCESS)
        return RoundReport(
            round_num=round_num,
            strategies_generated=k * len(train),
            trajectories_total=len(all_trajectories),
            trajectories_success=successes,
            trajectories_failure=len(all_trajectories) - successes,
            signals_extracted=len(signals),
            audit_passed=audit_passed,
            changelog=changelog,
            cost_estimate=self.llm.usage.estimated_cost_usd,
            held_out_passed=held_out_passed,
            gate_summary=gate_summary,
        )

    async def _score_tasks(self, skill: Skill, tasks: list[TaskSpec]) -> dict[str, float]:
        """Score a skill on a task split with a single follow-skill strategy."""
        scorer = PerTaskEvaluator(self.evaluator)
        scores: dict[str, float] = {}
        for task in tasks:
            traj = await self.executor.execute(
                task_description=task.prompt,
                skill_text=skill.full_text,
                strategy=FOLLOW_SKILL,
                package_dir=skill.package_dir,
                script_paths=skill.script_paths,
            )
            result = scorer.evaluate_task(task, traj.response)
            scores[task.id] = result.score
        return scores

    @staticmethod
    def _audit_findings_to_signals(report: AuditReport) -> list[DeltaSignal]:
        """Convert audit findings into DeltaSignals for the next evolution round."""
        signals = []
        for finding in report.findings:
            if finding.severity == AuditSeverity.PASS:
                continue
            signals.append(DeltaSignal(
                category="wrong_approach" if finding.severity == AuditSeverity.FAIL else "edge_case",
                description=f"Audit [{finding.check}]: {finding.description}",
                evidence=finding.suggestion or "See audit finding",
                confidence=0.9 if finding.severity == AuditSeverity.FAIL else 0.6,
                affects="body",
            ))
        return signals

    def _over_budget(self) -> bool:
        """Check if we've exceeded the configured budget."""
        budget = self.config.evolution.budget_usd
        if budget is None:
            return False
        return self.llm.usage.estimated_cost_usd >= budget
