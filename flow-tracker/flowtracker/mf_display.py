"""Rich display formatters for AMFI mutual fund flow data."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.mf_models import AMFIReportRow, MFAUMSummary, MFDailyFlow, MFMonthlyFlow
from flowtracker.mf_nav_models import MFSchemeNav
from flowtracker.utils import fmt_crores

console = Console()


def _colored_value(value: float) -> Text:
    """Return a Rich Text with green (positive) or red (negative) coloring."""
    color = "green" if value >= 0 else "red"
    return Text(fmt_crores(value), style=color)


def display_mf_fetch_result(rows: list[AMFIReportRow], month: str) -> None:
    """Show confirmation after fetching AMFI data."""
    if not rows:
        console.print("[yellow]No data fetched.[/]")
        return

    # Count by category
    cats: dict[str, int] = {}
    for r in rows:
        cats[r.category] = cats.get(r.category, 0) + 1

    console.print(f"\n[bold]Fetched AMFI data for {month}[/]")
    console.print(f"  {len(rows)} sub-category rows across {len(cats)} categories")
    for cat, count in sorted(cats.items()):
        console.print(f"  [dim]{cat}:[/] {count} rows")
    console.print()


def display_mf_summary(summary: MFAUMSummary) -> None:
    """Show latest month's MF AUM summary with equity % of total."""
    equity_pct = (summary.equity_aum / summary.total_aum * 100) if summary.total_aum > 0 else 0

    table = Table(show_header=True, header_style="bold cyan", show_lines=False)
    table.add_column("Category", style="bold", width=14)
    table.add_column("AUM (Cr)", justify="right", width=14)
    table.add_column("% of Total", justify="right", width=12)
    table.add_column("Net Flow (Cr)", justify="right", width=14)

    rows_data = [
        ("Equity", summary.equity_aum, summary.equity_net_flow),
        ("Debt", summary.debt_aum, summary.debt_net_flow),
        ("Hybrid", summary.hybrid_aum, summary.hybrid_net_flow),
        ("Other", summary.other_aum, 0.0),
    ]

    for cat, aum, flow in rows_data:
        pct = (aum / summary.total_aum * 100) if summary.total_aum > 0 else 0
        table.add_row(
            cat,
            fmt_crores(aum),
            f"{pct:.1f}%",
            _colored_value(flow) if flow != 0 else Text("\u2014", style="dim"),
        )

    table.add_section()
    table.add_row(
        "[bold]Total[/]",
        Text(fmt_crores(summary.total_aum), style="bold"),
        "100.0%",
        Text("", style="dim"),
    )

    title = f"MF Industry AUM \u2014 {summary.month}"
    subtitle = f"Equity share: {equity_pct:.1f}%"
    console.print(Panel(table, title=title, subtitle=subtitle, border_style="blue"))


def display_mf_flows_table(flows: list[MFMonthlyFlow], period: str) -> None:
    """Show monthly MF flows table with category breakdown."""
    if not flows:
        console.print("[yellow]No MF flow data available.[/]")
        return

    table = Table(
        title=f"MF Flows \u2014 Last {period}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Month", style="bold", width=10)
    table.add_column("Category", width=10)
    table.add_column("Sub-Category", width=24)
    table.add_column("Net Flow (Cr)", justify="right", width=14)
    table.add_column("AUM (Cr)", justify="right", width=14)

    for flow in flows:
        table.add_row(
            flow.month,
            flow.category,
            flow.sub_category,
            _colored_value(flow.net_flow),
            fmt_crores(flow.aum) if flow.aum else "\u2014",
        )

    console.print(table)


