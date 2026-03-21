"""CLI commands for bulk/block deals and short selling."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.deals_client import DealsClient
from flowtracker.deals_display import (
    display_deals_summary,
    display_deals_stock,
    display_deals_top,
    display_deals_fetch_result,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="deals",
    help="Bulk/block deals — track large institutional transactions",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch() -> None:
    """Fetch today's bulk/block deals from NSE."""
    with DealsClient() as client, FlowStore() as store:
        deals = client.fetch_deals()
        count = store.upsert_deals(deals)
    display_deals_fetch_result(count)


@app.command()
def summary() -> None:
    """Show latest day's deals grouped by type."""
    with FlowStore() as store:
        deals = store.get_deals_latest()
    display_deals_summary(deals)


@app.command()
def stock(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
) -> None:
    """Show deal history for a specific stock."""
    with FlowStore() as store:
        deals = store.get_deals_by_symbol(symbol.upper())
    display_deals_stock(deals, symbol.upper())


@app.command()
def top(
    days: Annotated[
        int, typer.Option("-d", "--days", help="Number of days to look back")
    ] = 30,
    limit: Annotated[
        int, typer.Option("-n", "--limit", help="Number of deals to show")
    ] = 20,
) -> None:
    """Show biggest deals by value."""
    with FlowStore() as store:
        deals = store.get_deals_top(days, limit)
    display_deals_top(deals)
