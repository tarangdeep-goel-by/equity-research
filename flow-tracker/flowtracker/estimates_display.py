"""Rich display formatters for consensus estimates."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise

console = Console()


def display_estimates_stock(
    est: ConsensusEstimate, surprises: list[EarningsSurprise],
) -> None:
    """Show full estimates for a single stock."""
    lines: list[str] = []

    # Target prices
    if est.target_mean:
        lines.append(f"Target Mean: {est.target_mean:,.2f}")
    if est.target_median:
        lines.append(f"Target Median: {est.target_median:,.2f}")
    if est.target_low and est.target_high:
        lines.append(f"Target Range: {est.target_low:,.2f} — {est.target_high:,.2f}")

    # Upside
    if est.target_mean and est.current_price and est.current_price > 0:
        upside = (est.target_mean - est.current_price) / est.current_price * 100
        up_color = "green" if upside >= 0 else "red"
        lines.append(f"Upside: [{up_color}]{upside:+.1f}%[/{up_color}] (CMP: {est.current_price:,.2f})")

    # Recommendation
    if est.recommendation:
        rec_colors = {
            "strong_buy": "bold green", "buy": "green",
            "hold": "yellow", "sell": "red", "strong_sell": "bold red",
        }
        color = rec_colors.get(est.recommendation, "")
        rec_str = est.recommendation.replace("_", " ").title()
        if color:
            lines.append(f"Recommendation: [{color}]{rec_str}[/{color}]")
        else:
            lines.append(f"Recommendation: {rec_str}")
        if est.num_analysts:
            lines[-1] += f" ({est.num_analysts} analysts)"

    # Valuation
    if est.forward_pe:
        lines.append(f"Forward P/E: {est.forward_pe:.1f}")
    if est.earnings_growth:
        eg_color = "green" if est.earnings_growth >= 0 else "red"
        lines.append(f"Earnings Growth: [{eg_color}]{est.earnings_growth:+.1f}%[/{eg_color}]")

    console.print(Panel(
        "\n".join(lines),
        title=f"Consensus Estimates — {est.symbol}",
        border_style="cyan",
    ))

    # Surprises table
    if surprises:
        table = Table(
            title="Earnings Surprises",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Quarter", width=12)
        table.add_column("Actual EPS", justify="right", width=12)
        table.add_column("Estimate", justify="right", width=12)
        table.add_column("Surprise%", justify="right", width=10)

        for s in surprises:
            surp_str = "—"
            if s.surprise_pct is not None:
                color = "green" if s.surprise_pct >= 0 else "red"
                surp_str = f"[{color}]{s.surprise_pct:+.1f}%[/{color}]"

            table.add_row(
                s.quarter_end,
                f"{s.eps_actual:.2f}" if s.eps_actual is not None else "—",
                f"{s.eps_estimate:.2f}" if s.eps_estimate is not None else "—",
                surp_str,
            )

        console.print(table)


def display_estimates_upside(estimates: list[ConsensusEstimate]) -> None:
    """Show stocks ranked by upside to analyst target."""
    if not estimates:
        console.print("[yellow]No estimates data found.[/]")
        return

    table = Table(
        title="Stocks by Analyst Upside",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Symbol", width=12)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Target", justify="right", width=10)
    table.add_column("Upside%", justify="right", width=10)
    table.add_column("Rec", width=10)
    table.add_column("#Analysts", justify="right", width=8)
    table.add_column("Fwd P/E", justify="right", width=8)

    for est in estimates:
        upside = None
        if est.target_mean and est.current_price and est.current_price > 0:
            upside = (est.target_mean - est.current_price) / est.current_price * 100

        upside_str = "—"
        if upside is not None:
            color = "green" if upside >= 0 else "red"
            upside_str = f"[{color}]{upside:+.1f}%[/{color}]"

        rec_str = (est.recommendation or "—").replace("_", " ").title()

        table.add_row(
            est.symbol,
            f"{est.current_price:,.2f}" if est.current_price else "—",
            f"{est.target_mean:,.2f}" if est.target_mean else "—",
            upside_str,
            rec_str,
            str(est.num_analysts) if est.num_analysts else "—",
            f"{est.forward_pe:.1f}" if est.forward_pe else "—",
        )

    console.print(table)


def display_estimates_surprises(surprises: list[EarningsSurprise]) -> None:
    """Show recent earnings beats/misses."""
    if not surprises:
        console.print("[yellow]No earnings surprises found.[/]")
        return

    table = Table(
        title="Earnings Surprises",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Symbol", width=12)
    table.add_column("Quarter", width=12)
    table.add_column("Actual", justify="right", width=10)
    table.add_column("Estimate", justify="right", width=10)
    table.add_column("Surprise%", justify="right", width=10)

    for s in surprises:
        surp_str = "—"
        if s.surprise_pct is not None:
            color = "green" if s.surprise_pct >= 0 else "red"
            surp_str = f"[{color}]{s.surprise_pct:+.1f}%[/{color}]"

        table.add_row(
            s.symbol,
            s.quarter_end,
            f"{s.eps_actual:.2f}" if s.eps_actual is not None else "—",
            f"{s.eps_estimate:.2f}" if s.eps_estimate is not None else "—",
            surp_str,
        )

    console.print(table)


def display_estimates_fetch_result(est_count: int, surp_count: int) -> None:
    """Show estimates fetch result summary."""
    console.print(Panel(
        f"Fetched {est_count} estimates + {surp_count} surprises",
        title="Estimates Fetch Complete",
        border_style="green",
    ))
