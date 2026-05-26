"""CLI commands for IPO + SME pipeline tracker.

Subcommands:
    upcoming                — list upcoming issues (filterable by segment)
    subscription <issuer>   — show subscription history for one issuer
    listings                — recent listings (last N days)
    fetch                   — refresh upcoming + subscription + listings + BSE SME
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.ipo_client import (
    BSEIPOClient,
    NSEIPOClient,
    NSEIPOError,
)
from flowtracker.ipo_display import (
    display_fetch_summary,
    display_listings,
    display_subscription,
    display_upcoming,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="ipo",
    help="IPO + SME pipeline tracker (NSE mainboard + SME, BSE SME)",
    no_args_is_help=True,
)
console = Console()
logger = logging.getLogger(__name__)


@app.command()
def fetch() -> None:
    """Fetch upcoming IPOs, subscription multiples, listings, and BSE SME.

    BSE SME is best-effort — failures are caught and reported as zero rows so
    a flaky BSE page doesn't block the NSE mainboard pull.
    """
    upcoming_count = subscription_count = listing_count = sme_count = 0

    # NSE block
    try:
        with NSEIPOClient() as client:
            upcoming = client.fetch_upcoming()
            subs = client.fetch_subscription()
            listings = client.fetch_listings()
    except NSEIPOError as e:
        console.print(f"[red]NSE fetch failed: {e}[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        upcoming_count = store.upsert_ipo_calendar(upcoming)
        subscription_count = store.upsert_ipo_subscription(subs)
        listing_count = store.upsert_ipo_listings(listings)

    # BSE SME block — quarantined
    try:
        with BSEIPOClient() as bse:
            bse_rows = bse.fetch_upcoming_sme()
        with FlowStore() as store:
            sme_count = store.upsert_ipo_calendar(bse_rows)
    except Exception as e:
        logger.warning("BSE SME fetch quarantined failure: %s", e)
        console.print(
            f"[yellow]BSE SME fetch failed (quarantined, NSE data still saved): {e}[/]"
        )

    display_fetch_summary(upcoming_count, subscription_count, listing_count, sme_count)


@app.command()
def upcoming(
    segment: Annotated[
        str | None,
        typer.Option(
            "--segment",
            help="Filter by segment: MAIN or SME",
            case_sensitive=False,
        ),
    ] = None,
) -> None:
    """Show upcoming IPOs from local store."""
    if segment and segment.upper() not in {"MAIN", "SME"}:
        console.print("[red]--segment must be MAIN or SME[/]")
        raise typer.Exit(1)
    with FlowStore() as store:
        issues = store.get_ipo_upcoming()
    display_upcoming(issues, segment_filter=segment.upper() if segment else None)


@app.command()
def subscription(
    issuer: Annotated[
        str,
        typer.Argument(help="Issuer name (substring match supported)"),
    ],
) -> None:
    """Show subscription history for an issuer."""
    with FlowStore() as store:
        rows = store.get_ipo_subscription(issuer)
    display_subscription(rows, issuer=issuer)


@app.command()
def listings(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Look-back window in days"),
    ] = 30,
) -> None:
    """Show recent listings from local store."""
    with FlowStore() as store:
        rows = store.get_ipo_listings(days=days)
    display_listings(rows, days=days)
