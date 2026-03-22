"""CLI commands for consensus estimates."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.estimates_client import EstimatesClient
from flowtracker.estimates_display import (
    display_estimates_stock,
    display_estimates_upside,
    display_estimates_surprises,
    display_estimates_fetch_result,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="estimates",
    help="Consensus estimates — analyst targets, recommendations, earnings surprises",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch() -> None:
    """Fetch estimates for all Nifty 500 stocks."""
    with FlowStore() as store:
        symbols = store.get_all_scanner_symbols()
        if not symbols:
            console.print("[yellow]No index constituents. Run 'flowtrack scan refresh' first.[/]")
            raise typer.Exit(1)

    console.print(f"[dim]Fetching estimates for {len(symbols)} stocks...[/]")
    client = EstimatesClient()
    estimates, surprises = client.fetch_batch(symbols)

    with FlowStore() as store:
        est_count = store.upsert_consensus_estimates(estimates)
        surp_count = store.upsert_earnings_surprises(surprises)

    display_estimates_fetch_result(est_count, surp_count)


@app.command()
def stock(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
) -> None:
    """Show full estimates for a stock."""
    with FlowStore() as store:
        est = store.get_estimate_latest(symbol.upper())
        surprises = store.get_surprises(symbol.upper())
    if est is None:
        console.print(f"[yellow]No estimates for {symbol.upper()}. Run 'flowtrack estimates fetch'.[/]")
        raise typer.Exit(1)
    display_estimates_stock(est, surprises)


@app.command()
def upside() -> None:
    """Show stocks ranked by upside to analyst target."""
    with FlowStore() as store:
        estimates = store.get_all_latest_estimates()
    display_estimates_upside(estimates)


@app.command()
def surprises(
    days: Annotated[
        int, typer.Option("-d", "--days", help="Days to look back")
    ] = 90,
) -> None:
    """Show recent earnings beats/misses."""
    with FlowStore() as store:
        surps = store.get_recent_surprises(days)
    display_estimates_surprises(surps)
