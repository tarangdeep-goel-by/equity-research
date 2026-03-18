"""CLI commands for AMFI mutual fund flow data."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.mf_client import AMFIClient, AMFIFetchError
from flowtracker.mf_display import (
    display_mf_aum_trend,
    display_mf_fetch_result,
    display_mf_flows_table,
    display_mf_summary,
)
from flowtracker.mf_models import MFMonthlyFlow
from flowtracker.store import FlowStore

app = typer.Typer(
    name="mf",
    help="AMFI mutual fund flow data — monthly scheme-category-level flows and AUM",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    month: Annotated[int, typer.Option("--month", "-m", help="Month (1-12)")] = 0,
    year: Annotated[int, typer.Option("--year", "-y", help="Year (e.g. 2026)")] = 0,
) -> None:
    """Fetch a specific month's AMFI report (defaults to previous month)."""
    if month == 0 or year == 0:
        today = date.today()
        # Default to previous month
        if today.month == 1:
            year = year or (today.year - 1)
            month = month or 12
        else:
            year = year or today.year
            month = month or (today.month - 1)

    month_str = f"{year}-{month:02d}"

    try:
        with AMFIClient() as client:
            rows, summary = client.fetch_monthly(year, month)
    except AMFIFetchError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        # Convert to MFMonthlyFlow for storage
        flows = [
            MFMonthlyFlow(
                month=month_str,
                category=r.category,
                sub_category=r.sub_category,
                num_schemes=r.num_schemes,
                funds_mobilized=r.funds_mobilized,
                redemption=r.redemption,
                net_flow=r.net_flow,
                aum=r.aum,
            )
            for r in rows
        ]
        store.upsert_mf_flows(flows)
        store.upsert_mf_aum(summary)

    display_mf_fetch_result(rows, month_str)


@app.command()
def summary() -> None:
    """Show latest month's MF AUM summary by category."""
    with FlowStore() as store:
        aum = store.get_mf_latest_aum()

    if aum is None:
        console.print("[yellow]No MF data available. Run 'flowtrack mf fetch' first.[/]")
        raise typer.Exit(1)

    display_mf_summary(aum)


@app.command()
def flows(
    period: Annotated[str, typer.Option("-p", "--period", help="Period like '12m' or '6m'")] = "12m",
    category: Annotated[str | None, typer.Option("-c", "--category", help="Filter by category: Equity, Debt, Hybrid")] = None,
) -> None:
    """Show historical MF flows by category."""
    # Parse period (e.g. "12m" -> 12 months)
    try:
        if period.endswith("m"):
            months = int(period[:-1])
        else:
            months = int(period)
    except ValueError:
        console.print(f"[red]Invalid period '{period}' — use format like '12m' or '6m'[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        data = store.get_mf_flows(months, category)

    display_mf_flows_table(data, period)


@app.command()
def aum() -> None:
    """Show MF AUM trend over time (equity % of total, monthly)."""
    with FlowStore() as store:
        summaries = store.get_mf_aum_trend(24)

    display_mf_aum_trend(summaries)


@app.command()
def backfill(
    from_month: Annotated[str, typer.Option("--from", help="Start month (YYYY-MM)")] = "2019-04",
    to_month: Annotated[str, typer.Option("--to", help="End month (YYYY-MM)")] = "",
) -> None:
    """Bulk import AMFI reports for a date range."""
    if not to_month:
        today = date.today()
        if today.month == 1:
            to_month = f"{today.year - 1}-12"
        else:
            to_month = f"{today.year}-{today.month - 1:02d}"

    try:
        start_y, start_m = map(int, from_month.split("-"))
        end_y, end_m = map(int, to_month.split("-"))
    except ValueError:
        console.print("[red]Invalid month format. Use YYYY-MM.[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Backfilling AMFI data from {from_month} to {to_month}...[/]\n")

    try:
        with AMFIClient() as client:
            results = client.fetch_range(start_y, start_m, end_y, end_m)
    except AMFIFetchError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    if not results:
        console.print("[yellow]No data fetched.[/]")
        raise typer.Exit(1)

    total_rows = 0
    with FlowStore() as store:
        for rows, summary in results:
            month_str = summary.month
            flows = [
                MFMonthlyFlow(
                    month=month_str,
                    category=r.category,
                    sub_category=r.sub_category,
                    num_schemes=r.num_schemes,
                    funds_mobilized=r.funds_mobilized,
                    redemption=r.redemption,
                    net_flow=r.net_flow,
                    aum=r.aum,
                )
                for r in rows
            ]
            count = store.upsert_mf_flows(flows)
            store.upsert_mf_aum(summary)
            total_rows += count
            console.print(f"  [dim]{month_str}:[/] {count} rows")

    console.print(f"\n[bold]Backfill complete:[/] {total_rows} rows across {len(results)} months")
