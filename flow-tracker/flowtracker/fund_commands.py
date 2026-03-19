"""Fundamentals CLI commands."""

from __future__ import annotations

import time
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress

from flowtracker.fund_client import FundClient, YFinanceError
from flowtracker.screener_client import ScreenerClient, ScreenerError
from flowtracker.fund_display import (
    display_live_snapshot,
    display_peer_comparison,
    display_quarterly_history,
    display_valuation_band,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="fund",
    help="Fundamentals: valuation, earnings, peer comparison",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    symbol: Annotated[str | None, typer.Option("-s", "--symbol", help="Fetch for specific symbol (default: all in watchlist)")] = None,
    quarters_only: Annotated[bool, typer.Option("--quarters-only", help="Only fetch quarterly results")] = False,
    valuation_only: Annotated[bool, typer.Option("--valuation-only", help="Only fetch valuation snapshot")] = False,
) -> None:
    """Fetch fundamentals for watchlist stocks and store them."""
    with FlowStore() as store:
        if symbol:
            symbols = [symbol.upper()]
        else:
            watchlist = store.get_watchlist()
            if not watchlist:
                console.print("[yellow]Watchlist is empty. Use 'flowtrack holding add SYMBOL' first.[/]")
                raise typer.Exit(1)
            symbols = [w.symbol for w in watchlist]

    client = FundClient()
    total = len(symbols)

    with Progress(console=console) as progress:
        task = progress.add_task("Fetching fundamentals...", total=total)

        with FlowStore() as store:
            for i, sym in enumerate(symbols):
                progress.update(task, description=f"[bold]{sym}[/]")

                try:
                    if not valuation_only:
                        results = client.fetch_quarterly_results(sym)
                        if results:
                            count = store.upsert_quarterly_results(results)
                            console.print(f"  [green]+[/] {sym}: {len(results)} quarters")

                    if not quarters_only:
                        snap = client.fetch_valuation_snapshot(sym)
                        store.upsert_valuation_snapshot(snap)
                        console.print(f"  [green]+[/] {sym}: valuation snapshot")

                except YFinanceError as e:
                    console.print(f"  [red]x[/] {sym}: {e}")

                progress.advance(task)

                # Rate limit between stocks
                if i < total - 1:
                    time.sleep(0.5)

    console.print(f"\n[bold]Done.[/] Fetched fundamentals for {total} stock(s).")


@app.command()
def show(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
) -> None:
    """Live fetch — display current fundamentals snapshot."""
    client = FundClient()
    try:
        snap = client.get_live_snapshot(symbol.upper())
    except YFinanceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    display_live_snapshot(snap)


@app.command()
def history(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    quarters: Annotated[int, typer.Option("-q", "--quarters", help="Number of quarters to show")] = 8,
) -> None:
    """Display stored quarterly earnings trajectory."""
    with FlowStore() as store:
        results = store.get_quarterly_results(symbol.upper(), limit=quarters)

    display_quarterly_history(results, symbol.upper())


@app.command()
def peers(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    with_peers: Annotated[str | None, typer.Option("--with", help="Comma-separated peer symbols (e.g. TCS,INFY,WIPRO)")] = None,
) -> None:
    """Live fetch peer comparison."""
    client = FundClient()

    # Determine peer list
    if with_peers:
        peer_symbols = [s.strip().upper() for s in with_peers.split(",")]
    else:
        # Auto-detect: get sector from yfinance, find watchlist stocks in same sector
        try:
            snap = client.get_live_snapshot(symbol.upper())
        except YFinanceError as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(1)

        if not snap.sector:
            console.print("[yellow]Cannot detect sector. Use --with to specify peers explicitly.[/]")
            raise typer.Exit(1)

        with FlowStore() as store:
            watchlist = store.get_watchlist()

        # Check each watchlist stock for same sector
        peer_symbols = []
        for w in watchlist:
            if w.symbol == symbol.upper():
                continue
            try:
                ws = client.get_live_snapshot(w.symbol)
                if ws.sector == snap.sector:
                    peer_symbols.append(w.symbol)
                time.sleep(0.5)
            except YFinanceError:
                continue

        if not peer_symbols:
            console.print(f"[yellow]No watchlist peers found in sector '{snap.sector}'. Use --with to specify.[/]")
            raise typer.Exit(1)

    # Always include the target symbol first
    all_symbols = [symbol.upper()] + [s for s in peer_symbols if s != symbol.upper()]

    # Fetch snapshots
    snapshots = []
    for sym in all_symbols:
        try:
            snapshots.append(client.get_live_snapshot(sym))
            time.sleep(0.5)
        except YFinanceError as e:
            console.print(f"[yellow]Skipping {sym}: {e}[/]")

    if not snapshots:
        console.print("[red]No data fetched for any peer.[/]")
        raise typer.Exit(1)

    # Build ownership data from store
    ownership_data: dict[str, dict] = {}
    with FlowStore() as store:
        for sym in all_symbols:
            changes = store.get_shareholding_changes(sym)
            fii = next((c for c in changes if c.category == "FII"), None)
            mf = next((c for c in changes if c.category == "MF"), None)
            ownership_data[sym] = {
                "fii_pct": fii.curr_pct if fii else 0,
                "fii_change": fii.change_pct if fii else None,
                "mf_pct": mf.curr_pct if mf else 0,
                "mf_change": mf.change_pct if mf else None,
            }

    display_peer_comparison(snapshots, ownership_data)


