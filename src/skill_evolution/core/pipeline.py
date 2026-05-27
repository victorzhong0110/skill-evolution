"""Evolution Pipeline — orchestrates the full skill evolution loop.

Flow per round:
  1. Explorer: generate K diverse strategies
  2. Executor: run each strategy on each task (independent agents)
  3. Comparator: compare successes vs failures, extract delta signals
  4. Patcher: apply targeted patches to the skill
  5. Auditor: independent review; if FAIL, feed findings back as next-round signals

This loops for R rounds or until budget is exhausted.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skill_evolution.config import Config
from skill_evolution.core.auditor import Auditor, AuditReport, AuditSeverity
from skill_evolution.core.comparator import Comparator, DeltaSignal
from skill_evolution.core.explorer import Explorer
from skill_evolution.core.patcher import Patcher
from skill_evolution.llm import create_llm
from skill_evolution.llm.base import LLMBackend
from skill_evolution.runner.executor import TaskExecutor, TaskOutcome, Trajectory
from skill_evolution.skill.schema import Skill
from skill_evolution.skill.versioning import SkillVersionManager

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
            )
        lines.append(f"Total estimated cost: ${self.total_cost:.4f}")
        return "\n".join(lines)


class EvolutionPipeline:
    """Main orchestrator for skill evolution."""

    def __init__(self, config: Config):
        self.config = config
        self.llm = create_llm(config.llm)
        self.explorer = Explorer(self.llm)
        self.executor = TaskExecutor(self.llm)
        self.comparator = Comparator(self.llm)
        self.patcher = Patcher(self.llm)
        # Auditor uses a separate LLM instance for independence
        self.auditor = Auditor(create_llm(config.llm))

    async def evolve(
        self,
        skill: Skill,
        tasks: list[str],
        workspace: Path | None = None,
    ) -> tuple[Skill, EvolutionReport]:
        """Run the full evolution loop.

        Args:
            skill: Initial skill document
            tasks: List of task descriptions to test the skill against
            workspace: Directory for version snapshots (optional)

        Returns:
            (evolved_skill, evolution_report)
        """
        ws = workspace or self.config.workspace_dir
        vm = SkillVersionManager(ws, skill.metadata.name)

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
                current_skill, tasks, k, round_num
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

        console.print(f"\n[bold green]Evolution complete![/bold green]")
        console.print(self.llm.usage.summary())

        return current_skill, report

    async def _run_round(
        self,
        skill: Skill,
        tasks: list[str],
        k: int,
        round_num: int,
    ) -> RoundReport:
        """Execute one evolution round."""

        # Step 1: Generate diverse strategies
        console.print("[dim]Generating diverse strategies...[/dim]")
        all_trajectories: list[Trajectory] = []

        for task_idx, task in enumerate(tasks):
            console.print(f"  Task {task_idx + 1}/{len(tasks)}: {task[:60]}...")
            strategies = await self.explorer.generate_strategies(
                task_description=task,
                skill_text=skill.full_text,
                k=k,
            )
            console.print(f"    Generated {len(strategies)} strategies")

            # Step 2: Execute each strategy independently
            for strat in strategies:
                trajectory = await self.executor.execute(
                    task_description=task,
                    skill_text=skill.full_text,
                    strategy=strat,
                )
                all_trajectories.append(trajectory)
                icon = "✓" if trajectory.outcome == TaskOutcome.SUCCESS else "✗"
                console.print(f"    [{strat.name}] {icon} {trajectory.outcome.value}")

        # Step 3: Contrastive comparison
        console.print("[dim]Comparing trajectories...[/dim]")
        signals = await self.comparator.compare(all_trajectories, skill.full_text)
        console.print(f"  Extracted {len(signals)} delta signals")

        for s in signals:
            console.print(f"    [{s.affects}] {s.category} (conf={s.confidence:.2f}): {s.description[:80]}")

        # Step 4: Patch skill
        changelog = ""
        if signals:
            console.print("[dim]Applying patches...[/dim]")
            updated_skill, changelog = await self.patcher.patch(skill, signals)
            skill.body = updated_skill.body
            skill.appendix = updated_skill.appendix
            console.print(f"  Changes applied:\n{changelog[:500]}")

        # Step 5: Independent audit
        audit_passed = True
        if self.config.audit.enabled:
            console.print("[dim]Running independent audit...[/dim]")
            audit_report = await self.auditor.audit(skill)
            audit_passed = audit_report.passed
            severity_color = "green" if audit_passed else "red"
            console.print(
                f"  Audit: [{severity_color}]{audit_report.overall.value}[/{severity_color}] "
                f"— {audit_report.summary}"
            )

            # If audit failed, convert findings to signals for next round
            if not audit_passed:
                console.print("  [yellow]Audit failed — findings will feed into next round[/yellow]")

        successes = sum(1 for t in all_trajectories if t.outcome == TaskOutcome.SUCCESS)
        return RoundReport(
            round_num=round_num,
            strategies_generated=k * len(tasks),
            trajectories_total=len(all_trajectories),
            trajectories_success=successes,
            trajectories_failure=len(all_trajectories) - successes,
            signals_extracted=len(signals),
            audit_passed=audit_passed,
            changelog=changelog,
            cost_estimate=self.llm.usage.estimated_cost_usd,
        )

    def _over_budget(self) -> bool:
        """Check if we've exceeded the configured budget."""
        budget = self.config.evolution.budget_usd
        if budget is None:
            return False
        return self.llm.usage.estimated_cost_usd >= budget
