"""Rich table renderers for market-breadth output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from flowtracker.breadth_models import BreadthSnapshot

console = Console()


def _fmt_pct(val: float | None) -> str:
    return f"{val:.1f}%" if val is not None else "—"


def _fmt_ratio(val: float | None) -> str:
    return f"{val:.2f}" if val is not None else "—"


def _color_pct_above_200(val: float | None) -> str:
    """Color-coded pct-above-200DMA — Baid's bear-bottom indicator.

    <20% green (oversold / capitulation zone), 20-50% yellow,
    >50% white/bold (broad participation), >75% magenta (frothy).
    """
    if val is None:
        return "—"
    if val < 20:
        return f"[green]{val:.1f}%[/green]"
    if val < 50:
        return f"[yellow]{val:.1f}%[/yellow]"
    if val < 75:
        return f"[white]{val:.1f}%[/white]"
    return f"[magenta]{val:.1f}%[/magenta]"


def display_breadth_latest(snapshots: list[BreadthSnapshot]) -> None:
    """Show latest breadth for several indices side-by-side."""
    if not snapshots:
        console.print(
            "[yellow]No breadth data. "
            "Run 'flowtrack breadth recompute' first.[/]"
        )
        return

    # All snapshots should share `date`; if mixed, show each.
    dates = sorted({s.date for s in snapshots})
    title = f"Market Breadth — {dates[-1]}" if dates else "Market Breadth"

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Index", style="bold", width=22)
    table.add_column("Total", justify="right", width=6)
    table.add_column("% > 200DMA", justify="right", width=12)
    table.add_column("Adv", justify="right", width=5, style="green")
    table.add_column("Dec", justify="right", width=5, style="red")
    table.add_column("Unch", justify="right", width=5)
    table.add_column("A/D", justify="right", width=6)
    table.add_column("52w Hi", justify="right", width=7)
    table.add_column("52w Lo", justify="right", width=7)
    table.add_column("Date", width=12)

    for s in snapshots:
        table.add_row(
            s.index_name,
            str(s.total),
            _color_pct_above_200(s.pct_above_200dma),
            str(s.advance),
            str(s.decline),
            str(s.unchanged),
            _fmt_ratio(s.ad_ratio),
            str(s.new_52w_highs),
            str(s.new_52w_lows),
            s.date,
        )

    console.print(table)


def display_breadth_trend(
    snapshots: list[BreadthSnapshot], index_name: str,
) -> None:
    """Show breadth trend for one index across N days (newest first)."""
    if not snapshots:
        console.print(
            f"[yellow]No breadth data for {index_name}. "
            "Run 'flowtrack breadth recompute' first.[/]"
        )
        return

    table = Table(
        title=f"Breadth Trend — {index_name}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Total", justify="right", width=6)
    table.add_column("% > 200DMA", justify="right", width=12)
    table.add_column("Adv", justify="right", width=5, style="green")
    table.add_column("Dec", justify="right", width=5, style="red")
    table.add_column("A/D", justify="right", width=6)
    table.add_column("52w Hi", justify="right", width=7)
    table.add_column("52w Lo", justify="right", width=7)

    for s in snapshots:
        table.add_row(
            s.date,
            str(s.total),
            _color_pct_above_200(s.pct_above_200dma),
            str(s.advance),
            str(s.decline),
            _fmt_ratio(s.ad_ratio),
            str(s.new_52w_highs),
            str(s.new_52w_lows),
        )

    console.print(table)


def display_recompute_result(
    written: int, dates: int, indices: int,
) -> None:
    """Summarize a recompute/backfill run."""
    console.print(
        f"[green]Upserted {written} breadth snapshots "
        f"({dates} date(s) × {indices} index/indices).[/]"
    )
