"""CLI commands for bulk/block deals and short selling."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress

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
def backfill(
    from_date: Annotated[
        str,
        typer.Option("--from", "-f", help="Start date YYYY-MM-DD (inclusive)."),
    ],
    to_date: Annotated[
        str,
        typer.Option("--to", "-t", help="End date YYYY-MM-DD (inclusive). Default: today."),
    ] = "",
    sleep: Annotated[
        float,
        typer.Option("--sleep", help="Seconds to pause between day fetches (NSE rate limit)."),
    ] = 0.6,
    skip_short: Annotated[
        bool,
        typer.Option("--skip-short", help="Skip short-selling option type (often empty)."),
    ] = False,
) -> None:
    """Backfill historical bulk/block/short deals from the NSE archive.

    The historical NSE endpoint caps responses at ~70 rows, so we page one
    day at a time. A 5-year backfill (~1250 trading days) takes ~15 min at
    the default sleep. Skips weekends. 404s and empty days are logged and
    silently skipped — exchange holidays + missing archives are normal.
    """
    try:
        start = datetime.strptime(from_date, "%Y-%m-%d").date()
    except ValueError:
        console.print(f"[red]Invalid --from date '{from_date}'. Use YYYY-MM-DD.[/]")
        raise typer.Exit(1)

    if to_date:
        try:
            end = datetime.strptime(to_date, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Invalid --to date '{to_date}'. Use YYYY-MM-DD.[/]")
            raise typer.Exit(1)
    else:
        end = date.today()

    if start > end:
        console.print(f"[red]--from {start} is after --to {end}.[/]")
        raise typer.Exit(1)

    option_types: tuple[str, ...]
    if skip_short:
        option_types = ("bulk_deals", "block_deals")
    else:
        option_types = ("bulk_deals", "block_deals", "short_deals")

    # Iterate trading days only (skip Sat/Sun). Exchange holidays still hit
    # but return an empty list — that's fine.
    days: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d = d + timedelta(days=1)

    total_days = len(days)
    total_deals = 0
    failed_days: list[str] = []
    empty_days = 0

    console.print(
        f"[bold]Backfilling deals[/] {start} → {end} "
        f"({total_days} trading days, option_types={option_types})"
    )

    with DealsClient() as client, FlowStore() as store:
        with Progress(console=console) as progress:
            task = progress.add_task("Fetching", total=total_days)
            for day in days:
                day_iso = day.strftime("%Y-%m-%d")
                progress.update(task, description=f"[cyan]{day_iso}[/]")
                try:
                    deals = client.fetch_historical_deals(
                        from_date=day_iso,
                        to_date=day_iso,
                        option_types=option_types,
                    )
                    if deals:
                        n = store.upsert_deals(deals)
                        total_deals += n
                    else:
                        empty_days += 1
                except Exception as e:  # pragma: no cover -- network defensive
                    failed_days.append(f"{day_iso}: {e}")
                    console.print(f"  [yellow]skip[/] {day_iso}: {e}")
                progress.advance(task)
                time.sleep(sleep)

    console.print(
        f"\n[bold green]Done.[/] {total_deals:,} deal records persisted "
        f"across {total_days - empty_days - len(failed_days)}/{total_days} days "
        f"(empty: {empty_days}, failed: {len(failed_days)})."
    )
    if failed_days:
        console.print(f"[yellow]Failed days ({len(failed_days)}, first 10 shown):[/]")
        for line in failed_days[:10]:
            console.print(f"  {line}")


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
