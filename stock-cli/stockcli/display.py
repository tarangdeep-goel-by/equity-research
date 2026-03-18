"""Rich display formatters for each CLI command."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from stockcli.models import (
    BalanceSheet,
    CashFlowStatement,
    CompanyProfile,
    IncomeStatement,
    KeyMetricsTTM,
    MarketMover,
    RatiosTTM,
    ScreenerResult,
)
from stockcli.utils import fmt_large, fmt_pct, fmt_price, fmt_ratio

console = Console()


def _margin(revenue: float | None, value: float | None) -> str:
    """Calculate margin % from revenue and a P&L line item."""
    if revenue and value:
        return fmt_pct(value / revenue * 100)
    return "N/A"


# ── Info ────────────────────────────────────────────────────


def display_profile(
    profile: CompanyProfile,
    ratios: RatiosTTM,
    metrics: KeyMetricsTTM,
) -> None:
    """Display company info panel."""
    change_color = "green" if (profile.change or 0) >= 0 else "red"
    change_str = f"[{change_color}]{profile.change:+.2f}[/]" if profile.change is not None else ""

    title = f"[bold]{profile.symbol}[/] — {profile.companyName or 'N/A'} {change_str}"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", min_width=18)
    grid.add_column()
    grid.add_column(style="dim", min_width=18)
    grid.add_column()

    cur = profile.currency
    rows = [
        ("Price", fmt_price(profile.price, cur), "Market Cap", fmt_large(profile.marketCap, cur)),
        ("Exchange", profile.exchange or "N/A", "Sector", profile.sector or "N/A"),
        ("Industry", profile.industry or "N/A", "Country", profile.country or "N/A"),
        ("52W Range", profile.range or "N/A", "Beta", fmt_ratio(profile.beta)),
        ("CEO", profile.ceo or "N/A", "Employees", profile.fullTimeEmployees or "N/A"),
        ("IPO Date", profile.ipoDate or "N/A", "ETF", str(profile.isEtf or False)),
    ]
    for r in rows:
        grid.add_row(*r)

    console.print(Panel(grid, title=title, border_style="blue"))

    # Ratios table
    rtable = Table(title="Key Ratios (TTM)", show_header=True, header_style="bold cyan")
    rtable.add_column("Metric", style="dim")
    rtable.add_column("Value", justify="right")
    rtable.add_column("Metric", style="dim")
    rtable.add_column("Value", justify="right")

    ratio_rows = [
        ("P/E", fmt_ratio(ratios.priceToEarningsRatio), "P/B", fmt_ratio(ratios.priceToBookRatio)),
        ("P/S", fmt_ratio(ratios.priceToSalesRatio), "EV/EBITDA", fmt_ratio(metrics.evToEBITDA)),
        ("PEG", fmt_ratio(ratios.priceToEarningsGrowthRatio), "P/FCF", fmt_ratio(ratios.priceToFreeCashFlowRatio)),
        ("ROE", fmt_pct(metrics.returnOnEquity and metrics.returnOnEquity * 100), "ROA", fmt_pct(metrics.returnOnAssets and metrics.returnOnAssets * 100)),
        ("Gross Margin", fmt_pct(ratios.grossProfitMargin and ratios.grossProfitMargin * 100), "Net Margin", fmt_pct(ratios.netProfitMargin and ratios.netProfitMargin * 100)),
        ("D/E", fmt_ratio(ratios.debtToEquityRatio), "Current Ratio", fmt_ratio(ratios.currentRatio)),
        ("Div Yield", fmt_pct(ratios.dividendYieldPercentage), "ROIC", fmt_pct(metrics.returnOnInvestedCapital and metrics.returnOnInvestedCapital * 100)),
    ]
    for r in ratio_rows:
        rtable.add_row(*r)

    console.print(rtable)

    # Description
    if profile.description:
        desc = profile.description[:500] + ("..." if len(profile.description) > 500 else "")
        console.print(Panel(desc, title="About", border_style="dim"))


# ── Screener ────────────────────────────────────────────────


def display_screener(results: list[ScreenerResult]) -> None:
    """Display screener results as a table."""
    if not results:
        console.print("[yellow]No stocks matched your filters.[/]")
        return

    table = Table(title=f"Screener Results ({len(results)} stocks)", show_header=True, header_style="bold cyan")
    table.add_column("Symbol", style="bold")
    table.add_column("Name", max_width=30)
    table.add_column("Price", justify="right")
    table.add_column("Mkt Cap", justify="right")
    table.add_column("Sector", max_width=20)
    table.add_column("Beta", justify="right")
    table.add_column("Exchange")

    for s in results:
        table.add_row(
            s.symbol or "",
            (s.companyName or "")[:30],
            fmt_price(s.price),
            fmt_large(s.marketCap),
            (s.sector or "")[:20],
            fmt_ratio(s.beta),
            s.exchange or "",
        )

    console.print(table)


# ── Fundamentals ────────────────────────────────────────────


def display_fundamentals(
    symbol: str,
    income: list[IncomeStatement],
    balance: list[BalanceSheet],
    cashflow: list[CashFlowStatement],
    currency: str | None = None,
) -> None:
    """Display financial statements as tables."""
    if not income:
        console.print(f"[yellow]No financial data found for {symbol}.[/]")
        return

    # Income Statement
    itable = Table(title=f"{symbol} — Income Statement", show_header=True, header_style="bold green")
    itable.add_column("Metric", style="dim")
    for stmt in income:
        itable.add_column(stmt.date or "?", justify="right")

    c = currency
    income_metrics = [
        ("Revenue", lambda s: fmt_large(s.revenue, c)),
        ("Cost of Revenue", lambda s: fmt_large(s.costOfRevenue, c)),
        ("Gross Profit", lambda s: fmt_large(s.grossProfit, c)),
        ("Gross Margin", lambda s: _margin(s.revenue, s.grossProfit)),
        ("Operating Income", lambda s: fmt_large(s.operatingIncome, c)),
        ("Op. Margin", lambda s: _margin(s.revenue, s.operatingIncome)),
        ("Net Income", lambda s: fmt_large(s.netIncome, c)),
        ("Net Margin", lambda s: _margin(s.revenue, s.netIncome)),
        ("EBITDA", lambda s: fmt_large(s.ebitda, c)),
        ("EPS (diluted)", lambda s: fmt_ratio(s.epsDiluted)),
    ]
    for label, fn in income_metrics:
        itable.add_row(label, *[fn(s) for s in income])
    console.print(itable)

    # Balance Sheet
    if balance:
        btable = Table(title=f"{symbol} — Balance Sheet", show_header=True, header_style="bold green")
        btable.add_column("Metric", style="dim")
        for stmt in balance:
            btable.add_column(stmt.date or "?", justify="right")

        balance_metrics = [
            ("Total Assets", lambda s: fmt_large(s.totalAssets, c)),
            ("Cash & Equiv", lambda s: fmt_large(s.cashAndCashEquivalents, c)),
            ("Total Liabilities", lambda s: fmt_large(s.totalLiabilities, c)),
            ("Long-Term Debt", lambda s: fmt_large(s.longTermDebt, c)),
            ("Total Debt", lambda s: fmt_large(s.totalDebt, c)),
            ("Equity", lambda s: fmt_large(s.totalStockholdersEquity, c)),
            ("Net Debt", lambda s: fmt_large(s.netDebt, c)),
        ]
        for label, fn in balance_metrics:
            btable.add_row(label, *[fn(s) for s in balance])
        console.print(btable)

    # Cash Flow
    if cashflow:
        ctable = Table(title=f"{symbol} — Cash Flow", show_header=True, header_style="bold green")
        ctable.add_column("Metric", style="dim")
        for stmt in cashflow:
            ctable.add_column(stmt.date or "?", justify="right")

        cf_metrics = [
            ("Operating CF", lambda s: fmt_large(s.operatingCashFlow, c)),
            ("CapEx", lambda s: fmt_large(s.capitalExpenditure, c)),
            ("Free Cash Flow", lambda s: fmt_large(s.freeCashFlow, c)),
            ("Investing", lambda s: fmt_large(s.netCashProvidedByInvestingActivities, c)),
            ("Financing", lambda s: fmt_large(s.netCashProvidedByFinancingActivities, c)),
            ("Dividends Paid", lambda s: fmt_large(s.commonDividendsPaid, c)),
            ("Net Change", lambda s: fmt_large(s.netChangeInCash, c)),
        ]
        for label, fn in cf_metrics:
            ctable.add_row(label, *[fn(s) for s in cashflow])
        console.print(ctable)


# ── Compare ─────────────────────────────────────────────────


def display_compare(
    profiles: list[CompanyProfile],
    ratios_list: list[RatiosTTM],
    metrics_list: list[KeyMetricsTTM],
) -> None:
    """Side-by-side comparison table."""
    table = Table(title="Stock Comparison", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="dim")
    for p in profiles:
        table.add_column(p.symbol or "?", justify="right", style="bold")

    compare_rows: list[tuple[str, ...]] = [
        ("Price", *[fmt_price(p.price, p.currency) for p in profiles]),
        ("Market Cap", *[fmt_large(p.marketCap, p.currency) for p in profiles]),
        ("Sector", *[p.sector or "N/A" for p in profiles]),
        ("Beta", *[fmt_ratio(p.beta) for p in profiles]),
        ("P/E", *[fmt_ratio(r.priceToEarningsRatio) for r in ratios_list]),
        ("P/B", *[fmt_ratio(r.priceToBookRatio) for r in ratios_list]),
        ("P/S", *[fmt_ratio(r.priceToSalesRatio) for r in ratios_list]),
        ("EV/EBITDA", *[fmt_ratio(m.evToEBITDA) for m in metrics_list]),
        ("ROE", *[fmt_pct(m.returnOnEquity and m.returnOnEquity * 100) for m in metrics_list]),
        ("Net Margin", *[fmt_pct(r.netProfitMargin and r.netProfitMargin * 100) for r in ratios_list]),
        ("D/E", *[fmt_ratio(r.debtToEquityRatio) for r in ratios_list]),
        ("Div Yield", *[fmt_pct(r.dividendYieldPercentage) for r in ratios_list]),
        ("ROIC", *[fmt_pct(m.returnOnInvestedCapital and m.returnOnInvestedCapital * 100) for m in metrics_list]),
        ("FCF/Share", *[fmt_ratio(m.freeCashFlowPerShare) for m in metrics_list]),
    ]
    for row in compare_rows:
        table.add_row(*row)

    console.print(table)


# ── Market Movers ───────────────────────────────────────────


def display_movers(movers: list[MarketMover], title: str, limit: int) -> None:
    """Display gainers/losers/actives table."""
    if not movers:
        console.print(f"[yellow]No data for {title}.[/]")
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Symbol", style="bold")
    table.add_column("Name", max_width=30)
    table.add_column("Price", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Change %", justify="right")

    for i, m in enumerate(movers[:limit], 1):
        chg_color = "green" if (m.change or 0) >= 0 else "red"
        table.add_row(
            str(i),
            m.symbol or "",
            (m.name or "")[:30],
            fmt_price(m.price),
            Text(f"{m.change:+.2f}" if m.change is not None else "N/A", style=chg_color),
            Text(f"{m.changesPercentage:+.2f}%" if m.changesPercentage is not None else "N/A", style=chg_color),
        )

    console.print(table)
