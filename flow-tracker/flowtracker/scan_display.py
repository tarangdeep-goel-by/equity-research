"""Rich display formatters for scanner operations."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.holding_models import ShareholdingChange
from flowtracker.scan_models import BatchFetchResult, IndexConstituent, ScanSummary

console = Console()


def display_constituents(constituents: list[IndexConstituent]) -> None:
    """Show index constituents as a table."""
    if not constituents:
        console.print("[yellow]No constituents found.[/]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", width=4)
    table.add_column("Symbol", style="bold", width=12)
    table.add_column("Index", width=18)
    table.add_column("Company", width=30)
    table.add_column("Industry", width=20)

    for i, c in enumerate(constituents, 1):
        table.add_row(
            str(i),
            c.symbol,
            c.index_name,
            c.company_name or "—",
            c.industry or "—",
        )

    console.print(table)


def display_scan_deviations(changes: list[ShareholdingChange]) -> None:
    """Show shareholding deviations found by the scanner."""
    if not changes:
        console.print("[yellow]No shareholding deviations found.[/]")
        return

    table = Table(
        title="Scanner — Shareholding Deviations",
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


def display_handoff_signals(handoffs: list[tuple[ShareholdingChange, ShareholdingChange]]) -> None:
    """Show FII selling + MF buying handoff signals."""
    if not handoffs:
        console.print("[yellow]No handoff signals found.[/]")
        return

    table = Table(
        title="Handoff Signals — FII Selling + MF Buying",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Symbol", style="bold", width=12)
    table.add_column("Quarter", width=12)
    table.add_column("FII Prev%", justify="right", width=10)
    table.add_column("FII Curr%", justify="right", width=10)
    table.add_column("FII Change", justify="right", width=10)
    table.add_column("MF Prev%", justify="right", width=10)
    table.add_column("MF Curr%", justify="right", width=10)
    table.add_column("MF Change", justify="right", width=10)

    for fii_change, mf_change in handoffs:
        fii_text = Text(f"{fii_change.change_pct:+.2f}%", style="bold red")
        mf_text = Text(f"{mf_change.change_pct:+.2f}%", style="bold green")

        table.add_row(
            fii_change.symbol,
            fii_change.curr_quarter_end,
            f"{fii_change.prev_pct:.2f}%",
            f"{fii_change.curr_pct:.2f}%",
            fii_text,
            f"{mf_change.prev_pct:.2f}%",
            f"{mf_change.curr_pct:.2f}%",
            mf_text,
        )

    console.print(table)


def display_scan_summary(summary: ScanSummary) -> None:
    """Show scanner coverage stats in a panel."""
    pct = (summary.symbols_with_data / summary.total_symbols * 100) if summary.total_symbols else 0
    quarter = summary.latest_quarter or "—"

    missing = ", ".join(summary.missing_symbols[:10]) if summary.missing_symbols else "None"
    if len(summary.missing_symbols) > 10:
        missing += f" ... (+{len(summary.missing_symbols) - 10} more)"

    content = (
        f"[bold]Total symbols:[/] {summary.total_symbols}\n"
        f"[bold]With data:[/] {summary.symbols_with_data}/{summary.total_symbols} ({pct:.0f}%)\n"
        f"[bold]Latest quarter:[/] {quarter}\n"
        f"[bold]Missing:[/] {missing}"
    )

    console.print(Panel(content, title="Scanner Status", border_style="cyan"))


def display_batch_result(result: BatchFetchResult) -> None:
    """Show batch fetch result summary in a panel."""
    border = "green" if result.failed == 0 else "yellow"

    content = f"Fetched {result.fetched} / Total {result.total} | Skipped: {result.skipped} | Failed: {result.failed}"

    if result.errors:
        content += "\n"
        for err in result.errors:
            content += f"\n[red]{err}[/]"

    console.print(Panel(content, title="Batch Fetch Complete", border_style=border))
