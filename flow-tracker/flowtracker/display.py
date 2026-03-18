"""Rich display formatters for flow tracker CLI output."""

from __future__ import annotations

from datetime import date
from itertools import groupby

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.models import DailyFlow, DailyFlowPair, StreakInfo
from flowtracker.utils import fmt_crores, fmt_crores_label, format_display_date

console = Console()


def _colored_value(value: float) -> Text:
    """Return a Rich Text with green (positive) or red (negative) coloring."""
    color = "green" if value >= 0 else "red"
    return Text(fmt_crores(value), style=color)


def display_fetch_result(flows: list[DailyFlow]) -> None:
    """Show confirmation after fetching data."""
    if not flows:
        console.print("[yellow]No data fetched.[/]")
        return

    flow_date = flows[0].date
    console.print(f"\n[bold]Fetched data for {format_display_date(flow_date)}[/]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Category", style="bold")
    table.add_column("Buy (Cr)", justify="right")
    table.add_column("Sell (Cr)", justify="right")
    table.add_column("Net (Cr)", justify="right")

    for f in sorted(flows, key=lambda x: x.category):
        table.add_row(
            f.category,
            fmt_crores(f.buy_value),
            fmt_crores(f.sell_value),
            _colored_value(f.net_value),
        )

    console.print(table)
    console.print(f"\n[dim]Stored {len(flows)} records.[/]")


def display_summary(pair: DailyFlowPair) -> None:
    """Show most recent day's FII/DII flows as a Rich Panel."""
    table = Table(show_header=True, header_style="bold cyan", show_lines=False)
    table.add_column("", style="bold", width=12)
    table.add_column("Buy (Cr)", justify="right")
    table.add_column("Sell (Cr)", justify="right")
    table.add_column("Net (Cr)", justify="right")

    for label, flow in [("FII", pair.fii), ("DII", pair.dii)]:
        table.add_row(
            label,
            fmt_crores(flow.buy_value),
            fmt_crores(flow.sell_value),
            _colored_value(flow.net_value),
        )

    # Add separator and net diff row
    table.add_section()
    diff = pair.fii_dii_net_diff
    diff_color = "green" if diff >= 0 else "red"
    table.add_row(
        "FII - DII",
        "",
        "",
        Text(fmt_crores(diff), style=f"bold {diff_color}"),
    )

    title = f"FII/DII Flows — {format_display_date(pair.date)}"
    console.print(Panel(table, title=title, border_style="blue"))


def display_flows_table(flows: list[DailyFlow], period_label: str) -> None:
    """Show historical flows table with totals row."""
    if not flows:
        display_no_data("Run 'flowtrack fetch' to get today's data.")
        return

    table = Table(
        title=f"FII/DII Flows — Last {period_label}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", style="bold")
    table.add_column("FII Buy", justify="right")
    table.add_column("FII Sell", justify="right")
    table.add_column("FII Net", justify="right")
    table.add_column("DII Net", justify="right")

    # Group flows by date
    sorted_flows = sorted(flows, key=lambda f: f.date, reverse=True)
    totals = {"fii_buy": 0.0, "fii_sell": 0.0, "fii_net": 0.0, "dii_net": 0.0}

    for dt, group in groupby(sorted_flows, key=lambda f: f.date):
        day_flows = {f.category: f for f in group}
        fii = day_flows.get("FII")
        dii = day_flows.get("DII")

        fii_buy = fii.buy_value if fii else 0.0
        fii_sell = fii.sell_value if fii else 0.0
        fii_net = fii.net_value if fii else 0.0
        dii_net = dii.net_value if dii else 0.0

        totals["fii_buy"] += fii_buy
        totals["fii_sell"] += fii_sell
        totals["fii_net"] += fii_net
        totals["dii_net"] += dii_net

        table.add_row(
            format_display_date(dt),
            fmt_crores(fii_buy),
            fmt_crores(fii_sell),
            _colored_value(fii_net),
            _colored_value(dii_net),
        )

    # Totals row
    table.add_section()
    table.add_row(
        "[bold]Total[/]",
        Text(fmt_crores(totals["fii_buy"]), style="bold"),
        Text(fmt_crores(totals["fii_sell"]), style="bold"),
        _colored_value(totals["fii_net"]),
        _colored_value(totals["dii_net"]),
    )

    console.print(table)


def display_streak(fii_streak: StreakInfo | None, dii_streak: StreakInfo | None) -> None:
    """Show current buying/selling streaks for FII and DII."""
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Category", style="bold")
    table.add_column("Direction")
    table.add_column("Days", justify="right")
    table.add_column("Cumulative Net (Cr)", justify="right")
    table.add_column("Since")

    for streak in [fii_streak, dii_streak]:
        if streak is None:
            continue
        dir_color = "green" if streak.direction == "buying" else "red"
        table.add_row(
            streak.category,
            Text(streak.direction.upper(), style=f"bold {dir_color}"),
            str(streak.days),
            _colored_value(streak.cumulative_net),
            format_display_date(streak.start_date),
        )

    if table.row_count == 0:
        display_no_data("Not enough data to determine streaks.")
        return

    console.print(Panel(table, title="FII/DII Streaks", border_style="blue"))


def display_no_data(suggestion: str) -> None:
    """Show a yellow warning when no data is available."""
    console.print(f"[yellow]No data available. {suggestion}[/]")
