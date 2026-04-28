"""CLI commands for USFDA inspection / drug-enforcement records.

Live-fetch follow-on (2026-04-29) to PR #125's CSV-seed loader. Pulls
records from openFDA's `/drug/enforcement.json` (the closest free public
proxy for USFDA compliance signal) and persists them to `fda_inspections`.

Usage:
    flowtrack fda fetch -s SUNPHARMA --firm "Sun Pharmaceutical"
    flowtrack fda list -s SUNPHARMA
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from .fda_client import fetch_inspections
from .fda_display import display_fda_inspections
from .store import FlowStore

app = typer.Typer(
    name="fda",
    help="USFDA inspection / drug-enforcement records (openFDA-sourced)",
    no_args_is_help=True,
)
console = Console()


@app.command("fetch")
def fetch_cmd(
    symbol: Annotated[
        str, typer.Option("-s", "--symbol", help="NSE symbol (uppercased)")
    ],
    firm: Annotated[
        str,
        typer.Option(
            "--firm",
            help='FDA-side firm name, e.g. "Sun Pharmaceutical". Required because '
            "openFDA records are keyed by firm name, not NSE ticker.",
        ),
    ],
    limit: Annotated[
        int, typer.Option("--limit", help="Max records to fetch (openFDA cap: 1000)")
    ] = 100,
) -> None:
    """Fetch FDA enforcement records for a firm and persist them under symbol."""
    sym = symbol.upper().strip()
    rows = asyncio.run(fetch_inspections(firm, limit=limit))
    if not rows:
        console.print(
            f"[yellow]No FDA records returned for firm={firm!r}.[/yellow]"
        )
        raise typer.Exit(0)
    with FlowStore() as store:
        n = store.upsert_fda_inspections(sym, rows)
    console.print(
        f"[green]Stored {n} FDA inspection record(s) for {sym} (firm={firm!r}).[/green]"
    )


@app.command("list")
def list_cmd(
    symbol: Annotated[
        str, typer.Option("-s", "--symbol", help="NSE symbol (uppercased)")
    ],
    limit: Annotated[
        int, typer.Option("--limit", help="Max records to display")
    ] = 50,
) -> None:
    """Show stored FDA inspection records for a symbol."""
    with FlowStore() as store:
        rows = store.get_fda_inspections(symbol.upper().strip(), limit=limit)
    display_fda_inspections(rows)
