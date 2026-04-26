"""CLI commands for NSE shareholding pattern data."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from flowtracker.holding_client import NSEHoldingClient, NSEHoldingError
from flowtracker.holding_display import (
    display_holding_changes,
    display_holding_fetch_result,
    display_shareholding,
    display_watchlist,
)
from flowtracker.screener_client import ScreenerClient, ScreenerError
from flowtracker.store import FlowStore

app = typer.Typer(
    name="holding",
    help="NSE shareholding patterns — quarterly promoter/FII/DII/MF/public ownership",
    no_args_is_help=True,
)
console = Console()


@app.command()
def add(
    symbols: Annotated[list[str], typer.Argument(help="Stock symbols to add (e.g. RELIANCE TCS INFY)")],
) -> None:
    """Add stocks to watchlist."""
    with FlowStore() as store:
        for symbol in symbols:
            store.add_to_watchlist(symbol.upper())
            console.print(f"  [green]+[/] {symbol.upper()}")
    console.print(f"\n[bold]Added {len(symbols)} symbol(s) to watchlist.[/]")


@app.command()
def remove(
    symbol: Annotated[str, typer.Argument(help="Stock symbol to remove")],
) -> None:
    """Remove a stock from watchlist."""
    with FlowStore() as store:
        store.remove_from_watchlist(symbol.upper())
    console.print(f"[yellow]Removed {symbol.upper()} from watchlist.[/]")


@app.command(name="list")
def list_watchlist() -> None:
    """Show all stocks in watchlist."""
    with FlowStore() as store:
        entries = store.get_watchlist()
    display_watchlist(entries)


@app.command()
def fetch(
    symbol: Annotated[str | None, typer.Option("--symbol", "-s", help="Fetch for specific symbol (default: all in watchlist)")] = None,
    quarters: Annotated[int, typer.Option("--quarters", "-q", help="Number of quarters to fetch")] = 4,
) -> None:
    """Fetch shareholding data from NSE XBRL filings."""
    with FlowStore() as store:
        if symbol:
            symbols = [symbol.upper()]
        else:
            watchlist = store.get_watchlist()
            if not watchlist:
                console.print("[yellow]Watchlist is empty. Use 'flowtrack holding add SYMBOL' first.[/]")
                raise typer.Exit(1)
            symbols = [w.symbol for w in watchlist]

    try:
        with NSEHoldingClient() as client:
            with FlowStore() as store:
                for sym in symbols:
                    console.print(f"[dim]Fetching {sym}...[/]")
                    try:
                        records, pledges, breakdowns = client.fetch_latest_quarters_full(sym, quarters)
                        if records:
                            count = store.upsert_shareholding(records)
                            if pledges:
                                store.upsert_promoter_pledges(pledges)
                            if breakdowns:
                                store.upsert_shareholding_breakdown(breakdowns)
                            display_holding_fetch_result(sym, records)
                        else:
                            console.print(f"[yellow]No data for {sym}.[/]")
                    except NSEHoldingError as e:
                        console.print(f"[red]Error fetching {sym}: {e}[/]")
    except NSEHoldingError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


@app.command()
def show(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    quarters: Annotated[int, typer.Option("-q", "--quarters", help="Number of quarters to show")] = 8,
) -> None:
    """Show shareholding history for a stock."""
    with FlowStore() as store:
        records = store.get_shareholding(symbol.upper(), quarters)
    display_shareholding(symbol.upper(), records)


@app.command()
def changes(
    category: Annotated[str | None, typer.Option("-c", "--category", help="Filter by category: FII, DII, MF, Promoter, Public")] = None,
    limit: Annotated[int, typer.Option("-n", "--limit", help="Number of results")] = 10,
) -> None:
    """Show biggest shareholding changes across watchlist stocks."""
    with FlowStore() as store:
        data = store.get_biggest_changes(category, limit)
    display_holding_changes(data)


@app.command()
def shareholders(
    symbol: Annotated[
        str, typer.Option("-s", "--symbol", help="Stock symbol")
    ],
    classification: Annotated[
        str | None,
        typer.Option(
            "-c",
            "--classification",
            help="Filter: promoters, foreign_institutions, domestic_institutions, public",
        ),
    ] = None,
) -> None:
    """Fetch individual shareholder details from Screener.in."""
    symbol = symbol.upper()
    try:
        with ScreenerClient() as sc:
            with FlowStore() as store:
                # Resolve company_id
                cached = store.get_screener_ids(symbol)
                if cached:
                    company_id = cached[0]
                else:
                    company_id, warehouse_id = sc._get_both_ids(symbol)
                    store.upsert_screener_ids(symbol, company_id, warehouse_id)

                console.print(f"[dim]Fetching shareholders for {symbol}...[/]")
                data = sc.fetch_shareholders(company_id)
                if not any(data.values()):
                    console.print("[yellow]No shareholder data returned.[/]")
                    raise typer.Exit(1)

                count = store.upsert_shareholder_details(symbol, data)
                console.print(f"[green]Stored {count} shareholder records.[/]")

        # Display tables per classification
        classifications_to_show = (
            [classification] if classification else list(data.keys())
        )

        for cls in classifications_to_show:
            holders = data.get(cls, [])
            if not holders:
                continue

            # Collect all quarter keys
            all_quarters: list[str] = []
            for h in holders:
                for q in h.get("values", {}):
                    if q not in all_quarters:
                        all_quarters.append(q)
            all_quarters.sort()
            display_quarters = all_quarters[-6:] if len(all_quarters) > 6 else all_quarters

            cls_title = cls.replace("_", " ").title()
            table = Table(
                title=f"{symbol} — {cls_title}",
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("Holder", style="bold", max_width=35)
            for q in display_quarters:
                table.add_column(q, justify="right")

            for h in holders:
                row = [h.get("name", "?")]
                vals = h.get("values", {})
                for q in display_quarters:
                    v = vals.get(q)
                    if v is not None:
                        try:
                            row.append(f"{float(v):.2f}%")
                        except (ValueError, TypeError):
                            row.append(str(v))
                    else:
                        row.append("—")
                table.add_row(*row)

            console.print(table)
            console.print()

    except ScreenerError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)
