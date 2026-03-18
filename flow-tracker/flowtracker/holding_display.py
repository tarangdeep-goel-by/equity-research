"""Rich display formatters for NSE shareholding pattern data."""

from __future__ import annotations

from itertools import groupby

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.holding_models import ShareholdingChange, ShareholdingRecord, WatchlistEntry

console = Console()


def display_watchlist(entries: list[WatchlistEntry]) -> None:
    """Show watchlist as a simple table."""
    if not entries:
        console.print("[yellow]Watchlist is empty. Use 'flowtrack holding add SYMBOL' to add stocks.[/]")
        return

    table = Table(title="Watchlist", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", width=4)
    table.add_column("Symbol", style="bold", width=12)
    table.add_column("Company", width=30)
    table.add_column("Added", width=12)

    for i, entry in enumerate(entries, 1):
        table.add_row(
            str(i),
            entry.symbol,
            entry.company_name or "—",
            entry.added_at[:10] if entry.added_at else "—",
        )

    console.print(table)


def display_shareholding(symbol: str, records: list[ShareholdingRecord]) -> None:
    """Show shareholding history: quarters as columns, categories as rows, with color-coded changes."""
    if not records:
        console.print(f"[yellow]No shareholding data for {symbol}.[/]")
        return

    # Group by quarter, get unique quarters (most recent first)
    sorted_records = sorted(records, key=lambda r: r.quarter_end, reverse=True)
    quarters: list[str] = []
    by_quarter: dict[str, dict[str, float]] = {}

    for r in sorted_records:
        if r.quarter_end not in by_quarter:
            quarters.append(r.quarter_end)
            by_quarter[r.quarter_end] = {}
        by_quarter[r.quarter_end][r.category] = r.percentage

    categories = ["Promoter", "FII", "DII", "MF", "Insurance", "Public"]

    table = Table(
        title=f"Shareholding Pattern — {symbol}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Category", style="bold", width=12)

    for q in quarters:
        table.add_column(q, justify="right", width=12)

    for cat in categories:
        row: list[str | Text] = [cat]
        vals = [(q, by_quarter[q].get(cat)) for q in quarters]

        for i, (q, val) in enumerate(vals):
            if val is None:
                row.append("—")
            else:
                # Compare with next column (which is the previous quarter since quarters are newest-first)
                next_val = vals[i + 1][1] if i + 1 < len(vals) else None
                if next_val is not None:
                    change = val - next_val
                    if abs(change) >= 0.01:
                        color = "green" if change > 0 else "red"
                        row.append(Text(f"{val:.2f}%", style=color))
                    else:
                        row.append(f"{val:.2f}%")
                else:
                    row.append(f"{val:.2f}%")

        table.add_row(*row)

    console.print(table)


def display_holding_changes(changes: list[ShareholdingChange]) -> None:
    """Show biggest shareholding changes, sorted by |change|, green for increase, red for decrease."""
    if not changes:
        console.print("[yellow]No shareholding changes found.[/]")
        return

    table = Table(
        title="Shareholding Changes",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Symbol", style="bold", width=12)
    table.add_column("Category", width=10)
    table.add_column("Prev Qtr", width=12)
    table.add_column("Prev %", justify="right", width=10)
    table.add_column("Curr Qtr", width=12)
    table.add_column("Curr %", justify="right", width=10)
    table.add_column("Change", justify="right", width=10)

    for c in changes:
        change_color = "green" if c.change_pct > 0 else "red" if c.change_pct < 0 else "dim"
        change_text = Text(f"{c.change_pct:+.2f}%", style=f"bold {change_color}")

        table.add_row(
            c.symbol,
            c.category,
            c.prev_quarter_end,
            f"{c.prev_pct:.2f}%",
            c.curr_quarter_end,
            f"{c.curr_pct:.2f}%",
            change_text,
        )

    console.print(table)


def display_holding_fetch_result(symbol: str, records: list[ShareholdingRecord]) -> None:
    """Show confirmation after fetching shareholding data."""
    if not records:
        console.print(f"[yellow]No shareholding data fetched for {symbol}.[/]")
        return

    quarters = sorted({r.quarter_end for r in records}, reverse=True)
    console.print(f"\n[bold]Fetched shareholding for {symbol}[/]")
    console.print(f"  {len(records)} records across {len(quarters)} quarters")
    for q in quarters:
        q_records = [r for r in records if r.quarter_end == q]
        console.print(f"  [dim]{q}:[/] {', '.join(f'{r.category}={r.percentage:.1f}%' for r in q_records)}")
    console.print()
