"""CLI commands for daily bhavcopy + delivery data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.bhavcopy_client import BhavcopyClient
from flowtracker.bhavcopy_display import (
    display_bhavcopy_fetch_result,
    display_top_delivery,
    display_delivery_trend,
    display_backfill_result,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="bhavcopy",
    help="Daily OHLCV + delivery data — track conviction via delivery %",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    date_str: Annotated[
        str | None, typer.Option("--date", help="Date as YYYY-MM-DD (default: today)")
    ] = None,
) -> None:
    """Fetch bhavcopy for a single trading day."""
    target = _parse_date(date_str) if date_str else date.today()
    with BhavcopyClient() as client, FlowStore() as store:
        records = client.fetch_day(target)
        if not records:
            console.print(f"[yellow]No data for {target.isoformat()} (holiday/weekend?)[/]")
            raise typer.Exit(1)
        count = store.upsert_daily_stock_data(records)
    display_bhavcopy_fetch_result(count, target.isoformat())


@app.command()
def backfill(
    from_date: Annotated[
        str, typer.Option("--from", help="Start date YYYY-MM-DD")
    ] = "2024-01-01",
    to_date: Annotated[
        str | None, typer.Option("--to", help="End date YYYY-MM-DD (default: today)")
    ] = None,
) -> None:
    """Bulk fetch historical bhavcopy data."""
    start = _parse_date(from_date)
    end = _parse_date(to_date) if to_date else date.today()
    console.print(f"[dim]Backfilling bhavcopy from {start} to {end}...[/]")
    with BhavcopyClient() as client, FlowStore() as store:
        records = client.fetch_range(start, end)
        count = store.upsert_daily_stock_data(records)
    display_backfill_result(count, start.isoformat(), end.isoformat())


@app.command(name="top-delivery")
def top_delivery(
    date_str: Annotated[
        str | None, typer.Option("--date", help="Date as YYYY-MM-DD")
    ] = None,
    limit: Annotated[
        int, typer.Option("-n", "--limit", help="Number of stocks to show")
    ] = 20,
) -> None:
    """Show stocks with highest delivery % (conviction signal)."""
    with FlowStore() as store:
        records = store.get_top_delivery(date_str, limit)
    display_date = date_str or (records[0].date if records else "N/A")
    display_top_delivery(records, display_date)


@app.command()
def delivery(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    days: Annotated[
        int, typer.Option("-d", "--days", help="Number of days")
    ] = 30,
) -> None:
    """Show delivery % trend for a stock."""
    with FlowStore() as store:
        records = store.get_stock_delivery(symbol.upper(), days)
    if not records:
        console.print(f"[yellow]No data for {symbol.upper()}[/]")
        raise typer.Exit(1)
    display_delivery_trend(records, symbol.upper())


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()