@app.command()
def valuation(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    period: Annotated[str, typer.Option("--period", help="Period: 1y, 2y, 3y")] = "3y",
) -> None:
    """Display valuation bands from stored snapshots."""
    period_map = {"1y": 365, "2y": 730, "3y": 1095}
    days = period_map.get(period)
    if days is None:
        console.print(f"[red]Invalid period '{period}'. Use 1y, 2y, or 3y.[/]")
        raise typer.Exit(1)

    metrics = ["pe_trailing", "ev_ebitda", "pb_ratio"]
    bands = []

    with FlowStore() as store:
        for metric in metrics:
            band = store.get_valuation_band(symbol.upper(), metric, days)
            if band is not None:
                bands.append(band)

    display_valuation_band(bands)


@app.command()
def backfill(
    symbol: Annotated[str | None, typer.Option("-s", "--symbol", help="Backfill single stock")] = None,
    quarters_only: Annotated[bool, typer.Option("--quarters-only", help="Only fetch Screener.in quarterly data")] = False,
    valuation_only: Annotated[bool, typer.Option("--valuation-only", help="Only compute historical P/E")] = False,
) -> None:
    """Backfill 10yr historical data from Screener.in + yfinance.

    Downloads quarterly results (10Q) and annual EPS (10yr) from Screener.in,
    then computes historical weekly P/E from annual EPS + yfinance prices.
    """
    # Get symbols to backfill
    if symbol:
        symbols = [symbol.upper()]
    else:
        with FlowStore() as store:
            watchlist = store.get_watchlist()
        if not watchlist:
            console.print("[red]Watchlist is empty. Add stocks first: flowtrack holding add SYMBOL[/]")
            raise typer.Exit(1)
        symbols = [w.symbol for w in watchlist]

    client = FundClient()
    total_quarters = 0
    total_annual = 0
    total_pe_snapshots = 0
    errors: list[str] = []

    # Stream 1: Screener.in quarterly results + annual EPS
    if not valuation_only:
        console.print(f"\n[bold]Stream 1: Screener.in quarterly results + annual EPS[/]")
        try:
            with ScreenerClient() as sc:
                with Progress() as progress:
                    task = progress.add_task("Fetching from Screener.in", total=len(symbols))
                    annual_eps_cache: dict[str, list] = {}

                    for sym in symbols:
                        progress.update(task, description=f"[cyan]{sym}[/]")
                        try:
                            quarters, annual = sc.fetch_all_with_annual(sym)

                            with FlowStore() as store:
                                if quarters:
                                    count = store.upsert_quarterly_results(quarters)
                                    total_quarters += len(quarters)
                                # Store annual EPS for Stream 2
                                annual_eps_cache[sym] = annual
                                total_annual += len(annual)

                        except ScreenerError as e:
                            errors.append(f"{sym}: {e}")

                        progress.advance(task)
                        time.sleep(3)  # Rate limit

        except ScreenerError as e:
            console.print(f"[red]Screener.in login failed: {e}[/]")
            raise typer.Exit(1)

        console.print(f"  Quarterly results: [green]{total_quarters}[/] records for {len(symbols)} stocks")
        console.print(f"  Annual EPS: [green]{total_annual}[/] records")
    else:
        # Still need annual EPS for P/E computation — load from Screener.in
        annual_eps_cache = {}
        try:
            with ScreenerClient() as sc:
                for sym in symbols:
                    try:
                        _, annual = sc.fetch_all_with_annual(sym)
                        annual_eps_cache[sym] = annual
                    except ScreenerError as e:
                        errors.append(f"{sym}: {e}")
                    time.sleep(3)
        except ScreenerError as e:
            console.print(f"[red]Screener.in login failed: {e}[/]")
            raise typer.Exit(1)

    # Stream 2: Historical P/E from yfinance prices + annual EPS
    if not quarters_only:
        console.print(f"\n[bold]Stream 2: Historical P/E computation[/]")
        with Progress() as progress:
            task = progress.add_task("Computing historical P/E", total=len(symbols))

            for sym in symbols:
                progress.update(task, description=f"[cyan]{sym}[/]")
                annual = annual_eps_cache.get(sym, [])
                if not annual:
                    progress.advance(task)
                    continue

                try:
                    snapshots = client.compute_historical_pe(sym, annual)
                    if snapshots:
                        with FlowStore() as store:
                            store.upsert_valuation_snapshots(snapshots)
                        total_pe_snapshots += len(snapshots)
                except YFinanceError as e:
                    errors.append(f"{sym} (P/E): {e}")

                progress.advance(task)
                time.sleep(0.5)

        console.print(f"  P/E snapshots: [green]{total_pe_snapshots}[/] records")

    # Summary
    console.print(f"\n[bold]Backfill complete.[/]")
    if errors:
        console.print(f"[yellow]Errors ({len(errors)}):[/]")
        for e in errors:
            console.print(f"  [red]• {e}[/]")
