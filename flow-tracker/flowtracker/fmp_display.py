"""Rich display formatters for FMP data."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.fmp_models import (
    FMPAnalystGrade,
    FMPDcfValue,
    FMPFinancialGrowth,
    FMPKeyMetrics,
    FMPPriceTarget,
    FMPTechnicalIndicator,
)

console = Console()


def _fmt(val: float | None, fmt: str = ",.2f", suffix: str = "") -> str:
    """Format a float or return dash."""
    if val is None:
        return "--"
    return f"{val:{fmt}}{suffix}"


def _pct(val: float | None) -> str:
    """Format as percentage (input already in pct form, e.g. 15.0 -> +15.0%)."""
    if val is None:
        return "--"
    return f"{val:+.1f}%"


def _color_pct(val: float | None) -> str:
    """Format percentage with color (input already in pct form)."""
    if val is None:
        return "--"
    color = "green" if val >= 0 else "red"
    return f"[{color}]{val:+.1f}%[/{color}]"


def display_fmp_fetch_result(summary: dict) -> None:
    """Show summary of what was fetched."""
    lines: list[str] = []
    if summary.get("dcf"):
        lines.append("DCF: 1 current value")
    dcf_hist = summary.get("dcf_history", [])
    if dcf_hist:
        lines.append(f"DCF History: {len(dcf_hist)} records")
    techs = summary.get("technicals", [])
    if techs:
        lines.append(f"Technicals: {len(techs)} indicator values")
    km = summary.get("key_metrics", [])
    if km:
        lines.append(f"Key Metrics: {len(km)} annual periods")
    fg = summary.get("financial_growth", [])
    if fg:
        lines.append(f"Financial Growth: {len(fg)} annual periods")
    ag = summary.get("analyst_grades", [])
    if ag:
        lines.append(f"Analyst Grades: {len(ag)} records")
    pt = summary.get("price_targets", [])
    if pt:
        lines.append(f"Price Targets: {len(pt)} records")

    if not lines:
        lines.append("No data fetched")

    console.print(Panel(
        "\n".join(lines),
        title="FMP Fetch Complete",
        border_style="green",
    ))


def display_dcf(dcf: FMPDcfValue | None, history: list[FMPDcfValue]) -> None:
    """Show DCF intrinsic value and history."""
    if dcf is None and not history:
        console.print("[yellow]No DCF data available.[/]")
        return

    # Current DCF panel
    if dcf:
        lines: list[str] = []
        lines.append(f"Intrinsic Value (DCF): {_fmt(dcf.dcf)}")
        lines.append(f"Stock Price: {_fmt(dcf.stock_price)}")
        if dcf.dcf and dcf.stock_price and dcf.stock_price > 0:
            margin = (dcf.dcf - dcf.stock_price) / dcf.stock_price * 100
            color = "green" if margin >= 0 else "red"
            lines.append(f"Margin of Safety: [{color}]{margin:+.1f}%[/{color}]")
        lines.append(f"Date: {dcf.date}")
        console.print(Panel(
            "\n".join(lines),
            title=f"DCF Valuation -- {dcf.symbol}",
            border_style="cyan",
        ))

    # History table
    if history:
        table = Table(
            title="DCF History",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Date", width=12)
        table.add_column("DCF", justify="right", width=12)
        table.add_column("Price", justify="right", width=12)
        table.add_column("Margin", justify="right", width=10)

        for h in history:
            margin_str = "--"
            if h.dcf and h.stock_price and h.stock_price > 0:
                m = (h.dcf - h.stock_price) / h.stock_price * 100
                c = "green" if m >= 0 else "red"
                margin_str = f"[{c}]{m:+.1f}%[/{c}]"
            table.add_row(
                h.date,
                _fmt(h.dcf),
                _fmt(h.stock_price),
                margin_str,
            )
        console.print(table)


def display_technicals(indicators: list[FMPTechnicalIndicator]) -> None:
    """Show latest technical indicator values."""
    if not indicators:
        console.print("[yellow]No technical indicators available.[/]")
        return

    # Group by indicator, take latest per indicator
    latest: dict[str, FMPTechnicalIndicator] = {}
    for ind in indicators:
        if ind.indicator not in latest:
            latest[ind.indicator] = ind

    table = Table(
        title="Technical Indicators",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Indicator", width=12)
    table.add_column("Value", justify="right", width=14)
    table.add_column("Date", width=12)

    indicator_order = ["rsi", "sma_50", "sma_200", "macd", "adx"]
    for name in indicator_order:
        if name in latest:
            ind = latest[name]
            val_str = _fmt(ind.value)
            # Color RSI zones
            if name == "rsi" and ind.value is not None:
                if ind.value > 70:
                    val_str = f"[red]{ind.value:.1f}[/red] (overbought)"
                elif ind.value < 30:
                    val_str = f"[green]{ind.value:.1f}[/green] (oversold)"
                else:
                    val_str = f"{ind.value:.1f}"
            table.add_row(name.upper().replace("_", " "), val_str, ind.date)

    # Any extra indicators not in the standard order
    for name, ind in latest.items():
        if name not in indicator_order:
            table.add_row(name.upper(), _fmt(ind.value), ind.date)

    console.print(table)


def display_key_metrics(metrics: list[FMPKeyMetrics]) -> None:
    """Show key metrics history."""
    if not metrics:
        console.print("[yellow]No key metrics available.[/]")
        return

    table = Table(
        title="Key Financial Metrics",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("P/E", justify="right", width=8)
    table.add_column("P/B", justify="right", width=8)
    table.add_column("EV/EBITDA", justify="right", width=10)
    table.add_column("ROE", justify="right", width=8)
    table.add_column("ROIC", justify="right", width=8)
    table.add_column("D/E", justify="right", width=8)
    table.add_column("Div Yld", justify="right", width=8)
    table.add_column("FCF Yld", justify="right", width=8)

    for m in metrics:
        table.add_row(
            m.date,
            _fmt(m.pe_ratio, ".1f"),
            _fmt(m.pb_ratio, ".1f"),
            _fmt(m.ev_to_ebitda, ".1f"),
            f"{m.roe:.1f}%" if m.roe is not None else "--",
            f"{m.roic:.1f}%" if m.roic is not None else "--",
            _fmt(m.debt_to_equity, ".2f"),
            f"{m.dividend_yield:.1f}%" if m.dividend_yield is not None else "--",
            f"{m.free_cash_flow_yield:.1f}%" if m.free_cash_flow_yield is not None else "--",
        )

    console.print(table)

    # DuPont breakdown for latest period
    latest = metrics[0]
    if latest.net_profit_margin_dupont is not None or latest.asset_turnover is not None:
        lines: list[str] = []
        lines.append("DuPont Decomposition (latest):")
        npm_str = f"{latest.net_profit_margin_dupont:.1f}%" if latest.net_profit_margin_dupont is not None else "--"
        lines.append(f"  Net Profit Margin: {npm_str}")
        lines.append(f"  Asset Turnover: {_fmt(latest.asset_turnover, '.2f')}")
        lines.append(f"  Equity Multiplier: {_fmt(latest.equity_multiplier, '.2f')}")
        if (
            latest.net_profit_margin_dupont is not None
            and latest.asset_turnover is not None
            and latest.equity_multiplier is not None
        ):
            implied_roe = latest.net_profit_margin_dupont * latest.asset_turnover * latest.equity_multiplier
            lines.append(f"  Implied ROE: {implied_roe:.1f}%")
        console.print(Panel("\n".join(lines), border_style="dim"))


def display_financial_growth(growth: list[FMPFinancialGrowth]) -> None:
    """Show financial growth rates."""
    if not growth:
        console.print("[yellow]No financial growth data available.[/]")
        return

    table = Table(
        title="Financial Growth Rates",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Revenue", justify="right", width=10)
    table.add_column("EBITDA", justify="right", width=10)
    table.add_column("Net Inc", justify="right", width=10)
    table.add_column("EPS", justify="right", width=10)
    table.add_column("FCF", justify="right", width=10)
    table.add_column("BV/Shr", justify="right", width=10)

    for g in growth:
        table.add_row(
            g.date,
            _color_pct(g.revenue_growth),
            _color_pct(g.ebitda_growth),
            _color_pct(g.net_income_growth),
            _color_pct(g.eps_growth),
            _color_pct(g.free_cash_flow_growth),
            _color_pct(g.book_value_per_share_growth),
        )

    console.print(table)

    # Multi-year CAGR summary from latest period
    latest = growth[0]
    cagr_lines: list[str] = []
    if latest.revenue_growth_3y is not None:
        cagr_lines.append(f"  Revenue 3Y CAGR: {_color_pct(latest.revenue_growth_3y)}")
    if latest.revenue_growth_5y is not None:
        cagr_lines.append(f"  Revenue 5Y CAGR: {_color_pct(latest.revenue_growth_5y)}")
    if latest.revenue_growth_10y is not None:
        cagr_lines.append(f"  Revenue 10Y CAGR: {_color_pct(latest.revenue_growth_10y)}")
    if latest.net_income_growth_3y is not None:
        cagr_lines.append(f"  Net Income 3Y CAGR: {_color_pct(latest.net_income_growth_3y)}")
    if latest.net_income_growth_5y is not None:
        cagr_lines.append(f"  Net Income 5Y CAGR: {_color_pct(latest.net_income_growth_5y)}")

    if cagr_lines:
        console.print(Panel(
            "Multi-Year Growth (CAGR):\n" + "\n".join(cagr_lines),
            border_style="dim",
        ))


def display_analyst_grades(grades: list[FMPAnalystGrade]) -> None:
    """Show analyst grade changes."""
    if not grades:
        console.print("[yellow]No analyst grades available.[/]")
        return

    table = Table(
        title="Analyst Grade Changes",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Firm", width=24)
    table.add_column("Previous", width=16)
    table.add_column("New Grade", width=16)

    _UPGRADE_GRADES = {"Buy", "Outperform", "Overweight", "Strong Buy", "Positive"}
    _DOWNGRADE_GRADES = {"Sell", "Underperform", "Underweight", "Strong Sell", "Negative", "Reduce"}

    for g in grades:
        new_str = g.new_grade or "--"
        if g.new_grade in _UPGRADE_GRADES:
            new_str = f"[green]{g.new_grade}[/green]"
        elif g.new_grade in _DOWNGRADE_GRADES:
            new_str = f"[red]{g.new_grade}[/red]"

        table.add_row(
            g.date,
            g.grading_company,
            g.previous_grade or "--",
            new_str,
        )

    console.print(table)


def display_price_targets(targets: list[FMPPriceTarget]) -> None:
    """Show analyst price targets with consensus summary."""
    if not targets:
        console.print("[yellow]No price targets available.[/]")
        return

    # Consensus summary
    valid_targets = [t.price_target for t in targets if t.price_target is not None]
    if valid_targets:
        avg_target = sum(valid_targets) / len(valid_targets)
        high = max(valid_targets)
        low = min(valid_targets)
        latest_price = None
        for t in targets:
            if t.price_when_posted is not None:
                latest_price = t.price_when_posted
                break

        lines: list[str] = []
        lines.append(f"Consensus Target: {avg_target:,.2f} ({len(valid_targets)} analysts)")
        lines.append(f"Range: {low:,.2f} -- {high:,.2f}")
        if latest_price and latest_price > 0:
            upside = (avg_target - latest_price) / latest_price * 100
            c = "green" if upside >= 0 else "red"
            lines.append(f"Upside: [{c}]{upside:+.1f}%[/{c}] (Price: {latest_price:,.2f})")

        console.print(Panel(
            "\n".join(lines),
            title="Price Target Consensus",
            border_style="cyan",
        ))

    # Individual targets table
    table = Table(
        title="Individual Price Targets",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Analyst", width=20)
    table.add_column("Firm", width=20)
    table.add_column("Target", justify="right", width=12)
    table.add_column("Price Then", justify="right", width=12)
    table.add_column("Upside", justify="right", width=10)

    for t in targets:
        upside_str = "--"
        if t.price_target and t.price_when_posted and t.price_when_posted > 0:
            up = (t.price_target - t.price_when_posted) / t.price_when_posted * 100
            c = "green" if up >= 0 else "red"
            upside_str = f"[{c}]{up:+.1f}%[/{c}]"

        table.add_row(
            t.published_date,
            t.analyst_name or "--",
            t.analyst_company or "--",
            _fmt(t.price_target),
            _fmt(t.price_when_posted),
            upside_str,
        )

    console.print(table)
