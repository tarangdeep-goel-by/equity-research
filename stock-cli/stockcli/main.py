"""Stock CLI — screening, research & comparison for US + Indian markets."""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.console import Console

from stockcli.client import YFinanceClient, YFinanceError
from stockcli.display import (
    display_compare,
    display_fundamentals,
    display_movers,
    display_profile,
    display_screener,
)
from stockcli.utils import normalize_symbol

app = typer.Typer(
    name="stock",
    help="Stock screening, research & comparison CLI",
    no_args_is_help=True,
)
console = Console()


def _client() -> YFinanceClient:
    return YFinanceClient()


# ── info ─────────────────────────────────────────────────────


@app.command()
def info(
    symbol: Annotated[str, typer.Argument(help="Stock symbol (e.g. AAPL, RELIANCE.NS)")],
) -> None:
    """Quick snapshot — price, ratios, sector, description."""
    client = _client()
    sym = normalize_symbol(symbol)
    try:
        profile = client.profile(sym)
        ratios = client.ratios_ttm(sym)
        metrics = client.key_metrics_ttm(sym)
    except YFinanceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    display_profile(profile, ratios, metrics)


# ── fundamentals ─────────────────────────────────────────────


@app.command()
def fundamentals(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    period: Annotated[str, typer.Option("-p", "--period", help="annual or quarter")] = "annual",
    years: Annotated[int, typer.Option("-y", "--years", help="Number of periods")] = 4,
) -> None:
    """Income statement, balance sheet, cash flow & key metrics."""
    client = _client()
    sym = normalize_symbol(symbol)
    try:
        profile = client.profile(sym)
        income = client.income_statement(sym, period=period, limit=years)
        balance = client.balance_sheet(sym, period=period, limit=years)
        cashflow = client.cash_flow(sym, period=period, limit=years)
        display_fundamentals(sym, income, balance, cashflow, currency=profile.currency)
    except YFinanceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


# ── compare ──────────────────────────────────────────────────


@app.command()
def compare(
    symbols: Annotated[list[str], typer.Argument(help="2+ stock symbols to compare")],
) -> None:
    """Side-by-side metric comparison table."""
    if len(symbols) < 2:
        console.print("[red]Provide at least 2 symbols to compare.[/]")
        raise typer.Exit(1)

    client = _client()
    profiles, ratios_list, metrics_list = [], [], []
    for s in symbols:
        sym = normalize_symbol(s)
        try:
            profiles.append(client.profile(sym))
            ratios_list.append(client.ratios_ttm(sym))
            metrics_list.append(client.key_metrics_ttm(sym))
        except YFinanceError as e:
            console.print(f"[red]{sym}: {e}[/]")
            raise typer.Exit(1)

    display_compare(profiles, ratios_list, metrics_list)


# ── screen ───────────────────────────────────────────────────


@app.command()
def screen(
    exchange: Annotated[Optional[str], typer.Option("-e", "--exchange", help="Exchange: NYSE, NASDAQ, NSE, BSE, etc.")] = None,
    sector: Annotated[Optional[str], typer.Option("-s", "--sector", help="Sector filter")] = None,
    industry: Annotated[Optional[str], typer.Option("--industry", help="Industry filter")] = None,
    country: Annotated[Optional[str], typer.Option("-c", "--country", help="Country: US, IN, etc.")] = None,
    market_cap_gt: Annotated[Optional[float], typer.Option("--market-cap-gt", help="Min market cap (e.g. 1000000000)")] = None,
    market_cap_lt: Annotated[Optional[float], typer.Option("--market-cap-lt", help="Max market cap")] = None,
    pe_gt: Annotated[Optional[float], typer.Option("--pe-gt", help="Min P/E ratio")] = None,
    pe_lt: Annotated[Optional[float], typer.Option("--pe-lt", help="Max P/E ratio")] = None,
    price_gt: Annotated[Optional[float], typer.Option("--price-gt", help="Min price")] = None,
    price_lt: Annotated[Optional[float], typer.Option("--price-lt", help="Max price")] = None,
    beta_gt: Annotated[Optional[float], typer.Option("--beta-gt", help="Min beta")] = None,
    beta_lt: Annotated[Optional[float], typer.Option("--beta-lt", help="Max beta")] = None,
    dividend_gt: Annotated[Optional[float], typer.Option("--dividend-gt", help="Min dividend yield")] = None,
    volume_gt: Annotated[Optional[int], typer.Option("--volume-gt", help="Min volume")] = None,
    is_etf: Annotated[Optional[bool], typer.Option("--etf/--no-etf", help="ETF filter")] = None,
    is_active: Annotated[Optional[bool], typer.Option("--active/--inactive", help="Actively trading filter")] = None,
    limit: Annotated[int, typer.Option("-l", "--limit", help="Max results")] = 20,
) -> None:
    """Filter stocks by exchange, sector, ratios, and more."""
    client = _client()

    # Build screener params
    params: dict = {"limit": limit}
    if exchange:
        params["exchange"] = exchange
    if sector:
        params["sector"] = sector
    if industry:
        params["industry"] = industry
    if country:
        params["country"] = country
    if market_cap_gt is not None:
        params["marketCapMoreThan"] = int(market_cap_gt)
    if market_cap_lt is not None:
        params["marketCapLowerThan"] = int(market_cap_lt)
    if pe_gt is not None:
        params["peMoreThan"] = pe_gt
    if pe_lt is not None:
        params["peLowerThan"] = pe_lt
    if price_gt is not None:
        params["priceMoreThan"] = price_gt
    if price_lt is not None:
        params["priceLowerThan"] = price_lt
    if beta_gt is not None:
        params["betaMoreThan"] = beta_gt
    if beta_lt is not None:
        params["betaLowerThan"] = beta_lt
    if dividend_gt is not None:
        params["dividendMoreThan"] = dividend_gt
    if volume_gt is not None:
        params["volumeMoreThan"] = volume_gt
    if is_etf is not None:
        params["isEtf"] = str(is_etf).lower()
    if is_active is not None:
        params["isActivelyTrading"] = str(is_active).lower()

    try:
        results = client.screen(**params)
        display_screener(results)
    except YFinanceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


# ── gainers / losers / actives ───────────────────────────────


@app.command()
def gainers(
    limit: Annotated[int, typer.Option("-l", "--limit", help="Max results")] = 10,
) -> None:
    """Today's top gainers."""
    client = _client()
    try:
        data = client.gainers()
        display_movers(data, "Top Gainers", limit)
    except YFinanceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


@app.command()
def losers(
    limit: Annotated[int, typer.Option("-l", "--limit", help="Max results")] = 10,
) -> None:
    """Today's top losers."""
    client = _client()
    try:
        data = client.losers()
        display_movers(data, "Top Losers", limit)
    except YFinanceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


@app.command()
def actives(
    limit: Annotated[int, typer.Option("-l", "--limit", help="Max results")] = 10,
) -> None:
    """Most actively traded stocks today."""
    client = _client()
    try:
        data = client.actives()
        display_movers(data, "Most Active", limit)
    except YFinanceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)
