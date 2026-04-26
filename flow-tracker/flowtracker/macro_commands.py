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
        # Backfill NULL gsec_10y rows in the last week with today's value.
        # CCIL only publishes today's yield; without this, any day the cron
        # ran before CCIL's end-of-day update keeps gsec_10y=NULL forever.
        latest_gsec = next(
            (s.gsec_10y for s in reversed(snapshots) if s.gsec_10y is not None),
            None,
        )
        if latest_gsec is not None:
            patched = store.backfill_missing_gsec(latest_gsec)
            if patched:
                console.print(
                    f"[dim]Backfilled gsec_10y={latest_gsec} into {patched} prior row(s)[/]"
                )
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


@app.command("wss-fetch")
def wss_fetch(
    selected_date: Annotated[
        str | None,
        typer.Option(
            "--date",
            help="Override release date (RBI format M/DD/YYYY). Default = latest release.",
        ),
    ] = None,
) -> None:
    """Fetch RBI WSS system credit/deposit aggregates (weekly).

    Idempotent — re-running for a release that's already in the DB overwrites
    with whatever the parser extracts this run.
    """
    with MacroClient() as client, FlowStore() as store:
        record = client._fetch_rbi_wss(selected_date)
        if record is None:
            console.print(
                "[yellow]RBI WSS fetch returned no data — see logs for parser/network detail.[/]"
            )
            raise typer.Exit(1)
        rowcount = store.upsert_system_credit(record)
    console.print(
        f"[green]RBI WSS upserted ({rowcount} row) — release {record.release_date}, "
        f"as_of {record.as_of_date}: credit YoY {record.credit_growth_yoy}%, "
        f"deposit YoY {record.deposit_growth_yoy}%, CD ratio {record.cd_ratio}%[/]"
    )


@app.command("wss-summary")
def wss_summary() -> None:
    """Show the latest RBI WSS system-credit snapshot."""
    with FlowStore() as store:
        record = store.get_latest_system_credit()
    if record is None:
        console.print("[yellow]No RBI WSS data. Run 'flowtrack macro wss-fetch' first.[/]")
        raise typer.Exit(1)
    console.print(
        f"[bold cyan]RBI WSS — release {record.release_date} (as of {record.as_of_date}):[/]\n"
        f"  Credit growth YoY:        {record.credit_growth_yoy}%\n"
        f"  Deposit growth YoY:       {record.deposit_growth_yoy}%\n"
        f"  Non-food credit YoY:      {record.non_food_credit_growth_yoy}%\n"
        f"  M3 growth YoY:            {record.m3_growth_yoy}%\n"
        f"  C/D ratio:                {record.cd_ratio}%\n"
        f"  Aggregate deposits (Cr):  {record.aggregate_deposits_cr}\n"
        f"  Bank credit (Cr):         {record.bank_credit_cr}\n"
    )
