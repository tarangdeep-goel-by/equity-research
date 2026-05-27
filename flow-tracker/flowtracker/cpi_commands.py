"""CLI commands for monthly India CPI (Consumer Price Index).

Four commands:

* ``flowtrack cpi fetch [--period YYYY-MM] [--source-url URL]`` — pull
  one month from the bundled seed (or live-parse a supplied URL).
  Defaults to the most recent seed period if ``--period`` is omitted.
* ``flowtrack cpi backfill --from YYYY-MM --to YYYY-MM`` — bulk-load
  every month in the range from the seed.
* ``flowtrack cpi latest`` — show the most recent stored row.
* ``flowtrack cpi trend [--months N]`` — show last N months with YoY%
  colored against the RBI's 4% target / 6% upper-tolerance band.
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.cpi_client import CPIClient, CPIClientError
from flowtracker.cpi_display import (
    display_cpi_fetch_result,
    display_cpi_latest,
    display_cpi_trend,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="cpi",
    help="Monthly India CPI inflation (MoSPI / FRED mirror)",
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
            help="Data source: 'dbnomics' (IMF/IFS via db.nomics.world — freshest, default) "
            "or 'seed' (bundled JSON). Ignored when --source-url is given.",
        ),
    ] = "dbnomics",
) -> None:
    """Fetch one month of India CPI and upsert into the DB."""
    try:
        client = CPIClient()
    except CPIClientError as exc:
        console.print(f"[red]CPI client error:[/] {exc}")
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
                f"[yellow]No CPI data for period {period!r} via source={source!r}. "
                f"Latest seed periods: {', '.join(client.known_periods[-6:])}[/yellow]",
            )
            raise typer.Exit(1)

        with FlowStore() as store:
            upserted = store.upsert_cpi_monthly([row])

    display_cpi_fetch_result(upserted, period=row.period)


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
    """Bulk-load CPI rows for every month in ``[--from, --to]`` from the seed."""
    try:
        client = CPIClient()
    except CPIClientError as exc:
        console.print(f"[red]CPI client error:[/] {exc}")
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
            upserted = store.upsert_cpi_monthly(rows)

    console.print(
        f"[green]Backfilled {upserted} month(s) of CPI "
        f"from {rows[0].period} to {rows[-1].period}.[/green]",
    )


@app.command("latest")
def latest() -> None:
    """Show the most recent stored CPI row as a headline panel."""
    with FlowStore() as store:
        row = store.get_cpi_latest()
    display_cpi_latest(row)


@app.command("trend")
def trend(
    months: Annotated[
        int,
        typer.Option("--months", "-n", help="Number of most recent months to show"),
    ] = 24,
) -> None:
    """Print the last N months of CPI with YoY% color-coded against the RBI band."""
    if months < 1:
        console.print("[red]--months must be >= 1.[/red]")
        raise typer.Exit(2)
    with FlowStore() as store:
        rows = store.get_cpi_trend(months)
    display_cpi_trend(rows)
