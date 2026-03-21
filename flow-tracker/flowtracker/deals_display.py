"""Rich display formatters for bulk/block deals."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.deals_models import BulkBlockDeal

console = Console()


def display_deals_summary(deals: list[BulkBlockDeal]) -> None:
    """Show deals grouped by type."""
    if not deals:
        console.print("[yellow]No deals found.[/]")
        return

    date_str = deals[0].date if deals else ""

    table = Table(
        title=f"Bulk/Block Deals — {date_str}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Type", width=6)
    table.add_column("Symbol", width=14)
    table.add_column("Client", width=30)
    table.add_column("B/S", width=5)
    table.add_column("Quantity", justify="right", width=12)
    table.add_column("Price", justify="right", width=10)

    for d in sorted(deals, key=lambda x: (x.deal_type, x.symbol)):
        bs_color = "green" if d.buy_sell == "BUY" else "red" if d.buy_sell == "SELL" else ""
        bs_text = f"[{bs_color}]{d.buy_sell or '—'}[/{bs_color}]" if bs_color else (d.buy_sell or "—")

        table.add_row(
            d.deal_type,
            d.symbol,
            (d.client_name or "—")[:30],
            bs_text,
            f"{d.quantity:,}",
            f"{d.price:,.2f}" if d.price else "—",
        )

    console.print(table)


def display_deals_stock(deals: list[BulkBlockDeal], symbol: str) -> None:
    """Show deal history for a specific stock."""
    if not deals:
        console.print(f"[yellow]No deals found for {symbol}.[/]")
        return

    table = Table(
        title=f"Deal History — {symbol}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Type", width=6)
    table.add_column("Client", width=30)
    table.add_column("B/S", width=5)
    table.add_column("Quantity", justify="right", width=12)
    table.add_column("Price", justify="right", width=10)

    for d in deals:
        bs_color = "green" if d.buy_sell == "BUY" else "red" if d.buy_sell == "SELL" else ""
        bs_text = f"[{bs_color}]{d.buy_sell or '—'}[/{bs_color}]" if bs_color else (d.buy_sell or "—")

        table.add_row(
            d.date,
            d.deal_type,
            (d.client_name or "—")[:30],
            bs_text,
            f"{d.quantity:,}",
            f"{d.price:,.2f}" if d.price else "—",
        )

    console.print(table)


def display_deals_top(deals: list[BulkBlockDeal]) -> None:
    """Show biggest deals by value."""
    if not deals:
        console.print("[yellow]No deals found.[/]")
        return

    table = Table(
        title="Top Deals by Value",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Symbol", width=14)
    table.add_column("Client", width=28)
    table.add_column("B/S", width=5)
    table.add_column("Value Cr", justify="right", width=12)
    table.add_column("Quantity", justify="right", width=12)
    table.add_column("Price", justify="right", width=10)

    for d in deals:
        value_cr = (d.quantity * d.price / 1e7) if d.price else 0
        bs_color = "green" if d.buy_sell == "BUY" else "red" if d.buy_sell == "SELL" else ""
        bs_text = f"[{bs_color}]{d.buy_sell or '—'}[/{bs_color}]" if bs_color else (d.buy_sell or "—")

        table.add_row(
            d.date,
            d.symbol,
            (d.client_name or "—")[:28],
            bs_text,
            f"{value_cr:,.2f}" if d.price else "—",
            f"{d.quantity:,}",
            f"{d.price:,.2f}" if d.price else "—",
        )

    console.print(table)


def display_deals_fetch_result(count: int) -> None:
    """Show deals fetch result summary."""
    console.print(Panel(
        f"Fetched {count} deals",
        title="Deals Fetch Complete",
        border_style="green",
    ))
