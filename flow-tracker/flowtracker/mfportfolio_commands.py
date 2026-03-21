"""CLI commands for MF scheme-level portfolio holdings."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.mfportfolio_client import MFPortfolioClient
from flowtracker.mfportfolio_display import (
    display_mfport_fetch_result,
    display_stock_holdings,
    display_top_changes,
    display_amc_summary,
)
from flowtracker.store import FlowStore

_SUPPORTED_AMCS = ["SBI", "ICICI", "PPFAS", "QUANT", "UTI"]

app = typer.Typer(
    name="mfport",
    help="MF scheme holdings — track what mutual funds are buying and selling",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    month: Annotated[
        str | None, typer.Option("--month", help="Month as YYYY-MM (default: previous month)")
    ] = None,
    amc: Annotated[
        str | None, typer.Option("--amc", help="Single AMC code: SBI, ICICI, PPFAS, QUANT, UTI")
    ] = None,
) -> None:
    """Fetch MF portfolio holdings from AMC disclosures."""
    if month is None:
        today = date.today()
        # Default to previous month
        if today.month == 1:
            month = f"{today.year - 1}-12"
        else:
            month = f"{today.year}-{today.month - 1:02d}"

    amcs = [amc.upper()] if amc else _SUPPORTED_AMCS

    console.print(f"[dim]Fetching MF portfolios for {month} from {', '.join(amcs)}...[/]")

    with MFPortfolioClient() as client, FlowStore() as store:
        all_holdings = []
        for a in amcs:
            console.print(f"[dim]  Fetching {a}...[/]")
            holdings = client.fetch_amc(a, month)
            all_holdings.extend(holdings)
            console.print(f"[dim]  {a}: {len(holdings):,} holdings[/]")

        count = store.upsert_mf_scheme_holdings(all_holdings)

    display_mfport_fetch_result(count, month, amcs)


@app.command()
def stock(
    symbol: Annotated[str, typer.Argument(help="Stock name or ISIN to search")],
) -> None:
    """Show which MF schemes hold a stock."""
    with FlowStore() as store:
        holdings = store.get_mf_stock_holdings(symbol.upper())
    display_stock_holdings(holdings, symbol.upper())


@app.command(name="top-buys")
def top_buys(
    month: Annotated[
        str | None, typer.Option("--month", help="Month as YYYY-MM")
    ] = None,
    limit: Annotated[
        int, typer.Option("-n", "--limit", help="Number of changes to show")
    ] = 30,
) -> None:
    """Show biggest new positions and increases by MFs."""
    with FlowStore() as store:
        changes = store.get_mf_holding_changes(month, change_type="buy", limit=limit)
    display_top_changes(changes, f"Top MF Buys — {month or 'latest'}")


@app.command(name="top-exits")
def top_exits(
    month: Annotated[
        str | None, typer.Option("--month", help="Month as YYYY-MM")
    ] = None,
    limit: Annotated[
        int, typer.Option("-n", "--limit", help="Number of changes to show")
    ] = 30,
) -> None:
    """Show biggest exits and decreases by MFs."""
    with FlowStore() as store:
        changes = store.get_mf_holding_changes(month, change_type="sell", limit=limit)
    display_top_changes(changes, f"Top MF Exits — {month or 'latest'}")


@app.command()
def summary(
    month: Annotated[
        str | None, typer.Option("--month", help="Month as YYYY-MM")
    ] = None,
) -> None:
    """Show AMC-level portfolio summary."""
    with FlowStore() as store:
        data = store.get_mf_portfolio_summary(month)
    display_amc_summary(data)
