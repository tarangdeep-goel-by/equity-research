"""CLI commands for daily per-scheme MF NAV history (mfapi.in).

Four commands, mirroring the cpi / commodity command groups:

* ``flowtrack mfnav fetch [--scheme CODE] [--since-days N]`` — pull recent
  NAVs for every scheme in the bundled equity universe (or one scheme via
  ``--scheme``) and upsert them. Defaults to the last ~10 days so the daily
  cron stays cheap; the upsert is idempotent on ``(scheme_code, date)``.
* ``flowtrack mfnav backfill [--scheme CODE] [--days N | --from --to]`` —
  bulk historical NAV fetch for all schemes (or one). ``--days`` is a
  lookback window; ``--from`` is an explicit ISO lower bound.
* ``flowtrack mfnav latest`` — show the most recent stored NAV per scheme
  (Rich table) for the full stored universe.
* ``flowtrack mfnav trend --scheme CODE [--days N]`` — tabular NAV history
  for one scheme.

Per-scheme fetch failures are logged and skipped (one bad scheme never
aborts the rest) — the client's ``fetch_universe`` already omits failed
codes, and the single-scheme path catches ``MFNavFetchError`` directly.
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from flowtracker.mf_nav_client import EQUITY_SCHEMES, MFNavClient, MFNavFetchError
from flowtracker.store import FlowStore

app = typer.Typer(
    name="mfnav",
    help="Daily MF scheme NAV history (mfapi.in) — ~30 equity schemes",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)


@app.command("fetch")
def fetch(
    scheme: Annotated[
        str | None,
        typer.Option(
            "--scheme", "-s",
            help="AMFI scheme code to fetch (default: full equity universe)",
        ),
    ] = None,
    since_days: Annotated[
        int,
        typer.Option(
            "--since-days", "-n",
            help="Only upsert NAVs from the last N days (keeps cron cheap)",
        ),
    ] = 10,
) -> None:
    """Fetch recent NAV(s) and upsert into the DB.

    Defaults to every scheme in the client's bundled universe; pass
    ``--scheme`` for a single AMFI code.
    """
    if since_days < 1:
        console.print("[red]--since-days must be >= 1.[/red]")
        raise typer.Exit(2)

    # ISO lower bound N calendar days back.
    from datetime import date, timedelta

    since = (date.today() - timedelta(days=since_days)).isoformat()

    total = 0
    schemes_done = 0
    with MFNavClient() as client, FlowStore() as store:
        if scheme is not None:
            try:
                code = int(scheme)
            except ValueError:
                console.print(f"[red]Invalid scheme code:[/] {scheme!r} (must be an integer)")
                raise typer.Exit(2)
            try:
                rows = client.fetch_scheme(code, since=since)
            except MFNavFetchError as exc:
                console.print(f"[red]Fetch failed for scheme {code}:[/] {exc}")
                raise typer.Exit(1)
            total += store.upsert_mf_scheme_navs(rows)
            schemes_done += 1
        else:
            results = client.fetch_universe(since=since)
            for code, rows in results.items():
                total += store.upsert_mf_scheme_navs(rows)
                schemes_done += 1
            missing = len(EQUITY_SCHEMES) - len(results)
            if missing:
                console.print(
                    f"[yellow]{missing} scheme(s) failed to fetch and were skipped.[/yellow]"
                )

    console.print(
        f"[green]Upserted {total} NAV row(s) across {schemes_done} scheme(s) "
        f"(since {since}).[/green]"
    )


@app.command("backfill")
def backfill(
    scheme: Annotated[
        str | None,
        typer.Option(
            "--scheme", "-s",
            help="AMFI scheme code to backfill (default: full equity universe)",
        ),
    ] = None,
    days: Annotated[
        int | None,
        typer.Option(
            "--days", "-d",
            help="Lookback window in days (mutually exclusive with --from)",
        ),
    ] = None,
    from_date: Annotated[
        str | None,
        typer.Option(
            "--from", "-f",
            help="Explicit ISO lower bound YYYY-MM-DD (overrides --days)",
        ),
    ] = None,
) -> None:
    """Bulk historical NAV fetch for all schemes (or one).

    With neither ``--days`` nor ``--from``, fetches the full
    inception-to-date history. ``--from`` takes precedence over ``--days``.
    """
    since: str | None
    if from_date is not None:
        since = from_date
    elif days is not None:
        if days < 1:
            console.print("[red]--days must be >= 1.[/red]")
            raise typer.Exit(2)
        from datetime import date, timedelta

        since = (date.today() - timedelta(days=days)).isoformat()
    else:
        since = None  # full history

    label = since if since is not None else "inception"
    total = 0
    schemes_done = 0
    with MFNavClient() as client, FlowStore() as store:
        if scheme is not None:
            try:
                code = int(scheme)
            except ValueError:
                console.print(f"[red]Invalid scheme code:[/] {scheme!r} (must be an integer)")
                raise typer.Exit(2)
            console.print(f"[dim]Backfilling scheme {code} since {label}...[/]")
            try:
                rows = client.fetch_scheme(code, since=since)
            except MFNavFetchError as exc:
                console.print(f"[red]Backfill failed for scheme {code}:[/] {exc}")
                raise typer.Exit(1)
            total += store.upsert_mf_scheme_navs(rows)
            schemes_done += 1
        else:
            console.print(
                f"[dim]Backfilling {len(EQUITY_SCHEMES)} schemes since {label}...[/]"
            )
            results = client.fetch_universe(since=since)
            for code, rows in results.items():
                total += store.upsert_mf_scheme_navs(rows)
                schemes_done += 1
            missing = len(EQUITY_SCHEMES) - len(results)
            if missing:
                console.print(
                    f"[yellow]{missing} scheme(s) failed to fetch and were skipped.[/yellow]"
                )

    console.print(
        f"[green]Backfilled {total} NAV row(s) across {schemes_done} scheme(s) "
        f"(since {label}).[/green]"
    )


@app.command("latest")
def latest() -> None:
    """Show the most recent stored NAV per scheme as a Rich table."""
    with FlowStore() as store:
        universe = store.get_mf_scheme_nav_universe()

    if not universe:
        console.print(
            "[yellow]No NAVs stored yet. Run "
            "'flowtrack mfnav fetch' or 'flowtrack mfnav backfill' first.[/yellow]"
        )
        return

    table = Table(title=f"Latest MF Scheme NAVs ({len(universe)} schemes)")
    table.add_column("Code", justify="right", style="cyan")
    table.add_column("Scheme", style="white")
    table.add_column("Latest Date", justify="center")
    table.add_column("NAV", justify="right", style="green")
    table.add_column("History", justify="right", style="dim")

    with FlowStore() as store:
        for code, name, first_date, last_date, n in universe:
            row = store.get_mf_scheme_nav_latest(code)
            nav_str = f"{row.nav:,.4f}" if row is not None else "—"
            table.add_row(
                str(code),
                name,
                last_date,
                nav_str,
                f"{n} rows · from {first_date}",
            )

    console.print(table)


@app.command("trend")
def trend(
    scheme: Annotated[
        str,
        typer.Option("--scheme", "-s", help="AMFI scheme code"),
    ],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of most recent days to show"),
    ] = 30,
) -> None:
    """Print the last N days of NAV history for one scheme."""
    if days < 1:
        console.print("[red]--days must be >= 1.[/red]")
        raise typer.Exit(2)
    try:
        code = int(scheme)
    except ValueError:
        console.print(f"[red]Invalid scheme code:[/] {scheme!r} (must be an integer)")
        raise typer.Exit(2)

    with FlowStore() as store:
        rows = store.get_mf_scheme_nav_history(code, days=days)

    if not rows:
        console.print(
            f"[yellow]No NAV history stored for scheme {code} "
            f"in the last {days} days.[/yellow]"
        )
        return

    scheme_name = rows[-1].scheme_name or str(code)
    table = Table(title=f"{scheme_name} ({code}) — last {days} days")
    table.add_column("Date", justify="center", style="cyan")
    table.add_column("NAV", justify="right", style="green")
    table.add_column("Δ%", justify="right")

    prev: float | None = None
    for r in rows:
        if prev is not None and prev != 0:
            pct = (r.nav - prev) / prev * 100.0
            color = "green" if pct >= 0 else "red"
            chg = f"[{color}]{pct:+.2f}%[/{color}]"
        else:
            chg = "—"
        table.add_row(r.date, f"{r.nav:,.4f}", chg)
        prev = r.nav

    console.print(table)
