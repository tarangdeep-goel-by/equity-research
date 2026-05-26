"""Rich display formatters for monthly CPI inflation.

Two surfaces:

* ``display_cpi_latest`` — one-panel headline showing the most recent month.
* ``display_cpi_trend`` — N-month table, newest first, with YoY% colored
  against the RBI's 4% target band (green: in-band, yellow: 4-6%,
  red: > 6% or < 0%).
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.cpi_client import period_to_display
from flowtracker.cpi_models import CPIMonth

console = Console()


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "[dim]—[/dim]"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def _color_yoy(pct: float | None) -> str:
    """RBI MPC inflation band coloring: 2-6% band, 4% target.

    Below 4 (or > 0%) → green (at-target / below).
    4-6% → yellow (above target but within band).
    > 6% → red (above upper tolerance).
    """
    if pct is None:
        return "[dim]—[/dim]"
    sign = "+" if pct >= 0 else ""
    if pct < 0:
        color = "red"
    elif pct <= 4.0:
        color = "green"
    elif pct <= 6.0:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{sign}{pct:.2f}%[/{color}]"


def _fmt_index(val: float | None) -> str:
    if val is None:
        return "[dim]—[/dim]"
    return f"{val:.2f}"


def display_cpi_latest(row: CPIMonth | None) -> None:
    if row is None:
        console.print(
            "[dim]No CPI data in store. Run 'flowtrack cpi fetch' first.[/dim]",
        )
        return
    parts = [
        f"[bold]Index:[/bold] {_fmt_index(row.cpi_index)}",
        f"[bold]YoY:[/bold] {_color_yoy(row.yoy_pct)}",
        f"[bold]Source:[/bold] {row.source}",
    ]
    body = "  ".join(parts)
    console.print(Panel(
        body,
        title=f"India CPI — {period_to_display(row.period)}",
        border_style="cyan",
    ))
    if row.source_url:
        console.print(f"[dim]Source: {row.source_url}[/dim]")


def display_cpi_trend(rows: list[dict] | list[CPIMonth]) -> None:
    if not rows:
        console.print("[yellow]No CPI data found.[/yellow]")
        return
    table = Table(
        title="India CPI — Monthly Trend (Above 6% = breach, 2-6% = target band)",
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
            _fmt_index(_get(r, "cpi_index")),
            _color_yoy(_get(r, "yoy_pct")),
            str(_get(r, "source") or "—"),
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} month(s).[/dim]")


def display_cpi_fetch_result(upserted: int, period: str | None = None) -> None:
    label = f" for {period_to_display(period)}" if period else ""
    console.print(Panel(
        f"Upserted {upserted} CPI row(s){label}.",
        title="CPI Fetch Complete",
        border_style="green",
    ))
