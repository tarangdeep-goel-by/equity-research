"""CLI commands for composite stock screening."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.screener_display import display_screen_results, display_stock_scorecard
from flowtracker.screener_engine import ScreenerEngine
from flowtracker.store import FlowStore

app = typer.Typer(
    name="screen",
    help="Composite stock screener — multi-factor scoring across all data layers",
    no_args_is_help=True,
)
console = Console()


@app.command(name="top")
def screen_top(
    limit: Annotated[
        int, typer.Option("-n", "--limit", help="Number of stocks to show")
    ] = 30,
    factor: Annotated[
        str | None, typer.Option(
            "--factor",
            help="Rank by single factor: ownership, insider, valuation, earnings, quality, delivery, estimates, risk",
        )
    ] = None,
    watchlist: Annotated[
        bool, typer.Option("--watchlist", help="Score watchlist stocks only")
    ] = False,
) -> None:
    """Show top-ranked stocks across all factors."""
    with FlowStore() as store:
        if watchlist:
            wl = store.get_watchlist()
            symbols = [w.symbol for w in wl]
            if not symbols:
                console.print("[yellow]Watchlist is empty.[/]")
                raise typer.Exit(1)
        else:
            symbols = None

        console.print("[dim]Scoring stocks...[/]")
        engine = ScreenerEngine(store)
        scores = engine.screen_all(symbols=symbols, factor=factor)

    display_screen_results(scores, limit)


@app.command()
def score(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
) -> None:
    """Show full scorecard for a single stock."""
    with FlowStore() as store:
        engine = ScreenerEngine(store)
        result = engine.score_stock(symbol.upper())

    if result is None:
        console.print(f"[yellow]No data for {symbol.upper()}[/]")
        raise typer.Exit(1)

    display_stock_scorecard(result)
