"""CLI for the Screener-vs-yfinance share-count sanity check.

Single-command subgroup: ``flowtrack share_count check`` runs the
divergence scan over the universe (or a single ``-s SYMBOL``) and
prints a Rich table of flagged stocks.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from flowtracker.share_count_sanity import (
    check_share_count_divergence,
    scan_universe_divergence,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="share_count",
    help="Screener-vs-yfinance share-count divergence sanity check",
    no_args_is_help=True,
)
console = Console()


def _fmt_shares(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:,.0f}"


def _render_results(results: list[dict], threshold_pct: float, *, only_flagged: bool) -> None:
    """Print a Rich table summarising the divergence scan."""
    if only_flagged:
        rows = [r for r in results if r.get("flagged")]
    else:
        rows = results

    if not rows:
        console.print(
            f"[green]No stocks exceed {threshold_pct:.1f}% divergence "
            f"(scanned {len(results)}).[/]"
        )
        return

    table = Table(
        title=f"Share-count divergence (threshold > {threshold_pct:.1f}%)",
        show_lines=False,
    )
    table.add_column("Symbol", style="bold")
    table.add_column("Screener", justify="right")
    table.add_column("yfinance", justify="right")
    table.add_column("Divergence %", justify="right")
    table.add_column("Status", style="yellow")

    for r in rows:
        if "status" in r:
            table.add_row(r["symbol"], "—", "—", "—", r["status"])
        else:
            div = r["divergence_pct"]
            colour = "red" if r.get("flagged") else "green"
            table.add_row(
                r["symbol"],
                _fmt_shares(r.get("screener_shares")),
                _fmt_shares(r.get("yfinance_shares")),
                f"[{colour}]{div:.2f}%[/]",
                "FLAGGED" if r.get("flagged") else "ok",
            )

    console.print(table)
    flagged_count = sum(1 for r in results if r.get("flagged"))
    console.print(
        f"\n[bold]{flagged_count}[/] flagged of [bold]{len(results)}[/] scanned."
    )


@app.command()
def check(
    symbol: Annotated[
        str | None,
        typer.Option("-s", "--symbol", help="Check a single symbol instead of the universe"),
    ] = None,
    threshold: Annotated[
        float,
        typer.Option("--threshold", help="Divergence % threshold for flagging"),
    ] = 10.0,
    show_all: Annotated[
        bool,
        typer.Option("--all", help="Show all rows, not just flagged ones"),
    ] = False,
) -> None:
    """Scan for >threshold% divergence between Screener & yfinance share counts."""
    with FlowStore() as store:
        if symbol is not None:
            result = check_share_count_divergence(
                symbol, threshold_pct=threshold, store=store
            )
            _render_results([result], threshold, only_flagged=False)
        else:
            results = scan_universe_divergence(
                threshold_pct=threshold, store=store
            )
            _render_results(results, threshold, only_flagged=not show_all)
