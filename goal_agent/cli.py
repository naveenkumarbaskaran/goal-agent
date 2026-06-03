"""CLI for Goal Agent — add goals, check in, view status, complete tasks."""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from .agent import GoalAgent
from .tracker import GoalTracker

console = Console()


def _make_agent(goals_file: str) -> GoalAgent:
    """Instantiate GoalAgent, exiting gracefully if the API key is missing."""
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[bold red]Error:[/bold red] ANTHROPIC_API_KEY environment variable is not set."
        )
        sys.exit(1)
    return GoalAgent(goals_path=goals_file)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option(
    "--goals-file",
    default="goals.json",
    show_default=True,
    help="Path to the goals JSON file.",
)
@click.pass_context
def cli(ctx: click.Context, goals_file: str) -> None:
    """Goal Agent — AI-powered goal tracking and nudging."""
    ctx.ensure_object(dict)
    ctx.obj["goals_file"] = goals_file


# ---------------------------------------------------------------------------
# add command
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("goal_description")
@click.pass_context
def add(ctx: click.Context, goal_description: str) -> None:
    """Add a new goal and let the AI decompose it into milestones and tasks.

    Example:

        goal-agent add "Run a marathon in 6 months"
    """
    agent = _make_agent(ctx.obj["goals_file"])
    console.print(Panel(f"[bold cyan]Adding goal:[/bold cyan] {goal_description}", expand=False))

    with console.status("[bold green]Thinking...[/bold green]", spinner="dots"):
        result = agent.add_goal(goal_description)

    console.print(Panel(result, title="[bold green]Goal Plan[/bold green]", border_style="green"))


# ---------------------------------------------------------------------------
# checkin command
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def checkin(ctx: click.Context) -> None:
    """Get your daily check-in: tasks due this week, progress, and nudges."""
    agent = _make_agent(ctx.obj["goals_file"])
    console.print(Panel("[bold cyan]Daily Check-In[/bold cyan]", expand=False))

    with console.status("[bold green]Checking in...[/bold green]", spinner="dots"):
        result = agent.daily_checkin()

    console.print(Panel(result, title="[bold yellow]Today's Briefing[/bold yellow]", border_style="yellow"))


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show progress summary for all goals."""
    goals_file = ctx.obj["goals_file"]
    tracker = GoalTracker(goals_file)
    prog = tracker.progress()

    if not prog["goals"]:
        # Ask the AI for a friendly message if there are no goals
        agent = _make_agent(goals_file)
        with console.status("[bold green]Loading status...[/bold green]", spinner="dots"):
            result = agent.status()
        console.print(Panel(result, title="Status", border_style="blue"))
        return

    # Build a Rich table directly from tracker data (no LLM call needed)
    table = Table(title="Goal Progress", box=box.ROUNDED, show_lines=True)
    table.add_column("Goal", style="bold", no_wrap=False)
    table.add_column("Tasks Done", justify="right")
    table.add_column("Total Tasks", justify="right")
    table.add_column("Progress", justify="right")
    table.add_column("Milestones", justify="right")

    for g in prog["goals"]:
        pct = g["completion_pct"]
        colour = "green" if pct >= 75 else ("yellow" if pct >= 40 else "red")
        table.add_row(
            g["title"],
            str(g["completed_tasks"]),
            str(g["total_tasks"]),
            f"[{colour}]{pct}%[/{colour}]",
            f"{g['milestones_done']}/{g['milestones_total']}",
        )

    overall = prog["overall"]
    console.print(table)
    console.print(
        f"\nOverall: [bold]{overall['completed_tasks']}/{overall['total_tasks']}[/bold] tasks "
        f"([bold cyan]{overall['completion_pct']}%[/bold cyan])"
    )


# ---------------------------------------------------------------------------
# complete command
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("task_id")
@click.pass_context
def complete(ctx: click.Context, task_id: str) -> None:
    """Mark a task as complete by its ID.

    The task ID is the UUID shown in goals.json or output from the status command.
    """
    goals_file = ctx.obj["goals_file"]
    tracker = GoalTracker(goals_file)

    # Try fast local path first
    if tracker.complete_task(task_id):
        console.print(f"[bold green]Done![/bold green] Task [cyan]{task_id}[/cyan] marked as completed.")
        # Show updated progress
        prog = tracker.progress()
        overall = prog["overall"]
        console.print(
            f"Overall progress: [bold cyan]{overall['completion_pct']}%[/bold cyan] "
            f"({overall['completed_tasks']}/{overall['total_tasks']} tasks)"
        )
    else:
        console.print(
            f"[bold red]Error:[/bold red] Task [cyan]{task_id}[/cyan] not found. "
            "Check the ID with [bold]goal-agent status[/bold] or inspect goals.json directly."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# list-tasks command (bonus — useful for finding task IDs)
# ---------------------------------------------------------------------------


@cli.command("list-tasks")
@click.option("--pending-only", is_flag=True, default=False, help="Show only incomplete tasks.")
@click.pass_context
def list_tasks(ctx: click.Context, pending_only: bool) -> None:
    """List all tasks with their IDs (useful for the complete command)."""
    tracker = GoalTracker(ctx.obj["goals_file"])
    completed_filter = False if pending_only else None
    tasks = tracker.list_tasks(completed=completed_filter)

    if not tasks:
        console.print("[yellow]No tasks found.[/yellow]")
        return

    table = Table(title="Tasks", box=box.SIMPLE_HEAD, show_lines=False)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Goal", style="bold")
    table.add_column("Task", no_wrap=False)
    table.add_column("Week", justify="right")
    table.add_column("Done", justify="center")

    for task in tasks:
        done_str = "[green]✓[/green]" if task["completed"] else "[red]✗[/red]"
        table.add_row(
            task["id"][:8] + "...",  # truncated UUID for readability
            task.get("_goal_title", "?"),
            task["title"],
            str(task.get("week", "?")),
            done_str,
        )

    console.print(table)
    console.print(f"[dim]Showing {len(tasks)} task(s). Use the full UUID with [bold]complete <task_id>[/bold].[/dim]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
