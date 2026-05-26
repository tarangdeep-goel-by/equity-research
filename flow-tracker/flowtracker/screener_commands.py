"""CLI commands for composite stock screening."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.screener_display import (
    display_screen_results,
    display_screen_summary,
    display_stock_scorecard,
)
from flowtracker.screener_engine import ScreenerEngine
from flowtracker.store import FlowStore

app = typer.Typer(
    name="screen",
    help="Composite stock screener — multi-factor scoring across all data layers",
    no_args_is_help=True,
)
console = Console()


def _annotate_surveillance(
    scores: list,
    store: FlowStore,
    *,
    exclude: bool,
) -> list:
    """Annotate / filter screener output with NSE/BSE surveillance flags.

    Additive by default: returns the same list, but prints a footnote
    listing any symbols carrying ASM/ESM/GSM flags so the caller sees the
    risk-flag before acting. When ``exclude`` is True, drops flagged rows
    entirely before display.
    """
    if not scores:
        return scores
    flagged_rows = {
        r["symbol"] for r in store.get_surveillance_flags()
    }
    if not flagged_rows:
        return scores
    hits = [s for s in scores if s.symbol in flagged_rows]
    if exclude:
        kept = [s for s in scores if s.symbol not in flagged_rows]
        # Re-rank the survivors so the display still shows contiguous 1..N.
        for i, s in enumerate(kept, start=1):
            s.rank = i
        if hits:
            console.print(
                f"[yellow]Excluded {len(hits)} stock(s) under "
                f"NSE/BSE surveillance:[/yellow] "
                + ", ".join(sorted(s.symbol for s in hits))
            )
        return kept
    if hits:
        console.print(
            f"[yellow]Warning:[/yellow] {len(hits)} ranked stock(s) "
            f"under NSE/BSE surveillance "
            f"(ASM/ESM/GSM): "
            + ", ".join(sorted(s.symbol for s in hits))
            + "  [dim](use --exclude-surveillance to drop)[/dim]"
        )
    return scores


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
    exclude_surveillance: Annotated[
        bool,
        typer.Option(
            "--exclude-surveillance",
            help="Drop stocks under NSE ASM/GSM or BSE ESM before ranking output",
        ),
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
        scores = _annotate_surveillance(
            scores, store, exclude=exclude_surveillance,
        )

    display_screen_results(scores, limit)


@app.command()
def rank(
    top: Annotated[int, typer.Option("--top", "-n", help="Number of stocks")] = 20,
    factor: Annotated[str | None, typer.Option("--factor", help="Single factor ranking")] = None,
    industry: Annotated[str | None, typer.Option("--industry", help="Filter by industry")] = None,
    weight: Annotated[list[str] | None, typer.Option("--weight", help="Custom weight e.g. valuation=0.3")] = None,
    min_score: Annotated[float, typer.Option("--min-score", help="Minimum composite score")] = 0,
    exclude_surveillance: Annotated[
        bool,
        typer.Option(
            "--exclude-surveillance",
            help="Drop stocks under NSE ASM/GSM or BSE ESM before ranking output",
        ),
    ] = False,
) -> None:
    """Rank stocks with custom weights, industry filter, and score threshold."""
    # Parse custom weights
    parsed_weights: dict[str, float] | None = None
    if weight:
        parsed_weights = {}
        for w in weight:
            if "=" not in w:
                console.print(f"[red]Invalid weight format '{w}' — use name=value (e.g. valuation=0.3)[/]")
                raise typer.Exit(1)
            name, val = w.split("=", 1)
            try:
                parsed_weights[name.strip()] = float(val.strip())
            except ValueError:
                console.print(f"[red]Invalid weight value in '{w}' — must be a number[/]")
                raise typer.Exit(1)

    with FlowStore() as store:
        console.print("[dim]Scoring stocks...[/]")
        engine = ScreenerEngine(store, weights=parsed_weights)
        scores = engine.screen_all(factor=factor, industry=industry, min_score=min_score)
        scores = _annotate_surveillance(
            scores, store, exclude=exclude_surveillance,
        )

    display_screen_results(scores, top)
    display_screen_summary(scores)


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
