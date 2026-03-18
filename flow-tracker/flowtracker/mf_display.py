"""Rich display formatters for AMFI mutual fund flow data."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.mf_models import AMFIReportRow, MFAUMSummary, MFMonthlyFlow
from flowtracker.utils import fmt_crores

console = Console()


def _colored_value(value: float) -> Text:
    """Return a Rich Text with green (positive) or red (negative) coloring."""
    color = "green" if value >= 0 else "red"
    return Text(fmt_crores(value), style=color)


def display_mf_fetch_result(rows: list[AMFIReportRow], month: str) -> None:
    """Show confirmation after fetching AMFI data."""
    if not rows:
        console.print("[yellow]No data fetched.[/]")
        return

    # Count by category
    cats: dict[str, int] = {}
    for r in rows:
        cats[r.category] = cats.get(r.category, 0) + 1

    console.print(f"\n[bold]Fetched AMFI data for {month}[/]")
    console.print(f"  {len(rows)} sub-category rows across {len(cats)} categories")
    for cat, count in sorted(cats.items()):
        console.print(f"  [dim]{cat}:[/] {count} rows")
    console.print()


def display_mf_summary(summary: MFAUMSummary) -> None:
    """Show latest month's MF AUM summary with equity % of total."""
    equity_pct = (summary.equity_aum / summary.total_aum * 100) if summary.total_aum > 0 else 0

    table = Table(show_header=True, header_style="bold cyan", show_lines=False)
    table.add_column("Category", style="bold", width=14)
    table.add_column("AUM (Cr)", justify="right", width=14)
    table.add_column("% of Total", justify="right", width=12)
    table.add_column("Net Flow (Cr)", justify="right", width=14)

    rows_data = [
        ("Equity", summary.equity_aum, summary.equity_net_flow),
        ("Debt", summary.debt_aum, summary.debt_net_flow),
        ("Hybrid", summary.hybrid_aum, summary.hybrid_net_flow),
        ("Other", summary.other_aum, 0.0),
    ]

    for cat, aum, flow in rows_data:
        pct = (aum / summary.total_aum * 100) if summary.total_aum > 0 else 0
        table.add_row(
            cat,
            fmt_crores(aum),
            f"{pct:.1f}%",
            _colored_value(flow) if flow != 0 else Text("\u2014", style="dim"),
        )

    table.add_section()
    table.add_row(
        "[bold]Total[/]",
        Text(fmt_crores(summary.total_aum), style="bold"),
        "100.0%",
        Text("", style="dim"),
    )

    title = f"MF Industry AUM \u2014 {summary.month}"
    subtitle = f"Equity share: {equity_pct:.1f}%"
    console.print(Panel(table, title=title, subtitle=subtitle, border_style="blue"))


def display_mf_flows_table(flows: list[MFMonthlyFlow], period: str) -> None:
    """Show monthly MF flows table with category breakdown."""
    if not flows:
        console.print("[yellow]No MF flow data available.[/]")
        return

    table = Table(
        title=f"MF Flows \u2014 Last {period}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Month", style="bold", width=10)
    table.add_column("Category", width=10)
    table.add_column("Sub-Category", width=24)
    table.add_column("Net Flow (Cr)", justify="right", width=14)
    table.add_column("AUM (Cr)", justify="right", width=14)

    for flow in flows:
        table.add_row(
            flow.month,
            flow.category,
            flow.sub_category,
            _colored_value(flow.net_flow),
            fmt_crores(flow.aum) if flow.aum else "\u2014",
        )

    console.print(table)


def display_mf_aum_trend(summaries: list[MFAUMSummary]) -> None:
    """Show AUM trend over time with equity/debt/hybrid breakdown."""
    if not summaries:
        console.print("[yellow]No AUM trend data available.[/]")
        return

    table = Table(
        title="MF AUM Trend",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Month", style="bold", width=10)
    table.add_column("Total AUM (Cr)", justify="right", width=16)
    table.add_column("Equity (Cr)", justify="right", width=14)
    table.add_column("Equity %", justify="right", width=10)
    table.add_column("Debt (Cr)", justify="right", width=14)
    table.add_column("Hybrid (Cr)", justify="right", width=14)
    table.add_column("Eq Net Flow", justify="right", width=14)

    # Show oldest first for trend
    for s in reversed(summaries):
        eq_pct = (s.equity_aum / s.total_aum * 100) if s.total_aum > 0 else 0
        table.add_row(
            s.month,
            fmt_crores(s.total_aum),
            fmt_crores(s.equity_aum),
            f"{eq_pct:.1f}%",
            fmt_crores(s.debt_aum),
            fmt_crores(s.hybrid_aum),
            _colored_value(s.equity_net_flow),
        )

    console.print(table)
