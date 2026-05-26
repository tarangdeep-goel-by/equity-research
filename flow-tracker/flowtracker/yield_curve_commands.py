"""CLI commands for the India G-sec yield curve (1Y / 5Y / 10Y / 30Y).

Today's curve is fetched as part of the existing ``flowtrack macro fetch``
flow (via the extended ``MacroClient._fetch_gsec_curve()``). This
subcommand group focuses on historical backfill and curve-shape display.

Commands:

* ``flowtrack yield-curve backfill [--from YYYY-MM-DD] [--to YYYY-MM-DD]``
  — load historical curve snapshots from the bundled FBIL/CCIL seed.
* ``flowtrack yield-curve curve`` — show today's full curve as a panel.
* ``flowtrack yield-curve trend [--days N]`` — show curve evolution
  over the last N days.
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.store import FlowStore
from flowtracker.yield_curve_client import YieldCurveClient, YieldCurveClientError
from flowtracker.yield_curve_display import display_yield_curve, display_yield_curve_trend

app = typer.Typer(
    name="yield-curve",
    help="India G-sec yield curve (1Y / 5Y / 10Y / 30Y) — backfill, curve, trend",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)


@app.command("backfill")
def backfill(
    from_date: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Start date YYYY-MM-DD (default: seed earliest)"),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", "-t", help="End date YYYY-MM-DD (default: seed latest)"),
    ] = None,
) -> None:
    """Load historical yield-curve snapshots from the bundled seed.

    Snapshots are upserted into ``macro_daily`` (only the gsec_* columns
    are populated; FX/VIX/Brent stay NULL on the seed-supplied rows).
    """
    try:
        client = YieldCurveClient()
    except YieldCurveClientError as exc:
        console.print(f"[red]Yield-curve client error:[/] {exc}")
        raise typer.Exit(1)

    if from_date is None:
        from_date = client.known_dates[0] if client.known_dates else ""
    if to_date is None:
        to_date = client.known_dates[-1] if client.known_dates else ""
    if not (from_date and to_date):
        console.print("[yellow]Yield-curve seed contains zero snapshots.[/yellow]")
        raise typer.Exit(1)

    snapshots = client.fetch_in_range(from_date, to_date)
    if not snapshots:
        console.print(
            f"[yellow]Seed has zero snapshots in [{from_date}, {to_date}].[/yellow]",
        )
        raise typer.Exit(1)

    records = client.to_macro_snapshots(snapshots)
    with FlowStore() as store:
        upserted = store.upsert_macro_snapshots(records)

    console.print(
        f"[green]Backfilled {upserted} yield-curve snapshot(s) "
        f"from {snapshots[0].date} to {snapshots[-1].date}.[/green]",
    )


@app.command("curve")
def curve() -> None:
    """Show today's (most-recent stored) full G-sec yield curve."""
    with FlowStore() as store:
        row = store.get_yield_curve_latest()
    display_yield_curve(row)


@app.command("trend")
def trend(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history to show"),
    ] = 90,
) -> None:
    """Show yield-curve evolution over the last N days."""
    if days < 1:
        console.print("[red]--days must be >= 1.[/red]")
        raise typer.Exit(2)
    with FlowStore() as store:
        rows = store.get_yield_curve_history(days)
    display_yield_curve_trend(rows)
