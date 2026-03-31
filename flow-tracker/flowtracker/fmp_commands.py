"""CLI commands for FMP (Financial Modeling Prep) data."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.fmp_client import FMPClient
from flowtracker.fmp_display import (
    display_analyst_grades,
    display_dcf,
    display_financial_growth,
    display_fmp_fetch_result,
    display_key_metrics,
    display_price_targets,
    display_technicals,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="fmp",
    help="FMP data — DCF valuation, technicals, key metrics, growth, analyst grades, price targets",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
) -> None:
    """Fetch all FMP data for a stock and store in DB."""
    symbol = symbol.upper()
    console.print(f"[dim]Fetching FMP data for {symbol}...[/]")

    client = FMPClient()
    data = client.fetch_all(symbol)

    with FlowStore() as store:
        if data["dcf"]:
            store.upsert_fmp_dcf([data["dcf"]])
        if data["dcf_history"]:
            store.upsert_fmp_dcf(data["dcf_history"])
        if data["technicals"]:
            store.upsert_fmp_technical_indicators(data["technicals"])
        if data["key_metrics"]:
            store.upsert_fmp_key_metrics(data["key_metrics"])
        if data["financial_growth"]:
            store.upsert_fmp_financial_growth(data["financial_growth"])
        if data["analyst_grades"]:
            store.upsert_fmp_analyst_grades(data["analyst_grades"])
        if data["price_targets"]:
            store.upsert_fmp_price_targets(data["price_targets"])

    display_fmp_fetch_result(data)


@app.command()
def dcf(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
) -> None:
    """Show DCF intrinsic value for a stock."""
    symbol = symbol.upper()
    with FlowStore() as store:
        current = store.get_fmp_dcf_latest(symbol)
        history = store.get_fmp_dcf_history(symbol)
    display_dcf(current, history)


@app.command()
def technicals(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
) -> None:
    """Show technical indicators (RSI, SMA, MACD, ADX)."""
    symbol = symbol.upper()
    with FlowStore() as store:
        indicators = store.get_fmp_technical_indicators(symbol)
    display_technicals(indicators)


@app.command()
def metrics(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
) -> None:
    """Show key financial metrics history."""
    symbol = symbol.upper()
    with FlowStore() as store:
        data = store.get_fmp_key_metrics(symbol)
    display_key_metrics(data)


@app.command()
def growth(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
) -> None:
    """Show financial growth rates."""
    symbol = symbol.upper()
    with FlowStore() as store:
        data = store.get_fmp_financial_growth(symbol)
    display_financial_growth(data)


@app.command()
def grades(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
) -> None:
    """Show analyst grade changes (upgrades/downgrades)."""
    symbol = symbol.upper()
    with FlowStore() as store:
        data = store.get_fmp_analyst_grades(symbol)
    display_analyst_grades(data)


@app.command()
def targets(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
) -> None:
    """Show analyst price targets."""
    symbol = symbol.upper()
    with FlowStore() as store:
        data = store.get_fmp_price_targets(symbol)
    display_price_targets(data)
