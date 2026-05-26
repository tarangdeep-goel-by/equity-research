"""Rich display formatters for index-level valuation (PE/PB/Div Yield)."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.indexpe_models import IndexValuation

console = Console()


def display_indexpe_fetch_result(index_name: str, count: int) -> None:
    """Summary panel printed after a fetch / backfill."""
    console.print(Panel(
        f"Upserted {count} rows for [bold cyan]{index_name}[/]",
        title="Index PE/PB Fetch Complete",
        border_style="green",
    ))


def display_indexpe_current(snapshot: IndexValuation | None) -> None:
    """Single-row valuation snapshot."""
    if snapshot is None:
        console.print("[yellow]No index-valuation data. Run 'flowtrack indexpe fetch' first.[/]")
        return
    body = (
        f"PE: [bold]{_fmt(snapshot.pe)}[/]   "
        f"PB: [bold]{_fmt(snapshot.pb)}[/]   "
        f"Div Yield: [bold]{_fmt(snapshot.dividend_yield)}%[/]"
    )
    console.print(Panel(
        body,
        title=f"{snapshot.index_name} — {snapshot.date}",
        border_style="cyan",
    ))


def display_indexpe_trend(snapshots: list[IndexValuation], days: int) -> None:
    """Tabular trend over the last N days."""
    if not snapshots:
        console.print("[yellow]No index-valuation data for the requested range.[/]")
        return

    table = Table(
        title=f"{snapshots[-1].index_name} — last {days} days",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("PE", justify="right", width=10)
    table.add_column("PB", justify="right", width=10)
    table.add_column("Div Yield %", justify="right", width=12)

    # iterate newest-first for display
    for s in reversed(snapshots):
        table.add_row(s.date, _fmt(s.pe), _fmt(s.pb), _fmt(s.dividend_yield))

    console.print(table)


def display_indexpe_percentile(payload: dict) -> None:
    """Percentile chart-style summary against the full distribution."""
    if not payload:
        console.print(
            "[yellow]No index-valuation data. "
            "Run 'flowtrack indexpe backfill --period 10y --index <NAME>' first.[/]"
        )
        return

    current = payload.get("current", {}) or {}
    median = payload.get("median_10y", {}) or {}

    table = Table(
        title=(
            f"{payload['index_name']} valuation regime "
            f"(as of {payload.get('as_of_date')}, n={payload.get('sample_size')} obs"
            f", {payload.get('history_start')} → {payload.get('history_end')})"
        ),
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Metric", width=15)
    table.add_column("Current", justify="right", width=10)
    table.add_column("Median", justify="right", width=10)
    table.add_column("Percentile", justify="right", width=12)
    table.add_column("Premium/Discount", justify="right", width=20)

    for label, key in (("PE", "pe"), ("PB", "pb"), ("Div Yield %", "dividend_yield")):
        cur = current.get(key)
        med = median.get(key)
        pct_key = {"pe": "pe_percentile", "pb": "pb_percentile", "dividend_yield": "divy_percentile"}[key]
        pctile = payload.get(pct_key)
        prem = _premium_str(cur, med)
        table.add_row(
            label,
            _fmt(cur),
            _fmt(med),
            _pctile_str(pctile),
            prem,
        )

    console.print(table)

    # Plain-English regime hint, driven by the PE percentile.
    pe_pct = payload.get("pe_percentile")
    if pe_pct is not None:
        if pe_pct >= 90:
            verdict = "[bold red]EXTREMELY RICH[/] — top decile of history"
        elif pe_pct >= 75:
            verdict = "[red]RICH[/] — top quartile of history"
        elif pe_pct >= 50:
            verdict = "[yellow]ABOVE MEDIAN[/]"
        elif pe_pct >= 25:
            verdict = "[green]BELOW MEDIAN[/]"
        else:
            verdict = "[bold green]CHEAP[/] — bottom quartile of history"
        console.print(f"PE regime: {verdict}")


def _fmt(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:.2f}"


def _pctile_str(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:.1f}%"


def _premium_str(cur: float | None, med: float | None) -> str:
    if cur is None or med is None or med == 0:
        return "—"
    pct = (cur - med) / med * 100.0
    color = "red" if pct > 0 else "green"
    sign = "+" if pct >= 0 else ""
    return f"[{color}]{sign}{pct:.1f}%[/]"
