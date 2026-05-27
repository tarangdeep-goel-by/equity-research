"""CLI commands for monthly India IIP (Industrial Production)."""

from __future__ import annotations

import logging
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.iip_client import IIPClient, IIPClientError
from flowtracker.iip_display import (
    display_iip_fetch_result,
    display_iip_latest,
    display_iip_trend,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="iip",
    help="Monthly India IIP industrial production (MoSPI / FRED mirror)",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)


@app.command("fetch")
def fetch(
    period: Annotated[
        str | None,
        typer.Option(
            "--period", "-p",
            help="Data month as YYYY-MM (default: most recent seed period)",
        ),
    ] = None,
    source_url: Annotated[
        str | None,
        typer.Option(
            "--source-url",
            help="Live-parse this URL (MoSPI PDF, FRED CSV, etc.) instead of using the seed",
        ),
    ] = None,
    source: Annotated[
        str,
        typer.Option(
            "--source",
            help="Data source: 'seed' (bundled JSON, default — currently the freshest India "
            "IIP available, to 2025-04) or 'dbnomics' (IMF/IFS — only reaches 2024-10, staler). "
            "Ignored when --source-url is given.",
        ),
    ] = "seed",
) -> None:
    """Fetch one month of India IIP and upsert into the DB."""
    try:
        client = IIPClient()
    except IIPClientError as exc:
        console.print(f"[red]IIP client error:[/] {exc}")
        raise typer.Exit(1)

    with client:
        if source_url is not None:
            if period is None:
                console.print(
                    "[red]--source-url requires --period to know which month it applies to.[/red]"
                )
                raise typer.Exit(2)
            row = client.fetch_month(period, source_url=source_url)
        elif source == "dbnomics":
            # period None → latest available dbnomics month (fresher than seed).
            row = client.fetch_from_dbnomics(period)
            period = row.period if row is not None else period
        else:
            target_period = period or (client.known_periods[-1] if client.known_periods else None)
            if target_period is None:
                console.print("[yellow]Seed contains zero periods.[/yellow]")
                raise typer.Exit(1)
            row = client.fetch_month(target_period)
            period = target_period

        if row is None:
            console.print(
                f"[yellow]No IIP data for period {period!r} via source={source!r}. "
                f"Latest seed periods: {', '.join(client.known_periods[-6:])}[/yellow]",
            )
            raise typer.Exit(1)

        with FlowStore() as store:
            upserted = store.upsert_iip_monthly([row])

    display_iip_fetch_result(upserted, period=row.period)


@app.command("backfill")
def backfill(
    from_period: Annotated[
        str,
        typer.Option("--from", "-f", help="Start period YYYY-MM (inclusive)"),
    ],
    to_period: Annotated[
        str,
        typer.Option("--to", "-t", help="End period YYYY-MM (inclusive)"),
    ],
) -> None:
    """Bulk-load IIP rows for every month in ``[--from, --to]`` from the seed."""
    try:
        client = IIPClient()
    except IIPClientError as exc:
        console.print(f"[red]IIP client error:[/] {exc}")
        raise typer.Exit(1)

    with client:
        try:
            rows = client.fetch_backfill(from_period, to_period)
        except ValueError as exc:
            console.print(f"[red]Invalid period range:[/] {exc}")
            raise typer.Exit(2)
        if not rows:
            console.print(
                f"[yellow]Seed has zero periods in [{from_period}, {to_period}].[/yellow]",
            )
            raise typer.Exit(1)
        with FlowStore() as store:
            upserted = store.upsert_iip_monthly(rows)

    console.print(
        f"[green]Backfilled {upserted} month(s) of IIP "
        f"from {rows[0].period} to {rows[-1].period}.[/green]",
    )


@app.command("latest")
def latest() -> None:
    """Show the most recent stored IIP row."""
    with FlowStore() as store:
        row = store.get_iip_latest()
    display_iip_latest(row)


@app.command("trend")
def trend(
    months: Annotated[
        int,
        typer.Option("--months", "-n", help="Number of most recent months to show"),
    ] = 24,
) -> None:
    """Print the last N months of IIP with YoY% color-coded."""
    if months < 1:
        console.print("[red]--months must be >= 1.[/red]")
        raise typer.Exit(2)
    with FlowStore() as store:
        rows = store.get_iip_trend(months)
    display_iip_trend(rows)
