"""CLI commands for index-level PE/PB/Div-Yield history (niftyindices.com)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.indexpe_client import (
    BROAD_INDICES,
    INDEX_NAME_MAP,
    SECTORAL_INDICES,
    SUPPORTED_INDICES,
    THEMATIC_INDICES,
    IndexValuationClient,
    IndexValuationFetchError,
)
from flowtracker.indexpe_display import (
    display_indexpe_current,
    display_indexpe_fetch_result,
    display_indexpe_percentile,
    display_indexpe_trend,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="indexpe",
    help=(
        "Index-level PE/PB/Dividend-Yield history (niftyindices.com). "
        "Use `percentile` to answer 'rich vs cheap vs 10yr median' questions."
    ),
    no_args_is_help=True,
)
console = Console()


_PERIOD_RE = re.compile(r"^\s*(\d+)\s*([dmy])\s*$", re.IGNORECASE)


def _parse_period_to_days(period: str) -> int:
    """Convert a period like ``5y`` / ``18m`` / ``90d`` to a day count."""
    m = _PERIOD_RE.match(period)
    if not m:
        raise typer.BadParameter(
            f"Invalid period {period!r}. Use e.g. '90d', '18m', '10y'."
        )
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit == "d":
        return n
    if unit == "m":
        return n * 31
    return n * 366  # generous "year" so we capture the full window


def _normalise_index(name: str) -> str:
    canonical = name.strip().upper()
    if canonical not in INDEX_NAME_MAP:
        raise typer.BadParameter(
            f"Unsupported index {name!r}. Supported: {SUPPORTED_INDICES}"
        )
    return canonical


_GROUPS: dict[str, list[str]] = {
    "broad": BROAD_INDICES,
    "sectoral": SECTORAL_INDICES,
    "thematic": THEMATIC_INDICES,
    "all": SUPPORTED_INDICES,
}


def _indices_iter(index: str | None, group: str | None = None) -> list[str]:
    """Resolve the --index / --group flags to a list of canonical names.

    Precedence: --group wins over --index. ``--index all`` is treated as
    ``--group all``. Returns indices in deterministic order.
    """
    if group is not None:
        key = group.strip().lower()
        if key not in _GROUPS:
            raise typer.BadParameter(
                f"Unknown group {group!r}. Choose one of: {list(_GROUPS)}"
            )
        return list(_GROUPS[key])
    if index is None or index.lower() == "all":
        return list(SUPPORTED_INDICES)
    return [_normalise_index(index)]


@app.command()
def fetch(
    index: Annotated[
        str | None,
        typer.Option(
            "--index", "-i",
            help=(
                "Index display name (e.g. 'NIFTY 50'). Omit or use 'all' to "
                "fetch every supported index (broad + sectoral + thematic)."
            ),
        ),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option(
            "--group", "-g",
            help="Index group: broad | sectoral | thematic | all. Overrides --index.",
        ),
    ] = None,
    days: Annotated[
        int, typer.Option("-d", "--days", help="Trailing window to fetch in days.")
    ] = 5,
) -> None:
    """Fetch recent PE/PB/Div-Yield rows for one or all supported indices."""
    end = date.today()
    start = end - timedelta(days=days)
    targets = _indices_iter(index, group)

    with IndexValuationClient() as client, FlowStore() as store:
        for target in targets:
            try:
                rows = client.fetch_range(target, start, end)
            except IndexValuationFetchError as exc:
                console.print(f"[red]{target}: {exc}[/]")
                continue
            count = store.upsert_index_valuations(rows)
            display_indexpe_fetch_result(target, count)


@app.command()
def backfill(
    period: Annotated[
        str, typer.Option("--period", "-p", help="Lookback like '10y' / '5y' / '90d'.")
    ] = "10y",
    index: Annotated[
        str | None,
        typer.Option(
            "--index", "-i",
            help=(
                "Index display name. Omit / 'all' to backfill every "
                "supported index (broad + sectoral + thematic)."
            ),
        ),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option(
            "--group", "-g",
            help="Index group: broad | sectoral | thematic | all. Overrides --index.",
        ),
    ] = None,
) -> None:
    """Backfill historical PE/PB/Div-Yield rows for one or all indices."""
    days = _parse_period_to_days(period)
    end = date.today()
    start = end - timedelta(days=days)
    targets = _indices_iter(index, group)

    with IndexValuationClient() as client, FlowStore() as store:
        for target in targets:
            console.print(f"[dim]Backfilling {target} ({start} → {end})…[/]")
            try:
                rows = client.fetch_range(target, start, end)
            except IndexValuationFetchError as exc:
                console.print(f"[red]{target}: {exc}[/]")
                continue
            count = store.upsert_index_valuations(rows)
            display_indexpe_fetch_result(target, count)


@app.command()
def current(
    index: Annotated[
        str, typer.Option("--index", "-i", help="Index display name."),
    ] = "NIFTY 50",
) -> None:
    """Show the most recent stored PE/PB/Div-Yield row for an index."""
    canonical = _normalise_index(index)
    with FlowStore() as store:
        snap = store.get_index_valuation_latest(canonical)
    display_indexpe_current(snap)


@app.command()
def trend(
    index: Annotated[
        str, typer.Option("--index", "-i", help="Index display name."),
    ] = "NIFTY 50",
    days: Annotated[
        int, typer.Option("-d", "--days", help="Trailing window in days."),
    ] = 90,
) -> None:
    """Tabular trend of PE/PB/Div-Yield for the last N days."""
    canonical = _normalise_index(index)
    with FlowStore() as store:
        rows = store.get_index_valuation_history(canonical, days=days)
    display_indexpe_trend(rows, days)


@app.command()
def percentile(
    index: Annotated[
        str, typer.Option("--index", "-i", help="Index display name."),
    ] = "NIFTY SMALLCAP 250",
) -> None:
    """Current PE/PB/Div-Yield percentile vs the full stored distribution.

    Backfill 10y of history first (`flowtrack indexpe backfill -p 10y -i ...`)
    so the percentile is computed against a meaningful sample.
    """
    canonical = _normalise_index(index)
    with FlowStore() as store:
        payload = store.get_index_valuation_percentile(canonical)
    display_indexpe_percentile(payload)
