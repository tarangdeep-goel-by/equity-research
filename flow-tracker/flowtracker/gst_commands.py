"""CLI commands for monthly GST (Goods & Services Tax) collections.

Four commands:

* ``flowtrack gst fetch [--period YYYY-MM] [--source-url URL]`` — pull one
  month's release. Defaults to "whatever is the freshest known row" if
  ``--period`` is omitted. ``--source-url`` activates the defensive live
  parser instead of the bundled seed.
* ``flowtrack gst backfill --from YYYY-MM --to YYYY-MM`` — bulk-load a
  period range from the seed; logs any missing periods so the analyst
  knows what to chase.
* ``flowtrack gst latest`` — print the most recent stored month as a panel.
* ``flowtrack gst trend [--months N]`` — print the last N months with
  YoY% color-coded.

GST is Alok's #1 macro indicator (the fastest real-time proxy for nominal
GDP / consumption), so the surface is intentionally lightweight — the value
is in having the data in the DB, not in elaborate CLI options.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.gst_client import GSTClient, GSTClientError
from flowtracker.gst_display import (
    display_gst_fetch_result,
    display_gst_latest,
    display_gst_trend,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="gst",
    help="Monthly GST collections (CBIC / PIB press release)",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)


def _previous_month_period() -> str:
    """Return the previous calendar month as ``YYYY-MM``.

    Used as the default target for ``gst fetch`` when no ``--period`` is
    supplied — GST collections for month N are published on the 1st of
    month N+1, so "the previous month" is the freshest live row.
    """
    today = date.today()
    y, m = today.year, today.month - 1
    if m < 1:
        m = 12
        y -= 1
    return f"{y:04d}-{m:02d}"


@app.command("fetch")
def fetch(
    period: Annotated[
        str | None,
        typer.Option(
            "--period", "-p",
            help="Collection month as YYYY-MM (default: previous calendar month)",
        ),
    ] = None,
    source_url: Annotated[
        str | None,
        typer.Option(
            "--source-url",
            help="Bypass discovery and live-parse this CBIC / PIB / GST Council URL",
        ),
    ] = None,
    no_live: Annotated[
        bool,
        typer.Option(
            "--no-live",
            help="Skip Playwright live discovery; serve only from the bundled seed.",
        ),
    ] = False,
) -> None:
    """Fetch one month of GST collections and upsert into the DB.

    Resolution order:

    1. If ``--source-url`` is given, live-parse that URL (no discovery).
    2. Otherwise (default) try Playwright live discovery on gst.gov.in
       for the target period.
    3. Fall back to the bundled seed JSON if live fetch fails or
       ``--no-live`` is set.
    4. If neither path yields data, exit with status 1.

    With no flags this targets the previous calendar month — the freshest
    one CBIC could realistically have published (released on the 1st of
    the following month).
    """
    try:
        client = GSTClient()
    except GSTClientError as exc:
        console.print(f"[red]GST client error:[/] {exc}")
        raise typer.Exit(1)

    with client:
        if source_url is not None:
            if period is None:
                console.print(
                    "[red]--source-url requires --period to know which month it applies to.[/red]"
                )
                raise typer.Exit(2)
            row = client.fetch_month(period, source_url=source_url)
            path_used = "explicit source-url"
        else:
            target_period = period or _previous_month_period()
            row = None

            if not no_live:
                try:
                    row = client.fetch_month_live(target_period)
                except Exception as exc:  # noqa: BLE001 — fall through to seed
                    logger.warning("GST live fetch raised; falling back to seed: %s", exc)
                    row = None

            if row is not None:
                path_used = "live (Playwright + PDF)"
            else:
                row = client.fetch_month(target_period)
                path_used = "seed (live unavailable)" if not no_live else "seed (forced)"

            period = target_period

        if row is None:
            console.print(
                f"[yellow]No GST data for period {period!r}. "
                f"Available seed periods: {', '.join(client.known_periods[-6:])}[/yellow]",
            )
            raise typer.Exit(1)

        logger.info("GST fetch path: %s; period=%s", path_used, row.period)
        console.print(f"[dim]Source: {path_used}[/dim]")

        with FlowStore() as store:
            upserted = store.upsert_gst_collections([row])

    display_gst_fetch_result(upserted, period=row.period)


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
    """Bulk-load every month in ``[--from, --to]`` from the bundled seed.

    Periods missing from the seed are reported but do not abort the run —
    backfill is best-effort. Use ``flowtrack gst fetch --period YYYY-MM
    --source-url ...`` to fill specific gaps after the fact.
    """
    try:
        client = GSTClient()
    except GSTClientError as exc:
        console.print(f"[red]GST client error:[/] {exc}")
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
            upserted = store.upsert_gst_collections(rows)

    console.print(
        f"[green]Backfilled {upserted} month(s) of GST collections "
        f"from {rows[0].period} to {rows[-1].period}.[/green]",
    )


@app.command("latest")
def latest() -> None:
    """Show the most recent stored GST collection row as a headline panel."""
    with FlowStore() as store:
        row = store.get_gst_latest()
    display_gst_latest(row)


@app.command("trend")
def trend(
    months: Annotated[
        int,
        typer.Option("--months", "-n", help="Number of most recent months to show"),
    ] = 24,
) -> None:
    """Print the last N months of GST collections with YoY% color-coded.

    The default 24 covers two full fiscal years — long enough to spot
    seasonality (April is always the all-time-high because Mar 31 financial-
    year-end transactions reconcile in April collections) and the broader
    growth trajectory.
    """
    if months < 1:
        console.print("[red]--months must be >= 1.[/red]")
        raise typer.Exit(2)
    with FlowStore() as store:
        rows = store.get_gst_trend(months)
    display_gst_trend(rows)
