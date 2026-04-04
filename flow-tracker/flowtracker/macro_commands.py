"""CLI commands for macro indicators."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.macro_client import MacroClient
from flowtracker.macro_display import (
    display_macro_summary,
    display_macro_trend,
    display_macro_fetch_result,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="macro",
    help="Macro indicators — VIX, USD/INR, Brent crude, 10Y G-sec yield",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    backfill: Annotated[
        bool, typer.Option("--backfill", help="Fetch full history from 2008")
    ] = False,
    days: Annotated[
        int, typer.Option("-d", "--days", help="Days of recent data")
    ] = 5,
) -> None:
    """Fetch macro indicator snapshots."""
    with MacroClient() as client, FlowStore() as store:
        if backfill:
            console.print("[dim]Fetching full macro history...[/]")
            snapshots = client.fetch_history()
        else:
            snapshots = client.fetch_snapshot(days)
        count = store.upsert_macro_snapshots(snapshots)
    display_macro_fetch_result(count)


@app.command()
def fetch_index(
    period: str = typer.Option("5d", help="yfinance period (e.g. '5d', '1mo', '3y')"),
) -> None:
    """Fetch Nifty 500 + Nifty 50 index daily prices."""
    with MacroClient() as client, FlowStore() as store:
        records = client.fetch_index_prices(period=period)
        if records:
            count = store.upsert_index_daily_prices(records)
            console.print(f"[green]Upserted {count} index price records[/green]")
        else:
            console.print("[yellow]No index price data fetched[/yellow]")


@app.command()
def summary() -> None:
    """Show latest macro indicators with changes."""
    with FlowStore() as store:
        latest = store.get_macro_latest()
        prev = store.get_macro_previous()
    if latest is None:
        console.print("[yellow]No macro data. Run 'flowtrack macro fetch' first.[/]")
        raise typer.Exit(1)
    display_macro_summary(latest, prev)


@app.command()
def trend(
    days: Annotated[
        int, typer.Option("-d", "--days", help="Number of days to show")
    ] = 30,
) -> None:
    """Show macro indicator trend."""
    with FlowStore() as store:
        snapshots = store.get_macro_trend(days)
    display_macro_trend(snapshots)
