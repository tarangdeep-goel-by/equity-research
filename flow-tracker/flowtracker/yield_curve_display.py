"""Rich display formatters for the India G-sec yield curve.

Two surfaces:

* ``display_yield_curve`` — single-snapshot table showing 1Y / 5Y / 10Y /
  30Y yields + computed slopes (10Y-1Y, 30Y-10Y in basis points).
* ``display_yield_curve_trend`` — N-period table showing how each tenor
  has evolved over time.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _fmt_yield(val: float | None) -> str:
    if val is None:
        return "[dim]—[/dim]"
    return f"{val:.2f}%"


def _color_slope(bps: float | None) -> str:
    """Slope coloring: negative = red (inversion), 0-50bps = yellow
    (flat), > 50bps = green (normal upward-sloping)."""
    if bps is None:
        return "[dim]—[/dim]"
    sign = "+" if bps >= 0 else ""
    if bps < 0:
        color = "red"
    elif bps < 50:
        color = "yellow"
    else:
        color = "green"
    return f"[{color}]{sign}{bps:.0f}bps[/{color}]"


def display_yield_curve(row: dict | None) -> None:
    """Show today's (or most-recent) full G-sec curve as a headline panel."""
    if row is None:
        console.print(
            "[dim]No yield-curve data in store. Run 'flowtrack macro fetch' "
            "or 'flowtrack yield-curve backfill' first.[/dim]",
        )
        return

    g1, g5, g10, g30 = (
        row.get("gsec_1y"), row.get("gsec_5y"),
        row.get("gsec_10y"), row.get("gsec_30y"),
    )
    slope_10y_1y = (
        round((g10 - g1) * 100, 0) if (g10 is not None and g1 is not None) else None
    )
    slope_30y_10y = (
        round((g30 - g10) * 100, 0) if (g30 is not None and g10 is not None) else None
    )

    parts = [
        f"[bold]1Y:[/bold] {_fmt_yield(g1)}",
        f"[bold]5Y:[/bold] {_fmt_yield(g5)}",
        f"[bold]10Y:[/bold] {_fmt_yield(g10)}",
        f"[bold]30Y:[/bold] {_fmt_yield(g30)}",
        f"[bold]10Y-1Y:[/bold] {_color_slope(slope_10y_1y)}",
        f"[bold]30Y-10Y:[/bold] {_color_slope(slope_30y_10y)}",
    ]
    body = "  ".join(parts)
    console.print(Panel(
        body,
        title=f"India G-sec Yield Curve — {row.get('date', '?')}",
        border_style="cyan",
    ))


def display_yield_curve_trend(rows: list[dict]) -> None:
    """Render N-period yield-curve trend (date ASC since users read top-down)."""
    if not rows:
        console.print("[yellow]No yield-curve history found.[/yellow]")
        return
    table = Table(
        title="India G-sec Yield Curve — Trend",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", style="cyan", width=12)
    table.add_column("1Y", justify="right", width=8)
    table.add_column("5Y", justify="right", width=8)
    table.add_column("10Y", justify="right", width=8)
    table.add_column("30Y", justify="right", width=8)
    table.add_column("10Y-1Y", justify="right", width=10)

    for r in rows:
        g1, g10 = r.get("gsec_1y"), r.get("gsec_10y")
        slope = (
            round((g10 - g1) * 100, 0)
            if (g10 is not None and g1 is not None) else None
        )
        table.add_row(
            r.get("date", "?"),
            _fmt_yield(g1),
            _fmt_yield(r.get("gsec_5y")),
            _fmt_yield(g10),
            _fmt_yield(r.get("gsec_30y")),
            _color_slope(slope),
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} observation(s).[/dim]")
