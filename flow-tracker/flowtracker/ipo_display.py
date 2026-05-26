"""Rich display formatters for IPO + SME pipeline."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.ipo_models import IPOIssue, IPOListing, IPOSubscription

console = Console()


def _fmt_band(low: float | None, high: float | None) -> str:
    if low is None and high is None:
        return "—"
    if low == high or high is None:
        return f"₹{low:.0f}"
    if low is None:
        return f"≤₹{high:.0f}"
    return f"₹{low:.0f}–{high:.0f}"


def _fmt_size(cr: float | None) -> str:
    if cr is None:
        return "—"
    return f"₹{cr:,.0f} Cr"


def _fmt_times(v: float | None) -> Text:
    if v is None:
        return Text("—", style="dim")
    if v >= 50:
        return Text(f"{v:.1f}×", style="bold red")
    if v >= 10:
        return Text(f"{v:.1f}×", style="yellow")
    if v >= 1:
        return Text(f"{v:.2f}×", style="green")
    return Text(f"{v:.2f}×", style="dim")


def display_upcoming(issues: list[IPOIssue], segment_filter: str | None = None) -> None:
    """Show upcoming IPO calendar."""
    rows = issues
    if segment_filter:
        rows = [i for i in issues if i.segment.upper() == segment_filter.upper()]

    if not rows:
        suffix = f" ({segment_filter})" if segment_filter else ""
        console.print(f"[yellow]No upcoming IPOs found{suffix}.[/]")
        return

    table = Table(
        title=f"Upcoming IPOs ({len(rows)})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Issuer", width=34, style="bold")
    table.add_column("Segment", width=8)
    table.add_column("Exchange", width=8)
    table.add_column("Open", width=11)
    table.add_column("Close", width=11)
    table.add_column("List", width=11)
    table.add_column("Price Band", width=14, justify="right")
    table.add_column("Size", width=12, justify="right")
    table.add_column("Lot", width=6, justify="right")

    # Sort: open date asc, NULLs last
    def _key(i: IPOIssue) -> tuple[int, str]:
        return (0, i.open_date) if i.open_date else (1, i.issuer_name)

    for i in sorted(rows, key=_key):
        seg_style = "magenta" if i.segment == "SME" else "cyan"
        table.add_row(
            i.issuer_name[:34],
            Text(i.segment, style=seg_style),
            i.exchange,
            i.open_date or "—",
            i.close_date or "—",
            i.listing_date or "—",
            _fmt_band(i.price_band_low, i.price_band_high),
            _fmt_size(i.issue_size_cr),
            str(i.lot_size) if i.lot_size else "—",
        )
    console.print(table)


def display_subscription(subs: list[IPOSubscription], issuer: str) -> None:
    """Show subscription history for a single issuer."""
    rows = [s for s in subs if s.issuer_name.lower() == issuer.lower()]
    if not rows:
        # Fallback: substring match (NSE sometimes prefixes "Ltd")
        rows = [s for s in subs if issuer.lower() in s.issuer_name.lower()]
    if not rows:
        console.print(f"[yellow]No subscription data for {issuer!r}.[/]")
        return

    table = Table(
        title=f"Subscription history — {rows[0].issuer_name}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("As of", width=12)
    table.add_column("QIB", justify="right", width=9)
    table.add_column("NII", justify="right", width=9)
    table.add_column("Retail", justify="right", width=9)
    table.add_column("Employee", justify="right", width=9)
    table.add_column("Total", justify="right", width=9)

    for s in sorted(rows, key=lambda r: r.as_of_date):
        table.add_row(
            s.as_of_date,
            _fmt_times(s.qib_times),
            _fmt_times(s.nii_times),
            _fmt_times(s.retail_times),
            _fmt_times(s.employee_times),
            _fmt_times(s.total_times),
        )
    console.print(table)


def display_listings(listings: list[IPOListing], days: int) -> None:
    """Show recent listings."""
    if not listings:
        console.print(f"[yellow]No listings in the last {days} days.[/]")
        return

    table = Table(
        title=f"New Listings (last {days} days, {len(listings)} stocks)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Symbol", style="bold", width=12)
    table.add_column("Issuer", width=34)
    table.add_column("Listing Date", width=12)
    table.add_column("List Price", justify="right", width=11)
    table.add_column("Close", justify="right", width=11)
    table.add_column("Pop %", justify="right", width=10)

    for l in sorted(listings, key=lambda r: r.listing_date, reverse=True):
        pop = l.listing_pop_pct
        if pop is None:
            pop_txt = Text("—", style="dim")
        elif pop >= 30:
            pop_txt = Text(f"{pop:+.1f}%", style="bold green")
        elif pop > 0:
            pop_txt = Text(f"{pop:+.1f}%", style="green")
        elif pop < 0:
            pop_txt = Text(f"{pop:+.1f}%", style="red")
        else:
            pop_txt = Text(f"{pop:+.1f}%", style="dim")

        table.add_row(
            l.symbol,
            l.issuer_name[:34],
            l.listing_date,
            f"₹{l.listing_price:.2f}" if l.listing_price is not None else "—",
            f"₹{l.listing_day_close:.2f}" if l.listing_day_close is not None else "—",
            pop_txt,
        )
    console.print(table)


def display_fetch_summary(
    upcoming: int, subscription: int, listings: int, sme: int
) -> None:
    """Summary panel after `flowtrack ipo fetch`."""
    content = (
        f"[bold]NSE upcoming:[/] {upcoming}\n"
        f"[bold]NSE subscription rows:[/] {subscription}\n"
        f"[bold]NSE listings today:[/] {listings}\n"
        f"[bold]BSE SME upcoming:[/] {sme}"
    )
    border = "green" if (upcoming + subscription + listings + sme) > 0 else "yellow"
    console.print(Panel(content, title="IPO fetch complete", border_style=border))
