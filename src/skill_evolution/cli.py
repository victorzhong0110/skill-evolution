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
@click.option("--provider", "-p", type=click.Choice(["claude", "openai"]), default=None)
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
@click.option("--provider", "-p", type=click.Choice(["claude", "openai"]), default=None)
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


if __name__ == "__main__":
    main()
