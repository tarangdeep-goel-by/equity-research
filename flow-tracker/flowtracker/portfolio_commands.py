"""CLI commands for portfolio tracking."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.portfolio_display import (
    display_portfolio_add,
    display_portfolio_concentration,
    display_portfolio_remove,
    display_portfolio_summary,
    display_portfolio_view,
)
from flowtracker.portfolio_models import PortfolioHolding
from flowtracker.store import FlowStore

app = typer.Typer(
    name="portfolio",
    help="Track portfolio holdings — P&L, sector concentration, summary",
    no_args_is_help=True,
)
console = Console()


@app.command()
def add(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    qty: Annotated[int, typer.Option("--qty", "-q", help="Number of shares")],
    cost: Annotated[float, typer.Option("--cost", "-c", help="Average cost per share")],
    date: Annotated[str | None, typer.Option("--date", "-d", help="Buy date (YYYY-MM-DD)")] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n", help="Notes")] = None,
) -> None:
    """Add or update a portfolio holding."""
    symbol = symbol.upper()
    holding = PortfolioHolding(
        symbol=symbol, quantity=qty, avg_cost=cost, buy_date=date, notes=notes,
    )
    with FlowStore() as store:
        store.upsert_portfolio_holding(holding)
    display_portfolio_add(symbol, qty, cost)


@app.command()
def remove(
    symbol: Annotated[str, typer.Argument(help="Stock symbol to remove")],
) -> None:
    """Remove a holding from the portfolio."""
    symbol = symbol.upper()
    with FlowStore() as store:
        removed = store.remove_portfolio_holding(symbol)
    if removed:
        display_portfolio_remove(symbol)
    else:
        console.print(f"[yellow]{symbol} not found in portfolio.[/]")


@app.command()
def view() -> None:
    """Show all holdings with current price and P&L."""
    with FlowStore() as store:
        holdings = store.get_portfolio_holdings()
        if not holdings:
            console.print("[yellow]No holdings. Use 'flowtrack portfolio add' to start.[/]")
            raise typer.Exit(1)

        enriched = []
        for h in holdings:
            row = store._conn.execute(
                "SELECT price FROM valuation_snapshot WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (h.symbol,),
            ).fetchone()
            enriched.append({
                "symbol": h.symbol,
                "quantity": h.quantity,
                "avg_cost": h.avg_cost,
                "cmp": row["price"] if row else None,
            })

    display_portfolio_view(enriched)


@app.command()
def concentration() -> None:
    """Show sector breakdown of portfolio."""
    with FlowStore() as store:
        holdings = store.get_portfolio_holdings()
        if not holdings:
            console.print("[yellow]No holdings.[/]")
            raise typer.Exit(1)

        constituents = store.get_index_constituents()
        sector_map = {c.symbol: c.industry for c in constituents}

        sector_data: dict[str, dict] = {}
        total_value = 0.0

        for h in holdings:
            row = store._conn.execute(
                "SELECT price FROM valuation_snapshot WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (h.symbol,),
            ).fetchone()
            cmp = row["price"] if row else h.avg_cost
            value = h.quantity * cmp
            total_value += value

            sector = sector_map.get(h.symbol, "Unknown")
            if sector not in sector_data:
                sector_data[sector] = {"sector": sector, "count": 0, "value": 0.0}
            sector_data[sector]["count"] += 1
            sector_data[sector]["value"] += value

        sectors = sorted(sector_data.values(), key=lambda s: s["value"], reverse=True)
        for s in sectors:
            s["weight"] = (s["value"] / total_value * 100) if total_value > 0 else 0

    display_portfolio_concentration(sectors)


@app.command()
def summary() -> None:
    """Show portfolio-level summary: total invested, P&L, top gainer/loser."""
    with FlowStore() as store:
        holdings = store.get_portfolio_holdings()
        if not holdings:
            console.print("[yellow]No holdings.[/]")
            raise typer.Exit(1)

        total_invested = 0.0
        total_value = 0.0
        stock_pnls: list[dict] = []

        for h in holdings:
            invested = h.quantity * h.avg_cost
            total_invested += invested

            row = store._conn.execute(
                "SELECT price FROM valuation_snapshot WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (h.symbol,),
            ).fetchone()
            if row and row["price"]:
                value = h.quantity * row["price"]
                total_value += value
                pnl = value - invested
                pnl_pct = (pnl / invested * 100) if invested > 0 else 0
                stock_pnls.append({"symbol": h.symbol, "pnl": pnl, "pnl_pct": pnl_pct})
            else:
                total_value += invested

    result: dict = {
        "num_holdings": len(holdings),
        "total_invested": total_invested,
        "total_value": total_value,
        "total_pnl": total_value - total_invested,
        "total_pnl_pct": ((total_value - total_invested) / total_invested * 100) if total_invested > 0 else 0,
    }

    if stock_pnls:
        best = max(stock_pnls, key=lambda x: x["pnl_pct"])
        worst = min(stock_pnls, key=lambda x: x["pnl_pct"])
        result["top_gainer"] = best
        result["top_loser"] = worst

    display_portfolio_summary(result)
