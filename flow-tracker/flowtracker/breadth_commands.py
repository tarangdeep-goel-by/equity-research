"""CLI commands for market-breadth metrics.

Breadth is computed from `daily_stock_data` + `index_constituents` —
no external HTTP. Recompute is cheap (~1s per (date, index)). Cron
should run `breadth recompute` after the daily bhavcopy fetch lands.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.breadth_compute import (
    DEFAULT_INDICES,
    compute_range,
    compute_snapshot,
)
from flowtracker.breadth_display import (
    display_breadth_latest,
    display_breadth_trend,
    display_recompute_result,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="breadth",
    help="Market breadth — % above 200DMA, advance/decline, 52w highs/lows",
    no_args_is_help=True,
)
console = Console()


@app.command()
def recompute(
    target_date: Annotated[
        str | None,
        typer.Option("--date", help="YYYY-MM-DD; default = latest trading day in DB"),
    ] = None,
    index_name: Annotated[
        str | None,
        typer.Option("--index", help="Index name; default = all 4 standard indices"),
    ] = None,
) -> None:
    """Recompute breadth for a single date across one or all indices."""
    indices = [index_name] if index_name else list(DEFAULT_INDICES)
    with FlowStore() as store:
        if target_date is None:
            row = store._conn.execute(
                "SELECT MAX(date) AS d FROM daily_stock_data"
            ).fetchone()
            target_date = row["d"]
            if target_date is None:
                console.print(
                    "[red]No bhavcopy data in DB — run "
                    "'flowtrack bhavcopy fetch' first.[/]"
                )
                raise typer.Exit(1)

        snapshots = []
        for idx in indices:
            snap = compute_snapshot(store, target_date, idx)
            if snap is not None:
                snapshots.append(snap)
            else:
                console.print(
                    f"[yellow]Skipped {idx} — no constituent prices on {target_date}.[/]"
                )

        if not snapshots:
            console.print(f"[red]No breadth snapshots produced for {target_date}.[/]")
            raise typer.Exit(1)
        written = store.upsert_breadth_snapshots(snapshots)

    display_recompute_result(written, dates=1, indices=len(snapshots))


@app.command()
def backfill(
    from_date: Annotated[
        str, typer.Option("--from", help="Start date YYYY-MM-DD (inclusive)"),
    ],
    to_date: Annotated[
        str | None,
        typer.Option("--to", help="End date YYYY-MM-DD (inclusive); default = today"),
    ] = None,
    index_name: Annotated[
        str | None,
        typer.Option("--index", help="Index name; default = all 4 standard indices"),
    ] = None,
) -> None:
    """Recompute breadth for every trading day in [from, to]."""
    indices = [index_name] if index_name else list(DEFAULT_INDICES)
    end = to_date or _date.today().isoformat()

    with FlowStore() as store:
        console.print(
            f"[dim]Computing breadth for {from_date} → {end} "
            f"across {len(indices)} index/indices...[/]"
        )
        snapshots = compute_range(store, from_date, end, indices)
        if not snapshots:
            console.print(
                f"[yellow]No snapshots produced — check that "
                f"daily_stock_data covers {from_date}..{end}.[/]"
            )
            raise typer.Exit(1)
        written = store.upsert_breadth_snapshots(snapshots)

    dates = len({s.date for s in snapshots})
    display_recompute_result(written, dates=dates, indices=len(indices))


@app.command()
def latest() -> None:
    """Show today's breadth for all 4 indices."""
    with FlowStore() as store:
        snapshots = [
            snap for idx in DEFAULT_INDICES
            if (snap := store.get_breadth_latest(idx)) is not None
        ]
    display_breadth_latest(snapshots)
    if not snapshots:
        raise typer.Exit(1)


@app.command()
def trend(
    index_name: Annotated[
        str, typer.Option("--index", help="Index name (e.g. 'NIFTY 500')"),
    ] = "NIFTY 500",
    days: Annotated[
        int, typer.Option("--days", "-d", help="Number of recent days to show"),
    ] = 30,
) -> None:
    """Show breadth trend for one index over the last N days."""
    with FlowStore() as store:
        snapshots = store.get_breadth_trend(index_name, days)
    display_breadth_trend(snapshots, index_name)
    if not snapshots:
        raise typer.Exit(1)
