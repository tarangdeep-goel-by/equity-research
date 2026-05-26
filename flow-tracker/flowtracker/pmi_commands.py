"""CLI commands for monthly India PMI (Services + Manufacturing)."""

from __future__ import annotations

import logging
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.pmi_client import PMIClient, PMIClientError
from flowtracker.pmi_display import (
    display_pmi_fetch_result,
    display_pmi_latest,
    display_pmi_trend,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="pmi",
    help="Monthly India PMI Services + Manufacturing (S&P Global)",
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
            help="Live-parse this S&P Global press-release URL instead of using the seed",
        ),
    ] = None,
) -> None:
    """Fetch one month of India PMI and upsert into the DB."""
    try:
        client = PMIClient()
    except PMIClientError as exc:
        console.print(f"[red]PMI client error:[/] {exc}")
        raise typer.Exit(1)

    with client:
        if source_url is not None:
            if period is None:
                console.print(
                    "[red]--source-url requires --period to know which month it applies to.[/red]"
                )
                raise typer.Exit(2)
            row = client.fetch_month(period, source_url=source_url)
        else:
            target_period = period or (client.known_periods[-1] if client.known_periods else None)
            if target_period is None:
                console.print("[yellow]Seed contains zero periods.[/yellow]")
                raise typer.Exit(1)
            row = client.fetch_month(target_period)
            period = target_period

        if row is None:
            console.print(
                f"[yellow]No PMI data for period {period!r}. "
                f"Latest seed periods: {', '.join(client.known_periods[-6:])}[/yellow]",
            )
            raise typer.Exit(1)

        with FlowStore() as store:
            upserted = store.upsert_pmi_monthly([row])

    display_pmi_fetch_result(upserted, period=row.period)


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
    """Bulk-load PMI rows for every month in ``[--from, --to]`` from the seed."""
    try:
        client = PMIClient()
    except PMIClientError as exc:
        console.print(f"[red]PMI client error:[/] {exc}")
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
            upserted = store.upsert_pmi_monthly(rows)

    console.print(
        f"[green]Backfilled {upserted} month(s) of PMI "
        f"from {rows[0].period} to {rows[-1].period}.[/green]",
    )


@app.command("latest")
def latest() -> None:
    """Show the most recent stored PMI row."""
    with FlowStore() as store:
        row = store.get_pmi_latest()
    display_pmi_latest(row)


@app.command("trend")
def trend(
    months: Annotated[
        int,
        typer.Option("--months", "-n", help="Number of most recent months to show"),
    ] = 24,
) -> None:
    """Print the last N months of PMI with color-coded readings."""
    if months < 1:
        console.print("[red]--months must be >= 1.[/red]")
        raise typer.Exit(2)
    with FlowStore() as store:
        rows = store.get_pmi_trend(months)
    display_pmi_trend(rows)
