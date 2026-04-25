"""CLI commands for gold and silver price tracking."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.commodity_client import CommodityClient
from flowtracker.commodity_display import (
    display_commodity_prices,
    display_etf_navs,
    display_gold_correlation,
    display_gold_fetch_result,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="gold",
    help="Gold and silver prices — track commodity rotation alongside equity flows",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    backfill: Annotated[
        bool, typer.Option("--backfill", help="Fetch full history from 2010")
    ] = False,
    days: Annotated[
        int, typer.Option("-d", "--days", help="Days of recent data")
    ] = 30,
) -> None:
    """Fetch gold/silver prices and ETF NAVs."""
    with CommodityClient() as client, FlowStore() as store:
        if backfill:
            console.print("[dim]Fetching full price history...[/]")
            prices = client.fetch_prices_history()
            console.print("[dim]Fetching full ETF NAV history...[/]")
            navs = client.fetch_etf_navs_all()
        else:
            prices = client.fetch_prices(days)
            navs = client.fetch_etf_navs(days)

        num_prices = store.upsert_commodity_prices(prices)
        num_navs = store.upsert_etf_navs(navs)

    display_gold_fetch_result(num_prices, num_navs)


@app.command()
def metals(
    backfill: Annotated[
        bool, typer.Option("--backfill", help="Fetch full history from 2010")
    ] = False,
    days: Annotated[
        int, typer.Option("-d", "--days", help="Days of recent data")
    ] = 30,
    start: Annotated[
        str, typer.Option("--start", help="Backfill start date (YYYY-MM-DD)")
    ] = "2010-01-01",
) -> None:
    """Fetch industrial metals prices (aluminium / copper) from yfinance.

    HG=F is COMEX copper (USD/lb) — the only liquid copper future on yfinance.
    ALI=F is CME aluminium tracking LME settlements (USD/MT). Zinc (ZNC=F
    stale) and lead (PB=F empty) are not exposed via yfinance.
    """
    with CommodityClient() as client, FlowStore() as store:
        if backfill:
            console.print(f"[dim]Fetching metals history from {start}...[/]")
            prices_data = client.fetch_metals_history(start=start)
        else:
            prices_data = client.fetch_metals(days)

        num_prices = store.upsert_commodity_prices(prices_data)

    console.print(f"[green]Stored {num_prices} metals price rows.[/]")


@app.command()
def prices(
    days: Annotated[
        int, typer.Option("-d", "--days", help="Number of days to show")
    ] = 14,
) -> None:
    """Show recent gold and silver prices."""
    with FlowStore() as store:
        gold = store.get_commodity_prices("GOLD", days) + store.get_commodity_prices(
            "GOLD_INR", days
        )
        silver = store.get_commodity_prices(
            "SILVER", days
        ) + store.get_commodity_prices("SILVER_INR", days)
    display_commodity_prices(gold, silver)


@app.command()
def etfs(
    days: Annotated[
        int, typer.Option("-d", "--days", help="Number of days to show")
    ] = 30,
) -> None:
    """Show gold/silver ETF NAV trends."""
    with FlowStore() as store:
        all_navs = store.get_etf_navs("140088", days) + store.get_etf_navs(
            "149758", days
        )
    display_etf_navs(all_navs)


@app.command()
def correlation(
    days: Annotated[
        int, typer.Option("-d", "--days", help="Number of days to analyze")
    ] = 30,
) -> None:
    """Show FII equity flows vs gold price changes."""
    with FlowStore() as store:
        data = store.get_gold_fii_correlation(days)
    display_gold_correlation(data)
