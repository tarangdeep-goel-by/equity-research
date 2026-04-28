"""CLI commands for the ADR/GDR program directory.

Two commands:

* ``flowtrack adr refresh`` — load the curated seed (or, in future, scrape live)
  and upsert into ``adr_programs``.
* ``flowtrack adr list [-s SYMBOL]`` — display stored programs, optionally
  filtered to one NSE symbol.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.adr_client import AdrClient, AdrClientError
from flowtracker.adr_display import display_adr_programs
from flowtracker.store import FlowStore

app = typer.Typer(
    name="adr",
    help="ADR/GDR program directory (Indian issuers)",
    no_args_is_help=True,
)

console = Console()


@app.command("refresh")
def refresh() -> None:
    """Refresh the local DR program directory from the bundled seed dataset.

    The seed JSON ships ~30 known Indian ADR/GDR/ADS programs cross-referenced
    from 20-F filings and depositary press releases. Runs synchronously over
    the async client surface so we keep API parity with a future live scrape.
    """
    try:
        client = AdrClient()
    except AdrClientError as exc:
        console.print(f"[red]ADR client error:[/] {exc}")
        raise typer.Exit(1)

    programs = asyncio.run(client.fetch_indian_dr_programs())
    if not programs:
        console.print("[yellow]No programs returned from the ADR client.[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        upserted = store.upsert_adr_programs(programs)

    console.print(
        f"[green]Refreshed {upserted} ADR/GDR program(s) "
        f"from the bundled seed dataset.[/]"
    )


@app.command("list")
def list_programs(
    symbol: Annotated[
        str | None,
        typer.Option("-s", "--symbol", help="Filter by NSE symbol (e.g. INFY)"),
    ] = None,
) -> None:
    """List stored DR programs, optionally filtered by NSE symbol."""
    with FlowStore() as store:
        rows = store.get_adr_programs(symbol)
    display_adr_programs(rows)
