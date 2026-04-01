"""Rich display formatters for catalyst events."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from .catalyst_models import CatalystEvent

console = Console()


def display_catalyst_table(events: list[CatalystEvent]) -> None:
    """Display catalyst events in a Rich table."""
    if not events:
        console.print("[dim]No upcoming catalyst events found.[/dim]")
        return

    table = Table(title="Upcoming Catalysts")
    table.add_column("Days", justify="right", style="bold")
    table.add_column("Symbol", style="cyan")
    table.add_column("Event", style="white")
    table.add_column("Date", style="white")
    table.add_column("Impact", justify="center")
    table.add_column("Source", style="dim")
    table.add_column("Status", justify="center")

    for e in events:
        # Color coding for days_until
        if e.days_until < 7:
            days_style = "bold red"
        elif e.days_until <= 30:
            days_style = "yellow"
        else:
            days_style = "green"

        # Impact styling
        if e.impact == "high":
            impact_str = "[red]HIGH[/red]"
        elif e.impact == "medium":
            impact_str = "[yellow]MED[/yellow]"
        else:
            impact_str = "[dim]LOW[/dim]"

        # Confirmed vs estimated
        status_str = "✓" if e.confirmed else "~est"

        table.add_row(
            f"[{days_style}]{e.days_until}d[/{days_style}]",
            e.symbol or "[dim]Market[/dim]",
            e.description[:50],
            str(e.event_date),
            impact_str,
            e.source,
            status_str,
        )

    console.print(table)
