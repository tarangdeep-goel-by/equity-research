"""Rich display formatters for monthly IIP (industrial production)."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.iip_client import period_to_display
from flowtracker.iip_models import IIPMonth

console = Console()


def _fmt_index(val: float | None) -> str:
    if val is None:
        return "[dim]—[/dim]"
    return f"{val:.1f}"


def _color_yoy(pct: float | None) -> str:
    """IIP YoY coloring: contraction = red, weak < 3 = yellow,
    healthy 3-7 = green, exceptional > 7 = bright green."""
    if pct is None:
        return "[dim]—[/dim]"
    sign = "+" if pct >= 0 else ""
    if pct < 0:
        color = "red"
    elif pct < 3:
        color = "yellow"
    else:
        color = "green"
    return f"[{color}]{sign}{pct:.1f}%[/{color}]"


def display_iip_latest(row: IIPMonth | None) -> None:
    if row is None:
        console.print(
            "[dim]No IIP data in store. Run 'flowtrack iip fetch' first.[/dim]",
        )
        return
    parts = [
        f"[bold]Index:[/bold] {_fmt_index(row.iip_index)}",
        f"[bold]YoY:[/bold] {_color_yoy(row.yoy_pct)}",
        f"[bold]Source:[/bold] {row.source}",
    ]
    body = "  ".join(parts)
    console.print(Panel(
        body,
        title=f"India IIP (General) — {period_to_display(row.period)}",
        border_style="cyan",
    ))
    if row.source_url:
        console.print(f"[dim]Source: {row.source_url}[/dim]")


def display_iip_trend(rows: list[dict] | list[IIPMonth]) -> None:
    if not rows:
        console.print("[yellow]No IIP data found.[/yellow]")
        return
    table = Table(
        title="India IIP General — Monthly Trend",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Period", style="cyan", width=10)
    table.add_column("Index", justify="right", width=10)
    table.add_column("YoY %", justify="right", width=10)
    table.add_column("Source", justify="left", width=12)

    def _get(r, key):
        if isinstance(r, dict):
            return r.get(key)
        return getattr(r, key, None)

    for r in rows:
        table.add_row(
            period_to_display(_get(r, "period")),
            _fmt_index(_get(r, "iip_index")),
            _color_yoy(_get(r, "yoy_pct")),
            str(_get(r, "source") or "—"),
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} month(s).[/dim]")


def display_iip_fetch_result(upserted: int, period: str | None = None) -> None:
    label = f" for {period_to_display(period)}" if period else ""
    console.print(Panel(
        f"Upserted {upserted} IIP row(s){label}.",
        title="IIP Fetch Complete",
        border_style="green",
    ))
