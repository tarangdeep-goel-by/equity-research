"""Rich display formatters for macro indicator data."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.macro_models import MacroSnapshot

console = Console()


def display_macro_summary(snapshot: MacroSnapshot, prev: MacroSnapshot | None) -> None:
    """Show latest macro indicators with colored deltas."""
    parts: list[str] = []

    def _fmt(label: str, val: float | None, prev_val: float | None, fmt: str = ".2f",
             prefix: str = "", invert: bool = False) -> str:
        if val is None:
            return f"{label}: [dim]—[/]"
        s = f"{label}: {prefix}{val:{fmt}}"
        if prev_val is not None:
            delta = val - prev_val
            # For VIX, up = bad (red), down = good (green) → invert
            color = ("green" if delta < 0 else "red") if invert else ("green" if delta >= 0 else "red")
            sign = "+" if delta >= 0 else ""
            s += f" [{color}]({sign}{delta:{fmt}})[/{color}]"
        return s

    parts.append(_fmt("VIX", snapshot.india_vix,
                       prev.india_vix if prev else None, invert=True))
    parts.append(_fmt("USD/INR", snapshot.usd_inr,
                       prev.usd_inr if prev else None))
    parts.append(_fmt("Brent", snapshot.brent_crude,
                       prev.brent_crude if prev else None, prefix="$"))
    parts.append(_fmt("10Y", snapshot.gsec_10y,
                       prev.gsec_10y if prev else None, fmt=".2f"))

    line = " | ".join(parts)
    console.print(Panel(
        line,
        title=f"Macro Indicators — {snapshot.date}",
        border_style="cyan",
    ))


def display_macro_trend(snapshots: list[MacroSnapshot]) -> None:
    """Show macro indicator trend as a table."""
    if not snapshots:
        console.print("[yellow]No macro data found.[/]")
        return

    table = Table(
        title="Macro Indicators Trend",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("India VIX", justify="right", width=10)
    table.add_column("USD/INR", justify="right", width=10)
    table.add_column("Brent USD", justify="right", width=10)
    table.add_column("10Y G-sec", justify="right", width=10)

    prev: MacroSnapshot | None = None
    # snapshots are most recent first; iterate in reverse for prev logic
    for i, s in enumerate(snapshots):
        next_s = snapshots[i + 1] if i + 1 < len(snapshots) else None

        vix_text = _colored_val(s.india_vix, next_s.india_vix if next_s else None, invert=True)
        usd_text = _colored_val(s.usd_inr, next_s.usd_inr if next_s else None)
        brent_text = _colored_val(s.brent_crude, next_s.brent_crude if next_s else None)
        gsec_text = f"{s.gsec_10y:.2f}%" if s.gsec_10y else "—"

        table.add_row(s.date, vix_text, usd_text, brent_text, gsec_text)

    console.print(table)


def _colored_val(
    val: float | None, prev_val: float | None, invert: bool = False,
) -> str:
    """Format a value with color based on change direction."""
    if val is None:
        return "—"
    s = f"{val:.2f}"
    if prev_val is not None:
        delta = val - prev_val
        if delta != 0:
            color = ("green" if delta < 0 else "red") if invert else ("green" if delta > 0 else "red")
            return f"[{color}]{s}[/{color}]"
    return s


def display_macro_fetch_result(count: int) -> None:
    """Show macro fetch result summary."""
    console.print(Panel(
        f"Fetched {count} macro snapshots",
        title="Macro Fetch Complete",
        border_style="green",
    ))
