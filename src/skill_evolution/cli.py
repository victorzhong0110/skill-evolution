"""CLI entry point for skill-evolution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skill_evolution.config import Config
from skill_evolution.skill.schema import Skill
from skill_evolution.skill.versioning import SkillVersionManager

console = Console()


def _load_config(config_path: str | None) -> Config:
    """Load config from file or use defaults."""
    if config_path:
        return Config.load(Path(config_path))
    # Try default locations
    for candidate in [Path("skill-evolution.yaml"), Path(".skill-evolution/config.yaml")]:
        if candidate.exists():
            return Config.load(candidate)
    return Config()


def _load_tasks(task_path: str) -> list[str]:
    """Load task descriptions from a file (one per line or JSON array)."""
    path = Path(task_path)
    text = path.read_text(encoding="utf-8").strip()

    # Try JSON array first
    if text.startswith("["):
        return json.loads(text)

    # Otherwise, treat as one task per line (skip empty lines and comments)
    return [
        line.strip()
        for line in text.split("\n")
        if line.strip() and not line.strip().startswith("#")
    ]


@click.group()
@click.version_option(package_name="skill-evolution")
def main():
    """skill-evolution: Evolve AI agent skills through iterative optimization."""
    pass


@main.command()
@click.argument("skill_path", type=click.Path(exists=True))
@click.argument("tasks_path", type=click.Path(exists=True))
@click.option("--config", "-c", "config_path", type=click.Path(), default=None, help="Config YAML file")
@click.option("--rounds", "-r", type=int, default=None, help="Override number of evolution rounds")
@click.option("--strategies", "-k", type=int, default=None, help="Override number of strategies per task")
@click.option("--budget", "-b", type=float, default=None, help="Max budget in USD")
@click.option("--provider", "-p", type=click.Choice(["claude", "openai", "cli"]), default=None)
@click.option("--model", "-m", type=str, default=None, help="LLM model name")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output path for evolved skill")
@click.option("--workspace", "-w", type=click.Path(), default=None, help="Workspace directory for versioning")
def evolve(
    skill_path: str,
    tasks_path: str,
    config_path: str | None,
    rounds: int | None,
    strategies: int | None,
    budget: float | None,
    provider: str | None,
    model: str | None,
    output: str | None,
    workspace: str | None,
):
    """Evolve a skill using a set of test tasks.

    SKILL_PATH: Path to the initial skill document (.md)
    TASKS_PATH: Path to task descriptions (one per line or JSON array)
    """
    config = _load_config(config_path)

    # Apply CLI overrides
    if rounds is not None:
        config.evolution.num_rounds = rounds
    if strategies is not None:
        config.evolution.num_strategies = strategies
    if budget is not None:
        config.evolution.budget_usd = budget
    if provider is not None:
        config.llm.provider = provider
    if model is not None:
        config.llm.model = model

    # Load inputs
    skill = Skill.from_file(Path(skill_path))
    tasks = _load_tasks(tasks_path)

    console.print(Panel(
        f"[bold]Skill:[/bold] {skill.metadata.name}\n"
        f"[bold]Tasks:[/bold] {len(tasks)}\n"
        f"[bold]Rounds:[/bold] {config.evolution.num_rounds}\n"
        f"[bold]Strategies/task:[/bold] {config.evolution.num_strategies}\n"
        f"[bold]Provider:[/bold] {config.llm.provider} ({config.llm.model})\n"
        f"[bold]Budget:[/bold] {'$' + str(config.evolution.budget_usd) if config.evolution.budget_usd else 'unlimited'}",
        title="skill-evolution",
        border_style="cyan",
    ))

    # Run evolution
    from skill_evolution.core.pipeline import EvolutionPipeline
    ws = Path(workspace) if workspace else config.workspace_dir
    pipeline = EvolutionPipeline(config, workspace=ws)

    evolved_skill, report = asyncio.run(pipeline.evolve(skill, tasks, ws))

    # Save output
    output_path = Path(output) if output else Path(skill_path).with_suffix(".evolved.md")
    evolved_skill.save(output_path)
    console.print(f"\n[bold green]Evolved skill saved to:[/bold green] {output_path}")
    console.print(report.summary())


@main.command()
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--config", "-c", "config_path", type=click.Path(), default=None)
@click.option("--provider", "-p", type=click.Choice(["claude", "openai", "cli"]), default=None)
@click.option("--model", "-m", type=str, default=None)
def audit(skill_path: str, config_path: str | None, provider: str | None, model: str | None):
    """Run an independent audit on a skill document."""
    config = _load_config(config_path)
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model

    skill = Skill.from_file(Path(skill_path))

    from skill_evolution.core.auditor import Auditor
    from skill_evolution.llm import create_llm

    auditor = Auditor(create_llm(config.llm), workspace=config.workspace_dir)
    report = asyncio.run(auditor.audit(skill))

    # Display results
    table = Table(title=f"Audit: {skill.metadata.name}")
    table.add_column("Check", style="bold")
    table.add_column("Severity")
    table.add_column("Description")
    table.add_column("Suggestion", style="dim")

    for finding in report.findings:
        severity_style = {
            "pass": "green",
            "warning": "yellow",
            "fail": "red",
        }.get(finding.severity.value, "white")
        table.add_row(
            finding.check,
            f"[{severity_style}]{finding.severity.value}[/{severity_style}]",
            finding.description,
            finding.suggestion,
        )

    console.print(table)
    overall_style = "green" if report.passed else "red"
    console.print(f"\nOverall: [{overall_style}]{report.overall.value}[/{overall_style}] — {report.summary}")


@main.command()
@click.argument("skill_name")
@click.option("--workspace", "-w", type=click.Path(), default=".skill-evolution")
def history(skill_name: str, workspace: str):
    """Show version history for a skill."""
    vm = SkillVersionManager(Path(workspace), skill_name)
    entries = vm.history()

    if not entries:
        console.print(f"[yellow]No version history found for '{skill_name}'[/yellow]")
        return

    table = Table(title=f"Version History: {skill_name}")
    table.add_column("Version", style="bold")
    table.add_column("Hash")
    table.add_column("Round")
    table.add_column("Timestamp")
    table.add_column("Notes", style="dim")

    for entry in entries:
        table.add_row(
            f"v{entry.version:03d}",
            entry.content_hash,
            str(entry.evolution_round),
            entry.timestamp[:19],
            entry.notes[:60] + ("..." if len(entry.notes) > 60 else ""),
        )

    console.print(table)


@main.command()
@click.argument("skill_name")
@click.argument("version", type=int)
@click.option("--workspace", "-w", type=click.Path(), default=".skill-evolution")
def rollback(skill_name: str, version: int, workspace: str):
    """Rollback a skill to a previous version."""
    vm = SkillVersionManager(Path(workspace), skill_name)
    skill = vm.rollback(version)
    if skill:
        console.print(f"[green]Rolled back '{skill_name}' to v{version:03d}[/green]")
    else:
        console.print(f"[red]Version {version} not found for '{skill_name}'[/red]")


@main.command()
@click.option("--output", "-o", type=click.Path(), default="skill-evolution.yaml")
def init(output: str):
    """Generate a default configuration file."""
    config = Config()
    config.save(Path(output))
    console.print(f"[green]Config saved to {output}[/green]")


@main.command()
@click.option("--workspace", "-w", type=click.Path(), default=None)
def doctor(workspace: str | None):
    """Validate meta-skill files, placeholders, and test suites."""
    from skill_evolution.meta_skills.testing.loader import list_builtin_suites, load_builtin_suite

    ws = Path(workspace) if workspace else None
    issues: list[tuple[str, str]] = []  # (severity, message)
    checks_passed = 0

    meta_skills_dir = Path(__file__).parent / "meta_skills"
    meta_skill_names = [p.stem for p in meta_skills_dir.glob("*.md")]

    # Check: meta-skill files parse as valid Skill objects
    for name in meta_skill_names:
        path = meta_skills_dir / f"{name}.md"
        try:
            skill = Skill.from_file(path)
            if not skill.body.strip():
                issues.append(("WARN", f"Meta-skill '{name}' has empty body"))
            else:
                checks_passed += 1
                console.print(f"  [green]OK[/green] {name}.md parses correctly")
        except Exception as exc:
            issues.append(("FAIL", f"Meta-skill '{name}' failed to parse: {exc}"))

    # Check: {k} placeholder in strategy_generation
    sg_path = meta_skills_dir / "strategy_generation.md"
    if sg_path.exists():
        content = sg_path.read_text(encoding="utf-8")
        if "{k}" in content:
            checks_passed += 1
            console.print("  [green]OK[/green] strategy_generation.md contains {k} placeholder")
        else:
            issues.append(("FAIL", "strategy_generation.md missing {k} placeholder"))

    # Check: test suites load without errors
    for suite_name in list_builtin_suites():
        try:
            cases = load_builtin_suite(suite_name)
            has_adversarial = any("adversarial" in c.tags for c in cases)
            has_edge = any("edge_case" in c.tags for c in cases)
            checks_passed += 1
            console.print(f"  [green]OK[/green] Test suite '{suite_name}': {len(cases)} cases")
            if not has_adversarial:
                issues.append(("WARN", f"Test suite '{suite_name}' has no adversarial cases"))
            if not has_edge:
                issues.append(("WARN", f"Test suite '{suite_name}' has no edge cases"))
        except Exception as exc:
            issues.append(("FAIL", f"Test suite '{suite_name}' failed to load: {exc}"))

    # Check: workspace overrides (if workspace provided)
    if ws:
        ws_meta = ws / "meta_skills"
        if ws_meta.exists():
            for md in ws_meta.glob("*.md"):
                try:
                    Skill.from_file(md)
                    checks_passed += 1
                    console.print(f"  [green]OK[/green] Workspace override '{md.stem}' parses correctly")
                except Exception as exc:
                    issues.append(("FAIL", f"Workspace override '{md.stem}' failed: {exc}"))

    # Summary
    console.print()
    fails = [i for i in issues if i[0] == "FAIL"]
    warns = [i for i in issues if i[0] == "WARN"]

    for severity, msg in issues:
        style = "red" if severity == "FAIL" else "yellow"
        console.print(f"  [{style}]{severity}[/{style}] {msg}")

    console.print()
    if fails:
        console.print(f"[red]UNHEALTHY: {len(fails)} failures, {len(warns)} warnings, {checks_passed} passed[/red]")
        raise SystemExit(1)
    elif warns:
        console.print(f"[yellow]HEALTHY with warnings: {len(warns)} warnings, {checks_passed} passed[/yellow]")
    else:
        console.print(f"[green]HEALTHY: {checks_passed} checks passed[/green]")


@main.command("meta-evolve")
@click.option("--target", "-t", required=True, help="Meta-skill name (e.g., strategy_generation)")
@click.option("--config", "-c", "config_path", type=click.Path(), default=None)
@click.option("--suite", "-s", type=click.Path(exists=True), default=None, help="Custom test suite JSONL")
@click.option("--workspace", "-w", type=click.Path(), default=None)
@click.option("--tolerance", type=float, default=0.0, help="Allowed score drop before regression gate fails")
@click.option("--dry-run", is_flag=True, help="Run full cycle without writing changes")
@click.option("--provider", "-p", type=click.Choice(["claude", "openai", "cli"]), default=None)
@click.option("--model", "-m", type=str, default=None)
def meta_evolve(
    target: str,
    config_path: str | None,
    suite: str | None,
    workspace: str | None,
    tolerance: float,
    dry_run: bool,
    provider: str | None,
    model: str | None,
):
    """Evolve a meta-skill with regression safety.

    Runs: snapshot → baseline score → evolve → candidate score → gate → accept/rollback
    """
    config = _load_config(config_path)
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model

    from skill_evolution.core.meta_evolver import MetaSkillEvolver

    ws = Path(workspace) if workspace else config.workspace_dir
    evolver = MetaSkillEvolver(config, workspace=ws)
    suite_path = Path(suite) if suite else None

    result = asyncio.run(evolver.evolve(
        target=target,
        suite_path=suite_path,
        dry_run=dry_run,
        tolerance=tolerance,
    ))

    # Summary table
    table = Table(title=f"Meta-Evolution: {target}")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Accepted", "[green]Yes[/green]" if result.accepted else "[red]No[/red]")
    table.add_row("Baseline mean", f"{_scores_mean(result.baseline_scores):.3f}")
    table.add_row("Candidate mean", f"{_scores_mean(result.candidate_scores):.3f}")
    table.add_row("Gate", result.gate_verdict.summary)
    if result.version:
        table.add_row("Version", f"v{result.version:03d}")
    console.print(table)


@main.command("meta-test")
@click.option("--target", "-t", required=True, help="Meta-skill name")
@click.option("--config", "-c", "config_path", type=click.Path(), default=None)
@click.option("--suite", "-s", type=click.Path(exists=True), default=None, help="Custom test suite JSONL")
@click.option("--workspace", "-w", type=click.Path(), default=None)
@click.option("--provider", "-p", type=click.Choice(["claude", "openai", "cli"]), default=None)
@click.option("--model", "-m", type=str, default=None)
def meta_test(
    target: str,
    config_path: str | None,
    suite: str | None,
    workspace: str | None,
    provider: str | None,
    model: str | None,
):
    """Run a meta-skill's test suite and display scores.

    Calls the LLM with each test case and scores the output structurally.
    """
    config = _load_config(config_path)
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model

    from skill_evolution.core.meta_evolver import MetaSkillEvolver

    ws = Path(workspace) if workspace else config.workspace_dir
    evolver = MetaSkillEvolver(config, workspace=ws)

    skill = evolver._load_meta_skill_as_skill(target)
    suite_path = Path(suite) if suite else None
    scores = evolver.run_test_suite(target, skill.full_text, suite_path)

    table = Table(title=f"Meta-Test: {target}")
    table.add_column("Case", style="bold")
    table.add_column("Score")
    table.add_column("Status")

    for case_id, score in sorted(scores.items()):
        status = "[green]PASS[/green]" if score >= 0.8 else "[red]FAIL[/red]"
        table.add_row(case_id, f"{score:.3f}", status)

    table.add_row("", "", "")
    table.add_row("[bold]Mean[/bold]", f"[bold]{_scores_mean(scores):.3f}[/bold]", "")
    console.print(table)


@main.command("meta-snapshot")
@click.option("--target", "-t", required=True, help="Meta-skill name")
@click.option("--workspace", "-w", type=click.Path(), default=".skill-evolution")
@click.option("--history", "show_history", is_flag=True, help="Show evolution changelog with score trend")
def meta_snapshot(target: str, workspace: str, show_history: bool):
    """Show version history and scores for a meta-skill."""
    ws_path = Path(workspace)
    vm = SkillVersionManager(ws_path, f"meta-{target}")
    entries = vm.history()

    if not entries:
        console.print(f"[yellow]No snapshots found for meta-skill '{target}'[/yellow]")
        return

    table = Table(title=f"Meta-Skill Snapshots: {target}")
    table.add_column("Version", style="bold")
    table.add_column("Hash")
    table.add_column("Mean Score")
    table.add_column("Trend")
    table.add_column("Timestamp")
    table.add_column("Notes", style="dim")

    prev_mean = None
    for entry in entries:
        mean = _scores_mean(entry.scores) if entry.scores else None
        score_str = f"{mean:.3f}" if mean is not None else "—"
        if mean is not None and prev_mean is not None:
            delta = mean - prev_mean
            if delta > 0.01:
                trend = f"[green]+{delta:.3f}[/green]"
            elif delta < -0.01:
                trend = f"[red]{delta:.3f}[/red]"
            else:
                trend = "[dim]=[/dim]"
        else:
            trend = "—"
        table.add_row(
            f"v{entry.version:03d}",
            entry.content_hash,
            score_str,
            trend,
            entry.timestamp[:19],
            entry.notes[:50] + ("..." if len(entry.notes) > 50 else ""),
        )
        if mean is not None:
            prev_mean = mean

    console.print(table)

    if show_history:
        from skill_evolution.core.changelog import read_changelog_for_skill

        changelog = read_changelog_for_skill(ws_path, target)
        if not changelog:
            console.print("[dim]No changelog entries found[/dim]")
            return

        console.print()
        ht = Table(title=f"Evolution History: {target}")
        ht.add_column("Time", style="dim")
        ht.add_column("Action")
        ht.add_column("Baseline")
        ht.add_column("Candidate")
        ht.add_column("Delta")
        ht.add_column("Gate")

        for e in changelog:
            action_style = "green" if e.action == "accepted" else "red"
            delta_str = f"{e.delta:+.3f}"
            delta_style = "green" if e.delta > 0 else ("red" if e.delta < 0 else "dim")
            ht.add_row(
                e.timestamp[:19],
                f"[{action_style}]{e.action}[/{action_style}]",
                f"{e.baseline_mean:.3f}",
                f"{e.candidate_mean:.3f}",
                f"[{delta_style}]{delta_str}[/{delta_style}]",
                e.summary,
            )

        console.print(ht)


def _scores_mean(scores: dict[str, float]) -> float:
    vals = list(scores.values())
    return sum(vals) / len(vals) if vals else 0.0


if __name__ == "__main__":
    main()
