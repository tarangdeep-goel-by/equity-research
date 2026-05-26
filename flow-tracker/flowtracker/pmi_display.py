"""Rich display formatters for monthly India PMI (Services + Manufacturing)."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.pmi_client import period_to_display
from flowtracker.pmi_models import PMIMonth

console = Console()


def _color_pmi(val: float | None) -> str:
    """PMI coloring: < 50 contraction = red, 50-52 = yellow, > 52 = green.

    A 50 print is technically unchanged — we treat 50 and 51.9 alike since
    'just barely' expansion isn't an analytically interesting distinction
    in monthly data (within survey noise band)."""
    if val is None:
        return "[dim]—[/dim]"
    if val < 50:
        color = "red"
    elif val < 52:
        color = "yellow"
    else:
        color = "green"
    return f"[{color}]{val:.1f}[/{color}]"


def display_pmi_latest(row: PMIMonth | None) -> None:
    if row is None:
        console.print(
            "[dim]No PMI data in store. Run 'flowtrack pmi fetch' first.[/dim]",
        )
        return
    parts = [
        f"[bold]Services PMI:[/bold] {_color_pmi(row.services_pmi)}",
        f"[bold]Manufacturing PMI:[/bold] {_color_pmi(row.manufacturing_pmi)}",
        f"[bold]Source:[/bold] {row.source}",
    ]
    body = "  ".join(parts)
    console.print(Panel(
        body,
        title=f"India PMI — {period_to_display(row.period)} ({'>50 = expansion'})",
        border_style="cyan",
    ))
    if row.source_url:
        console.print(f"[dim]Source: {row.source_url}[/dim]")


def display_pmi_trend(rows: list[dict] | list[PMIMonth]) -> None:
    if not rows:
        console.print("[yellow]No PMI data found.[/yellow]")
        return
    table = Table(
        title="India PMI — Monthly Trend  (50 = neutral, <50 contraction, >52 strong expansion)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Period", style="cyan", width=10)
    table.add_column("Services", justify="right", width=10)
    table.add_column("Manufacturing", justify="right", width=14)
    table.add_column("Source", justify="left", width=12)

    def _get(r, key):
        if isinstance(r, dict):
            return r.get(key)
        return getattr(r, key, None)

    for r in rows:
        table.add_row(
            period_to_display(_get(r, "period")),
            _color_pmi(_get(r, "services_pmi")),
            _color_pmi(_get(r, "manufacturing_pmi")),
            str(_get(r, "source") or "—"),
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} month(s).[/dim]")


def display_pmi_fetch_result(upserted: int, period: str | None = None) -> None:
    label = f" for {period_to_display(period)}" if period else ""
    console.print(Panel(
        f"Upserted {upserted} PMI row(s){label}.",
        title="PMI Fetch Complete",
        border_style="green",
    ))
