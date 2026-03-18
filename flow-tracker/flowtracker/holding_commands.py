"""CLI commands for NSE shareholding pattern data."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.holding_client import NSEHoldingClient, NSEHoldingError
from flowtracker.holding_display import (
    display_holding_changes,
    display_holding_fetch_result,
    display_shareholding,
    display_watchlist,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="holding",
    help="NSE shareholding patterns — quarterly promoter/FII/DII/MF/public ownership",
    no_args_is_help=True,
)
console = Console()


@app.command()
def add(
    symbols: Annotated[list[str], typer.Argument(help="Stock symbols to add (e.g. RELIANCE TCS INFY)")],
) -> None:
    """Add stocks to watchlist."""
    with FlowStore() as store:
        for symbol in symbols:
            store.add_to_watchlist(symbol.upper())
            console.print(f"  [green]+[/] {symbol.upper()}")
    console.print(f"\n[bold]Added {len(symbols)} symbol(s) to watchlist.[/]")


@app.command()
def remove(
    symbol: Annotated[str, typer.Argument(help="Stock symbol to remove")],
) -> None:
    """Remove a stock from watchlist."""
    with FlowStore() as store:
        store.remove_from_watchlist(symbol.upper())
    console.print(f"[yellow]Removed {symbol.upper()} from watchlist.[/]")


@app.command(name="list")
def list_watchlist() -> None:
    """Show all stocks in watchlist."""
    with FlowStore() as store:
        entries = store.get_watchlist()
    display_watchlist(entries)


@app.command()
def fetch(
    symbol: Annotated[str | None, typer.Option("--symbol", "-s", help="Fetch for specific symbol (default: all in watchlist)")] = None,
    quarters: Annotated[int, typer.Option("--quarters", "-q", help="Number of quarters to fetch")] = 4,
) -> None:
    """Fetch shareholding data from NSE XBRL filings."""
    with FlowStore() as store:
        if symbol:
            symbols = [symbol.upper()]
        else:
            watchlist = store.get_watchlist()
            if not watchlist:
                console.print("[yellow]Watchlist is empty. Use 'flowtrack holding add SYMBOL' first.[/]")
                raise typer.Exit(1)
            symbols = [w.symbol for w in watchlist]

    try:
        with NSEHoldingClient() as client:
            with FlowStore() as store:
                for sym in symbols:
                    console.print(f"[dim]Fetching {sym}...[/]")
                    try:
                        records = client.fetch_latest_quarters(sym, quarters)
                        if records:
                            count = store.upsert_shareholding(records)
                            display_holding_fetch_result(sym, records)
                        else:
                            console.print(f"[yellow]No data for {sym}.[/]")
                    except NSEHoldingError as e:
                        console.print(f"[red]Error fetching {sym}: {e}[/]")
    except NSEHoldingError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


@app.command()
def show(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    quarters: Annotated[int, typer.Option("-q", "--quarters", help="Number of quarters to show")] = 8,
) -> None:
    """Show shareholding history for a stock."""
    with FlowStore() as store:
        records = store.get_shareholding(symbol.upper(), quarters)
    display_shareholding(symbol.upper(), records)


@app.command()
def changes(
    category: Annotated[str | None, typer.Option("-c", "--category", help="Filter by category: FII, DII, MF, Promoter, Public")] = None,
    limit: Annotated[int, typer.Option("-n", "--limit", help="Number of results")] = 10,
) -> None:
    """Show biggest shareholding changes across watchlist stocks."""
    with FlowStore() as store:
        data = store.get_biggest_changes(category, limit)
    display_holding_changes(data)
