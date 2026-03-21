"""Rich display formatters for bhavcopy + delivery data."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.bhavcopy_models import DailyStockData

console = Console()


def display_bhavcopy_fetch_result(count: int, date_str: str) -> None:
    """Show bhavcopy fetch result summary."""
    console.print(Panel(
        f"Fetched {count} stock records for {date_str}",
        title="Bhavcopy Fetch Complete",
        border_style="green",
    ))


def display_top_delivery(records: list[DailyStockData], date_str: str) -> None:
    """Show stocks with highest delivery % for a date."""
    if not records:
        console.print("[yellow]No delivery data found.[/]")
        return

    table = Table(
        title=f"Top Delivery % — {date_str}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Symbol", width=14)
    table.add_column("Close", justify="right", width=10)
    table.add_column("Chg%", justify="right", width=8)
    table.add_column("Volume", justify="right", width=14)
    table.add_column("Delivery%", justify="right", width=10)
    table.add_column("Turnover ₹L", justify="right", width=12)

    for r in records:
        # Price change %
        chg = ((r.close - r.prev_close) / r.prev_close * 100) if r.prev_close else 0
        chg_color = "green" if chg >= 0 else "red"
        chg_str = f"[{chg_color}]{chg:+.2f}%[/{chg_color}]"

        # Delivery % coloring
        dpct = r.delivery_pct or 0
        if dpct >= 60:
            del_color = "green"
        elif dpct >= 40:
            del_color = "yellow"
        else:
            del_color = "red"
        del_str = f"[{del_color}]{dpct:.1f}%[/{del_color}]" if r.delivery_pct else "—"

        table.add_row(
            r.symbol,
            f"{r.close:,.2f}",
            chg_str,
            f"{r.volume:,}",
            del_str,
            f"{r.turnover:,.0f}",
        )

    console.print(table)


def display_delivery_trend(records: list[DailyStockData], symbol: str) -> None:
    """Show delivery % trend for a specific stock."""
    if not records:
        console.print(f"[yellow]No delivery data for {symbol}.[/]")
        return

    table = Table(
        title=f"Delivery Trend — {symbol}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Close", justify="right", width=10)
    table.add_column("Chg%", justify="right", width=8)
    table.add_column("Volume", justify="right", width=14)
    table.add_column("Delivery%", justify="right", width=10)
    table.add_column("Turnover ₹L", justify="right", width=12)

    for r in records:
        chg = ((r.close - r.prev_close) / r.prev_close * 100) if r.prev_close else 0
        chg_color = "green" if chg >= 0 else "red"
        chg_str = f"[{chg_color}]{chg:+.2f}%[/{chg_color}]"

        dpct = r.delivery_pct or 0
        if dpct >= 60:
            del_color = "green"
        elif dpct >= 40:
            del_color = "yellow"
        else:
            del_color = "red"
        del_str = f"[{del_color}]{dpct:.1f}%[/{del_color}]" if r.delivery_pct else "—"

        table.add_row(
            r.date,
            f"{r.close:,.2f}",
            chg_str,
            f"{r.volume:,}",
            del_str,
            f"{r.turnover:,.0f}",
        )

    console.print(table)


def display_backfill_result(count: int, start: str, end: str) -> None:
    """Show backfill result summary."""
    console.print(Panel(
        f"Backfilled {count} records from {start} to {end}",
        title="Bhavcopy Backfill Complete",
        border_style="green",
    ))
