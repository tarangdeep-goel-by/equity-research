"""CLI commands for AMFI mutual fund flow data."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.mf_client import AMFIClient, AMFIFetchError
from flowtracker.mf_display import (
    display_mf_aum_trend,
    display_mf_daily_summary,
    display_mf_daily_trend,
    display_mf_fetch_result,
    display_mf_flows_table,
    display_mf_nav_backfill_result,
    display_mf_nav_coverage,
    display_mf_nav_latest,
    display_mf_nav_trend,
    display_mf_summary,
)
from flowtracker.mf_models import MFMonthlyFlow
from flowtracker.mf_nav_client import EQUITY_SCHEMES, MFNavClient, MFNavFetchError
from flowtracker.sebi_client import SEBIClient, SEBIFetchError
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


# -- Daily MF flows (SEBI) --

daily_app = typer.Typer(
    name="daily",
    help="SEBI daily MF equity/debt purchase and sale data",
    no_args_is_help=True,
)
app.add_typer(daily_app)


@daily_app.command("fetch")
def daily_fetch() -> None:
    """Fetch current month's daily MF flows from SEBI."""
    try:
        with SEBIClient() as client:
            flows = client.fetch_daily()
    except SEBIFetchError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    if not flows:
        console.print("[yellow]No daily MF data found on SEBI page.[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        count = store.upsert_mf_daily_flows(flows)

    dates = sorted({f.date for f in flows})
    console.print(f"Fetched {len(flows)} records ({len(dates)} trading days: {dates[0]} to {dates[-1]})")
    console.print(f"Stored {count} records.")


@daily_app.command("summary")
def daily_summary() -> None:
    """Show latest day's MF daily flows (equity + debt)."""
    with FlowStore() as store:
        flows = store.get_mf_daily_latest()

    display_mf_daily_summary(flows)


@daily_app.command("trend")
def daily_trend(
    days: Annotated[int, typer.Option("-d", "--days", help="Number of days")] = 30,
) -> None:
    """Show daily MF equity/debt net investment trend."""
    with FlowStore() as store:
        data = store.get_mf_daily_summary(days)

    display_mf_daily_trend(data)


# -- Daily per-scheme NAVs (mfapi.in) --

nav_app = typer.Typer(
    name="nav",
    help=(
        "Daily per-scheme NAV history from mfapi.in. The curated equity"
        " universe (~30 schemes — large / mid / small / flexi / multi /"
        " focused / ELSS / value / contra / index / sectoral) lives in"
        " flowtracker.mf_nav_client.EQUITY_SCHEMES."
    ),
    no_args_is_help=True,
)
app.add_typer(nav_app)


def _resolve_scheme_arg(scheme: str | None) -> list[tuple[int, str]]:
    """Resolve --scheme to a (code, label) list.

    ``None`` / ``"all"`` → curated EQUITY_SCHEMES.
    Integer string → single scheme with no label.
    Anything else → BadParameter.
    """
    if scheme is None or scheme.lower() == "all":
        return list(EQUITY_SCHEMES)
    try:
        code = int(scheme)
    except ValueError as exc:
        raise typer.BadParameter(
            "--scheme must be an AMFI scheme code (integer) or 'all'."
        ) from exc
    # Look up label from curated list if it's there
    for c, label in EQUITY_SCHEMES:
        if c == code:
            return [(code, label)]
    return [(code, f"scheme {code}")]


@nav_app.command("fetch")
def nav_fetch(
    scheme: Annotated[
        str | None,
        typer.Option(
            "--scheme", "-s",
            help="AMFI scheme code (integer) or 'all' for the curated universe.",
        ),
    ] = None,
    days: Annotated[
        int,
        typer.Option(
            "-d", "--days",
            help="Trailing window in days (default 30; mfapi serves history.).",
        ),
    ] = 30,
) -> None:
    """Fetch recent NAV rows for one scheme or the curated equity universe."""
    targets = _resolve_scheme_arg(scheme)
    since = MFNavClient.default_since(years=max(1, (days // 366) + 1))
    # Use days-based cutoff via direct date for tight windows
    if days < 366:
        from datetime import date as _d, timedelta as _td
        since = (_d.today() - _td(days=days)).isoformat()

    total = 0
    with MFNavClient() as client, FlowStore() as store:
        for code, label in targets:
            try:
                rows = client.fetch_scheme(code, since=since)
            except MFNavFetchError as exc:
                console.print(f"[red]{label} ({code}): {exc}[/]")
                continue
            count = store.upsert_mf_scheme_navs(rows)
            total += count
            console.print(f"  [dim]{label}[/] ({code}): {count} rows")
    console.print(f"\n[bold]NAV fetch complete:[/] {total} rows across {len(targets)} schemes")


@nav_app.command("backfill")
def nav_backfill(
    scheme: Annotated[
        str | None,
        typer.Option(
            "--scheme", "-s",
            help="AMFI scheme code (integer) or 'all' for the curated universe.",
        ),
    ] = None,
    since: Annotated[
        str,
        typer.Option(
            "--since",
            help="Lower-bound ISO date (YYYY-MM-DD). Default 2015-01-01 covers ~10yr.",
        ),
    ] = "2015-01-01",
) -> None:
    """Backfill NAV history for the curated equity universe (or one scheme)."""
    targets = _resolve_scheme_arg(scheme)
    console.print(
        f"[bold]Backfilling NAVs since {since} for {len(targets)} scheme(s)[/]"
    )
    total = 0
    per_scheme: list[tuple[int, str, int]] = []
    with MFNavClient() as client, FlowStore() as store:
        for code, label in targets:
            try:
                rows = client.fetch_scheme(code, since=since)
            except MFNavFetchError as exc:
                console.print(f"[red]{label} ({code}): {exc}[/]")
                per_scheme.append((code, label, 0))
                continue
            count = store.upsert_mf_scheme_navs(rows)
            total += count
            per_scheme.append((code, label, count))
            console.print(f"  [dim]{label}[/] ({code}): {count} rows")
    display_mf_nav_backfill_result(per_scheme, total)


@nav_app.command("trend")
def nav_trend(
    scheme: Annotated[
        int,
        typer.Option(
            "--scheme", "-s",
            help="AMFI scheme code (integer).",
        ),
    ],
    days: Annotated[
        int, typer.Option("-d", "--days", help="Trailing window in days."),
    ] = 90,
) -> None:
    """Tabular NAV trend for one scheme over the last N days."""
    with FlowStore() as store:
        rows = store.get_mf_scheme_nav_history(scheme, days=days)
    display_mf_nav_trend(rows, days)


@nav_app.command("latest")
def nav_latest(
    scheme: Annotated[
        int,
        typer.Option("--scheme", "-s", help="AMFI scheme code (integer)."),
    ],
) -> None:
    """Print the most recent NAV for a scheme."""
    with FlowStore() as store:
        row = store.get_mf_scheme_nav_latest(scheme)
    display_mf_nav_latest(row)


@nav_app.command("coverage")
def nav_coverage() -> None:
    """Show stored NAV coverage per scheme (first / last date, row count)."""
    with FlowStore() as store:
        universe = store.get_mf_scheme_nav_universe()
    display_mf_nav_coverage(universe)
