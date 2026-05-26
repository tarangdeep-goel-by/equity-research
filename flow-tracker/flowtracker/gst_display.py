"""Rich display formatters for monthly GST collections.

Two surfaces:

* ``display_gst_latest`` — single-row "headline" panel showing the most
  recent month with the gross collection, YoY%, and the component split.
* ``display_gst_trend`` — table of N months, newest-first, with the YoY
  column color-coded (green ≥ 10%, yellow 5-10%, red < 5%).

Both surfaces are pure presentation — they accept already-resolved data
(GSTCollectionMonth instances or dicts) and never read from the DB.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.gst_client import period_to_display
from flowtracker.gst_models import GSTCollectionMonth

console = Console()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_cr(val: float | None) -> str:
    """Render an INR-crore value with thousand separators, or em-dash if None."""
    if val is None:
        return "[dim]—[/dim]"
    return f"₹{val:,.0f} cr"


def _fmt_cr_short(val: float | None) -> str:
    """Compact crore rendering for table cells (drop the ₹ prefix)."""
    if val is None:
        return "[dim]—[/dim]"
    return f"{val:,.0f}"


def _color_yoy(pct: float | None) -> str:
    """Color-code the YoY growth percentage.

    Strong (>= 10%) → green, mid (5-10%) → yellow, weak (< 5%) → red,
    None → dim em-dash. The thresholds mirror the macro briefings used by
    the markets pulse and have proven legible in tmux panes."""
    if pct is None:
        return "[dim]—[/dim]"
    if pct >= 10:
        color = "green"
    elif pct >= 5:
        color = "yellow"
    else:
        color = "red"
    sign = "+" if pct >= 0 else ""
    return f"[{color}]{sign}{pct:.1f}%[/{color}]"


# ---------------------------------------------------------------------------
# Public surfaces
# ---------------------------------------------------------------------------


def display_gst_latest(row: GSTCollectionMonth | None) -> None:
    """Show the most recent GST collection as a one-panel headline.

    Empty input prints a dim hint rather than an empty panel — the most
    common cause is a fresh DB before the first ``flowtrack gst fetch``."""
    if row is None:
        console.print(
            "[dim]No GST collection data in store. Run 'flowtrack gst fetch' first.[/dim]",
        )
        return

    parts = [
        f"[bold]Gross:[/bold] {_fmt_cr(row.gross_collection_cr)}",
        f"[bold]YoY:[/bold] {_color_yoy(row.growth_yoy_pct)}",
        f"[bold]CGST:[/bold] {_fmt_cr(row.cgst_cr)}",
        f"[bold]SGST:[/bold] {_fmt_cr(row.sgst_cr)}",
        f"[bold]IGST:[/bold] {_fmt_cr(row.igst_cr)}",
        f"[bold]Cess:[/bold] {_fmt_cr(row.cess_cr)}",
    ]
    if row.domestic_cr is not None or row.imports_cr is not None:
        parts.append(
            f"[bold]Domestic:[/bold] {_fmt_cr(row.domestic_cr)} | "
            f"[bold]Imports:[/bold] {_fmt_cr(row.imports_cr)}",
        )

    body = "\n".join(parts)
    console.print(
        Panel(
            body,
            title=f"GST Collection — {period_to_display(row.period)}",
            border_style="cyan",
        ),
    )
    if row.source_url:
        console.print(f"[dim]Source: {row.source_url}[/dim]")


def display_gst_trend(rows: list[dict] | list[GSTCollectionMonth]) -> None:
    """Render an N-month trend table, newest first, with YoY color-coded.

    Accepts either GSTCollectionMonth instances or plain dicts from
    ``FlowStore.get_gst_trend()`` — the table cell builders normalize via
    attribute-or-key lookup so the same display works for both.
    """
    if not rows:
        console.print("[yellow]No GST collection data found.[/yellow]")
        return

    table = Table(
        title="GST Collections — Monthly Trend",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Period", style="cyan", width=10)
    table.add_column("Gross (₹ cr)", justify="right", width=14)
    table.add_column("YoY %", justify="right", width=10)
    table.add_column("CGST", justify="right", width=10)
    table.add_column("SGST", justify="right", width=10)
    table.add_column("IGST", justify="right", width=10)
    table.add_column("Cess", justify="right", width=9)
    table.add_column("Domestic", justify="right", width=11)
    table.add_column("Imports", justify="right", width=10)

    def _get(r: dict | GSTCollectionMonth, key: str):
        if isinstance(r, dict):
            return r.get(key)
        return getattr(r, key, None)

    for r in rows:
        table.add_row(
            period_to_display(_get(r, "period")),
            _fmt_cr_short(_get(r, "gross_collection_cr")),
            _color_yoy(_get(r, "growth_yoy_pct")),
            _fmt_cr_short(_get(r, "cgst_cr")),
            _fmt_cr_short(_get(r, "sgst_cr")),
            _fmt_cr_short(_get(r, "igst_cr")),
            _fmt_cr_short(_get(r, "cess_cr")),
            _fmt_cr_short(_get(r, "domestic_cr")),
            _fmt_cr_short(_get(r, "imports_cr")),
        )

    console.print(table)
    console.print(f"[dim]{len(rows)} month(s).[/dim]")


def display_gst_fetch_result(upserted: int, period: str | None = None) -> None:
    """Brief post-fetch status panel."""
    label = f" for {period_to_display(period)}" if period else ""
    console.print(
        Panel(
            f"Upserted {upserted} GST collection row(s){label}.",
            title="GST Fetch Complete",
            border_style="green",
        ),
    )