def display_mf_aum_trend(summaries: list[MFAUMSummary]) -> None:
    """Show AUM trend over time with equity/debt/hybrid breakdown."""
    if not summaries:
        console.print("[yellow]No AUM trend data available.[/]")
        return

    table = Table(
        title="MF AUM Trend",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Month", style="bold", width=10)
    table.add_column("Total AUM (Cr)", justify="right", width=16)
    table.add_column("Equity (Cr)", justify="right", width=14)
    table.add_column("Equity %", justify="right", width=10)
    table.add_column("Debt (Cr)", justify="right", width=14)
    table.add_column("Hybrid (Cr)", justify="right", width=14)
    table.add_column("Eq Net Flow", justify="right", width=14)

    # Show oldest first for trend
    for s in reversed(summaries):
        eq_pct = (s.equity_aum / s.total_aum * 100) if s.total_aum > 0 else 0
        table.add_row(
            s.month,
            fmt_crores(s.total_aum),
            fmt_crores(s.equity_aum),
            f"{eq_pct:.1f}%",
            fmt_crores(s.debt_aum),
            fmt_crores(s.hybrid_aum),
            _colored_value(s.equity_net_flow),
        )

    console.print(table)


def display_mf_daily_summary(flows: list[MFDailyFlow]) -> None:
    """Show latest day's MF daily flows from SEBI (equity + debt)."""
    if not flows:
        console.print("[yellow]No daily MF data available. Run 'flowtrack mf daily fetch' first.[/]")
        return

    data_date = flows[0].date

    table = Table(show_header=True, header_style="bold cyan", show_lines=False)
    table.add_column("Category", style="bold", width=10)
    table.add_column("Purchase (Cr)", justify="right", width=16)
    table.add_column("Sale (Cr)", justify="right", width=16)
    table.add_column("Net (Cr)", justify="right", width=16)

    for f in flows:
        table.add_row(
            f.category,
            fmt_crores(f.gross_purchase),
            fmt_crores(f.gross_sale),
            _colored_value(f.net_investment),
        )

    # Add total row
    total_purchase = sum(f.gross_purchase for f in flows)
    total_sale = sum(f.gross_sale for f in flows)
    total_net = sum(f.net_investment for f in flows)
    table.add_section()
    table.add_row(
        "[bold]Total[/]",
        Text(fmt_crores(total_purchase), style="bold"),
        Text(fmt_crores(total_sale), style="bold"),
        _colored_value(total_net),
    )

    console.print(Panel(
        table,
        title=f"MF Daily Flows (SEBI) — {data_date}",
        border_style="blue",
    ))


def display_mf_daily_trend(daily_data: list[dict]) -> None:
    """Show daily MF equity/debt net investment trend."""
    if not daily_data:
        console.print("[yellow]No daily MF trend data available.[/]")
        return

    table = Table(
        title="MF Daily Net Investment Trend",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", style="bold", width=12)
    table.add_column("Equity Net (Cr)", justify="right", width=16)
    table.add_column("Debt Net (Cr)", justify="right", width=16)

    for row in daily_data:
        table.add_row(
            row["date"],
            _colored_value(row["equity_net"]),
            _colored_value(row["debt_net"]),
        )

    console.print(table)


# -- Daily scheme NAV display (mfapi.in) --


def display_mf_nav_latest(snapshot: MFSchemeNav | None) -> None:
    """Single-row NAV snapshot for a scheme."""
    if snapshot is None:
        console.print(
            "[yellow]No NAV data for this scheme. "
            "Run 'flowtrack mf nav backfill --scheme <code>' first.[/]"
        )
        return
    body = (
        f"NAV: [bold]Rs. {snapshot.nav:.4f}[/]   "
        f"as of [bold]{snapshot.date}[/]"
    )
    console.print(Panel(
        body,
        title=f"{snapshot.scheme_name} ({snapshot.scheme_code})",
        border_style="cyan",
    ))


def display_mf_nav_trend(snapshots: list[MFSchemeNav], days: int) -> None:
    """Tabular NAV trend over the last N days."""
    if not snapshots:
        console.print("[yellow]No NAV data for the requested scheme/range.[/]")
        return

    table = Table(
        title=f"{snapshots[-1].scheme_name} ({snapshots[-1].scheme_code}) — last {days} days",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("NAV (Rs.)", justify="right", width=14)
    table.add_column("Daily %", justify="right", width=10)

    prev: float | None = None
    rows = list(reversed(snapshots))  # newest first
    # For display purposes, daily % vs the next-older row in reversed order
    for i, s in enumerate(rows):
        if i + 1 < len(rows):
            older = rows[i + 1].nav
            pct = (s.nav - older) / older * 100.0 if older else None
        else:
            pct = None
        pct_str = f"{pct:+.2f}%" if pct is not None else "—"
        color = "green" if (pct or 0) >= 0 else "red"
        table.add_row(s.date, f"{s.nav:.4f}", f"[{color}]{pct_str}[/]")

    console.print(table)


def display_mf_nav_backfill_result(
    per_scheme: list[tuple[int, str, int]],
    total: int,
) -> None:
    """Summary panel after a backfill across many schemes."""
    body_lines = [f"Total rows upserted: [bold]{total}[/]", ""]
    body_lines.append("Per-scheme breakdown:")
    for code, label, count in per_scheme:
        color = "green" if count > 0 else "red"
        body_lines.append(f"  [{color}]{count:>6,d}[/] rows — {label} ({code})")
    console.print(Panel(
        "\n".join(body_lines),
        title="MF NAV Backfill Complete",
        border_style="green",
    ))


def display_mf_nav_coverage(
    universe: list[tuple[int, str, str, str, int]],
) -> None:
    """Per-scheme coverage table: first/last date + row count."""
    if not universe:
        console.print(
            "[yellow]No NAV data stored. "
            "Run 'flowtrack mf nav backfill' first.[/]"
        )
        return

    table = Table(
        title=f"MF NAV Coverage ({len(universe)} schemes)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Code", justify="right", width=8)
    table.add_column("Scheme", width=44)
    table.add_column("First", width=12)
    table.add_column("Last", width=12)
    table.add_column("Rows", justify="right", width=8)

    for code, name, first_date, last_date, n in universe:
        table.add_row(
            str(code), name[:44], first_date or "—", last_date or "—", f"{n:,}",
        )

    console.print(table)
