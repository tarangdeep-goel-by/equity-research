"""CLI commands for catalyst events."""

from __future__ import annotations

from typing import Annotated

import typer

from .catalyst_client import gather_catalysts, gather_watchlist_catalysts
from .catalyst_display import display_catalyst_table
from .store import FlowStore

app = typer.Typer(
    name="catalyst",
    help="Upcoming stock catalyst events",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def show(
    ctx: typer.Context,
    symbol: Annotated[str | None, typer.Option("-s", "--symbol", help="Stock symbol")] = None,
    watchlist: Annotated[bool, typer.Option("--watchlist", help="All watchlist stocks")] = False,
    all_: Annotated[bool, typer.Option("--all", help="Portfolio + watchlist stocks")] = False,
    days: Annotated[int, typer.Option("--days", help="Lookahead window in days")] = 90,
    event_type: Annotated[str | None, typer.Option("--type", help="Filter by event type")] = None,
) -> None:
    """Show upcoming catalyst events for stocks."""
    if ctx.invoked_subcommand is not None:
        return

    with FlowStore() as store:
        if symbol:
            events = gather_catalysts(symbol.upper(), store, days=days)
        elif watchlist or all_:
            symbols = [w.symbol for w in store.get_watchlist()]
            if all_:
                holdings = store.get_portfolio_holdings()
                portfolio_syms = [h.symbol for h in holdings] if holdings else []
                symbols = list(set(symbols + portfolio_syms))
            events = gather_watchlist_catalysts(symbols, store, days=days)
        else:
            typer.echo("Specify --symbol, --watchlist, or --all")
            raise typer.Exit(1)

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        display_catalyst_table(events)
