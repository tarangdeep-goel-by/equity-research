"""Rich display formatters for portfolio tracking."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def display_portfolio_view(holdings: list[dict]) -> None:
    """Show all holdings with current value and P&L."""
    if not holdings:
        console.print("[yellow]No holdings in portfolio. Use 'flowtrack portfolio add' to start.[/]")
        return

    table = Table(
        title="Portfolio Holdings",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Symbol", width=12)
    table.add_column("Qty", justify="right", width=8)
    table.add_column("Avg Cost", justify="right", width=10)
    table.add_column("CMP", justify="right", width=10)
    table.add_column("Value", justify="right", width=12)
    table.add_column("P&L", justify="right", width=12)
    table.add_column("P&L%", justify="right", width=8)

    for h in holdings:
        cmp = h.get("cmp")
        qty = h["quantity"]
        cost = h["avg_cost"]
        invested = qty * cost

        if cmp:
            value = qty * cmp
            pnl = value - invested
            pnl_pct = (pnl / invested * 100) if invested > 0 else 0
            color = "green" if pnl >= 0 else "red"
            table.add_row(
                h["symbol"],
                str(qty),
                f"{cost:,.2f}",
                f"{cmp:,.2f}",
                f"{value:,.2f}",
                f"[{color}]{pnl:+,.2f}[/{color}]",
                f"[{color}]{pnl_pct:+.1f}%[/{color}]",
            )
        else:
            table.add_row(
                h["symbol"],
                str(qty),
                f"{cost:,.2f}",
                "—",
                "—",
                "—",
                "—",
            )

    console.print(table)


def display_portfolio_concentration(sectors: list[dict]) -> None:
    """Show sector breakdown by value weight."""
    if not sectors:
        console.print("[yellow]No sector data available.[/]")
        return

    table = Table(
        title="Sector Concentration",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Sector", min_width=20)
    table.add_column("Stocks", justify="right", width=8)
    table.add_column("Value", justify="right", width=12)
    table.add_column("Weight%", justify="right", width=10)

    for s in sectors:
        table.add_row(
            s["sector"],
            str(s["count"]),
            f"{s['value']:,.2f}" if s.get("value") else "—",
            f"{s['weight']:.1f}%" if s.get("weight") else "—",
        )

    console.print(table)


def display_portfolio_summary(summary: dict) -> None:
    """Show portfolio-level summary."""
    lines: list[str] = []
    lines.append(f"Holdings: {summary.get('num_holdings', 0)}")
    lines.append(f"Total Invested: ₹{summary.get('total_invested', 0):,.2f}")

    if summary.get("total_value"):
        lines.append(f"Current Value: ₹{summary['total_value']:,.2f}")
        pnl = summary.get("total_pnl", 0)
        pnl_pct = summary.get("total_pnl_pct", 0)
        color = "green" if pnl >= 0 else "red"
        lines.append(f"P&L: [{color}]₹{pnl:+,.2f} ({pnl_pct:+.1f}%)[/{color}]")

    if summary.get("top_gainer"):
        g = summary["top_gainer"]
        lines.append(f"Top Gainer: [green]{g['symbol']} {g['pnl_pct']:+.1f}%[/]")
    if summary.get("top_loser"):
        lo = summary["top_loser"]
        lines.append(f"Top Loser: [red]{lo['symbol']} {lo['pnl_pct']:+.1f}%[/]")

    console.print(Panel(
        "\n".join(lines),
        title="Portfolio Summary",
        border_style="cyan",
    ))


def display_portfolio_add(symbol: str, qty: int, cost: float) -> None:
    """Show confirmation after adding a holding."""
    console.print(Panel(
        f"Added {symbol}: {qty} shares @ ₹{cost:,.2f}",
        title="Holding Added",
        border_style="green",
    ))


def display_portfolio_remove(symbol: str) -> None:
    """Show confirmation after removing a holding."""
    console.print(Panel(
        f"Removed {symbol} from portfolio",
        title="Holding Removed",
        border_style="yellow",
    ))
