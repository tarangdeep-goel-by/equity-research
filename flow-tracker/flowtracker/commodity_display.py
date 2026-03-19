"""Rich display formatters for commodity operations."""

from __future__ import annotations

from collections import defaultdict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flowtracker.commodity_models import CommodityPrice, GoldCorrelation, GoldETFNav

console = Console()


def display_commodity_prices(
    gold_prices: list[CommodityPrice],
    silver_prices: list[CommodityPrice],
) -> None:
    """Show gold and silver prices as a combined table."""
    if not gold_prices and not silver_prices:
        console.print("[yellow]No commodity prices found.[/]")
        return

    # Build lookup dicts keyed by date
    gold_usd: dict[str, float] = {}
    gold_inr: dict[str, float] = {}
    silver_usd: dict[str, float] = {}
    silver_inr: dict[str, float] = {}

    for p in gold_prices:
        if p.symbol == "GOLD":
            gold_usd[p.date] = p.price
        elif p.symbol == "GOLD_INR":
            gold_inr[p.date] = p.price

    for p in silver_prices:
        if p.symbol == "SILVER":
            silver_usd[p.date] = p.price
        elif p.symbol == "SILVER_INR":
            silver_inr[p.date] = p.price

    dates = sorted(
        set(gold_usd) | set(gold_inr) | set(silver_usd) | set(silver_inr),
        reverse=True,
    )

    if not dates:
        console.print("[yellow]No commodity prices found.[/]")
        return

    table = Table(
        title="Gold & Silver Prices",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Gold USD/oz", justify="right", width=12)
    table.add_column("Gold INR/10g", justify="right", width=14)
    table.add_column("Silver USD/oz", justify="right", width=12)
    table.add_column("Silver INR/kg", justify="right", width=14)

    for d in dates:
        table.add_row(
            d,
            f"{gold_usd[d]:,.2f}" if d in gold_usd else "—",
            f"{gold_inr[d]:,.2f}" if d in gold_inr else "—",
            f"{silver_usd[d]:,.2f}" if d in silver_usd else "—",
            f"{silver_inr[d]:,.2f}" if d in silver_inr else "—",
        )

    console.print(table)


def display_etf_navs(navs: list[GoldETFNav]) -> None:
    """Show gold/silver ETF NAVs as a table."""
    if not navs:
        console.print("[yellow]No ETF NAVs found.[/]")
        return

    table = Table(
        title="Gold/Silver ETF NAVs",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("Scheme", width=30)
    table.add_column("NAV", justify="right", width=12)

    sorted_navs = sorted(navs, key=lambda n: n.date, reverse=True)

    for n in sorted_navs:
        table.add_row(
            n.date,
            n.scheme_name or n.scheme_code,
            f"{n.nav:.4f}",
        )

    console.print(table)


def display_gold_correlation(correlations: list[GoldCorrelation]) -> None:
    """Show FII flows vs gold price correlation table."""
    if not correlations:
        console.print("[yellow]No correlation data found.[/]")
        return

    table = Table(
        title="FII Flows vs Gold Price",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", width=12)
    table.add_column("FII Net \u20b9cr", justify="right", width=12)
    table.add_column("Gold USD/oz", justify="right", width=12)
    table.add_column("Gold Chg%", justify="right", width=10)
    table.add_column("Gold INR/10g", justify="right", width=14)
    table.add_column("Signal", width=12)

    sorted_corr = sorted(correlations, key=lambda c: c.date, reverse=True)

    for c in sorted_corr:
        # FII net coloring
        fii_color = "green" if c.fii_net >= 0 else "red"
        fii_text = Text(f"{c.fii_net:,.2f}", style=fii_color)

        # Gold change coloring
        chg_color = "green" if c.gold_change_pct >= 0 else "red"
        chg_text = Text(f"{c.gold_change_pct:+.2f}%", style=chg_color)

        # Signal logic
        fii_selling = c.fii_net < 0
        fii_buying = c.fii_net >= 0
        gold_rising = c.gold_change_pct > 0
        gold_falling = c.gold_change_pct < 0

        if fii_selling and gold_rising:
            signal = Text("RISK-OFF", style="bold yellow")
        elif fii_buying and gold_falling:
            signal = Text("RISK-ON", style="bold green")
        elif fii_selling and gold_falling:
            signal = Text("PANIC", style="bold red")
        else:
            signal = Text("\u2014")

        # Gold INR
        gold_inr_str = f"{c.gold_inr:,.2f}" if c.gold_inr is not None else "\u2014"

        table.add_row(
            c.date,
            fii_text,
            f"{c.gold_close:,.2f}",
            chg_text,
            gold_inr_str,
            signal,
        )

    console.print(table)


def display_gold_fetch_result(num_prices: int, num_navs: int) -> None:
    """Show commodity fetch result summary in a panel."""
    content = f"Fetched {num_prices} commodity prices + {num_navs} ETF NAVs"
    console.print(Panel(content, title="Commodity Fetch Complete", border_style="green"))
