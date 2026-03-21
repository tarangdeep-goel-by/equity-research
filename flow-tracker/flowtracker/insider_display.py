"""Rich display formatters for insider/SAST transactions."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.insider_models import InsiderTransaction

console = Console()


def display_insider_trades(
    trades: list[InsiderTransaction], title: str = "Insider Transactions",
) -> None:
    """Show insider transactions as a Rich table."""
    if not trades:
        console.print("[yellow]No insider transactions found.[/]")
        return

    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Symbol", width=12)
    table.add_column("Person", width=22)
    table.add_column("Category", width=12)
    table.add_column("Type", width=6)
    table.add_column("Qty", justify="right", width=10)
    table.add_column("Value Cr", justify="right", width=10)
    table.add_column("Mode", width=14)

    for t in trades:
        txn_color = "green" if t.transaction_type == "Buy" else "red" if t.transaction_type == "Sell" else ""
        txn_str = (
            f"[{txn_color}]{t.transaction_type}[/{txn_color}]"
            if txn_color else t.transaction_type
        )

        # Value in crores (input is INR)
        value_cr = t.value / 1e7 if t.value else 0

        table.add_row(
            t.date,
            t.symbol,
            t.person_name[:22],
            t.person_category[:12],
            txn_str,
            f"{t.quantity:,}",
            f"{value_cr:,.2f}",
            (t.mode or "—")[:14],
        )

    console.print(table)


def display_promoter_buys(trades: list[InsiderTransaction]) -> None:
    """Show promoter buying activity."""
    if not trades:
        console.print("[yellow]No promoter buying activity found.[/]")
        return

    display_insider_trades(trades, title="Promoter Buying (Highest Conviction Signal)")


def display_insider_fetch_result(count: int) -> None:
    """Show insider fetch result summary."""
    console.print(Panel(
        f"Fetched {count} insider transactions",
        title="Insider Fetch Complete",
        border_style="green",
    ))
