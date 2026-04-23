"""F&O (futures & options) ingestion CLI."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

from flowtracker.fno_client import FnoClient, FnoFetchError
from flowtracker.store import FlowStore

app = typer.Typer(
    name="fno",
    help="F&O (futures & options) ingestion — bhavcopy, participant OI, option chain",
    no_args_is_help=True,
)

universe_app = typer.Typer(
    name="universe",
    help="F&O-eligible symbol universe",
    no_args_is_help=True,
)
app.add_typer(universe_app)

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _fmt(val: object, suffix: str = "") -> str:
    """Format a value with '–' for None/missing."""
    if val is None:
        return "–"
    if isinstance(val, float):
        return f"{val:,.2f}{suffix}"
    if isinstance(val, int):
        return f"{val:,}{suffix}"
    return f"{val}{suffix}"


# ---------------------------------------------------------------------------
# 1. fno fetch
# ---------------------------------------------------------------------------

@app.command()
def fetch(
    date_str: Annotated[
        str | None, typer.Option("--date", help="Date as YYYY-MM-DD (default: today)")
    ] = None,
) -> None:
    """Fetch F&O bhavcopy + participant OI for a single trading day."""
    target = _parse_date(date_str) if date_str else date.today()
    try:
        with FnoClient() as client, FlowStore() as store:
            contracts = client.fetch_fno_bhavcopy(target)
            participants = client.fetch_participant_oi(target)
            if not contracts and not participants:
                console.print(
                    f"[yellow]No F&O data for {target.isoformat()} "
                    f"(holiday/weekend?)[/]"
                )
                raise typer.Exit(1)
            contracts_upserted = store.upsert_fno_contracts(contracts)
            participants_upserted = store.upsert_fno_participant_oi(participants)
    except FnoFetchError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    table = Table(title=f"F&O Fetch — {target.isoformat()}")
    table.add_column("metric")
    table.add_column("count", justify="right")
    table.add_row("bhavcopy contracts", f"{contracts_upserted:,}")
    table.add_row("participant OI rows", f"{participants_upserted:,}")
    console.print(table)


# ---------------------------------------------------------------------------
# 2. fno backfill
# ---------------------------------------------------------------------------

@app.command()
def backfill(
    from_date: Annotated[
        str | None,
        typer.Option("--from", help="Start date YYYY-MM-DD (default: 90 days ago)"),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", help="End date YYYY-MM-DD (default: yesterday)"),
    ] = None,
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing/--no-skip-existing",
            help="Skip days that already have F&O contract rows",
        ),
    ] = True,
) -> None:
    """Bulk backfill F&O bhavcopy + participant OI over a date range."""
    today = date.today()
    start = _parse_date(from_date) if from_date else today - timedelta(days=90)
    end = _parse_date(to_date) if to_date else today - timedelta(days=1)

    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)

    total_attempted = 0
    skipped = 0
    succeeded = 0
    failed = 0
    contracts_inserted = 0
    participant_rows_inserted = 0

    with FnoClient() as client, FlowStore() as store:
        for d in track(days, description="Backfilling F&O data..."):
            total_attempted += 1

            if skip_existing:
                existing = store._conn.execute(
                    "SELECT COUNT(*) FROM fno_contracts WHERE trade_date = ?",
                    (d.isoformat(),),
                ).fetchone()[0]
                if existing > 0:
                    skipped += 1
                    continue

            try:
                contracts = client.fetch_fno_bhavcopy(d)
                participants = client.fetch_participant_oi(d)
                if not contracts and not participants:
                    # Treat empty day as a no-op — holiday the calendar didn't catch.
                    continue
                contracts_inserted += store.upsert_fno_contracts(contracts)
                participant_rows_inserted += store.upsert_fno_participant_oi(participants)
                succeeded += 1
            except FnoFetchError as e:
                console.print(f"[red]{d.isoformat()}: {e}[/]")
                failed += 1
                continue

    table = Table(title=f"F&O Backfill — {start.isoformat()} to {end.isoformat()}")
    table.add_column("metric")
    table.add_column("count", justify="right")
    table.add_row("days attempted", f"{total_attempted:,}")
    table.add_row("skipped (already present)", f"{skipped:,}")
    table.add_row("succeeded", f"{succeeded:,}")
    table.add_row("failed", f"{failed:,}")
    table.add_row("contracts inserted", f"{contracts_inserted:,}")
    table.add_row("participant rows inserted", f"{participant_rows_inserted:,}")
    console.print(table)


# ---------------------------------------------------------------------------
# 3. fno universe refresh
# ---------------------------------------------------------------------------

@universe_app.command("refresh")
def universe_refresh() -> None:
    """Refresh the F&O-eligible symbol universe from NSE's lot-size CSV."""
    try:
        with FnoClient() as client, FlowStore() as store:
            before = set(store.get_fno_eligible_stocks())
            entries = client.fetch_eligible_universe()
            store.upsert_fno_universe(entries)
            after = set(store.get_fno_eligible_stocks())
    except FnoFetchError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    console.print(f"[green]Refreshed {len(entries)} eligible symbols[/]")

    added = sorted(after - before)
    removed = sorted(before - after)

    if not added and not removed:
        console.print("[dim]No change since last refresh[/]")
        return

    if added:
        console.print(f"[yellow]Added:[/] {', '.join(added)}")
    if removed:
        console.print(
            f"[yellow]Removed:[/] {', '.join(removed)} "
            f"(no longer in NSE-published file; rows retained in DB)"
        )


