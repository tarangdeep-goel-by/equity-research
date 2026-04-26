"""CLI commands for Nifty 250 shareholding scanner."""

from __future__ import annotations

import time
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)

from flowtracker.holding_client import NSEHoldingClient, NSEHoldingError
from flowtracker.scan_client import NSEIndexClient, NSEIndexError
from flowtracker.scan_display import (
    display_batch_result,
    display_constituents,
    display_handoff_signals,
    display_pledge_stocks,
    display_scan_deviations,
    display_scan_summary,
)
from flowtracker.scan_models import BatchFetchResult
from flowtracker.store import FlowStore

app = typer.Typer(
    name="scan",
    help="Nifty 250 shareholding scanner — batch fetch and rank ownership deviations",
    no_args_is_help=True,
)
console = Console()


@app.command()
def refresh() -> None:
    """Fetch all Nifty 250 constituents from NSE and upsert into store."""
    try:
        with NSEIndexClient() as client:
            constituents = client.fetch_all_nifty250()
    except NSEIndexError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        store.upsert_index_constituents(constituents)

    unique = len({c.symbol for c in constituents})
    console.print(
        f"[green]Refreshed {len(constituents)} symbols ({unique} unique across 3 indices)[/]"
    )


@app.command()
def constituents(
    index: Annotated[
        str | None,
        typer.Option("-i", "--index", help="Filter by index name (e.g. 'NIFTY 50')"),
    ] = None,
) -> None:
    """Show index constituents from the local store."""
    with FlowStore() as store:
        data = store.get_index_constituents(index)
    display_constituents(data)


@app.command()
def fetch(
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-fetch all, ignoring existing data"),
    ] = False,
    quarters: Annotated[
        int,
        typer.Option("-q", "--quarters", help="Number of quarters to fetch"),
    ] = 2,
    limit: Annotated[
        int,
        typer.Option("-l", "--limit", help="Limit to N stocks (0=all)"),
    ] = 0,
) -> None:
    """Batch fetch shareholding for all scanner stocks."""
    with FlowStore() as store:
        symbols = store.get_all_scanner_symbols()

    if not symbols:
        console.print("[yellow]No scanner stocks. Run 'flowtrack scan refresh' first.[/]")
        raise typer.Exit(1)

    if limit > 0:
        symbols = symbols[:limit]

    result = BatchFetchResult(total=len(symbols), fetched=0, skipped=0, failed=0, errors=[])

    try:
        with NSEHoldingClient() as client, FlowStore() as store:
            if not force:
                summary = store.get_scan_summary()
                missing = set(summary.missing_symbols)
                to_fetch = [s for s in symbols if s in missing]
                result.skipped = len(symbols) - len(to_fetch)
            else:
                to_fetch = list(symbols)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Scanning", total=len(to_fetch))

                for sym in to_fetch:
                    progress.update(task, description=f"[cyan]{sym}[/]")
                    try:
                        records, pledges, breakdowns = client.fetch_latest_quarters_full(sym, quarters)
                        if records:
                            store.upsert_shareholding(records)
                            if pledges:
                                store.upsert_promoter_pledges(pledges)
                            if breakdowns:
                                store.upsert_shareholding_breakdown(breakdowns)
                            result.fetched += 1
                        else:
                            result.skipped += 1
                    except (NSEHoldingError, Exception) as e:
                        result.failed += 1
                        result.errors.append(f"{sym}: {e}")

                    progress.advance(task)
                    time.sleep(1)
    except NSEHoldingError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    display_batch_result(result)


@app.command()
def deviations(
    category: Annotated[
        str | None,
        typer.Option("-c", "--category", help="Filter by category: FII, DII, MF, Promoter, Public"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("-n", "--limit", help="Number of results"),
    ] = 20,
    handoff: Annotated[
        bool,
        typer.Option("--handoff", help="Show FII→MF handoff signals instead"),
    ] = False,
    min_change: Annotated[
        float,
        typer.Option("--min-change", help="Minimum absolute change % to include"),
    ] = 0.0,
) -> None:
    """Show biggest shareholding deviations across Nifty 250."""
    with FlowStore() as store:
        if handoff:
            data = store.get_handoff_signals(limit)
            display_handoff_signals(data)
        else:
            data = store.get_scanner_deviations(category, limit, min_change)
            display_scan_deviations(data)


@app.command()
def pledges(
    min_pct: Annotated[
        float,
        typer.Option("--min", help="Minimum pledge % to show"),
    ] = 1.0,
    limit: Annotated[
        int,
        typer.Option("-n", "--limit", help="Number of results"),
    ] = 20,
) -> None:
    """Show stocks with high promoter pledging across Nifty 250."""
    with FlowStore() as store:
        data = store.get_high_pledge_stocks(min_pct, limit)
    display_pledge_stocks(data)


@app.command()
def status() -> None:
    """Show scanner coverage stats."""
    with FlowStore() as store:
        summary = store.get_scan_summary()
    display_scan_summary(summary)
