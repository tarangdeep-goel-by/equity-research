"""CLI commands for NSE/BSE surveillance flags (ASM/ESM/GSM).

Three commands:

* ``flowtrack surveillance fetch`` — pull ASM + GSM (NSE) + ESM (BSE) and
  upsert into ``surveillance_flags``.
* ``flowtrack surveillance list [--type ASM|ESM|GSM] [--exchange NSE|BSE]``
  — show current flags filtered by type / exchange.
* ``flowtrack surveillance check SYMBOL`` — show every active flag for a
  given symbol (useful for screener row-level checks).
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.store import FlowStore
from flowtracker.surveillance_client import fetch_all_flags
from flowtracker.surveillance_display import (
    display_fetch_summary,
    display_surveillance_flags,
    display_symbol_check,
)

app = typer.Typer(
    name="surveillance",
    help="NSE/BSE surveillance flags (ASM/ESM/GSM) — regulatory risk flags",
    no_args_is_help=True,
)

console = Console()


@app.command("fetch")
def fetch() -> None:
    """Fetch ASM + GSM (NSE) + ESM (BSE) and upsert into the local store.

    Each source is wrapped in its own try/except — a partial outage on one
    exchange does not block the other. Failures log to WARNING and
    contribute zero rows.
    """
    console.print("[dim]Fetching ASM/GSM/ESM surveillance flags...[/dim]")
    flags = fetch_all_flags()

    if not flags:
        console.print(
            "[yellow]No flags fetched. NSE may be rate-limiting; BSE ESM "
            "may be returning the SPA shell. Try again in a minute.[/yellow]"
        )
        raise typer.Exit(1)

    with FlowStore() as store:
        upserted = store.upsert_surveillance_flags(flags)

    by_type = Counter(f.alert_type for f in flags)
    console.print(
        f"[green]Upserted {upserted} surveillance flag(s).[/green]"
    )
    display_fetch_summary(by_type)


@app.command("list")
def list_flags(
    type_: Annotated[
        str | None,
        typer.Option(
            "--type", "-t",
            help="Filter by alert type: ASM, ESM, or GSM (case-insensitive).",
        ),
    ] = None,
    exchange: Annotated[
        str | None,
        typer.Option(
            "--exchange", "-e",
            help="Filter by exchange: NSE or BSE (case-insensitive).",
        ),
    ] = None,
) -> None:
    """List current surveillance flags, optionally filtered by type/exchange."""
    alert_type = type_.upper().strip() if type_ else None
    if alert_type and alert_type not in {"ASM", "ESM", "GSM"}:
        console.print(f"[red]Unknown --type {type_!r}; use ASM, ESM, or GSM.[/red]")
        raise typer.Exit(1)
    exch = exchange.upper().strip() if exchange else None
    if exch and exch not in {"NSE", "BSE"}:
        console.print(f"[red]Unknown --exchange {exchange!r}; use NSE or BSE.[/red]")
        raise typer.Exit(1)

    with FlowStore() as store:
        rows = store.get_surveillance_flags(alert_type=alert_type, exchange=exch)

    display_surveillance_flags(rows)


@app.command("check")
def check(
    symbol: Annotated[str, typer.Argument(help="Symbol or BSE scrip code")],
) -> None:
    """Show every active surveillance flag on a single symbol."""
    sym = symbol.upper().strip()
    with FlowStore() as store:
        rows = store.get_surveillance_flags(symbol=sym)

    display_symbol_check(sym, rows)