# ---------------------------------------------------------------------------
# 4. fno summary
# ---------------------------------------------------------------------------

@app.command()
def summary(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol")],
    as_of: Annotated[
        str | None,
        typer.Option("--as-of", help="Date as YYYY-MM-DD (default: today)"),
    ] = None,
) -> None:
    """Show F&O summary for a symbol — basis, PCR, OI percentile, top strikes."""
    sym = symbol.strip().upper()
    requested = _parse_date(as_of) if as_of else date.today()

    with FlowStore() as store:
        eligible = set(store.get_fno_eligible_stocks())
        if sym not in eligible:
            console.print(
                f"[yellow]{sym} is not F&O-eligible "
                f"(or universe not refreshed yet).[/]"
            )
            raise typer.Exit(1)

        # Walk back up to 5 days to find a trade date with data.
        effective: date | None = None
        for offset in range(6):
            candidate = requested - timedelta(days=offset)
            contracts = store.get_fno_contracts_for_date(sym, candidate)
            if contracts:
                effective = candidate
                break
        if effective is None:
            console.print(
                f"[yellow]No F&O data for {sym} within 5 days of "
                f"{requested.isoformat()}[/]"
            )
            raise typer.Exit(1)

        basis = store.get_basis(sym, effective)
        pcr = store.get_pcr(sym, effective)
        oi_pct = store.get_oi_percentile(sym, effective, lookback_days=90)
        contracts = store.get_fno_contracts_for_date(sym, effective)

    console.print(f"[bold]F&O Summary — {sym} ({effective.isoformat()})[/]")

    # Table 1 — Futures
    fut_table = Table(title="Futures")
    fut_table.add_column("metric")
    fut_table.add_column("value", justify="right")
    if basis:
        fut_table.add_row("spot", _fmt(basis.get("spot")))
        fut_table.add_row("front-month futures", _fmt(basis.get("futures")))
        fut_table.add_row("basis (abs)", _fmt(basis.get("basis_abs")))
        basis_pct = basis.get("basis_pct")
        fut_table.add_row(
            "basis (pct)",
            _fmt(basis_pct, "%") if basis_pct is not None else "–",
        )
        fut_table.add_row("days to expiry", _fmt(basis.get("days_to_expiry")))
    else:
        fut_table.add_row("spot", "–")
        fut_table.add_row("front-month futures", "–")
        fut_table.add_row("basis (abs)", "–")
        fut_table.add_row("basis (pct)", "–")
        fut_table.add_row("days to expiry", "–")
    console.print(fut_table)

    # Table 2 — Options (OI)
    opt_table = Table(title="Options (OI)")
    opt_table.add_column("metric")
    opt_table.add_column("value", justify="right")
    if pcr:
        pcr_oi = pcr.get("pcr_oi")
        opt_table.add_row("PCR (OI)", _fmt(pcr_oi) if pcr_oi is not None else "–")
        opt_table.add_row("total CE OI", _fmt(pcr.get("total_ce_oi")))
        opt_table.add_row("total PE OI", _fmt(pcr.get("total_pe_oi")))
    else:
        opt_table.add_row("PCR (OI)", "–")
        opt_table.add_row("total CE OI", "–")
        opt_table.add_row("total PE OI", "–")
    opt_table.add_row(
        "90d OI percentile",
        _fmt(oi_pct, "%") if oi_pct is not None else "–",
    )
    console.print(opt_table)

    # Top-3 CE/PE strikes by OI across OPTSTK rows.
    optstk = [c for c in contracts if c.get("instrument") == "OPTSTK"]
    ce_rows = sorted(
        [c for c in optstk if c.get("option_type") == "CE"],
        key=lambda r: r.get("open_interest") or 0,
        reverse=True,
    )[:3]
    pe_rows = sorted(
        [c for c in optstk if c.get("option_type") == "PE"],
        key=lambda r: r.get("open_interest") or 0,
        reverse=True,
    )[:3]

    ce_table = Table(title="Top call OI strikes")
    ce_table.add_column("strike", justify="right")
    ce_table.add_column("OI", justify="right")
    if ce_rows:
        for r in ce_rows:
            ce_table.add_row(_fmt(r.get("strike")), _fmt(r.get("open_interest")))
    else:
        ce_table.add_row("–", "–")
    console.print(ce_table)

    pe_table = Table(title="Top put OI strikes")
    pe_table.add_column("strike", justify="right")
    pe_table.add_column("OI", justify="right")
    if pe_rows:
        for r in pe_rows:
            pe_table.add_row(_fmt(r.get("strike")), _fmt(r.get("open_interest")))
    else:
        pe_table.add_row("–", "–")
    console.print(pe_table)


