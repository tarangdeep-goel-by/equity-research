"""CLI commands for insider/SAST transactions."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.insider_client import InsiderClient
from flowtracker.insider_display import (
    display_insider_trades,
    display_promoter_buys,
    display_insider_fetch_result,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="insider",
    help="Insider/SAST transactions — track promoter and insider trading activity",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    days: Annotated[
        int, typer.Option("-d", "--days", help="Days to look back")
    ] = 7,
) -> None:
    """Fetch recent insider transactions from NSE."""
    with InsiderClient() as client, FlowStore() as store:
        trades = client.fetch_recent(days)
        count = store.upsert_insider_transactions(trades)
    display_insider_fetch_result(count)


@app.command()
def stock(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    days: Annotated[
        int, typer.Option("-d", "--days", help="Days to look back")
    ] = 365,
) -> None:
    """Show insider activity for a specific stock."""
    with FlowStore() as store:
        trades = store.get_insider_by_symbol(symbol.upper(), days)
    if not trades:
        console.print(f"[yellow]No insider transactions for {symbol.upper()}[/]")
        raise typer.Exit(1)
    display_insider_trades(trades, title=f"Insider Transactions — {symbol.upper()}")


@app.command(name="promoter-buys")
def promoter_buys(
    days: Annotated[
        int, typer.Option("-d", "--days", help="Days to look back")
    ] = 30,
) -> None:
    """Show promoter buying activity (highest conviction signal)."""
    with FlowStore() as store:
        trades = store.get_promoter_buys(days)
    display_promoter_buys(trades)


@app.command()
def backfill(
    year: Annotated[
        int, typer.Argument(help="Year to backfill (e.g. 2024)")
    ],
) -> None:
    """Backfill insider transactions for a full year."""
    console.print(f"[dim]Fetching insider transactions for {year}...[/]")
    with InsiderClient() as client, FlowStore() as store:
        trades = client.fetch_year(year)
        count = store.upsert_insider_transactions(trades)
    display_insider_fetch_result(count)
