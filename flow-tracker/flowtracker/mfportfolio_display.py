"""Rich display formatters for MF scheme portfolio holdings."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.mfportfolio_models import MFSchemeHolding, MFHoldingChange

console = Console()


def display_mfport_fetch_result(count: int, month: str, amcs: list[str]) -> None:
    """Show fetch result summary."""
    console.print(Panel(
        f"Fetched {count:,} holdings for {month} from {', '.join(amcs)}",
        title="MF Portfolio Fetch Complete",
        border_style="green",
    ))


def display_stock_holdings(
    holdings: list[MFSchemeHolding], symbol_or_isin: str,
) -> None:
    """Show which MF schemes hold a particular stock."""
    if not holdings:
        console.print(f"[yellow]No MF holdings found for {symbol_or_isin}.[/]")
        return

    table = Table(
        title=f"MF Holdings — {symbol_or_isin}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Month", width=8)
    table.add_column("AMC", width=6)
    table.add_column("Scheme", width=28)
    table.add_column("Qty", justify="right", width=12)
    table.add_column("Value ₹L", justify="right", width=12)
    table.add_column("% NAV", justify="right", width=7)

    for h in holdings:
        table.add_row(
            h.month,
            h.amc,
            h.scheme_name[:28],
            f"{h.quantity:,}",
            f"{h.market_value_lakhs:,.0f}",
            f"{h.pct_of_nav:.2f}%",
        )

    console.print(table)


def display_top_changes(changes: list[MFHoldingChange], title: str) -> None:
    """Show top MF holding changes (buys or exits)."""
    if not changes:
        console.print("[yellow]No holding changes found.[/]")
        return

    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Stock", width=22)
    table.add_column("AMC", width=6)
    table.add_column("Scheme", width=22)
    table.add_column("Type", width=8)
    table.add_column("Qty Chg", justify="right", width=12)
    table.add_column("Value Chg ₹L", justify="right", width=12)

    for c in changes:
        type_color = {
            "NEW": "bold green", "EXIT": "bold red",
            "INCREASE": "green", "DECREASE": "red",
        }.get(c.change_type, "")
        type_str = f"[{type_color}]{c.change_type}[/{type_color}]" if type_color else c.change_type

        val_chg = c.curr_value - c.prev_value
        val_color = "green" if val_chg >= 0 else "red"

        table.add_row(
            c.stock_name[:22],
            c.amc,
            c.scheme_name[:22],
            type_str,
            f"{c.qty_change:+,}",
            f"[{val_color}]{val_chg:+,.0f}[/{val_color}]",
        )

    console.print(table)


def display_amc_summary(summary: list[dict]) -> None:
    """Show AMC-level summary for a month.

    Each dict: {amc, num_schemes, num_stocks, total_value_lakhs}
    """
    if not summary:
        console.print("[yellow]No portfolio data found.[/]")
        return

    table = Table(
        title="MF Portfolio Summary by AMC",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("AMC", width=8)
    table.add_column("Schemes", justify="right", width=8)
    table.add_column("Stocks", justify="right", width=8)
    table.add_column("Total Value ₹Cr", justify="right", width=14)

    for s in summary:
        table.add_row(
            s["amc"],
            str(s["num_schemes"]),
            str(s["num_stocks"]),
            f"{s['total_value_lakhs'] / 100:,.0f}",  # lakhs to crores
        )

    console.print(table)