# ---------------------------------------------------------------------------
# 5. fno participant
# ---------------------------------------------------------------------------

_CATEGORIES = (
    "idx_fut",
    "idx_opt_ce",
    "idx_opt_pe",
    "stk_fut",
    "stk_opt_ce",
    "stk_opt_pe",
)


@app.command()
def participant(
    days: Annotated[
        int, typer.Option("--days", help="Number of trading days to show")
    ] = 5,
) -> None:
    """Show FII derivative positioning (long/short %) over the last N trading days."""
    trading_days: list[date] = []
    cursor = date.today()
    while len(trading_days) < days:
        if cursor.weekday() < 5:
            trading_days.append(cursor)
        cursor -= timedelta(days=1)
    trading_days.sort()

    with FlowStore() as store:
        rows_by_date: dict[date, dict[str, dict]] = {}
        for d in trading_days:
            pos = store.get_fii_derivative_positioning(d)
            rows_by_date[d] = (pos or {}).get("by_category", {}) if pos else {}

    table = Table(title=f"FII derivative positioning — last {days} trading days")
    table.add_column("date")
    for cat in _CATEGORIES:
        table.add_column(cat, justify="right")

    for d in trading_days:
        by_cat = rows_by_date.get(d, {})
        cells: list[str] = [d.isoformat()]
        for cat in _CATEGORIES:
            entry = by_cat.get(cat)
            if not entry:
                cells.append("–")
                continue
            net_long_pct = entry.get("net_long_pct")
            long_oi = entry.get("long_oi") or 0
            short_oi = entry.get("short_oi") or 0
            if net_long_pct is None:
                cells.append("–")
            else:
                cells.append(
                    f"{net_long_pct:.0f}% ({long_oi:,}/{short_oi:,})"
                )
        table.add_row(*cells)

    console.print(table)
