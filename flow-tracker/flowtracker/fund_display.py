"""Rich display functions for fundamentals output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.fund_models import LiveSnapshot, QuarterlyResult, ValuationBand

console = Console()


def _fmt_cr(value: float | None) -> str:
    """Format value in crores with appropriate suffix."""
    if value is None:
        return "—"
    if abs(value) >= 100_000:  # 1 lakh crore+
        return f"₹{value / 100_000:.1f}L Cr"
    return f"₹{value:,.0f} Cr"


def _fmt_pct(value: float | None, multiply: bool = False) -> str:
    """Format as percentage. If multiply=True, value is a ratio (0.15 -> 15.0%)."""
    if value is None:
        return "—"
    if multiply:
        value *= 100
    return f"{value:.1f}%"


def _fmt_ratio(value: float | None) -> str:
    """Format a ratio like P/E, P/B."""
    if value is None:
        return "—"
    return f"{value:.1f}"


def _color_change(value: float | None) -> str:
    """Color positive green, negative red."""
    if value is None:
        return "—"
    color = "green" if value > 0 else "red" if value < 0 else "white"
    return f"[{color}]{value:+.1f}%[/{color}]"


def display_live_snapshot(snap: LiveSnapshot) -> None:
    """Display current fundamentals snapshot for a stock."""
    # Build a panel with three columns: Valuation | Profitability | Health
    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Valuation", style="bold")
    table.add_column("")
    table.add_column("Profitability", style="bold")
    table.add_column("")
    table.add_column("Health", style="bold")
    table.add_column("")

    # Row 1
    table.add_row(
        "P/E (TTM)", _fmt_ratio(snap.pe_trailing),
        "Gross Margin", _fmt_pct(snap.gross_margin, multiply=True),
        "D/E", _fmt_ratio(snap.debt_to_equity),
    )
    # Row 2
    table.add_row(
        "P/E (Fwd)", _fmt_ratio(snap.pe_forward),
        "OPM", _fmt_pct(snap.operating_margin, multiply=True),
        "Current", _fmt_ratio(snap.current_ratio),
    )
    # Row 3
    table.add_row(
        "P/B", _fmt_ratio(snap.pb_ratio),
        "NPM", _fmt_pct(snap.net_margin, multiply=True),
        "FCF", _fmt_cr(snap.free_cash_flow),
    )
    # Row 4
    table.add_row(
        "EV/EBITDA", _fmt_ratio(snap.ev_ebitda),
        "ROE", _fmt_pct(snap.roe, multiply=True),
        "", "",
    )
    # Row 5
    table.add_row(
        "Div Yield", _fmt_pct(snap.dividend_yield, multiply=True),
        "ROA", _fmt_pct(snap.roa, multiply=True),
        "", "",
    )

    # Growth row
    growth_text = ""
    if snap.revenue_growth is not None:
        growth_text += f"Revenue {_color_change(snap.revenue_growth * 100)} YoY"
    if snap.earnings_growth is not None:
        if growth_text:
            growth_text += "  |  "
        growth_text += f"Earnings {_color_change(snap.earnings_growth * 100)} YoY"

    # Header line
    price_str = f"₹{snap.price:,.2f}" if snap.price else "—"
    mcap_str = _fmt_cr(snap.market_cap)
    sector_str = snap.sector or ""
    header = f"Price: {price_str}  |  MCap: {mcap_str}  |  {sector_str}"

    title = f"{snap.symbol} — {snap.company_name or ''}"

    console.print(Panel(
        table,
        title=title,
        subtitle=header,
        border_style="blue",
    ))

    if growth_text:
        console.print(f"  Growth: {growth_text}")


def display_quarterly_history(results: list[QuarterlyResult], symbol: str) -> None:
    """Display quarterly earnings trajectory table."""
    if not results:
        console.print("[yellow]No quarterly data stored. Run 'flowtrack fund fetch' first.[/]")
        return

    table = Table(title=f"{symbol} — Quarterly Earnings Trajectory", show_lines=False)
    table.add_column("Quarter", style="bold")
    table.add_column("Revenue", justify="right")
    table.add_column("Net Inc", justify="right")
    table.add_column("EPS", justify="right")
    table.add_column("OPM%", justify="right")
    table.add_column("NPM%", justify="right")

    # Results come in most-recent-first; display same order
    for r in results:
        # Format quarter_end as "Dec 2025"
        from datetime import datetime

        try:
            dt = datetime.strptime(r.quarter_end, "%Y-%m-%d")
            qtr_label = dt.strftime("%b %Y")
        except ValueError:
            qtr_label = r.quarter_end

        rev_str = f"{r.revenue:,.0f}" if r.revenue else "—"
        ni_str = f"{r.net_income:,.0f}" if r.net_income else "—"
        eps_str = f"{r.eps:.2f}" if r.eps else "—"
        opm_str = (
            _fmt_pct(r.operating_margin, multiply=True)
            if r.operating_margin and r.operating_margin < 1
            else _fmt_pct(r.operating_margin)
        )
        npm_str = (
            _fmt_pct(r.net_margin, multiply=True)
            if r.net_margin and r.net_margin < 1
            else _fmt_pct(r.net_margin)
        )

        table.add_row(qtr_label, rev_str, ni_str, eps_str, opm_str, npm_str)

    console.print(Panel(table, border_style="blue"))


def display_peer_comparison(
    snapshots: list[LiveSnapshot], ownership_data: dict | None = None
) -> None:
    """Display side-by-side peer comparison table.

    ownership_data: optional dict of {symbol: {fii_pct, fii_change, mf_pct, mf_change}}
    """
    if not snapshots:
        console.print("[yellow]No peer data available.[/]")
        return

    table = Table(title="Peer Comparison (Live)", show_lines=False)
    table.add_column("Metric", style="bold")
    for s in snapshots:
        table.add_column(s.symbol, justify="right")

    # Valuation metrics
    metrics = [
        ("Price", lambda s: f"₹{s.price:,.0f}" if s.price else "—"),
        ("MCap", lambda s: _fmt_cr(s.market_cap)),
        ("P/E", lambda s: _fmt_ratio(s.pe_trailing)),
        ("EV/EBITDA", lambda s: _fmt_ratio(s.ev_ebitda)),
        ("P/B", lambda s: _fmt_ratio(s.pb_ratio)),
        ("ROE", lambda s: _fmt_pct(s.roe, multiply=True)),
        ("OPM", lambda s: _fmt_pct(s.operating_margin, multiply=True)),
        ("NPM", lambda s: _fmt_pct(s.net_margin, multiply=True)),
        ("D/E", lambda s: _fmt_ratio(s.debt_to_equity)),
        ("Rev Grw", lambda s: _fmt_pct(s.revenue_growth, multiply=True) if s.revenue_growth else "—"),
    ]

    for label, fmt_fn in metrics:
        table.add_row(label, *[fmt_fn(s) for s in snapshots])

    # Add ownership data if available
    if ownership_data:
        table.add_section()
        table.add_row(
            "FII%",
            *[
                f"{ownership_data.get(s.symbol, {}).get('fii_pct', 0):.1f}%"
                for s in snapshots
            ],
        )
        table.add_row(
            "FII Δ QoQ",
            *[
                _color_change(ownership_data.get(s.symbol, {}).get("fii_change"))
                for s in snapshots
            ],
        )
        table.add_row(
            "MF%",
            *[
                f"{ownership_data.get(s.symbol, {}).get('mf_pct', 0):.1f}%"
                for s in snapshots
            ],
        )
        table.add_row(
            "MF Δ QoQ",
            *[
                _color_change(ownership_data.get(s.symbol, {}).get("mf_change"))
                for s in snapshots
            ],
        )

    console.print(Panel(table, border_style="blue"))


def display_valuation_band(bands: list[ValuationBand]) -> None:
    """Display valuation band analysis."""
    if not bands:
        console.print("[yellow]Not enough valuation data. Weekly snapshots accumulate over time.[/]")
        return

    symbol = bands[0].symbol
    period = f"{bands[0].period_start} to {bands[0].period_end}"

    table = Table(show_lines=False)
    table.add_column("Metric", style="bold")
    table.add_column("Min", justify="right")
    table.add_column("25th", justify="right")
    table.add_column("Median", justify="right")
    table.add_column("75th", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Current", justify="right", style="bold")
    table.add_column("Pctl", justify="right")

    metric_labels = {
        "pe_trailing": "P/E",
        "ev_ebitda": "EV/EBITDA",
        "pb_ratio": "P/B",
    }

    for b in bands:
        label = metric_labels.get(b.metric, b.metric)
        # Compute 25th and 75th percentile approximations
        q25 = b.min_val + (b.median_val - b.min_val) * 0.5
        q75 = b.median_val + (b.max_val - b.median_val) * 0.5

        pctl_color = "green" if b.percentile < 30 else "red" if b.percentile > 70 else "yellow"

        table.add_row(
            label,
            _fmt_ratio(b.min_val),
            _fmt_ratio(q25),
            _fmt_ratio(b.median_val),
            _fmt_ratio(q75),
            _fmt_ratio(b.max_val),
            _fmt_ratio(b.current_val),
            f"[{pctl_color}]{b.percentile:.0f}%[/{pctl_color}]",
        )

    console.print(Panel(
        table,
        title=f"{symbol} — Valuation Band ({b.num_observations} obs)",
        subtitle=period,
        border_style="blue",
    ))
