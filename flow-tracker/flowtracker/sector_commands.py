"""CLI commands for sector aggregation views."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.sector_display import display_sector_overview, display_sector_detail
from flowtracker.store import FlowStore

app = typer.Typer(
    name="sector",
    help="Sector aggregation — ownership shifts and rotation by industry",
    no_args_is_help=True,
)
console = Console()


@app.command()
def overview() -> None:
    """Show sector-level ownership shifts across all industries."""
    with FlowStore() as store:
        sectors = store.get_sector_overview()
    display_sector_overview(sectors)


@app.command()
def detail(
    industry: Annotated[str, typer.Argument(help="Industry name (use 'sector list' to see options)")],
) -> None:
    """Drill into a specific sector's stock-level ownership data."""
    with FlowStore() as store:
        stocks = store.get_sector_detail(industry)
    display_sector_detail(industry, stocks)


@app.command(name="list")
def list_sectors() -> None:
    """List all available industry/sector names."""
    with FlowStore() as store:
        sectors = store.get_sector_list()
    for s in sectors:
        console.print(s)
